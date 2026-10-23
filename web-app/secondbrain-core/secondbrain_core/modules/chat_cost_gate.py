"""Opt-in Core-side Chat cost admission using Organizer's durable state lock.

The current Hermes v0.22.2 Runs contract does not advertise the required
enforced per-run cost envelope. Therefore the live gate remains disabled by
default and refuses admission when enabled against an incompatible Hermes.
Local amounts are estimates, never provider-enforced spend caps.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from .organizer_engine import OrganizerState, budget_periods, iso


MAX_POLICY_BYTES = 64 * 1024
MAX_LEDGER_RECORDS = 20_000
SAFE_POLICY_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")


def _json_digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Chat cost policy contains duplicate JSON keys")
        result[key] = value
    return result


def _microcny(tokens: int, price_microcny_per_million: int) -> int:
    return math.ceil(tokens * price_microcny_per_million / 1_000_000)


@dataclass(frozen=True)
class ChatCostRoute:
    provider: str
    model: str
    input_microcny_per_million: int
    output_microcny_per_million: int

    @property
    def key(self) -> str:
        return f"{self.provider}/{self.model}"


@dataclass(frozen=True)
class ChatCostPolicy:
    policy_id: str
    primary: ChatCostRoute
    routes: tuple[ChatCostRoute, ...]
    price_source: str
    price_version: str
    price_valid_until: str
    max_input_tokens: int
    max_output_tokens: int
    max_model_calls: int
    passive_daily_microcny: int
    passive_monthly_microcny: int
    active_daily_microcny: int
    active_monthly_microcny: int

    @classmethod
    def parse(cls, value: Any) -> "ChatCostPolicy":
        required = {
            "policy_id", "primary_route", "allowed_routes", "price_source", "price_version", "price_valid_until",
            "max_input_tokens", "max_output_tokens", "max_model_calls",
            "passive_daily_microcny", "passive_monthly_microcny",
            "active_daily_microcny", "active_monthly_microcny",
        }
        if not isinstance(value, dict) or set(value) != required:
            raise ValueError("Chat cost policy has an invalid schema")
        if (not isinstance(value["policy_id"], str) or not SAFE_POLICY_ID.fullmatch(value["policy_id"])
                or not isinstance(value["price_source"], str) or not value["price_source"].strip()
                or len(value["price_source"]) > 240
                or not isinstance(value["price_version"], str) or not value["price_version"].strip()
                or len(value["price_version"]) > 80
                or not isinstance(value["price_valid_until"], str)):
            raise ValueError("Chat cost policy identity or price provenance is invalid")
        try:
            price_valid_until = datetime.fromisoformat(value["price_valid_until"].replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("Chat cost price expiry is invalid") from exc
        if price_valid_until.tzinfo is None:
            raise ValueError("Chat cost price expiry must include a timezone")

        def positive_int(key: str, *, allow_zero: bool = False, maximum: int = 1_000_000_000) -> int:
            item = value[key]
            if type(item) is not int or item < (0 if allow_zero else 1) or item > maximum:
                raise ValueError("Chat cost policy limit is invalid")
            return item

        for key in ("max_input_tokens", "max_output_tokens"):
            positive_int(key, maximum=2_000_000)
        positive_int("max_model_calls", maximum=100)
        for key in ("passive_daily_microcny", "passive_monthly_microcny",
                    "active_daily_microcny", "active_monthly_microcny"):
            positive_int(key, allow_zero=True)
        if value["max_input_tokens"] > 1_000_000 or value["max_output_tokens"] > 1_000_000:
            raise ValueError("Chat cost token envelope is too large")
        rows = value["allowed_routes"]
        if not isinstance(rows, list) or not rows or len(rows) > 32:
            raise ValueError("Chat cost policy requires a bounded route allowlist")
        routes = []
        seen = set()
        for row in rows:
            if not isinstance(row, dict) or set(row) != {
                "provider", "model", "input_microcny_per_million", "output_microcny_per_million"
            }:
                raise ValueError("Chat cost route has an invalid schema")
            provider, model = row["provider"], row["model"]
            if (not isinstance(provider, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", provider)
                    or not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9_./:-]{1,160}", model)):
                raise ValueError("Chat cost route identity is invalid")
            input_rate, output_rate = row["input_microcny_per_million"], row["output_microcny_per_million"]
            if any(type(rate) is not int or rate <= 0 or rate > 10**15 for rate in (input_rate, output_rate)):
                raise ValueError("Chat cost route price is invalid")
            route = ChatCostRoute(provider, model, input_rate, output_rate)
            if route.key in seen:
                raise ValueError("Chat cost route is duplicated")
            seen.add(route.key)
            routes.append(route)
        primary_data = value["primary_route"]
        if not isinstance(primary_data, dict) or set(primary_data) != {"provider", "model"}:
            raise ValueError("Chat cost primary route is invalid")
        primary_key = f"{primary_data['provider']}/{primary_data['model']}"
        primary = next((route for route in routes if route.key == primary_key), None)
        if primary is None:
            raise ValueError("Chat cost primary route is not allowlisted")
        return cls(
            value["policy_id"], primary, tuple(routes), value["price_source"].strip(),
            value["price_version"].strip(), value["price_valid_until"],
            value["max_input_tokens"], value["max_output_tokens"],
            value["max_model_calls"], value["passive_daily_microcny"],
            value["passive_monthly_microcny"], value["active_daily_microcny"],
            value["active_monthly_microcny"],
        )

    @property
    def digest(self) -> str:
        return _json_digest({
            "policy_id": self.policy_id,
            "primary_route": self.primary.key,
            "allowed_routes": [
                {"provider": row.provider, "model": row.model,
                 "input_microcny_per_million": row.input_microcny_per_million,
                 "output_microcny_per_million": row.output_microcny_per_million}
                for row in self.routes
            ],
            "price_source": self.price_source,
            "price_version": self.price_version,
            "price_valid_until": self.price_valid_until,
            "max_input_tokens": self.max_input_tokens,
            "max_output_tokens": self.max_output_tokens,
            "max_model_calls": self.max_model_calls,
            "limits": [self.passive_daily_microcny, self.passive_monthly_microcny,
                       self.active_daily_microcny, self.active_monthly_microcny],
        })

    @property
    def reservation_microcny(self) -> int:
        # Reserve each configured maximum for every allowed paid model call,
        # using the most expensive primary/fallback price in the approved set.
        input_rate = max(route.input_microcny_per_million for route in self.routes)
        output_rate = max(route.output_microcny_per_million for route in self.routes)
        return (_microcny(self.max_input_tokens * self.max_model_calls, input_rate)
                + _microcny(self.max_output_tokens * self.max_model_calls, output_rate))

    def envelope(self) -> dict[str, Any]:
        return {
            "version": 1,
            "max_input_tokens": self.max_input_tokens,
            "max_output_tokens": self.max_output_tokens,
            "max_model_calls": self.max_model_calls,
            "allowed_routes": [{"provider": route.provider, "model": route.model} for route in self.routes],
        }


class ChatCostGate:
    """Durable admission and reconciliation over OrganizerState's flock/atomic store."""

    def __init__(self, state: OrganizerState, policy: ChatCostPolicy):
        if not isinstance(state, OrganizerState):
            raise ValueError("Chat cost gate requires Organizer's durable state store")
        self.state = state
        self.policy = policy

    @classmethod
    def from_environment(cls, state: OrganizerState) -> "ChatCostGate | None":
        raw_enabled = os.environ.get("SB_CHAT_COST_GATE_ENABLED", "false").strip().lower()
        if raw_enabled not in {"true", "false"}:
            raise RuntimeError("SB_CHAT_COST_GATE_ENABLED must be true or false")
        if raw_enabled != "true":
            return None
        path = os.environ.get("SB_CHAT_COST_POLICY_FILE", "").strip()
        if not path or not os.path.isabs(path):
            raise RuntimeError("An absolute Chat cost policy file is required when the gate is enabled")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        fd = os.open(path, flags)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_mode & 0o077 or info.st_size > MAX_POLICY_BYTES):
                raise RuntimeError("Chat cost policy must be a private, bounded Core-owned file")
            payload = os.read(fd, MAX_POLICY_BYTES + 1)
        finally:
            os.close(fd)
        if len(payload) > MAX_POLICY_BYTES:
            raise RuntimeError("Chat cost policy is too large")
        try:
            policy = ChatCostPolicy.parse(json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_object))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise RuntimeError("Chat cost policy is invalid") from exc
        return cls(state, policy)

    def require_hermes_envelope(self, capabilities: Any) -> None:
        features = capabilities.get("features") if isinstance(capabilities, dict) else None
        contract = features.get("run_cost_envelope") if isinstance(features, dict) else None
        if (not isinstance(contract, dict) or contract.get("version") != 1
                or contract.get("enforced") is not True
                or type(contract.get("max_input_tokens")) is not int
                or type(contract.get("max_output_tokens")) is not int
                or type(contract.get("max_model_calls")) is not int
                or contract.get("route_allowlist_enforced") is not True
                or contract["max_input_tokens"] < self.policy.max_input_tokens
                or contract["max_output_tokens"] < self.policy.max_output_tokens
                or contract["max_model_calls"] < self.policy.max_model_calls):
            raise HTTPException(
                status_code=503,
                detail={"code": "chat_cost_envelope_unavailable",
                        "message": "Hermes has no verified request cost envelope; the Run was not sent."},
            )
        expires = datetime.fromisoformat(self.policy.price_valid_until.replace("Z", "+00:00"))
        if datetime.now(timezone.utc) >= expires.astimezone(timezone.utc):
            raise HTTPException(
                status_code=503,
                detail={"code": "chat_cost_price_expired",
                        "message": "Chat pricing policy is expired; the Run was not sent."},
            )

    def bind_envelope(self, run_body: dict[str, Any]) -> dict[str, Any]:
        return {**run_body, "provider": self.policy.primary.provider,
                "model": self.policy.primary.model, "cost_envelope": self.policy.envelope()}

    @staticmethod
    def require_replay_window(reservation: dict[str, Any], *,
                              now: datetime | None = None) -> None:
        if not reservation.get("replay"):
            return
        try:
            created = datetime.fromisoformat(str(reservation["created_at"]).replace("Z", "+00:00"))
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=503, detail={"code": "chat_cost_recovery_required"}) from exc
        now = now or datetime.now(timezone.utc)
        # Hermes documents a 24-hour idempotency retention window. Use a
        # conservative window from Core's original reservation timestamp.
        if now.astimezone(timezone.utc) >= created.astimezone(timezone.utc) + timedelta(hours=24):
            raise HTTPException(
                status_code=409,
                detail={"code": "chat_cost_recovery_required",
                        "message": "Run 的 Hermes 幂等保留窗口已过；禁止自动或显式重发，需人工核对。"},
            )

    def reserve(self, *, owner: str, session_id: str, idempotency_key: str,
                run_body: dict[str, Any], request_class: str = "passive",
                now: datetime | None = None) -> dict[str, Any]:
        if request_class not in {"passive", "active"}:
            raise HTTPException(status_code=503, detail={"code": "chat_cost_class_invalid"})
        if not owner or not session_id or not idempotency_key:
            raise HTTPException(status_code=400, detail={"code": "chat_cost_identity_required"})
        now = now or datetime.now(timezone.utc)
        input_text = run_body.get("input") if isinstance(run_body, dict) else None
        if not isinstance(input_text, str):
            raise HTTPException(status_code=503, detail={"code": "chat_cost_input_unavailable"})
        input_estimate = math.ceil(len(input_text.encode("utf-8")) / 2)
        if input_estimate > self.policy.max_input_tokens:
            raise HTTPException(status_code=413,
                                detail={"code": "chat_cost_input_envelope_exceeded",
                                        "message": "请求超过本地费用预检输入封套；Run 未发送。"})
        day_key, month_key = budget_periods(now)
        scope = hashlib.sha256(f"{owner}\0{session_id}\0{idempotency_key}".encode()).hexdigest()
        run_digest = _json_digest({"body": run_body, "request_class": request_class,
                                   "policy_digest": self.policy.digest})
        amount = self.policy.reservation_microcny
        failure: list[HTTPException] = []
        result: list[dict[str, Any]] = []

        def mutate(state):
            budget = state.setdefault("budget", {})
            rows = budget.setdefault("chat_runs", {})
            existing = rows.get(scope)
            if existing:
                if existing.get("request_digest") != run_digest:
                    failure.append(HTTPException(status_code=409,
                                                 detail={"code": "chat_cost_idempotency_conflict",
                                                         "message": "Idempotency-Key was already used for a different request."}))
                else:
                    result.append({**existing, "replay": True})
                return
            if len(rows) >= MAX_LEDGER_RECORDS:
                failure.append(HTTPException(status_code=503,
                                             detail={"code": "chat_cost_ledger_full",
                                                     "message": "Chat cost ledger requires reconciliation."}))
                return
            daily_limit = (self.policy.passive_daily_microcny if request_class == "passive"
                           else self.policy.active_daily_microcny)
            monthly_limit = (self.policy.passive_monthly_microcny if request_class == "passive"
                             else self.policy.active_monthly_microcny)
            daily_used = sum(int(row["accounted_microcny"]) for row in rows.values()
                             if row.get("request_class") == request_class and row.get("day") == day_key)
            monthly_used = sum(int(row["accounted_microcny"]) for row in rows.values()
                               if row.get("request_class") == request_class and row.get("month") == month_key)
            if daily_used + amount > daily_limit or monthly_used + amount > monthly_limit:
                required_addition = max(daily_used + amount - daily_limit,
                                        monthly_used + amount - monthly_limit, 0)
                failure.append(HTTPException(
                    status_code=429,
                    detail={"code": "chat_cost_budget_exceeded",
                            "message": ("主动额度已用完，任务未启动。" if request_class == "active"
                                        else "被动额度不足；请求未启动，可选择稍后或明确追加额度。"),
                            "estimated_microcny": amount,
                            "required_addition_microcny": required_addition,
                            "estimate_basis": "local pre-reservation estimate; not an invoice or provider hard limit"},
                ))
                return
            row = {
                "reservation_id": uuid.uuid4().hex, "idempotency_scope_sha256": scope,
                "request_digest": run_digest, "owner": owner, "session_id": session_id,
                "request_class": request_class, "day": day_key, "month": month_key,
                "status": "reserved", "run_id": None, "created_at": iso(now),
                "accounted_microcny": amount, "reserved_microcny": amount,
                "actual_microcny": None, "runtime": None, "usage": None,
                "policy_id": self.policy.policy_id, "policy_digest": self.policy.digest,
                "price_source": self.policy.price_source, "price_version": self.policy.price_version,
                "estimate_basis": "maximum configured local estimate; not a provider cap or invoice",
            }
            rows[scope] = row
            result.append({**row, "replay": False})

        self.state.update(mutate)
        if failure:
            raise failure[0]
        return result[0]

    def attach_run(self, reservation_id: str, run_id: str) -> None:
        def mutate(state):
            rows = state.get("budget", {}).get("chat_runs", {})
            row = next((item for item in rows.values() if item.get("reservation_id") == reservation_id), None)
            if row:
                if row.get("run_id") not in (None, run_id):
                    row["status"] = "unknown"
                else:
                    row["run_id"] = run_id
                    if row.get("status") == "reserved":
                        row["status"] = "started"
        self.state.update(mutate)

    def mark_unknown(self, run_id: str) -> None:
        def mutate(state):
            rows = state.get("budget", {}).get("chat_runs", {})
            for row in rows.values():
                if row.get("run_id") == run_id and row.get("status") in {"reserved", "started"}:
                    row["status"] = "unknown"
                    row["resolved_at"] = iso()
        self.state.update(mutate)

    def mark_reservation_unknown(self, reservation_id: str) -> None:
        def mutate(state):
            rows = state.get("budget", {}).get("chat_runs", {})
            for row in rows.values():
                if row.get("reservation_id") == reservation_id and row.get("status") in {"reserved", "started"}:
                    row["status"] = "unknown"
                    row["resolved_at"] = iso()
        self.state.update(mutate)

    def settle_completed(self, run_id: str, event: Any) -> bool:
        """Settle only a matching eligible Run with a complete bounded terminal receipt."""
        if not isinstance(run_id, str) or not run_id:
            return False
        runtime = event.get("runtime") if isinstance(event, dict) else None
        usage = event.get("usage") if isinstance(event, dict) else None
        route = None
        valid = (isinstance(event, dict) and event.get("event") == "run.completed"
                 and event.get("run_id", run_id) == run_id
                 and isinstance(runtime, dict) and isinstance(usage, dict))
        if valid:
            provider, model = runtime.get("provider"), runtime.get("model")
            if isinstance(provider, str) and isinstance(model, str):
                route = next((item for item in self.policy.routes
                              if item.provider == provider and item.model == model), None)
        input_tokens = usage.get("input_tokens") if isinstance(usage, dict) else None
        output_tokens = usage.get("output_tokens") if isinstance(usage, dict) else None
        model_calls = usage.get("model_calls") if isinstance(usage, dict) else None
        if isinstance(usage, dict):
            # Conflicting aliases are not a trustworthy terminal usage report.
            if ("prompt_tokens" in usage and usage["prompt_tokens"] != input_tokens
                    or "completion_tokens" in usage and usage["completion_tokens"] != output_tokens):
                valid = False
        valid = (valid and route is not None
                 and type(input_tokens) is int and type(output_tokens) is int
                 and type(model_calls) is int and 1 <= model_calls <= self.policy.max_model_calls
                 and 0 <= input_tokens <= self.policy.max_input_tokens * model_calls
                 and 0 <= output_tokens <= self.policy.max_output_tokens * model_calls)
        amount = (_microcny(input_tokens, route.input_microcny_per_million)
                  + _microcny(output_tokens, route.output_microcny_per_million)) if valid else None
        transitioned = [False]

        def mutate(state):
            rows = state.get("budget", {}).get("chat_runs", {})
            row = next((item for item in rows.values()
                        if item.get("run_id") == run_id), None)
            if row is None or row.get("status") not in {"reserved", "started", "unknown"}:
                return
            # Preserve the full reservation on any integrity mismatch. A prior
            # failure/interrupt or ambiguous transport must not free the budget.
            eligible = (valid and row.get("policy_id") == self.policy.policy_id
                        and row.get("policy_digest") == self.policy.digest
                        and row.get("price_version") == self.policy.price_version
                        and row.get("price_source") == self.policy.price_source
                        and type(row.get("reserved_microcny")) is int
                        and amount <= row["reserved_microcny"])
            if not eligible:
                row["status"] = "unknown"
                row["resolved_at"] = iso()
                return
            row["status"] = "settled"
            row["actual_microcny"] = amount
            row["accounted_microcny"] = amount
            row["runtime"] = {"provider": route.provider, "model": route.model}
            row["usage"] = {"input_tokens": input_tokens, "output_tokens": output_tokens,
                            "model_calls": model_calls}
            row["over_reservation"] = False
            row["estimate_basis"] = "trusted Hermes runtime/usage priced locally; not an invoice or provider cap"
            row["resolved_at"] = iso()
            transitioned[0] = True

        self.state.update(mutate)
        return transitioned[0]

    def finish_stream(self, run_id: str, terminal_seen: bool) -> None:
        if not terminal_seen:
            self.mark_unknown(run_id)

    def rows(self) -> list[dict[str, Any]]:
        return list(self.state.read().get("budget", {}).get("chat_runs", {}).values())
