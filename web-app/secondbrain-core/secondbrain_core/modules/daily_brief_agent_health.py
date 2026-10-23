"""Authenticated Daily Brief write/read and minimal Agent Health contracts."""
import hashlib
import json
import re
import uuid
import ipaddress
from datetime import date, datetime, timezone
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Query, Request, Response

from .daily_brief_store import DailyBriefRecordReadStore
from .daily_brief_import import (
    BriefImportConflict,
    BriefImportForbidden,
    BriefImportRejected,
    BriefImportStale,
    BriefImportUnavailable,
    DailyBriefAuditStore,
    DailyBriefImportStore,
    _canonical,
)
from .source_reference_authority import SourceReferenceAuthority


def _valid_date(value):
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="date must use YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise HTTPException(status_code=400, detail="date must use YYYY-MM-DD")
    return value


def _valid_timezone(value):
    if not isinstance(value, str) or not value or len(value) > 64:
        raise HTTPException(status_code=400, detail="timezone is invalid")
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="timezone is invalid") from exc
    return value


def _checked_at():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _strict_json_object(payload):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result
    def reject_constant(_value):
        raise ValueError("non-standard JSON number")
    value = json.loads(payload.decode("utf-8"), object_pairs_hook=unique,
                       parse_constant=reject_constant)
    if not isinstance(value, dict):
        raise ValueError("object required")
    return value


def _check_d089_same_origin_get(auth, request):
    """Apply the frozen D089 same-origin GET exception to Brief selection."""
    headers = request.headers
    origins = headers.getlist("origin")
    fetch_sites = headers.getlist("sec-fetch-site")
    fetch_modes = headers.getlist("sec-fetch-mode")
    fetch_dests = headers.getlist("sec-fetch-dest")
    if (len(origins) > 1 or len(fetch_sites) > 1
            or len(fetch_modes) > 1 or len(fetch_dests) > 1):
        raise HTTPException(status_code=403, detail="Trusted App Origin required")
    site = fetch_sites[0] if fetch_sites else None
    if site is not None and site != "same-origin":
        raise HTTPException(status_code=403, detail="Trusted App Origin required")
    if (fetch_modes and fetch_modes[0] not in {"cors", "same-origin"}) or (
            fetch_dests and fetch_dests[0] != "empty"):
        raise HTTPException(status_code=403, detail="Trusted App Origin required")
    hosts = headers.getlist("host")
    if len(hosts) != 1 or not hosts[0] or hosts[0].strip() != hosts[0]:
        raise HTTPException(status_code=403, detail="Trusted App Origin required")
    effective = f"{request.url.scheme}://{request.url.netloc}"
    if (effective not in auth.allowed_origins
            or request.url.netloc.lower() != hosts[0].lower()):
        raise HTTPException(status_code=403, detail="Trusted App Origin required")
    parsed = urlsplit(effective)
    if not parsed.hostname or parsed.username or parsed.password:
        raise HTTPException(status_code=403, detail="Trusted App Origin required")
    try:
        port = parsed.port
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Trusted App Origin required") from exc
    if parsed.scheme == "http":
        if parsed.hostname not in {"localhost", "127.0.0.1", "::1"} or port is None:
            raise HTTPException(status_code=403, detail="Trusted App Origin required")
        client = request.client.host if request.client else ""
        try:
            loopback_client = ipaddress.ip_address(client).is_loopback
        except ValueError:
            loopback_client = client == "localhost"
        if not loopback_client:
            raise HTTPException(status_code=403, detail="Trusted App Origin required")
    elif parsed.scheme != "https":
        raise HTTPException(status_code=403, detail="Trusted App Origin required")
    if origins:
        if origins[0] != effective:
            raise HTTPException(status_code=403, detail="Trusted App Origin required")
        auth.check_origin(request)
    elif site != "same-origin":
        raise HTTPException(status_code=403, detail="Trusted App Origin required")


def create_daily_brief_agent_health_router(auth, hermes, brief_store=None, projects_store=None,
                                          task_store=None, journal_store=None, notes_store=None,
                                          brief_import_store=None, brief_audit_store=None):
    router = APIRouter(prefix="/api")
    brief_store = brief_store or DailyBriefRecordReadStore(None)
    brief_import_store = brief_import_store or DailyBriefImportStore(None)
    brief_audit_store = brief_audit_store or DailyBriefAuditStore("")

    def authority_factory(request):
        return SourceReferenceAuthority(
            projects_store=projects_store,
            task_store=task_store,
            journal_store=journal_store,
            notes_store=notes_store,
            permission_checks={
                "project": lambda: auth.require_action(request, "projects.read"),
                "task": lambda: auth.require_action(request, "task.read"),
                "journal": lambda: auth.require_action(request, "journal.read"),
            },
        )

    def write_audit(*, request_id, brief_id, day, timezone_name, refs, outcome, actor):
        counts = {kind: sum(ref.get("kind") == kind for ref in refs)
                  for kind in ("task", "project", "journal")}
        brief_audit_store.append({
            "event_type": "daily_brief_import",
            "request_id": request_id,
            "brief_id": brief_id,
            "date": day,
            "timezone": timezone_name,
            "source_kind_counts": {key: value for key, value in counts.items() if value},
            "outcome": outcome,
            "recorded_at": _checked_at(),
            "actor": actor,
        })

    def require_source_permissions(request, refs):
        required = {
            "task": "task.read",
            "project": "projects.read",
            "journal": "journal.read",
        }
        kinds = {reference["kind"] for reference in refs}
        for kind in ("task", "project", "journal"):
            if kind in kinds:
                try:
                    auth.require_action(request, required[kind])
                except HTTPException as exc:
                    if exc.status_code == 403:
                        raise HTTPException(status_code=403,
                                            detail="Daily Brief source access denied") from None
                    raise

    def read_selected_brief(request, day, brief_id, version, *, expected_copy=None):
        """Read one exact source date, revalidate all refs, and compare its raw version."""
        try:
            if brief_import_store.has_pending_for_date(day):
                raise BriefImportUnavailable("source record is pending commit")
            authority = authority_factory(request)
            snapshot = brief_store.read(
                day, "Asia/Shanghai", source_verifier=authority.verify,
                source_permission_preflight=lambda refs: require_source_permissions(request, refs),
            )
        except HTTPException as exc:
            if exc.status_code == 403:
                raise BriefImportForbidden("source permission denied") from None
            raise BriefImportUnavailable("source record unavailable") from None
        except (BriefImportForbidden, BriefImportRejected, BriefImportUnavailable):
            raise
        except Exception as exc:
            raise BriefImportUnavailable("source record unavailable") from exc
        if not snapshot.configured or not snapshot.available:
            raise BriefImportUnavailable("source record unavailable")
        if not snapshot.found or not snapshot.record:
            raise BriefImportStale("source record is missing")
        if snapshot.source_verification == "forbidden":
            raise BriefImportForbidden("source permission denied")
        if snapshot.source_verification in {"unavailable", "failed"}:
            raise BriefImportUnavailable("source record unavailable")
        if snapshot.source_verification != "verified":
            raise BriefImportStale("source references are not current")
        record = snapshot.record
        if (record.get("brief_id") != brief_id or snapshot.sha256 != version
                or record.get("generation_status") != "generated"):
            raise BriefImportStale("source record changed")
        if expected_copy is not None and any(
                _canonical(record[key]) != _canonical(expected_copy[key])
                for key in ("categories", "summary", "source_refs")):
            raise BriefImportConflict("import content differs from selected source")
        return snapshot

    @router.get("/daily-brief/source-options/brief")
    def brief_source_options(request: Request, response: Response):
        response.headers["Cache-Control"] = "private, no-store"
        _check_d089_same_origin_get(auth, request)
        auth.require_action(request, "daily_brief.read")
        pairs = request.query_params.multi_items()
        if (any(key not in {"date", "limit"} for key, _ in pairs)
                or len({key for key, _ in pairs}) != len(pairs)):
            raise HTTPException(status_code=400, detail="Invalid source selection request")
        query = dict(pairs)
        if "date" not in query:
            raise HTTPException(status_code=422, detail="Invalid source selection request")
        day = _valid_date(query["date"])
        if query.get("limit", "1") != "1":
            raise HTTPException(status_code=400, detail="Invalid source selection request")
        try:
            pending = brief_import_store.has_pending_for_date(day)
            if pending:
                return {"status": "unavailable", "items": [],
                        "freshness": {"checked_at": _checked_at()}}
            authority = authority_factory(request)
            snapshot = brief_store.read(
                day, "Asia/Shanghai", source_verifier=authority.verify,
                source_permission_preflight=lambda refs: require_source_permissions(request, refs),
            )
        except HTTPException as exc:
            if exc.status_code in {401, 403}:
                raise
            snapshot = None
        except Exception:
            snapshot = None
        if snapshot is None or not snapshot.configured or not snapshot.available:
            status, items = "unavailable", []
        elif not snapshot.found:
            status, items = "empty", []
        elif (snapshot.source_verification != "verified" or not snapshot.record
              or snapshot.record.get("generation_status") != "generated"):
            status, items = "unavailable", []
        else:
            record = snapshot.record
            status = "real"
            items = [{"kind": "existing_brief",
                      "id": f"{day}:{record['brief_id']}",
                      "date": day, "timezone": record["timezone"],
                      "version": snapshot.sha256}]
        return {"status": status, "items": items,
                "freshness": {"checked_at": _checked_at()}}

    @router.get("/daily-brief")
    def daily_brief(request: Request,
                    day: str = Query(..., alias="date"),
                    timezone_name: str = Query("Asia/Shanghai", alias="timezone")):
        auth.require_action(request, "daily_brief.read")
        day = _valid_date(day)
        timezone_name = _valid_timezone(timezone_name)
        checked_at = _checked_at()
        source = {"kind": "core-daily-brief-store"} if brief_store.configured else None
        try:
            if brief_import_store.has_pending_for_date(day):
                return {"status": "unavailable", "items": [], "source": source,
                        "freshness": {"checked_at": checked_at}}
            # Each request gets one bounded, exact-ID Projects snapshot. No
            # arbitrary caller path or cross-scope lookup enters this adapter.
            authority = authority_factory(request)
            snapshot = brief_store.read(
                day, timezone_name, source_verifier=authority.verify,
                source_permission_preflight=lambda refs: require_source_permissions(request, refs),
            )
        except HTTPException as exc:
            if exc.status_code in {401, 403}:
                raise
            return {"status": "unavailable", "items": [], "source": source,
                    "freshness": {"checked_at": checked_at}}
        except Exception:
            return {"status": "unavailable", "items": [], "source": source,
                    "freshness": {"checked_at": checked_at}}
        if not snapshot.configured:
            status, items = "not_configured", []
        elif snapshot.failure_status == "unavailable":
            status, items = "unavailable", []
        elif snapshot.failure_status == "failed":
            status, items = "failed", []
        elif not snapshot.available:
            status, items = "unavailable", []
        elif not snapshot.found:
            status, items = "empty", []
        else:
            record = snapshot.record
            if record["generation_status"] == "failed":
                status, items = "failed", []
            elif record["generation_status"] == "stale" or snapshot.source_verification in {"stale", "missing"}:
                status, items = "stale", []
            elif snapshot.source_verification == "forbidden":
                raise HTTPException(status_code=403, detail="Daily Brief source access denied")
            elif snapshot.source_verification == "unavailable":
                status, items = "unavailable", []
            elif snapshot.source_verification == "failed":
                status, items = "failed", []
            elif snapshot.source_verification != "verified":
                # Do not expose an unverified summary to the public API.
                status, items = "partial", []
            else:
                status = "partial" if record["generation_status"] == "partial" else "real"
                items = [{key: record[key] for key in (
                    "brief_id", "date", "timezone", "generated_at", "generation_status",
                    "categories", "summary", "source_refs",
                )}]
        return {"status": status, "items": items, "source": source,
                "freshness": {"checked_at": checked_at}}

    @router.post("/daily-brief")
    async def import_daily_brief(request: Request):
        actor = auth.require_action(request, "daily_brief.write")
        request_id = str(uuid.uuid4())
        if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise HTTPException(status_code=422, detail="invalid request")
        declared_size = request.headers.get("content-length")
        if declared_size is not None:
            try:
                if int(declared_size) > 128 * 1024:
                    raise HTTPException(status_code=422, detail="invalid request")
            except ValueError as exc:
                raise HTTPException(status_code=422, detail="invalid request") from exc
        chunks, total = [], 0
        async for chunk in request.stream():
            total += len(chunk)
            if total > 128 * 1024:
                raise HTTPException(status_code=422, detail="invalid request")
            chunks.append(chunk)
        try:
            body = _strict_json_object(b"".join(chunks))
        except (UnicodeError, ValueError, json.JSONDecodeError, RecursionError) as exc:
            raise HTTPException(status_code=422, detail="invalid request") from exc
        mode = body.get("mode")
        if not isinstance(mode, str) or mode not in {"manual_generate", "approved_import"}:
            raise HTTPException(status_code=422, detail="invalid request")
        expected = {"mode", "date", "timezone", "categories", "summary",
                    "source_refs", "approved"}
        if mode == "manual_generate":
            expected.add("idempotency_key")
        else:
            expected.add("import_ref")
        if set(body) != expected or body.get("approved") is not True:
            raise HTTPException(status_code=422, detail="invalid request")
        day, timezone_name = body.get("date"), body.get("timezone")
        if (timezone_name != "Asia/Shanghai" or not isinstance(day, str)
                or day != datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()):
            raise HTTPException(status_code=422, detail="invalid request")
        header_keys = request.headers.getlist("idempotency-key")
        if len(header_keys) > 1:
            raise HTTPException(status_code=422, detail="invalid request")
        header_key = header_keys[0] if header_keys else None
        body_key = body.get("idempotency_key")
        if mode == "approved_import":
            key = header_key
        else:
            if header_key is not None and body_key != header_key:
                raise HTTPException(status_code=422, detail="invalid request")
            key = body_key
        if (not isinstance(key, str) or not 16 <= len(key) <= 128
                or any(ord(char) < 33 or ord(char) > 126 for char in key)):
            raise HTTPException(status_code=422, detail="invalid request")
        refs = body.get("source_refs")
        if (not isinstance(refs, list) or not 1 <= len(refs) <= 50
                or any(not isinstance(ref, dict) or set(ref) != {"kind", "id", "version"}
                       or ref.get("kind") not in {"task", "project", "journal"}
                       or not isinstance(ref.get("id"), str)
                       or not isinstance(ref.get("version"), str) for ref in refs)
                or len({(ref["kind"], ref["id"]) for ref in refs}) != len(refs)):
            raise HTTPException(status_code=422, detail="invalid request")
        if mode == "approved_import":
            import_ref = body.get("import_ref")
            if (not isinstance(import_ref, dict) or set(import_ref) != {"kind", "id", "version"}
                    or import_ref.get("kind") != "existing_brief"
                    or not isinstance(import_ref.get("id"), str)
                    or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", import_ref["id"])
                    or not isinstance(import_ref.get("version"), str)
                    or not re.fullmatch(r"[a-f0-9]{64}", import_ref["version"])):
                raise HTTPException(status_code=422, detail="invalid request")
            try:
                auth.require_action(request, "daily_brief.read")
                require_source_permissions(request, refs)
            except HTTPException as exc:
                if exc.status_code == 403:
                    try:
                        write_audit(request_id=request_id, brief_id="", day=day,
                                    timezone_name=timezone_name, refs=refs,
                                    outcome="rejected", actor=actor)
                    except Exception as audit_exc:
                        raise HTTPException(status_code=503, detail="Daily Brief unavailable") from audit_exc
                    raise HTTPException(status_code=403,
                                        detail="Daily Brief source access denied") from None
                raise
            source_day, separator, selected_brief_id = import_ref["id"].partition(":")
            if (not separator or not selected_brief_id
                    or len(selected_brief_id) > 128):
                raise HTTPException(status_code=422, detail="invalid request")
            source_day = _valid_date(source_day)
            selected_version = import_ref["version"]
            copied = {key: body[key] for key in ("categories", "summary", "source_refs")}
            try:
                read_selected_brief(request, source_day, selected_brief_id,
                                    selected_version, expected_copy=copied)
            except BriefImportForbidden as exc:
                raise HTTPException(status_code=403,
                                    detail="Daily Brief source access denied") from exc
            except BriefImportConflict as exc:
                raise HTTPException(status_code=409,
                                    detail="Daily Brief import differs from selected source") from exc
            except BriefImportStale as exc:
                raise HTTPException(status_code=409,
                                    detail="Daily Brief source changed") from exc
            except BriefImportUnavailable as exc:
                raise HTTPException(status_code=503,
                                    detail="Daily Brief unavailable") from exc

            def verified_selected_source():
                read_selected_brief(request, source_day, selected_brief_id,
                                    selected_version, expected_copy=copied)
                authority_verify = authority_factory(request).verify
                remaining = len(copied["source_refs"])

                def verify_selected_reference(reference):
                    nonlocal remaining
                    if remaining == 0:
                        read_selected_brief(request, source_day, selected_brief_id,
                                            selected_version, expected_copy=copied)
                        remaining = len(copied["source_refs"])
                    remaining -= 1
                    return authority_verify(reference)

                return verify_selected_reference

            candidate = {key: body[key] for key in (
                "date", "timezone", "categories", "summary", "source_refs")}
            request_sha256 = hashlib.sha256(_canonical(body)).hexdigest()
            def audit_created(result):
                write_audit(request_id=request_id, brief_id=result["brief_id"], day=day,
                            timezone_name=timezone_name, refs=refs,
                            outcome="created", actor=actor)
            try:
                result = brief_import_store.import_idempotent(
                    candidate, source_verifier_factory=verified_selected_source,
                    idempotency_key=key, actor=actor,
                    request_sha256=request_sha256, before_commit=audit_created,
                )
            except BriefImportConflict as exc:
                try:
                    write_audit(request_id=request_id, brief_id="", day=day,
                                timezone_name=timezone_name, refs=refs,
                                outcome="rejected", actor=actor)
                except Exception as audit_exc:
                    raise HTTPException(status_code=503,
                                        detail="Daily Brief unavailable") from audit_exc
                raise HTTPException(status_code=409, detail="Daily Brief conflict") from exc
            except BriefImportForbidden as exc:
                raise HTTPException(status_code=403,
                                    detail="Daily Brief source access denied") from exc
            except BriefImportStale as exc:
                raise HTTPException(status_code=409,
                                    detail="Daily Brief source changed") from exc
            except BriefImportRejected as exc:
                raise HTTPException(status_code=422,
                                    detail="Daily Brief source verification failed") from exc
            except BriefImportUnavailable as exc:
                raise HTTPException(status_code=503,
                                    detail="Daily Brief unavailable") from exc
            if result["status"] == "duplicate":
                try:
                    write_audit(request_id=request_id, brief_id=result["brief_id"], day=day,
                                timezone_name=timezone_name, refs=refs,
                                outcome="duplicate", actor=actor)
                except Exception as exc:
                    raise HTTPException(status_code=503,
                                        detail="Daily Brief unavailable") from exc
            from fastapi.responses import JSONResponse
            response_status = 201 if result["status"] == "created" else 200
            return JSONResponse(status_code=response_status, content={
                "status": result["status"], "brief_id": result["brief_id"],
                "date": day, "timezone": timezone_name,
                "record_version": result["record_sha256"],
                "operation_id": result["operation_id"],
            })

        try:
            require_source_permissions(request, refs)
        except HTTPException as exc:
            if exc.status_code == 403:
                try:
                    write_audit(request_id=request_id, brief_id="", day=day,
                                timezone_name=timezone_name, refs=refs,
                                outcome="rejected", actor=actor)
                except Exception as audit_exc:
                    raise HTTPException(status_code=503, detail="Daily Brief unavailable") from audit_exc
                raise HTTPException(status_code=403, detail="Daily Brief source access denied") from None
            raise

        candidate = {key: body[key] for key in ("date", "timezone", "categories", "summary", "source_refs")}
        request_sha256 = hashlib.sha256(_canonical(body)).hexdigest()
        def audit_created(result):
            write_audit(request_id=request_id, brief_id=result["brief_id"], day=day,
                        timezone_name=timezone_name, refs=refs,
                        outcome="created", actor=actor)
        try:
            result = brief_import_store.import_idempotent(
                candidate,
                source_verifier_factory=lambda: authority_factory(request).verify,
                idempotency_key=key,
                actor=actor,
                request_sha256=request_sha256,
                before_commit=audit_created,
            )
        except BriefImportConflict as exc:
            try:
                write_audit(request_id=request_id, brief_id="", day=day,
                            timezone_name=timezone_name, refs=refs,
                            outcome="rejected", actor=actor)
            except Exception as audit_exc:
                raise HTTPException(status_code=503, detail="Daily Brief unavailable") from audit_exc
            raise HTTPException(status_code=409, detail="Daily Brief conflict") from exc
        except BriefImportForbidden as exc:
            try:
                write_audit(request_id=request_id, brief_id="", day=day,
                            timezone_name=timezone_name, refs=refs,
                            outcome="rejected", actor=actor)
            except Exception as audit_exc:
                raise HTTPException(status_code=503, detail="Daily Brief unavailable") from audit_exc
            raise HTTPException(status_code=403, detail="Daily Brief source access denied") from exc
        except BriefImportStale as exc:
            try:
                write_audit(request_id=request_id, brief_id="", day=day,
                            timezone_name=timezone_name, refs=refs,
                            outcome="rejected", actor=actor)
            except Exception as audit_exc:
                raise HTTPException(status_code=503, detail="Daily Brief unavailable") from audit_exc
            raise HTTPException(status_code=409, detail="Daily Brief source changed") from exc
        except BriefImportRejected as exc:
            try:
                write_audit(request_id=request_id, brief_id="", day=day,
                            timezone_name=timezone_name, refs=refs,
                            outcome="rejected", actor=actor)
            except Exception as audit_exc:
                raise HTTPException(status_code=503, detail="Daily Brief unavailable") from audit_exc
            raise HTTPException(status_code=422, detail="source verification failed") from exc
        except BriefImportUnavailable as exc:
            try:
                write_audit(request_id=request_id, brief_id="", day=day,
                            timezone_name=timezone_name, refs=refs,
                            outcome="failed", actor=actor)
            except Exception:
                pass
            raise HTTPException(status_code=503, detail="Daily Brief unavailable") from exc
        if result["status"] == "duplicate":
            try:
                write_audit(request_id=request_id, brief_id=result["brief_id"], day=day,
                            timezone_name=timezone_name, refs=refs,
                            outcome="duplicate", actor=actor)
            except Exception as exc:
                raise HTTPException(status_code=503, detail="Daily Brief unavailable") from exc
        from fastapi.responses import JSONResponse
        response_status = 201 if result["status"] == "created" else 200
        return JSONResponse(status_code=response_status, content={
            "status": result["status"], "brief_id": result["brief_id"],
            "date": day, "timezone": timezone_name,
            "record_version": result["record_sha256"],
            "operation_id": result["operation_id"],
        })

    @router.get("/agent/health")
    async def agent_health(request: Request):
        auth.require_action(request, "agent.health.read")
        checked_at = _checked_at()
        if not getattr(hermes, "configured", False):
            return {"status": "not_configured", "source": None, "checked_at": checked_at}
        try:
            await hermes.capabilities()
        except HTTPException:
            return {"status": "unavailable", "source": "hermes-runtime",
                    "checked_at": checked_at}
        return {"status": "online", "source": "hermes-runtime", "checked_at": checked_at}

    return router
