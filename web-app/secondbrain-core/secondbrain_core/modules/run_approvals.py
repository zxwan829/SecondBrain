"""Fail-closed, single-use bridge for Hermes API Run tool approvals."""
import hashlib
import hmac
import json
import threading
import time

from fastapi import HTTPException


APPROVAL_PREFIX = "SECONDBRAIN_TERMINAL_APPROVAL_V1:"
APPROVAL_TTL_SECONDS = 240
RUN_TTL_SECONDS = 3600


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class RunApprovalRegistry:
    """In-process run ownership and approval state; process restarts invalidate approval."""

    def __init__(self, *, clock=time.time):
        self._clock = clock
        self._lock = threading.RLock()
        self._runs = {}
        self._approvals = {}

    def register_run(self, run_id, session_id, owner):
        with self._lock:
            self._prune()
            self._runs[run_id] = {"session_id": session_id, "owner": owner,
                                  "expires_at": self._clock() + RUN_TTL_SECONDS}

    def _prune(self):
        now = self._clock()
        for key, record in list(self._approvals.items()):
            if record["expires_at"] <= now and record["state"] == "pending":
                record["state"] = "expired"
        for run_id, record in list(self._runs.items()):
            if record["expires_at"] <= now:
                self._runs.pop(run_id, None)
                for key in [key for key in self._approvals if key[0] == run_id]:
                    self._approvals.pop(key, None)

    def bind_event(self, run_id, owner, event):
        """Validate the exact Hermes approval event and return a UI-safe, digest-bound card."""
        request_id = event.get("request_id") if isinstance(event, dict) else None
        with self._lock:
            self._prune()
            run = self._runs.get(run_id)
            if not run or run["owner"] != owner:
                return None
            description = event.get("description")
            if not isinstance(request_id, str) or not request_id or len(request_id) > 256:
                return None
            if not isinstance(description, str) or not description.startswith(APPROVAL_PREFIX):
                return None
            try:
                request = json.loads(description[len(APPROVAL_PREFIX):])
            except (ValueError, TypeError):
                return None
            if (not isinstance(request, dict) or request.get("schema") != 1
                    or request.get("tool") not in {"terminal", "process_manage", "execute_code"}
                    or not isinstance(request.get("arguments"), dict)):
                return None
            if request["tool"] == "terminal" and (not isinstance(request["arguments"].get("command"), str)
                                                     or not request["arguments"]["command"].strip()):
                return None
            serialized = _canonical(request)
            digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
            key = (run_id, request_id)
            prior = self._approvals.get(key)
            if prior:
                if prior["digest"] != digest or prior["session_id"] != run["session_id"]:
                    prior["state"] = "invalid"
                    return None
                if prior["state"] != "pending":
                    return None
                return self._card(run_id, request_id, prior)
            record = {"session_id": run["session_id"], "owner": owner, "digest": digest,
                      "request": request, "state": "pending",
                      "expires_at": min(self._clock() + APPROVAL_TTL_SECONDS, run["expires_at"])}
            self._approvals[key] = record
            return self._card(run_id, request_id, record)

    @staticmethod
    def _card(run_id, request_id, record):
        args = record["request"]["arguments"]
        command = args.get("command", args.get("input", args.get("code", "")))
        if not isinstance(command, str) or not command:
            command = _canonical({"tool": record["request"]["tool"], "arguments": args})
        return {"event": "approval.request", "run_id": run_id,
                "session_id": record["session_id"], "approval_id": request_id,
                "tool": record["request"]["tool"], "command": command, "arguments": args,
                "command_sha256": record["digest"], "expires_at": record["expires_at"],
                "scope": "Local Hermes terminal; executes with the Hermes worker's OS permissions."}

    def begin_resolution(self, *, run_id, session_id, request_id, owner, digest, choice):
        if choice not in {"once", "deny"}:
            raise HTTPException(status_code=400, detail="Only approve once or deny is supported")
        with self._lock:
            self._prune()
            run = self._runs.get(run_id)
            record = self._approvals.get((run_id, request_id))
            if not run or not record:
                raise HTTPException(status_code=404, detail="Approval is unavailable")
            if run["owner"] != owner or record["owner"] != owner or run["session_id"] != session_id or record["session_id"] != session_id:
                raise HTTPException(status_code=404, detail="Approval is unavailable")
            if record["expires_at"] <= self._clock() or record["state"] != "pending":
                raise HTTPException(status_code=409, detail="Approval is expired or already resolved")
            if not isinstance(digest, str) or not hmac.compare_digest(record["digest"], digest):
                raise HTTPException(status_code=409, detail="Approval command has changed")
            record["state"] = "resolving"
            return dict(record)

    def finish_resolution(self, run_id, request_id, succeeded):
        with self._lock:
            record = self._approvals.get((run_id, request_id))
            if record and record["state"] == "resolving":
                record["state"] = "resolved" if succeeded else "failed_closed"

    def pending_ids(self, run_id):
        with self._lock:
            self._prune()
            return [request_id for (rid, request_id), record in self._approvals.items()
                    if rid == run_id and record["state"] == "pending"]

    def cancel_pending(self, run_id):
        """Atomically consume unapproved requests before a user stops the run."""
        with self._lock:
            pending = []
            for (rid, request_id), record in self._approvals.items():
                if rid == run_id and record["state"] == "pending":
                    record["state"] = "resolving"
                    pending.append(request_id)
            return pending
