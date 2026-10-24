"""Synthetic Core + Hermes v0.22.2 post-admission capture slice.

Set HERMES_SOURCE_ROOT to the pinned v0.22.2 source checkout to exercise its
real post-admission dispatcher. No Gateway, account, model or external network is used.
"""
import asyncio
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from secondbrain_core.modules.capture import CaptureService
from secondbrain_core.modules.channel_identity import WeixinHmacIdentityProvider
from secondbrain_core.modules.trusted_channel_adapter import create_trusted_channel_router


HERMES_ROOT = os.environ.get("HERMES_SOURCE_ROOT", "")


@unittest.skipUnless(HERMES_ROOT, "requires pinned Hermes source via HERMES_SOURCE_ROOT")
class WeixinPostAdmissionE2ETests(unittest.TestCase):
    def setUp(self):
        hermes = Path(HERMES_ROOT).resolve()
        if not (hermes / "gateway/run_inbound_consumer.py").is_file():
            self.skipTest("HERMES_SOURCE_ROOT does not contain gateway source")
        sys.path.insert(0, str(hermes))
        from gateway.run_inbound_consumer import run_post_admission_hook
        self.run_hook = run_post_admission_hook

        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        raw, review, state = (root / name for name in ("raw", "review", "state"))
        for path in (raw, review, state):
            path.mkdir(mode=0o700)
        self.service = CaptureService(str(raw), str(review), str(state))
        self.client = TestClient(FastAPI())
        self.plugin_path = Path(__file__).resolve().parents[2] / "hermes-agent/weixin-inbox/__init__.py"
        spec = importlib.util.spec_from_file_location("synthetic_weixin_inbox_plugin", self.plugin_path)
        self.plugin = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.plugin)
        self.key = b"synthetic-weixin-hmac-key-not-a-credential"
        self.key_file = root / "weixin-hmac-key"
        self.key_file.write_bytes(self.key + b"\n")
        self.key_file.chmod(0o600)
        provider = WeixinHmacIdentityProvider(self.key, {"synthetic-weixin-user": "synthetic-owner"})
        app = FastAPI()
        app.include_router(create_trusted_channel_router(self.service, provider))
        self.client.close()
        self.client = TestClient(app)
        self.posts = 0

        def fake_urlopen(request, timeout):
            self.posts += 1
            response = self.client.post(request.full_url, content=request.data,
                                        headers=dict(request.header_items()))
            wrapped = _SyntheticResponse(response.status_code, response.content,
                                         response.headers.get("X-SecondBrain-Receipt-Signature", ""))
            self.last_response = wrapped
            return wrapped

        self.urlopen_patch = patch.object(self.plugin, "urlopen", fake_urlopen)
        self.urlopen_patch.start()
        self.env_patch = patch.dict(os.environ, {
            "SB_WEIXIN_CORE_INBOX_URL": "http://core.test/api/internal/v1/channel-events",
            "SB_WEIXIN_CORE_INBOX_HMAC_KEY_FILE": str(self.key_file),
        })
        os.environ.pop("SB_WEIXIN_CORE_INBOX_HMAC_KEY", None)
        self.env_patch.start()
        self.hook_patches = patch("hermes_cli.lifecycle.has_hook", return_value=True), patch(
            "hermes_cli.lifecycle.ainvoke_hook", side_effect=self.invoke_plugin)
        for item in self.hook_patches:
            item.start()
        self.runner = SimpleNamespace(config=SimpleNamespace(multiplex_profiles=False))

    def tearDown(self):
        for item in self.hook_patches:
            item.stop()
        self.env_patch.stop()
        self.urlopen_patch.stop()
        self.client.close()
        self.temp.cleanup()
        if HERMES_ROOT:
            try:
                sys.path.remove(str(Path(HERMES_ROOT).resolve()))
            except ValueError:
                pass

    async def invoke_plugin(self, hook_name, **payload):
        return [self.plugin._post_gateway_admission(**payload)]

    def _source(self, user="synthetic-weixin-user", chat_type="dm"):
        platform = SimpleNamespace(value="weixin")
        return SimpleNamespace(platform=platform, to_dict=lambda: {
            "platform": "weixin", "chat_type": chat_type, "user_id": user,
            "chat_id": "synthetic-chat",
        })

    def _event(self, message_id, text):
        return SimpleNamespace(message_id=message_id, text=text)

    def _dispatch(self, text, message_id="synthetic-event-1", user="synthetic-weixin-user", chat_type="dm"):
        with patch.object(self.service, "mark_scheduled", return_value=False):
            return asyncio.run(self.run_hook(self.runner, self._event(message_id, text),
                                             self._source(user, chat_type), "synthetic-session"))

    def test_normal_chat_passes_to_hermes_and_explicit_capture_is_idempotent(self):
        handled, reply = self._dispatch("你好")
        self.assertFalse(handled)
        self.assertIsNone(reply)
        self.assertEqual(self.posts, 0)
        first = self._dispatch("收录：合成测试备忘", "synthetic-event-1")
        self.assertEqual(first, (True, "已收录到 Inbox。"))
        replay = self._dispatch("收录：合成测试备忘", "synthetic-event-1")
        self.assertEqual(replay, (True, "已收录到 Inbox。"))
        self.assertEqual(self.posts, 2)
        self.assertEqual(len(list((Path(self.temp.name) / "raw").glob("Inbox-*.md"))), 1)

    def test_untrusted_sender_and_group_do_not_write_or_claim_success(self):
        denied = self._dispatch("收录：不可写入", "synthetic-event-2", user="unknown-user")
        self.assertTrue(denied[0])
        self.assertIn("保存失败", denied[1])
        group = self._dispatch("收录：群聊不可收录", "synthetic-event-3", chat_type="group")
        self.assertTrue(group[0])
        self.assertIn("仅支持微信私聊", group[1])
        self.assertEqual(len(list((Path(self.temp.name) / "raw").glob("Inbox-*.md"))), 0)

    def test_unsigned_202_cannot_be_reported_as_a_successful_save(self):
        def forged_receipt(_request, timeout):
            return _SyntheticResponse(
                202, json.dumps({"inbox_id": "forged-id", "status": "processing"}).encode(), "")

        with patch.object(self.plugin, "urlopen", forged_receipt):
            result = self._dispatch("收录：合成失败回执", "synthetic-event-forged")
        self.assertTrue(result[0])
        self.assertIn("保存失败", result[1])
        self.assertEqual(len(list((Path(self.temp.name) / "raw").glob("Inbox-*.md"))), 0)

    def test_old_valid_receipt_cannot_confirm_changed_content_for_same_event(self):
        first = self._dispatch("收录：原始合成内容", "synthetic-event-stale")
        self.assertEqual(first, (True, "已收录到 Inbox。"))
        def replay_old_receipt(_request, timeout):
            return _SyntheticResponse(202, old_receipt_response.content,
                                     old_receipt_response.headers[
                                         "X-SecondBrain-Receipt-Signature"])

        old_receipt_response = self.last_response
        with patch.object(self.plugin, "urlopen", replay_old_receipt):
            changed = self._dispatch("收录：被修改的合成内容", "synthetic-event-stale")
        self.assertTrue(changed[0])
        self.assertIn("保存失败", changed[1])
        self.assertEqual(len(list((Path(self.temp.name) / "raw").glob("Inbox-*.md"))), 1)

    def test_ambiguous_or_missing_file_key_fails_without_claiming_success(self):
        with patch.dict(os.environ, {"SB_WEIXIN_CORE_INBOX_HMAC_KEY": self.key.decode()}):
            ambiguous = self._dispatch("收录：配置歧义", "synthetic-event-ambiguous")
        self.assertIn("保存失败", ambiguous[1])
        self.assertEqual(len(list((Path(self.temp.name) / "raw").glob("Inbox-*.md"))), 0)
        self.key_file.unlink()
        missing = self._dispatch("收录：文件缺失", "synthetic-event-missing")
        self.assertIn("保存失败", missing[1])
        self.assertEqual(len(list((Path(self.temp.name) / "raw").glob("Inbox-*.md"))), 0)


class _SyntheticResponse:
    def __init__(self, status, content, receipt_signature):
        self.status = status
        self.content = content
        self.headers = {"X-SecondBrain-Receipt-Signature": receipt_signature}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, limit=-1):
        return self.content[:limit]
