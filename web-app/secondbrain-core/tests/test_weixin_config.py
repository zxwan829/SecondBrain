import pytest

from secondbrain_core.modules.weixin_config import load_weixin_inbox_config

KEY = b"synthetic-file-weixin-hmac-key-0001"
SENDERS = b'{"synthetic-user":"synthetic-owner"}'


def _files(tmp_path):
    key_file, sender_file = tmp_path / "hmac-key", tmp_path / "senders.json"
    key_file.write_bytes(KEY + b"\n")
    sender_file.write_bytes(SENDERS + b"\n")
    key_file.chmod(0o600)
    sender_file.chmod(0o600)
    return key_file, sender_file


def test_loads_hmac_and_sender_map_from_private_files(tmp_path, monkeypatch):
    key_file, sender_file = _files(tmp_path)
    monkeypatch.setenv("SB_WEIXIN_INBOX_HMAC_KEY_FILE", str(key_file))
    monkeypatch.setenv("SB_WEIXIN_ALLOWED_SENDERS_JSON_FILE", str(sender_file))
    monkeypatch.delenv("SB_WEIXIN_INBOX_HMAC_KEY", raising=False)
    monkeypatch.delenv("SB_WEIXIN_ALLOWED_SENDERS_JSON", raising=False)
    assert load_weixin_inbox_config() == (KEY, {"synthetic-user": "synthetic-owner"})


@pytest.mark.parametrize(("env_name", "file_name", "value"), [
    ("SB_WEIXIN_INBOX_HMAC_KEY", "SB_WEIXIN_INBOX_HMAC_KEY_FILE", KEY.decode()),
    ("SB_WEIXIN_ALLOWED_SENDERS_JSON", "SB_WEIXIN_ALLOWED_SENDERS_JSON_FILE", SENDERS.decode()),
])
def test_rejects_environment_and_file_ambiguity(tmp_path, monkeypatch, env_name, file_name, value):
    key_file, sender_file = _files(tmp_path)
    monkeypatch.setenv("SB_WEIXIN_INBOX_HMAC_KEY_FILE", str(key_file))
    monkeypatch.setenv("SB_WEIXIN_ALLOWED_SENDERS_JSON_FILE", str(sender_file))
    monkeypatch.setenv("SB_WEIXIN_INBOX_HMAC_KEY", KEY.decode())
    monkeypatch.setenv("SB_WEIXIN_ALLOWED_SENDERS_JSON", SENDERS.decode())
    monkeypatch.setenv(env_name, value)
    with pytest.raises(ValueError, match="Set only one"):
        load_weixin_inbox_config()


def test_rejects_empty_unreadable_or_unprotected_key_file(tmp_path, monkeypatch):
    key_file, sender_file = _files(tmp_path)
    key_file.write_bytes(b" \n")
    monkeypatch.setenv("SB_WEIXIN_INBOX_HMAC_KEY_FILE", str(key_file))
    monkeypatch.setenv("SB_WEIXIN_ALLOWED_SENDERS_JSON_FILE", str(sender_file))
    monkeypatch.delenv("SB_WEIXIN_INBOX_HMAC_KEY", raising=False)
    monkeypatch.delenv("SB_WEIXIN_ALLOWED_SENDERS_JSON", raising=False)
    with pytest.raises(ValueError, match="at least 32 bytes"):
        load_weixin_inbox_config()
    key_file.write_bytes(KEY)
    key_file.chmod(0o644)
    with pytest.raises(ValueError, match="private regular file"):
        load_weixin_inbox_config()
    key_file.unlink()
    with pytest.raises(FileNotFoundError):
        load_weixin_inbox_config()


def test_rejects_malformed_sender_json(tmp_path, monkeypatch):
    key_file, sender_file = _files(tmp_path)
    sender_file.write_bytes(b"not-json")
    monkeypatch.setenv("SB_WEIXIN_INBOX_HMAC_KEY_FILE", str(key_file))
    monkeypatch.setenv("SB_WEIXIN_ALLOWED_SENDERS_JSON_FILE", str(sender_file))
    monkeypatch.delenv("SB_WEIXIN_INBOX_HMAC_KEY", raising=False)
    monkeypatch.delenv("SB_WEIXIN_ALLOWED_SENDERS_JSON", raising=False)
    with pytest.raises(ValueError, match="valid UTF-8 JSON"):
        load_weixin_inbox_config()
