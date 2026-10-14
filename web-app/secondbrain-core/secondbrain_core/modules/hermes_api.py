"""Server-only client for the Hermes API server. Never expose its bearer key."""
import json
import os
import re
import stat

import httpx
from fastapi import HTTPException


_SAFE_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,256}$")


class HermesAPI:
    def __init__(self, base_url=None, api_key=None, transport=None):
        self.base_url = (base_url or os.environ.get("SB_HERMES_API_URL", "")).rstrip("/")
        key_file = os.environ.get("SB_HERMES_API_KEY_FILE", "")
        if api_key is not None:
            self.api_key = api_key
        elif key_file:
            if not os.path.isabs(key_file):
                raise ValueError("Hermes API key file path must be absolute")
            fd = os.open(key_file, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.geteuid():
                    raise ValueError("Hermes API key file must be private and owned by the App UID")
                with os.fdopen(fd, "rb", closefd=False) as stream:
                    self.api_key = stream.read(4097).strip().decode("utf-8")
            finally:
                os.close(fd)
        else:
            self.api_key = os.environ.get("SB_HERMES_API_KEY", "")
        if self.base_url and not self.base_url.startswith(("http://", "https://")):
            raise ValueError("Hermes API URL must use HTTP or HTTPS")
        self.transport = transport

    @property
    def configured(self):
        return bool(self.base_url and self.api_key)

    def _client(self, timeout=30):
        if not self.configured:
            raise HTTPException(status_code=503, detail="Hermes API is not configured on the server")
        return httpx.AsyncClient(base_url=self.base_url, headers={"Authorization": f"Bearer {self.api_key}"},
                                 timeout=timeout, follow_redirects=False, transport=self.transport)

    @staticmethod
    def _safe_id(value):
        if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
            raise HTTPException(status_code=400, detail="Invalid Hermes identifier")
        return value

    async def json_request(self, method, path, *, params=None, body=None):
        try:
            async with self._client() as client:
                response = await client.request(method, path, params=params, json=body)
        except HTTPException:
            raise
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="Hermes API unavailable") from exc
        if response.status_code >= 400:
            # Do not return upstream response bodies: they may include internal details.
            raise HTTPException(status_code=502 if response.status_code >= 500 else response.status_code,
                                detail=f"Hermes API returned HTTP {response.status_code}")
        if response.status_code == 204 or not response.content:
            return {"status": "ok"}
        try:
            return response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=502, detail="Hermes API returned invalid JSON") from exc

    async def list_sessions(self, limit=50, offset=0):
        payload = await self.json_request("GET", "/api/sessions", params={"limit": limit, "offset": offset})
        rows = payload.get("data", payload.get("sessions", [])) if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise HTTPException(status_code=502, detail="Hermes returned invalid session data")
        return {"sessions": [self._session(row) for row in rows if isinstance(row, dict)],
                "pagination": {key: payload[key] for key in ("limit", "offset", "has_more")
                               if key in payload} if isinstance(payload, dict) else {}}

    async def create_session(self, body):
        return self._session_result(await self.json_request("POST", "/api/sessions", body=body))

    async def get_session(self, session_id):
        return self._session_result(await self.json_request("GET", f"/api/sessions/{self._safe_id(session_id)}"))

    async def get_messages(self, session_id):
        payload = await self.json_request("GET", f"/api/sessions/{self._safe_id(session_id)}/messages",
                                          params={"inline_images": "false"})
        rows = payload.get("data", payload.get("messages", [])) if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise HTTPException(status_code=502, detail="Hermes returned invalid message history")
        messages = []
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            content = row.get("content", row.get("text", ""))
            if isinstance(content, list):
                content = "\n".join(part.get("text", "") for part in content
                                    if isinstance(part, dict) and isinstance(part.get("text"), str))
            messages.append({"id": str(row.get("id", index)), "role": row.get("role", ""),
                             "text": content if isinstance(content, str) else ""})
        return {"messages": messages}

    async def fork_session(self, session_id, body):
        return self._session_result(await self.json_request("POST", f"/api/sessions/{self._safe_id(session_id)}/fork", body=body))

    @staticmethod
    def _session(row):
        return {"session_id": str(row.get("id", row.get("session_id", ""))),
                "title": row.get("title", ""), "updated_at": row.get("updated_at")}

    @classmethod
    def _session_result(cls, payload):
        row = payload.get("session", payload) if isinstance(payload, dict) else {}
        if not isinstance(row, dict) or not (row.get("id") or row.get("session_id")):
            raise HTTPException(status_code=502, detail="Hermes returned an invalid session")
        return cls._session(row)

    async def patch_session(self, session_id, body):
        return await self.json_request("PATCH", f"/api/sessions/{self._safe_id(session_id)}", body=body)

    async def delete_session(self, session_id):
        return await self.json_request("DELETE", f"/api/sessions/{self._safe_id(session_id)}")

    async def capabilities(self):
        return await self.json_request("GET", "/v1/capabilities")

    async def start_run(self, body, idempotency_key):
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        try:
            async with self._client() as client:
                response = await client.post("/v1/runs", json=body, headers=headers)
        except HTTPException:
            raise
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="Hermes API unavailable") from exc
        if response.status_code >= 400:
            raise HTTPException(status_code=502 if response.status_code >= 500 else response.status_code,
                                detail=f"Hermes API returned HTTP {response.status_code}")
        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=502, detail="Hermes returned invalid run data") from exc
        run_id = payload.get("run_id") if isinstance(payload, dict) else None
        if not isinstance(run_id, str) or not run_id:
            raise HTTPException(status_code=502, detail="Hermes returned an invalid run identifier")
        return {"run_id": run_id, "status": payload.get("status", "accepted")}

    async def get_run(self, run_id):
        payload = await self.json_request("GET", f"/v1/runs/{self._safe_id(run_id)}")
        if not isinstance(payload, dict):
            raise HTTPException(status_code=502, detail="Hermes returned invalid run status")
        return {key: payload[key] for key in ("run_id", "status", "error", "output", "created_at", "updated_at")
                if key in payload}

    async def stream_run(self, run_id):
        run_id = self._safe_id(run_id)
        client = self._client(timeout=None)
        request = client.build_request("GET", f"/v1/runs/{run_id}/events", headers={"Accept": "text/event-stream"})
        try:
            response = await client.send(request, stream=True)
            if response.status_code >= 400:
                await response.aread()
                await response.aclose()
                await client.aclose()
                raise HTTPException(status_code=502 if response.status_code >= 500 else response.status_code,
                                    detail=f"Hermes API returned HTTP {response.status_code}")
        except HTTPException:
            raise
        except httpx.HTTPError as exc:
            await client.aclose()
            raise HTTPException(status_code=502, detail="Hermes event stream unavailable") from exc

        async def chunks():
            try:
                buffer = ""
                async for chunk in response.aiter_text():
                    buffer += chunk
                    frames = re.split(r"\r?\n\r?\n", buffer)
                    buffer = frames.pop() or ""
                    for frame in frames:
                        normalized = self._normalize_event_frame(frame)
                        if normalized:
                            yield normalized.encode("utf-8")
                if buffer.strip():
                    normalized = self._normalize_event_frame(buffer)
                    if normalized:
                        yield normalized.encode("utf-8")
            finally:
                await response.aclose()
                await client.aclose()
        return chunks()

    @staticmethod
    def _normalize_event_frame(frame):
        data = [line[5:].lstrip() for line in frame.splitlines() if line.startswith("data:")]
        if not data:
            return ""
        raw = "\n".join(data)
        try:
            payload = json.loads(raw)
        except (ValueError, json.JSONDecodeError):
            payload = {"event": "message", "text": raw}
        if not isinstance(payload, dict):
            payload = {"event": "message", "data": payload}
        event = payload.get("event")
        if not isinstance(event, str):
            # Older compatible event-stream implementations may use the SSE event field.
            event = next((line[6:].strip() for line in frame.splitlines() if line.startswith("event:")), "message")
            payload["event"] = event
        return f"data: {json.dumps(payload, separators=(',', ':'), ensure_ascii=False)}\n\n"

    async def stop_run(self, run_id):
        return await self.json_request("POST", f"/v1/runs/{self._safe_id(run_id)}/stop", body={})
