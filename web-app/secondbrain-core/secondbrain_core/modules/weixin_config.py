"""Fail-closed loading for the Weixin Inbox integration configuration."""
import json
import os
import stat


def _private_file(path, name, *, max_bytes):
    if not path:
        raise ValueError(f"{name} file path is empty")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077
                or info.st_uid != os.geteuid()):
            raise ValueError(f"{name} must be a private regular file owned by the service user")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError(f"{name} exceeds the size limit")
        return data.strip()
    finally:
        os.close(fd)


def _configured_value(env_name, file_env_name, *, max_bytes):
    env_value = os.environ.get(env_name)
    file_path = os.environ.get(file_env_name, "").strip()
    if env_value is not None and file_path:
        raise ValueError(f"Set only one of {env_name} or {file_env_name}")
    if file_path:
        return _private_file(file_path, file_env_name, max_bytes=max_bytes)
    if env_value is None:
        raise ValueError(f"{env_name} or {file_env_name} is required")
    return env_value.encode("utf-8")


def load_weixin_inbox_config():
    key = _configured_value(
        "SB_WEIXIN_INBOX_HMAC_KEY", "SB_WEIXIN_INBOX_HMAC_KEY_FILE", max_bytes=4096,
    )
    if len(key) < 32:
        raise ValueError("Weixin Inbox HMAC key must contain at least 32 bytes")
    senders_payload = _configured_value(
        "SB_WEIXIN_ALLOWED_SENDERS_JSON", "SB_WEIXIN_ALLOWED_SENDERS_JSON_FILE",
        max_bytes=64 * 1024,
    )
    try:
        senders = json.loads(senders_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Weixin Inbox sender allowlist must be valid UTF-8 JSON") from exc
    return key, senders
