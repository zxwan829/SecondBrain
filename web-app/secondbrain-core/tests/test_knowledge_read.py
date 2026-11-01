import hashlib
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.testclient import TestClient
from starlette.middleware.trustedhost import TrustedHostMiddleware

from secondbrain_core.modules.app_auth import AppSessionAuth
from secondbrain_core.modules.knowledge_read import (
    MAX_FILE_BYTES,
    KnowledgeReadStore,
    _token,
    create_knowledge_read_router,
)


ORIGIN = "https://app.test"


class KnowledgeReadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / "knowledge"
        self.root.mkdir(mode=0o700)
        self.review = self.base / "review"
        self.raw = self.base / "raw"
        self.review.mkdir(mode=0o700)
        self.raw.mkdir(mode=0o700)
        (self.review / "must-not-be-read.md").write_text("private review decoy")
        (self.raw / "must-not-be-read.md").write_text("private raw decoy")
        self.store = KnowledgeReadStore(str(self.root))
        self.password_file = self.base / "password"
        self.password_file.write_text("synthetic-test-password-2026\n")
        self.password_file.chmod(0o600)
        self.auth = AppSessionAuth(str(self.password_file), [ORIGIN])
        self.app = FastAPI()
        self.app.add_middleware(TrustedHostMiddleware, allowed_hosts=["app.test"])
        self.app.include_router(create_knowledge_read_router(self.auth, self.store))

        @self.app.post("/test-login")
        def test_login(request: Request, response: Response, body: dict):
            token = self.auth.login(request, body.get("password"))
            self.auth.set_cookie(response, request, token, self.auth.session_ttl)
            return {"status": "ok"}

        self.client = TestClient(self.app, base_url=ORIGIN)
        self.headers = {"Origin": ORIGIN}

    def tearDown(self):
        self.temp.cleanup()

    def login(self):
        response = self.client.post("/test-login", json={"password": "synthetic-test-password-2026"},
                                    headers=self.headers)
        self.assertEqual(response.status_code, 200)

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
        path.chmod(0o600)
        return path

    def test_session_host_and_origin_guards_run_before_knowledge_reads(self):
        with patch.object(self.store, "search", wraps=self.store.search) as search:
            unauthenticated = self.client.get("/api/knowledge/search?q=synthetic", headers=self.headers)
            self.assertEqual(unauthenticated.status_code, 401)
            self.assertEqual(search.call_count, 0)

        self.login()
        bad_origin = self.client.get("/api/knowledge/search?q=synthetic", headers={"Origin": "https://evil.test"})
        self.assertEqual(bad_origin.status_code, 403)
        bad_host = self.client.get("/api/knowledge/search?q=synthetic",
                                   headers={"Origin": ORIGIN, "Host": "evil.test"})
        self.assertEqual(bad_host.status_code, 400)

    def test_search_requires_nonempty_bounded_query_and_limit(self):
        self.write("note.md", "# Synthetic\nknowledge token")
        self.login()
        with patch("secondbrain_core.modules.knowledge_read.os.scandir", side_effect=AssertionError("invalid query scanned root")):
            for params in ({}, {"q": "   "}, {"q": "x" * 201}, {"q": "synthetic", "limit": 0},
                           {"q": "synthetic", "limit": 51}):
                response = self.client.get("/api/knowledge/search", params=params, headers=self.headers)
                self.assertEqual(response.status_code, 400, params)
        self.assertEqual(self.client.get("/api/knowledge/search?q=synthetic&limit=1", headers=self.headers).status_code, 200)
        self.assertEqual(self.client.get("/api/knowledge/search?q=synthetic&limit=50", headers=self.headers).status_code, 200)

    def test_search_is_sorted_bounded_allowlisted_and_does_not_write(self):
        a = self.write("nested/a.md", "---\ntitle: Alpha\n---\n\nSynthetic query body.\n")
        b = self.write("z.md", "# Zulu\n\nSynthetic query body.\n")
        before = {p: (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
                  for p in (a, b)}
        directory_before = sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*"))
        self.login()
        response = self.client.get("/api/knowledge/search?q=synthetic&limit=1", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(len(payload["items"]), 1)
        row = payload["items"][0]
        self.assertEqual(set(row), {"id", "title", "snippet", "match", "updated", "sha256", "provenance_status"})
        self.assertEqual(row["title"], "Alpha")
        self.assertLessEqual(len(row["snippet"]), 240)
        self.assertNotIn(str(self.root), json.dumps(payload))
        all_rows = self.client.get("/api/knowledge/search?q=synthetic&limit=50", headers=self.headers).json()["items"]
        self.assertEqual([r["title"] for r in all_rows], ["Alpha", "Zulu"])
        self.assertTrue(all("content" not in r for r in all_rows))
        after = {p: (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
                 for p in (a, b)}
        self.assertEqual(after, before)
        self.assertEqual(sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*")), directory_before)

    def test_store_ids_use_independent_process_key_and_expire_across_instances(self):
        note = self.write("keyed.md", "# Synthetic key\n")
        self.assertEqual(len(self.store._id_secret), 32)
        self.login()
        item_id = self.client.get("/api/knowledge/search?q=Synthetic", headers=self.headers).json()["items"][0]["id"]
        other_store = KnowledgeReadStore(str(self.root))
        self.assertNotEqual(other_store._id_secret, self.store._id_secret)
        self.assertNotEqual(item_id, _token("keyed.md", hashlib.sha256(note.read_bytes()).hexdigest(), other_store._id_secret))
        with self.assertRaises(Exception) as unavailable:
            other_store.detail(item_id)
        self.assertEqual(getattr(unavailable.exception, "status_code", None), 404)

    def test_search_stops_at_entry_budget_without_materializing_directory(self):
        yielded = []

        class LazyEntries:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def __iter__(self):
                for index in range(2500):
                    yielded.append(index)
                    yield SimpleNamespace(name=f"missing-{index}.txt")

        self.login()
        with patch("secondbrain_core.modules.knowledge_read.os.listdir",
                   side_effect=AssertionError("unbounded listdir must not be used")):
            with patch("secondbrain_core.modules.knowledge_read.os.scandir", return_value=LazyEntries()):
                response = self.client.get("/api/knowledge/search?q=not-present", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "truncated")
        self.assertEqual(response.json()["items"], [])
        self.assertEqual(len(yielded), 2000)

    def test_malformed_ids_are_404_on_detail_and_source_http_routes(self):
        self.login()
        malformed = (
            "v1.A." + "0" * 32,
            "v1.%%%." + "0" * 32,
            "v1.__8." + "0" * 32,  # valid base64url, invalid UTF-8 payload
        )
        for item_id in malformed:
            with self.subTest(item_id=item_id):
                detail = self.client.get(f"/api/knowledge/items/{item_id}", headers=self.headers)
                source = self.client.get(f"/api/knowledge/items/{item_id}/source", headers=self.headers)
                self.assertEqual(detail.status_code, 404, detail.text)
                self.assertEqual(source.status_code, 404, source.text)

    def assert_search_skips_unsafe_path_and_reports_partial_coverage(self):
        self.write("sibling.md", "# Needle sibling\n")
        self.login()
        response = self.client.get("/api/knowledge/search?q=Needle", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "truncated")
        self.assertEqual([row["title"] for row in response.json()["items"]], ["Needle sibling"])
        self.assertNotIn("hidden malformed", response.text)
        self.assertNotIn("private review decoy", response.text)
        self.assertNotIn("private raw decoy", response.text)

    def test_search_skips_percent_encoded_path_component_without_http_500(self):
        self.write("note%2e.md", "# Needle hidden malformed path\n")
        self.assert_search_skips_unsafe_path_and_reports_partial_coverage()

    def test_search_skips_path_exceeding_validated_component_limit(self):
        relative = "/".join([*(f"d{index}" for index in range(32)), "note.md"])
        self.write(relative, "# Needle hidden malformed path\n")
        self.assert_search_skips_unsafe_path_and_reports_partial_coverage()

    def test_search_skips_surrogateescaped_filename_without_http_500(self):
        self.write("sibling.md", "# Needle sibling\n")
        self.login()
        bad_name = "bad-\udcff.md"
        real_scandir = os.scandir
        real_stat = os.stat

        class EntriesWithSurrogate:
            def __init__(self, directory_fd):
                self.directory_fd = directory_fd

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def __iter__(self):
                with real_scandir(self.directory_fd) as entries:
                    yield from entries
                yield SimpleNamespace(name=bad_name)

        def stat_with_surrogate(path, *args, **kwargs):
            if path == bad_name:
                return SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_nlink=1, st_size=30)
            return real_stat(path, *args, **kwargs)

        with patch("secondbrain_core.modules.knowledge_read.os.scandir", side_effect=EntriesWithSurrogate):
            with patch("secondbrain_core.modules.knowledge_read.os.stat", side_effect=stat_with_surrogate):
                response = self.client.get("/api/knowledge/search?q=Needle", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "truncated")
        self.assertEqual([row["title"] for row in response.json()["items"]], ["Needle sibling"])
        self.assertNotIn("private review decoy", response.text)
        self.assertNotIn("private raw decoy", response.text)

    def test_no_implicit_search_and_detail_reads_only_the_selected_file(self):
        selected = self.write("nested/selected.md", "# Selected\n\nSynthetic body.\n")
        other = self.write("other.md", "# Other\n\nSynthetic body.\n")
        self.login()
        self.assertEqual(self.client.get("/api/knowledge/items/invalid", headers=self.headers).status_code, 404)
        with patch.object(self.auth, "require_action", wraps=self.auth.require_action) as require_action:
            found = self.client.get("/api/knowledge/search?q=Selected", headers=self.headers).json()["items"][0]
            require_action.assert_any_call(unittest.mock.ANY, "knowledge.read")
        with patch("secondbrain_core.modules.knowledge_read.os.scandir", side_effect=AssertionError("detail enumerated root")):
            detail = self.store.detail(found["id"])
            source = self.store.source(found["id"])
        response = self.client.get(f"/api/knowledge/items/{found['id']}", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {"id", "content", "sha256", "updated", "provenance_status"})
        self.assertEqual(response.headers["cache-control"], "private, no-store")
        self.assertEqual(detail["content"], "# Selected\n\nSynthetic body.\n")
        self.assertEqual(detail["sha256"], hashlib.sha256(selected.read_bytes()).hexdigest())
        self.assertNotIn(str(self.root), response.text)
        self.assertEqual(source, {"status": "missing", "provenance_status": "missing", "source": None})
        self.assertEqual(other.read_text(), "# Other\n\nSynthetic body.\n")

    def test_untrusted_or_inconsistent_source_claims_never_become_verified_links(self):
        samples = {
            "claim.md": "---\nsource_kind: review\nsource_ref: forged.md\nsource_sha256: " + "0" * 64 + "\n---\n# Claim\n",
            "fake.md": "---\nsource_ref: ../raw/secret.md\nsource_sha256: not-a-hash\n---\n# Fake\n",
            "mismatch.md": "---\nsource_kind: capture\nsource_id: known-id\nsource_sha256: " + "f" * 64 + "\n---\n# Mismatch\n",
            "capture.md": "---\nsource_type: inbox_proposal_review\noriginal_asset: /raw/original.md\ncapture_context: source=note.md\n---\n# Captured\n",
            "promoted.md": "<!-- secondbrain-promote request_id=trusted-looking review_sha256=" + "a" * 64 + " -->\n---\ntype: knowledge\n---\n# Promoted\n",
            "plain.md": "# No source\n\nNo source metadata.\n",
        }
        ids = {}
        for name, content in samples.items():
            path = self.write(name, content)
            ids[name] = _token(name, hashlib.sha256(path.read_bytes()).hexdigest(), self.store._id_secret)
        self.login()
        for name in ("claim.md", "fake.md", "mismatch.md", "capture.md", "promoted.md"):
            result = self.client.get(f"/api/knowledge/items/{ids[name]}/source", headers=self.headers)
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json(), {"status": "unavailable", "provenance_status": "unverified", "source": None})
        missing = self.client.get(f"/api/knowledge/items/{ids['plain.md']}/source", headers=self.headers)
        self.assertEqual(missing.json(), {"status": "missing", "provenance_status": "missing", "source": None})
        self.assertFalse(any(p.name == "must-not-be-read.md" for p in self.root.iterdir()))
        self.assertEqual((self.review / "must-not-be-read.md").read_text(), "private review decoy")
        self.assertEqual((self.raw / "must-not-be-read.md").read_text(), "private raw decoy")

    def test_invalid_utf8_blank_oversize_symlinks_and_nested_symlink_paths_fail_closed(self):
        self.write("invalid.md", b"\xff\xfe")
        self.write("blank.md", b" \n\t")
        large = self.write("large.md", b"x" * (MAX_FILE_BYTES + 1))
        self.write("nested/ok.md", "# Synthetic\n")
        outside = self.base / "outside.md"
        outside.write_text("# Outside secret")
        outside.chmod(0o600)
        (self.root / "linked.md").symlink_to(outside)
        (self.root / "linked-dir").symlink_to(outside.parent, target_is_directory=True)
        (self.root / "linked-hard.md").hardlink_to(outside)
        self.login()
        found = self.client.get("/api/knowledge/search?q=Synthetic", headers=self.headers)
        self.assertEqual(found.status_code, 200)
        self.assertEqual([row["title"] for row in found.json()["items"]], ["Synthetic"])
        for relative in ("../outside.md", "/etc/passwd", "nested/../../outside.md", "%2e%2e/outside.md",
                         "%252e%252e/outside.md", "linked.md", "linked-dir/outside.md", "linked-hard.md",
                         "large.md", "invalid.md"):
            response = self.client.get(f"/api/knowledge/items/{_token(relative, '0' * 64, self.store._id_secret)}", headers=self.headers)
            self.assertIn(response.status_code, {404, 413, 422}, relative)
        self.assertEqual(outside.read_text(), "# Outside secret")
        self.assertTrue(large.exists())

    def test_missing_root_and_stale_or_renamed_item_are_deterministic(self):
        absent = KnowledgeReadStore(str(self.base / "not-created"))
        with self.assertRaises(Exception) as unavailable:
            absent.search("query", 10)
        self.assertEqual(getattr(unavailable.exception, "status_code", None), 503)
        self.assertFalse((self.base / "not-created").exists())
        original = self.write("stable.md", "# Original\n")
        item_id = _token("stable.md", hashlib.sha256(original.read_bytes()).hexdigest(), self.store._id_secret)
        original.write_text("# Changed\n")
        with self.assertRaises(Exception) as conflict:
            self.store.detail(item_id)
        self.assertEqual(getattr(conflict.exception, "status_code", None), 409)
        self.assertEqual(getattr(conflict.exception, "detail", None), "Knowledge item changed; search again")
        current_id = _token("stable.md", hashlib.sha256(original.read_bytes()).hexdigest(), self.store._id_secret)
        self.assertEqual(self.store.detail(current_id)["sha256"], hashlib.sha256(b"# Changed\n").hexdigest())
        original.rename(self.root / "renamed.md")
        with self.assertRaises(Exception) as missing:
            self.store.detail(current_id)
        self.assertEqual(getattr(missing.exception, "status_code", None), 404)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["renamed.md"])

    def test_tampered_item_identifier_and_symlinked_root_are_rejected(self):
        note = self.write("safe.md", "# Safe\n")
        original_id = _token("safe.md", hashlib.sha256(note.read_bytes()).hexdigest(), self.store._id_secret)
        version, payload, signature = original_id.split(".")
        altered = f"{version}.{payload}.{('0' if signature[0] != '0' else '1') + signature[1:]}"
        with self.assertRaises(Exception) as invalid:
            self.store.detail(altered)
        self.assertEqual(getattr(invalid.exception, "status_code", None), 404)
        root_link = self.base / "knowledge-link"
        root_link.symlink_to(self.root, target_is_directory=True)
        linked_store = KnowledgeReadStore(str(root_link))
        with self.assertRaises(Exception) as unavailable:
            linked_store.search("Safe", 10)
        self.assertEqual(getattr(unavailable.exception, "status_code", None), 503)

    def test_folder_browser_returns_real_frontmatter_tags_and_supports_and_or_filters(self):
        root_note = self.write("Projects/Alpha.md", '---\ntags: ["研究", "AI"]\n---\n# Alpha\nPrivate body must not be listed.\n')
        self.write("Projects/sub/Field.md", "---\ntags:\n  - 研究\n  - Obsidian\n---\n# Field\n")
        self.write("Projects/sub/Other.md", "---\ntags: [AI]\n---\n# Other\n")
        self.write("Projects/No-tags.md", "# No tags\n")
        before = hashlib.sha256(root_note.read_bytes()).hexdigest()
        self.login()

        folders = self.client.get("/api/knowledge/folders?path=Projects", headers=self.headers)
        self.assertEqual(folders.status_code, 200, folders.text)
        self.assertEqual(folders.headers["cache-control"], "private, no-store")
        self.assertEqual(folders.json(), {"status": "ok", "path": "Projects",
                                         "folders": [{"name": "sub", "path": "Projects/sub"}],
                                         "scan": {"entries": 3, "complete": True}})

        unfiltered = self.client.get("/api/knowledge/browse", params={"path": "Projects"}, headers=self.headers)
        self.assertEqual(unfiltered.status_code, 200, unfiltered.text)
        self.assertEqual(unfiltered.json()["total"], 4)
        no_tags = next(item for item in unfiltered.json()["items"] if item["title"] == "No tags")
        self.assertEqual(no_tags["tags"], [])

        and_result = self.client.get("/api/knowledge/browse", params=[
            ("path", "Projects"), ("tag", "研究"), ("tag", "AI"), ("match", "and"), ("limit", "1")
        ], headers=self.headers)
        self.assertEqual(and_result.status_code, 200, and_result.text)
        self.assertEqual(and_result.headers["cache-control"], "private, no-store")
        self.assertEqual(and_result.json()["status"], "ok")
        self.assertEqual(and_result.json()["total"], 1)
        self.assertTrue(and_result.json()["total_complete"])
        self.assertEqual(and_result.json()["items"][0]["path"], "Projects/Alpha.md")
        self.assertEqual(and_result.json()["items"][0]["tags"], ["AI", "研究"])

        or_result = self.client.get("/api/knowledge/browse", params=[
            ("path", "Projects"), ("tag", "研究"), ("tag", "AI"), ("match", "or"), ("limit", "1")
        ], headers=self.headers)
        self.assertEqual(or_result.status_code, 200, or_result.text)
        payload = or_result.json()
        self.assertEqual(payload["total"], 3)
        self.assertEqual(payload["next_offset"], 1)
        self.assertEqual(payload["tag_facets"], [
            {"name": "AI", "count": 2, "count_complete": True},
            {"name": "Obsidian", "count": 1, "count_complete": True},
            {"name": "研究", "count": 2, "count_complete": True},
        ])
        item = payload["items"][0]
        self.assertEqual(set(item), {"id", "path", "title", "updated", "tags", "metadata_status"})
        self.assertEqual(self.store.detail(item["id"])["content"], root_note.read_text())
        self.assertNotIn(str(self.root), or_result.text)
        self.assertNotIn("Private body must not be listed", or_result.text)
        self.assertEqual(hashlib.sha256(root_note.read_bytes()).hexdigest(), before)
        second_page = self.client.get("/api/knowledge/browse", params=[
            ("path", "Projects"), ("tag", "研究"), ("tag", "AI"), ("match", "or"),
            ("offset", "1"), ("limit", "1")
        ], headers=self.headers)
        self.assertEqual(second_page.status_code, 200, second_page.text)
        self.assertEqual(second_page.json()["offset"], 1)
        self.assertNotEqual(second_page.json()["items"][0]["id"], item["id"])

    def test_frontmatter_comment_after_tags_key_is_not_counted_as_a_tag(self):
        self.write("comment.md", "---\ntags: # explanatory comment\n---\n# Commented tags\n")
        self.login()

        unfiltered = self.client.get("/api/knowledge/browse", headers=self.headers)
        self.assertEqual(unfiltered.status_code, 200, unfiltered.text)
        item = unfiltered.json()["items"][0]
        self.assertEqual(item["title"], "Commented tags")
        self.assertEqual(item["tags"], [])
        self.assertEqual(item["metadata_status"], "ok")
        self.assertNotIn("# explanatory comment", {facet["name"] for facet in unfiltered.json()["tag_facets"]})

        comment_filter = self.client.get("/api/knowledge/browse", params={"tag": "# explanatory comment"},
                                         headers=self.headers)
        self.assertEqual(comment_filter.status_code, 200, comment_filter.text)
        self.assertEqual(comment_filter.json()["total"], 0)

    def test_folder_browser_marks_unsupported_frontmatter_and_truncated_counts_partial(self):
        self.write("good.md", "---\ntags: [safe]\n---\n# Good\n")
        self.write("bad.md", "---\ntags: [safe]\ntags: [hidden]\n---\n# Unsupported\n")
        self.login()
        response = self.client.get("/api/knowledge/browse", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["status"], "partial")
        self.assertFalse(payload["total_complete"])
        self.assertTrue(all(not facet["count_complete"] for facet in payload["tag_facets"]))
        unsupported = next(item for item in payload["items"] if item["title"] == "Unsupported")
        self.assertEqual(unsupported["metadata_status"], "unsupported")
        self.assertEqual(unsupported["tags"], [])

        with patch("secondbrain_core.modules.knowledge_read.MAX_SCAN_ENTRIES", 1):
            limited = self.client.get("/api/knowledge/browse", headers=self.headers)
        self.assertEqual(limited.status_code, 200, limited.text)
        self.assertEqual(limited.json()["status"], "partial")
        self.assertFalse(limited.json()["scan"]["complete"])
        self.assertFalse(limited.json()["total_complete"])

    def test_folder_browser_distinguishes_yaml_null_from_unsupported_boolean_tags(self):
        self.write("null-tags.md", "---\ntags: null\n---\n# Null tags\n")
        self.write("boolean-tags.md", "---\ntags: true\n---\n# Boolean tags\n")
        self.login()
        response = self.client.get("/api/knowledge/browse", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["status"], "partial")
        null_item = next(item for item in payload["items"] if item["title"] == "Null tags")
        self.assertEqual(null_item["metadata_status"], "ok")
        self.assertEqual(null_item["tags"], [])
        boolean_item = next(item for item in payload["items"] if item["title"] == "Boolean tags")
        self.assertEqual(boolean_item["metadata_status"], "unsupported")
        self.assertEqual(boolean_item["tags"], [])

    def test_folder_browser_bounds_facet_cardinality_without_claiming_complete_counts(self):
        self.write("first.md", "---\ntags: [one]\n---\n# First\n")
        self.write("second.md", "---\ntags: [two]\n---\n# Second\n")
        self.login()
        with patch("secondbrain_core.modules.knowledge_read.MAX_TAG_FACETS", 1):
            response = self.client.get("/api/knowledge/browse", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["status"], "partial")
        self.assertFalse(payload["total_complete"])
        self.assertEqual(len(payload["tag_facets"]), 1)
        self.assertFalse(payload["tag_facets"][0]["count_complete"])

    def test_folder_browser_rejects_unauthorized_traversal_and_symlink_scopes(self):
        outside = self.base / "outside-folder"
        outside.mkdir(mode=0o700)
        (outside / "secret.md").write_text("secret")
        (self.root / "linked-folder").symlink_to(outside, target_is_directory=True)
        unauthorized = self.client.get("/api/knowledge/browse", headers=self.headers)
        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(unauthorized.headers.get("cache-control"), "private, no-store")
        self.login()
        for invalid in ("../outside-folder", "%2e%2e/outside-folder", "%252e%252e/outside-folder", "/"):
            response = self.client.get("/api/knowledge/folders", params={"path": invalid}, headers=self.headers)
            self.assertEqual(response.status_code, 400, (invalid, response.text))
        linked = self.client.get("/api/knowledge/browse", params={"path": "linked-folder"}, headers=self.headers)
        self.assertEqual(linked.status_code, 404)
        self.assertNotIn("secret", linked.text)

    def test_folder_endpoints_require_knowledge_read_and_preserve_no_store(self):
        self.write("note.md", "# Synthetic\n")
        self.login()
        with patch.object(self.auth, "require_action", wraps=self.auth.require_action) as require_action:
            self.client.get("/api/knowledge/folders", headers=self.headers)
            self.client.get("/api/knowledge/browse", headers=self.headers)
        require_action.assert_any_call(unittest.mock.ANY, "knowledge.read")

    def test_folder_endpoints_fail_closed_on_revoked_knowledge_read_grant(self):
        self.login()
        with patch.object(self.auth, "require_action", side_effect=HTTPException(status_code=403, detail="Action is not enabled")):
            for endpoint in ("/api/knowledge/folders", "/api/knowledge/browse"):
                denied = self.client.get(endpoint, headers=self.headers)
                self.assertEqual(denied.status_code, 403)
                self.assertEqual(denied.headers.get("cache-control"), "private, no-store")


if __name__ == "__main__":
    unittest.main()
