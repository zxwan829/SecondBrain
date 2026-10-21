"""Fail-closed, single-use bridge for Hermes API Run tool approvals."""
import json
import hashlib
import hmac
import posixpath
import threading
import time

from fastapi import HTTPException


APPROVAL_PREFIX = "SECONDBRAIN_TERMINAL_APPROVAL_V1:"
FILE_WRITE_APPROVAL_PREFIX = "SECONDBRAIN_FILE_WRITE_APPROVAL_V1:"
FILE_WRITE_TOOLS = {"write_file", "patch"}
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

    def session_for_run(self, run_id, owner):
        """Return the registered Session only for the matching App owner."""
        with self._lock:
            self._prune()
            run = self._runs.get(run_id)
            if not run or run.get("owner") != owner:
                return None
            return run.get("session_id")

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
            if (not run or run["owner"] != owner or not isinstance(event, dict)
                    or event.get("event") != "approval.request" or event.get("run_id") != run_id):
                return None
            description = event.get("description")
            if not isinstance(request_id, str) or not request_id or len(request_id) > 256:
                return None
            if not isinstance(description, str):
                return None
            if description.startswith(APPROVAL_PREFIX):
                prefix, approved_tools = APPROVAL_PREFIX, {"terminal", "process_manage", "execute_code"}
            elif description.startswith(FILE_WRITE_APPROVAL_PREFIX):
                prefix, approved_tools = FILE_WRITE_APPROVAL_PREFIX, FILE_WRITE_TOOLS
            else:
                return None
            try:
                request = json.loads(description[len(prefix):])
            except (ValueError, TypeError):
                return None
            if (not isinstance(request, dict) or request.get("schema") != 1
                    or request.get("tool") not in approved_tools
                    or not isinstance(request.get("arguments"), dict)):
                return None
            tool, args = request["tool"], request["arguments"]
            if tool == "terminal":
                if (set(args) - {"command", "background", "timeout", "workdir", "pty", "notify",
                                 "heartbeat", "persist_on_release"}
                        or not isinstance(args.get("command"), str) or not args["command"].strip()
                        or not isinstance(args.get("workdir"), str) or not args["workdir"].startswith("/")):
                    return None
            elif tool == "execute_code":
                if (set(args) - {"code", "reset"} or not isinstance(args.get("code"), str)
                        or not args["code"].strip()
                        or ("reset" in args and not isinstance(args["reset"], bool))):
                    return None
            elif tool == "process_manage":
                if (set(args) - {"action", "session_id", "data", "timeout", "offset", "limit"}
                        or args.get("action") not in {"list", "poll", "log", "wait", "kill", "write",
                                                       "submit", "close", "handoff"}
                        or (args.get("action") != "list" and
                            (not isinstance(args.get("session_id"), str) or not args["session_id"]))):
                    return None
            elif tool in FILE_WRITE_TOOLS:
                allowed = {"path", "content"} if tool == "write_file" else {
                    "path", "old_string", "new_string", "replace_all", "mode", "patch"
                }
                if set(args) - allowed:
                    return None
                if tool == "write_file" and not isinstance(args.get("content"), str):
                    return None
                if tool == "patch" and (args.get("mode") == "patch" or "patch" in args
                                         or not isinstance(args.get("path"), str)
                                         or not isinstance(args.get("old_string"), str)
                                         or not isinstance(args.get("new_string"), str)
                                         or args.get("mode", "replace") != "replace"
                                         or ("replace_all" in args and not isinstance(args["replace_all"], bool))):
                    # Hermes' multi-file V4A patch form has no single explicit path and
                    # is intentionally blocked until every embedded target can be bound.
                    return None
                path = args.get("path")
                if (not isinstance(path, str) or not path.startswith("/")
                        or "\x00" in path or path != posixpath.normpath(path)):
                    return None
                if len(_canonical(request).encode("utf-8")) > 12_000:
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
        tool = record["request"]["tool"]
        command = args.get("command", args.get("input", args.get("code", "")))
        if tool in FILE_WRITE_TOOLS:
            command = f"{tool} → {args.get('path', '')}"
        elif not isinstance(command, str) or not command:
            command = _canonical({"tool": tool, "arguments": args})
        return {"event": "approval.request", "run_id": run_id,
                "session_id": record["session_id"], "approval_id": request_id,
                "tool": tool, "command": command, "arguments": args,
                "workdir": args.get("workdir") if tool == "terminal" else None,
                "command_sha256": record["digest"], "expires_at": record["expires_at"],
                "scope": ("One file mutation in this Hermes Run; the full arguments and target are digest-bound."
                          if tool in FILE_WRITE_TOOLS else
                          "Local Hermes terminal; executes with the Hermes worker's OS permissions.")}

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
