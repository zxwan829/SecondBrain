"""Opt-in, synthetic-only Brief generation candidate.

The public trigger and a production model adapter remain separate contracts.
Source text is passed only as untrusted data; this module never constructs a
system/developer message or calls Hermes.
"""
from __future__ import annotations

import hashlib
import json
from typing import Callable
from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException

from .daily_brief_import import DailyBriefImportStore
from .daily_brief_store import _valid_source_reference
from .daily_brief_store import DailyBriefRecordReadStore
from .source_reference_authority import SourceReferenceAuthority


_MAX_CONTEXT_BYTES = 64 * 1024


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


class DailyBriefGenerationCandidate:
    """One explicitly confirmed, fail-closed synthetic generation attempt."""

    def __init__(self, *, authority_factory: Callable[[], SourceReferenceAuthority],
                 store: DailyBriefImportStore, cost_gate, model,
                 permission_preflight: Callable[[], None], enabled=False):
        self.authority_factory = authority_factory
        self.store = store
        self.cost_gate = cost_gate
        self.model = model
        self.permission_preflight = permission_preflight
        self.enabled = enabled

    def _read_sources(self, authority, refs):
        rows = []
        for ref in refs:
            outcome = authority.verify(ref)
            if outcome != "verified":
                code = 403 if outcome == "forbidden" else 409 if outcome in {"stale", "missing"} else 503
                raise HTTPException(code, "Brief source unavailable")
            kind, identifier = ref["kind"], ref["id"]
            if kind == "project":
                matches = [item.document for item in authority._project_snapshot.documents
                           if item.project_id == identifier]
                if len(matches) != 1:
                    raise HTTPException(503, "Brief source unavailable")
                content = {key: matches[0].get(key) for key in ("title", "status", "next_step")}
            elif kind == "task":
                matches = [item for item in authority._task_rows if item.get("id") == identifier]
                if len(matches) != 1:
                    raise HTTPException(503, "Brief source unavailable")
                content = {key: matches[0].get(key) for key in ("title", "status", "due_date")}
            elif kind == "journal":
                day, entry_id = identifier.split(":", 1)
                record = authority._journal_days[day]["entries"][entry_id]["record"]
                original = record.get("original_text")
                if not isinstance(original, str):
                    raise HTTPException(503, "Brief source unavailable")
                content = {"original_text": original}
            else:
                raise HTTPException(503, "Brief source unavailable")
            rows.append({"ref": dict(ref), "content": content})
            if len(json.dumps(rows, ensure_ascii=False).encode("utf-8")) > _MAX_CONTEXT_BYTES:
                raise HTTPException(413, "Brief source budget exceeded")
        return rows

    def _bind_intent(self, reservation, day, timezone, refs):
        """Record only reconciliation metadata before the synthetic model call."""
        def bind(state):
            rows = state.get("budget", {}).get("chat_runs", {})
            row = next((item for item in rows.values()
                        if item.get("reservation_id") == reservation["reservation_id"]), None)
            if row is None or row.get("status") != "reserved" or "brief_intent" in row:
                raise ValueError("Brief reservation changed")
            row["brief_intent"] = {"date": day, "timezone": timezone,
                                   "refs_sha256": _digest(refs)}
            row["brief_recovery_state"] = "reserved"
        self.cost_gate.state.update(bind)

    def _mark_recovery(self, reservation_id, state_name):
        def mark(state):
            rows = state.get("budget", {}).get("chat_runs", {})
            row = next((item for item in rows.values()
                        if item.get("reservation_id") == reservation_id), None)
            if row is not None and row.get("brief_result") is None:
                row["brief_recovery_state"] = state_name
        try:
            self.cost_gate.state.update(mark)
        except Exception:
            # The read-only operator diagnosis still detects a missing receipt.
            pass

    def diagnose(self, *, actor: str, session_id: str, idempotency_key: str,
                 operator_preflight: Callable[[], None]):
        """Operator-only, read-only reconciliation. Never exposes source text or paths."""
        operator_preflight()
        if (not all(isinstance(value, str) and value for value in
                    (actor, session_id, idempotency_key))):
            raise HTTPException(422, "Invalid Brief operation")
        scope = hashlib.sha256(f"{actor}\0{session_id}\0{idempotency_key}".encode()).hexdigest()
        rows = self.cost_gate.state.read().get("budget", {}).get("chat_runs", {})
        row = rows.get(scope)
        if row is None:
            return {"state": "not_found", "recovery_required": False,
                    "manual_action": False}
        intent = row.get("brief_intent")
        if (not isinstance(intent, dict) or not isinstance(intent.get("date"), str)
                or intent.get("timezone") != "Asia/Shanghai"):
            return {"state": "unbound_reservation", "recovery_required": True,
                    "manual_action": True}
        try:
            pending = self.store.has_pending_for_date(intent["date"])
            snapshot = DailyBriefRecordReadStore(self.store.root).read(
                intent["date"], intent["timezone"])
        except Exception:
            pending, snapshot = False, None
        if pending:
            state_name = "brief_pending_commit"
        elif snapshot is None or not snapshot.available or snapshot.failure_status is not None:
            state_name = "brief_unavailable"
        elif not snapshot.found:
            state_name = ("cost_settled_no_brief" if row.get("status") == "settled"
                          else "outcome_unknown_no_brief")
        elif (isinstance(row.get("brief_result"), dict)
              and row["brief_result"].get("record_sha256") == snapshot.sha256
              and row["brief_result"].get("brief_id") == snapshot.record["brief_id"]
              and intent.get("refs_sha256") == _digest(snapshot.record["source_refs"])
              and row.get("status") == "settled"):
            state_name = "committed"
        else:
            # A same-date file alone cannot prove which request published it.
            state_name = "date_record_present_unattributed"
        phase = row.get("brief_recovery_state")
        if phase not in {"reserved", "model_unknown", "cost_settled_brief_unknown", "committed"}:
            phase = "unknown"
        return {"state": state_name, "recovery_required": state_name != "committed",
                "cost_status": row.get("status") if row.get("status") in
                {"reserved", "started", "unknown", "settled"} else "unknown",
                "phase": phase,
                "accounted_microcny": row.get("accounted_microcny") if
                type(row.get("accounted_microcny")) is int else None,
                "manual_action": state_name != "committed"}

    def generate(self, *, day: str, timezone: str, refs: list[dict], actor: str,
                 session_id: str, idempotency_key: str, confirmed: bool):
        if not self.enabled or not getattr(self.model, "synthetic_only", False):
            raise HTTPException(503, "Brief generation unavailable")
        if (confirmed is not True or not isinstance(actor, str) or not actor
                or not isinstance(session_id, str) or not session_id
                or not isinstance(idempotency_key, str)
                or not 16 <= len(idempotency_key) <= 128
                or any(ord(char) < 33 or ord(char) > 126 for char in idempotency_key)):
            raise HTTPException(422, "Brief confirmation required")
        try:
            if (not isinstance(day, str) or date.fromisoformat(day).isoformat() != day
                    or day != datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
                    or timezone != "Asia/Shanghai"):
                raise ValueError
            ZoneInfo(timezone)
        except (TypeError, ValueError, ZoneInfoNotFoundError) as exc:
            raise HTTPException(422, "Invalid Brief target") from exc
        if (not isinstance(refs, list) or not 1 <= len(refs) <= 50
                or any(not _valid_source_reference(ref) for ref in refs)
                or len({(ref["kind"], ref["id"]) for ref in refs}) != len(refs)):
            raise HTTPException(422, "Invalid Brief sources")
        # Auth must run before any source or budget IO.
        self.permission_preflight()
        sources = self._read_sources(self.authority_factory(), refs)
        context = {"date": day, "timezone": timezone, "untrusted_sources": sources}
        run_body = {"input": json.dumps(context, ensure_ascii=False, sort_keys=True)}
        reservation = self.cost_gate.reserve(owner=actor, session_id=session_id,
                                             idempotency_key=idempotency_key,
                                             run_body=run_body, request_class="active")
        if reservation["replay"]:
            prior = reservation.get("brief_result")
            if isinstance(prior, dict) and prior.get("date") == day:
                fresh = self.authority_factory()
                snapshot = DailyBriefRecordReadStore(self.store.root).read(
                    day, timezone, source_verifier=fresh.verify,
                    source_permission_preflight=lambda _refs: self.permission_preflight())
                if (snapshot.found and snapshot.source_verification == "verified"
                        and snapshot.sha256 == prior.get("record_sha256")
                        and snapshot.record["brief_id"] == prior.get("brief_id")):
                    return {**prior, "status": "duplicate"}
            # A crashed model/write outcome must never trigger a second call.
            raise HTTPException(409, "Brief generation recovery required")
        try:
            self._bind_intent(reservation, day, timezone, refs)
        except Exception as exc:
            raise HTTPException(503, "Brief generation recovery required") from exc
        phase = "model_unknown"
        try:
            run_id = "brief-" + reservation["reservation_id"]
            result = self.model.generate(context, run_id=run_id)
            if (not isinstance(result, dict) or not isinstance(result.get("run_id"), str)
                    or result["run_id"] != run_id):
                raise ValueError("untrusted generation receipt")
            self.cost_gate.attach_run(reservation["reservation_id"], run_id)
            if not self.cost_gate.settle_completed(run_id, result.get("terminal")):
                raise ValueError("usage receipt unavailable")
            phase = "cost_settled_brief_unknown"
            candidate = {"date": day, "timezone": timezone,
                         "categories": result["categories"], "summary": result["summary"],
                         "source_refs": refs}
            def commit_verifier():
                fresh = self.authority_factory()
                def verify(ref):
                    self.permission_preflight()
                    return fresh.verify(ref)
                return verify
            # The store rechecks versions under its create-only commit lock.
            persisted = self.store.import_idempotent(
                candidate, source_verifier_factory=commit_verifier,
                idempotency_key=idempotency_key, actor=actor,
                request_sha256=_digest({"date": day, "timezone": timezone,
                                        "refs": refs, "actor": actor, "session": session_id}),
            )
            def save_receipt(state):
                rows = state.get("budget", {}).get("chat_runs", {})
                row = next((item for item in rows.values()
                            if item.get("reservation_id") == reservation["reservation_id"]), None)
                if row is None or row.get("status") != "settled":
                    raise ValueError("cost receipt changed")
                row["brief_result"] = persisted
                row["brief_recovery_state"] = "committed"
            self.cost_gate.state.update(save_receipt)
            return persisted
        except Exception as exc:
            try:
                self.cost_gate.mark_reservation_unknown(reservation["reservation_id"])
            except Exception:
                pass
            self._mark_recovery(reservation["reservation_id"], phase)
            raise HTTPException(503, "Brief generation recovery required") from exc
