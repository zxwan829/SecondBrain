"""Synthetic Gateway pipeline smoke for the pinned Hermes v0.22.2 image.

Run inside the built image with no network, credentials, account, or model. The
fake Core response exercises the plugin's signed-receipt path; Core's actual
authorization and persistence are covered by the Core synthetic integration suite.
"""
import asyncio
import hashlib
import hmac
import importlib.util
import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from urllib.error import HTTPError


KEY = b"synthetic-weixin-image-smoke-key"
HOOK = "post_gateway_admission"
PLUGIN = Path("/opt/hermes/plugins/secondbrain-weixin-inbox/__init__.py")


class Response:
    status = 202

    def __init__(self, body, signature):
        self._body = body
        self.headers = {"X-SecondBrain-Receipt-Signature": signature}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, limit=-1):
        return self._body[:limit]


def main():
    os.environ["SB_WEIXIN_CORE_INBOX_URL"] = "http://synthetic-core.invalid/api/internal/v1/channel-events"
    with tempfile.TemporaryDirectory(prefix="weixin-gateway-smoke-") as home:
        os.environ["HERMES_HOME"] = home
        Path(home).mkdir(exist_ok=True)
        key_file = Path(home) / "weixin-hmac-key"
        key_file.write_bytes(KEY + b"\n")
        key_file.chmod(0o600)
        os.environ.pop("SB_WEIXIN_CORE_INBOX_HMAC_KEY", None)
        os.environ["SB_WEIXIN_CORE_INBOX_HMAC_KEY_FILE"] = str(key_file)

        from gateway.config import GatewayConfig, Platform, PlatformConfig
        from gateway.platforms.event import MessageEvent
        from gateway.run import GatewayRunner
        from gateway.session import SessionSource
        from hermes_cli.plugins import get_plugin_manager

        spec = importlib.util.spec_from_file_location("secondbrain_weixin_smoke", PLUGIN)
        plugin = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(plugin)

        saved = {}
        def fake_core(request, timeout):
            raw = request.data
            body = json.loads(raw)
            supplied = next((value for name, value in request.header_items()
                             if name.lower() == "x-secondbrain-signature"), None)
            expected = hmac.new(KEY, raw, hashlib.sha256).hexdigest()
            assert hmac.compare_digest(supplied or "", expected), "plugin request HMAC mismatch"
            sender = body["source"]["user_id"]
            if sender != "synthetic-allowed-user":
                raise HTTPError(request.full_url, 403, "forbidden", {}, None)
            event_id = body["source_event_id"]
            inbox_id = saved.setdefault(event_id, "synthetic-inbox-" + event_id)
            status = "processing"
            receipt = "secondbrain-weixin-receipt-v1\0{}\0{}\0{}\0{}".format(
                event_id, inbox_id, status, hashlib.sha256(raw).hexdigest())
            signature = hmac.new(KEY, receipt.encode(), hashlib.sha256).hexdigest()
            return Response(json.dumps({"inbox_id": inbox_id, "status": status}).encode(), signature)

        plugin.urlopen = fake_core
        manager = get_plugin_manager()
        manager._discovered = True
        manager._hooks[HOOK] = [plugin._post_gateway_admission]

        runner = object.__new__(GatewayRunner)
        runner.config = GatewayConfig(platforms={Platform.WEIXIN: PlatformConfig(enabled=True)})
        adapter = SimpleNamespace(send=AsyncMock())
        runner.adapters = {Platform.WEIXIN: adapter}
        runner.pairing_store = MagicMock()
        runner.session_store = MagicMock()
        runner._is_user_authorized_for_source = lambda _source: True
        runner._admit_bot_message_for_source = lambda _source: True
        runner._delivery_adapter_for = lambda _source: adapter
        runner._intake_adapter_for = lambda _source: adapter
        runner._rescue_orphaned_overflow = lambda _key, _adapter: None
        runner._enqueue_fifo = MagicMock()
        runner._handle_message_with_agent = AsyncMock(return_value="synthetic-agent-reply")
        runner._run_post_turn_hooks = AsyncMock()

        def send(text, message_id, sender="synthetic-allowed-user"):
            source = SessionSource(
                platform=Platform.WEIXIN, user_id=sender, chat_id="synthetic-chat",
                user_name="synthetic-user", chat_type="dm",
            )
            event = MessageEvent(text=text, message_id=message_id, source=source)
            return asyncio.run(runner._handle_message(event))

        ordinary = send("你好", "chat-1")
        assert ordinary == "synthetic-agent-reply", ordinary
        assert runner._handle_message_with_agent.await_count == 1
        assert saved == {}, "ordinary chat must not write to Inbox"

        first = send("收录：合成备注", "capture-1")
        replay = send("收录：合成备注", "capture-1")
        assert first == "已收录到 Inbox。", first
        assert replay == first, replay
        assert len(saved) == 1, saved
        assert runner._handle_message_with_agent.await_count == 1

        denied = send("收录：不可授权", "capture-denied", sender="unknown-user")
        assert isinstance(denied, str) and "保存失败" in denied, denied
        assert "capture-denied" not in saved
        assert runner._handle_message_with_agent.await_count == 1

        os.environ["SB_WEIXIN_CORE_INBOX_HMAC_KEY"] = KEY.decode()
        ambiguous = send("收录：配置歧义", "capture-ambiguous")
        assert isinstance(ambiguous, str) and "保存失败" in ambiguous, ambiguous
        assert "capture-ambiguous" not in saved
        os.environ.pop("SB_WEIXIN_CORE_INBOX_HMAC_KEY", None)
        key_file.unlink()
        missing = send("收录：凭据缺失", "capture-missing")
        assert isinstance(missing, str) and "保存失败" in missing, missing
        assert "capture-missing" not in saved

    print("WEIXIN_GATEWAY_SYNTHETIC_PASS")


if __name__ == "__main__":
    main()
