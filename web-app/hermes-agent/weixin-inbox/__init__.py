"""Minimal Hermes v0.22.2 Weixin DM to SecondBrain Inbox adapter.

The Gateway's hook is fail-open. This plugin therefore returns ``handled`` for
an explicit save command even when Core refuses or cannot be reached, preventing
the model from inventing a successful save. Ordinary chat is left to Hermes.
"""
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PREFIXES = ("收录：", "收录:")
MAX_CAPTURE_CHARS = 20_000


def _capture_text(text):
    if not isinstance(text, str):
        return None
    for prefix in PREFIXES:
        if text.startswith(prefix):
            value = text[len(prefix):].strip()
            return value
    return None


def _handle_post_gateway_admission(*, platform="", source=None, message_id=None,
                                   text="", **_kwargs):
    source = source if isinstance(source, dict) else {}
    if platform != "weixin" or source.get("platform") != "weixin":
        return None
    capture_text = _capture_text(text)
    if capture_text is None:
        return None
    if source.get("chat_type") != "dm":
        return {"action": "handled", "reply": "收录功能目前仅支持微信私聊；未写入 Inbox。"}
    if not capture_text:
        return {"action": "handled", "reply": "请在“收录：”后提供要保存的内容。"}
    if len(capture_text) > MAX_CAPTURE_CHARS:
        return {"action": "handled", "reply": "保存失败：内容超过单条收录上限，未写入 Inbox。"}
    sender = source.get("user_id")
    if not isinstance(sender, str) or not sender or not isinstance(message_id, str) or not message_id:
        return {"action": "handled", "reply": "保存失败：缺少可信发送者或消息编号，未写入 Inbox。"}

    endpoint = os.environ.get("SB_WEIXIN_CORE_INBOX_URL", "").strip()
    secret = os.environ.get("SB_WEIXIN_CORE_INBOX_HMAC_KEY", "").encode("utf-8")
    if not endpoint.startswith("http://") and not endpoint.startswith("https://"):
        return {"action": "handled", "reply": "保存失败：Core Inbox 尚未配置，未写入 Inbox。"}
    if len(secret) < 32:
        return {"action": "handled", "reply": "保存失败：渠道认证未配置，未写入 Inbox。"}

    body = {
        "original_text": capture_text,
        "source_event_id": message_id,
        "occurred_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "intent": "explicit_capture",
        "attachment_refs": [],
        "source": {
            "platform": "weixin", "chat_type": "dm", "user_id": sender,
            "chat_id": source.get("chat_id", ""),
        },
    }
    raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(secret, raw, hashlib.sha256).hexdigest()
    request = Request(endpoint, data=raw, method="POST", headers={
        "Content-Type": "application/json",
        "X-SecondBrain-Signature": signature,
    })
    try:
        with urlopen(request, timeout=5) as response:
            if response.status != 202:
                raise ValueError("unexpected Core status")
            result = json.loads(response.read(65537))
            receipt_signature = response.headers.get("X-SecondBrain-Receipt-Signature", "")
        if (not isinstance(result, dict) or not isinstance(result.get("inbox_id"), str) or
                not isinstance(result.get("status"), str)):
            raise ValueError("invalid Core receipt")
        request_digest = hashlib.sha256(raw).hexdigest()
        receipt = "secondbrain-weixin-receipt-v1\0{}\0{}\0{}\0{}".format(
            message_id, result["inbox_id"], result["status"], request_digest)
        expected_receipt = hmac.new(secret, receipt.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(receipt_signature, expected_receipt):
            raise ValueError("Core receipt signature invalid")
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        return {"action": "handled", "reply": "保存失败，当前未确认写入 Inbox。请稍后重试。"}
    return {"action": "handled", "reply": "已收录到 Inbox。"}


def _post_gateway_admission(**kwargs):
    try:
        return _handle_post_gateway_admission(**kwargs)
    except Exception:
        # Ordinary plugin errors must not reach the Gateway's fail-open fallback
        # for an explicit save command.
        text = kwargs.get("text", "")
        if _capture_text(text) is not None:
            return {"action": "handled", "reply": "保存失败，当前未确认写入 Inbox。请稍后重试。"}
        return None


def register(ctx):
    ctx.register_hook("post_gateway_admission", _post_gateway_admission)
