"""Internal-only fail-closed binding candidate for Hermes capture suggestions.

No production Hermes source adapter or Core consent ledger is registered. This
module defines the proof checks needed before such an adapter can be approved;
it intentionally exposes no HTTP route and cannot create Inbox entries.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat


_EVENT_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
MAX_SOURCE_TEXT_UTF8_BYTES = 200_000
MAX_BINDING_STATE_BYTES = 512_000


@dataclass(frozen=True)
class VerifiedCaptureSuggestionSource:
    """Server adapter result, returned only after authenticating its source."""

    source_event_id: str
    original_text: str
    original_text_sha256: str
    source_record_version: str
    subject: str
    received_at: str
    expires_at: str


@dataclass(frozen=True)
class CoreCaptureConsentRecord:
    """Core-owned explicit consent audit row bound to one source version."""

    consent_id: str
    subject: str
    source_event_id: str
    original_text_sha256: str
    source_record_version: str
    decision: str
    recorded_at: str


@dataclass(frozen=True)
class TrustedCaptureSuggestionBinding:
    """Verified metadata only; never a bearer credential or approval by itself."""

    subject: str
    source_event_id: str
    original_text_sha256: str
    source_record_version: str
    consent_id: str
    binding_id: str


class CaptureSuggestionBindingConflict(RuntimeError):
    """One source event already has a different bound consent/content tuple."""


class CaptureSuggestionBindingStoreError(RuntimeError):
    """Candidate metadata could not be safely read or persisted."""


class TrustedCaptureSuggestionBindingAuthority:
    """Resolve a suggestion only from injected server-side authorities.

    ``source_reader.read_verified_suggestion`` must authenticate the original
    Hermes event and return the exact persisted record. ``consent_reader`` must
    return a Core-owned explicit user decision. Missing dependencies mean no
    trusted source exists and always fail closed.
    """

    def __init__(self, source_reader=None, consent_reader=None, clock=None):
        self.source_reader = source_reader
        self.consent_reader = consent_reader
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def resolve(self, *, source_event_id, expected_text, expected_version,
                authenticated_subject, consent_id):
        if (self.source_reader is None or self.consent_reader is None
                or not isinstance(source_event_id, str) or not _EVENT_ID.fullmatch(source_event_id)
                or not isinstance(expected_text, str) or not expected_text.strip()
                or not _within_utf8_budget(expected_text)
                or not isinstance(expected_version, str) or not expected_version or len(expected_version) > 256
                or not isinstance(authenticated_subject, str) or not authenticated_subject
                or len(authenticated_subject) > 256
                or not isinstance(consent_id, str) or not consent_id or len(consent_id) > 128):
            return None
        # Read both authorities twice. The second read is the candidate's
        # final verification point: source edits/version changes and consent
        # revocation between reads fail closed. This is not transactional with
        # any later ledger or Inbox write.
        try:
            source = self.source_reader.read_verified_suggestion(source_event_id)
            consent = self.consent_reader.read_consent(consent_id)
            confirm_source = self.source_reader.read_verified_suggestion(source_event_id)
            confirm_consent = self.consent_reader.read_consent(consent_id)
        except Exception:
            return None
        if source != confirm_source or consent != confirm_consent:
            return None
        if not isinstance(source, VerifiedCaptureSuggestionSource):
            return None
        if not isinstance(consent, CoreCaptureConsentRecord):
            return None
        if (not isinstance(source.source_event_id, str)
                or not isinstance(source.original_text, str)
                or not isinstance(source.original_text_sha256, str)
                or not isinstance(source.source_record_version, str)
                or not isinstance(source.subject, str)
                or not isinstance(source.received_at, str)
                or not isinstance(source.expires_at, str)
                or not isinstance(consent.consent_id, str)
                or not isinstance(consent.subject, str)
                or not isinstance(consent.source_event_id, str)
                or not isinstance(consent.original_text_sha256, str)
                or not isinstance(consent.source_record_version, str)
                or not isinstance(consent.decision, str)
                or not isinstance(consent.recorded_at, str)
                or not _within_utf8_budget(source.original_text)
                or not source.source_record_version or len(source.source_record_version) > 256
                or not source.subject or len(source.subject) > 256
                or not consent.consent_id or len(consent.consent_id) > 128):
            return None
        try:
            digest = hashlib.sha256(source.original_text.encode("utf-8")).hexdigest()
            payload_bytes = len(json.dumps(
                {"source": source.__dict__, "consent": consent.__dict__},
                sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            ).encode("utf-8"))
        except (UnicodeError, TypeError, ValueError):
            return None
        if payload_bytes > MAX_BINDING_STATE_BYTES:
            return None
        if (source.source_event_id != source_event_id
                or source.original_text != expected_text
                or source.original_text_sha256 != digest
                or not _SHA256.fullmatch(source.original_text_sha256)
                or source.source_record_version != expected_version
                or not source.source_record_version
                or source.subject != authenticated_subject):
            return None
        if (consent.consent_id != consent_id
                or consent.subject != authenticated_subject
                or consent.source_event_id != source_event_id
                or consent.original_text_sha256 != digest
                or consent.source_record_version != expected_version
                or consent.decision != "consented"):
            return None
        try:
            received_at = datetime.fromisoformat(source.received_at.replace("Z", "+00:00"))
            expires_at = datetime.fromisoformat(source.expires_at.replace("Z", "+00:00"))
            recorded_at = datetime.fromisoformat(consent.recorded_at.replace("Z", "+00:00"))
            now = self.clock()
            if (received_at.tzinfo is None or expires_at.tzinfo is None
                    or recorded_at.tzinfo is None or now.tzinfo is None):
                return None
            received_at = received_at.astimezone(timezone.utc)
            expires_at = expires_at.astimezone(timezone.utc)
            recorded_at = recorded_at.astimezone(timezone.utc)
            now = now.astimezone(timezone.utc)
            if (expires_at <= received_at or now > expires_at or received_at > now
                    or recorded_at > now or recorded_at < received_at
                    or recorded_at > expires_at):
                return None
        except (AttributeError, TypeError, ValueError, OverflowError):
            return None
        material = {"subject": authenticated_subject, "source_event_id": source_event_id,
                    "original_text_sha256": digest, "source_record_version": expected_version,
                    "consent_id": consent_id}
        binding_id = hashlib.sha256(json.dumps(
            material, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")).hexdigest()
        return TrustedCaptureSuggestionBinding(binding_id=binding_id, **material)


def _within_utf8_budget(value):
    try:
        return len(value.encode("utf-8")) <= MAX_SOURCE_TEXT_UTF8_BYTES
    except UnicodeError:
        return False


class TrustedCaptureSuggestionBindingStore:
    """Durable internal candidate ledger; never writes Inbox or source data.

    The caller supplies an already-existing canonical absolute local directory
    owned by the effective user with exact mode 0700. This class is not
    configured in ``create_app``. The event/subject key allows identical
    replays and rejects a different version, consent, or content for that
    event. Atomic replacement leaves either the previous complete state or a
    complete new state; orphan temp files are removed only after the state has
    been validated under the inter-process lock.
    """

    def __init__(self, root):
        self.root = Path(root)
        if not self.root.is_absolute() or Path(os.path.realpath(self.root)) != self.root:
            raise CaptureSuggestionBindingStoreError("candidate store root must be canonical and absolute")
        root_fd = self._open_root()
        try:
            root_stat = os.fstat(root_fd)
            self.root_identity = (root_stat.st_dev, root_stat.st_ino)
        finally:
            os.close(root_fd)

    def _open_root(self):
        try:
            fd = os.open(self.root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                         | getattr(os, "O_NOFOLLOW", 0))
        except OSError as exc:
            raise CaptureSuggestionBindingStoreError("candidate store root unavailable") from exc
        try:
            root_stat = os.fstat(fd)
            if (not stat.S_ISDIR(root_stat.st_mode) or root_stat.st_uid != os.geteuid()
                    or stat.S_IMODE(root_stat.st_mode) != 0o700):
                raise CaptureSuggestionBindingStoreError(
                    "candidate store root must be owned by this user with mode 0700")
            if (hasattr(self, "root_identity")
                    and (root_stat.st_dev, root_stat.st_ino) != self.root_identity):
                raise CaptureSuggestionBindingStoreError("candidate store root identity changed")
            return fd
        except Exception:
            os.close(fd)
            raise

    @staticmethod
    def _validate_private_file(file_stat, label):
        if (not stat.S_ISREG(file_stat.st_mode) or file_stat.st_uid != os.geteuid()
                or stat.S_IMODE(file_stat.st_mode) != 0o600 or file_stat.st_nlink != 1):
            raise CaptureSuggestionBindingStoreError(f"candidate {label} file is unsafe")

    @staticmethod
    def _empty_state():
        return {"schema_version": 1, "records": {}}

    def _load(self, root_fd):
        state_fd = None
        try:
            state_fd = os.open("capture-suggestion-bindings.json",
                               os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                               | getattr(os, "O_NONBLOCK", 0), dir_fd=root_fd)
        except FileNotFoundError:
            return self._empty_state()
        except OSError as exc:
            raise CaptureSuggestionBindingStoreError("candidate state unavailable") from exc
        try:
            state_stat = os.fstat(state_fd)
            self._validate_private_file(state_stat, "state")
            if state_stat.st_size > MAX_BINDING_STATE_BYTES:
                raise CaptureSuggestionBindingStoreError("candidate state exceeds budget")
            with os.fdopen(state_fd, "rb") as state_file:
                state_fd = None
                raw = state_file.read(MAX_BINDING_STATE_BYTES + 1)
            if len(raw) > MAX_BINDING_STATE_BYTES:
                raise CaptureSuggestionBindingStoreError("candidate state exceeds budget")
            try:
                state = json.loads(raw.decode("utf-8"))
            except (UnicodeError, ValueError) as exc:
                raise CaptureSuggestionBindingStoreError("candidate state is corrupt") from exc
        except OSError as exc:
            raise CaptureSuggestionBindingStoreError("candidate state unavailable") from exc
        finally:
            if state_fd is not None:
                os.close(state_fd)
        if (not isinstance(state, dict) or set(state) != {"schema_version", "records"}
                or state["schema_version"] != 1 or not isinstance(state["records"], dict)):
            raise CaptureSuggestionBindingStoreError("candidate state schema is invalid")
        for key, value in state["records"].items():
            if (not isinstance(key, str) or not _SHA256.fullmatch(key)
                    or not isinstance(value, dict)
                    or set(value) != {"subject", "source_event_id", "original_text_sha256",
                                      "source_record_version", "consent_id", "binding_id"}
                    or any(not isinstance(item, str) for item in value.values())
                    or not _SHA256.fullmatch(value["binding_id"])
                    or not _SHA256.fullmatch(value["original_text_sha256"])):
                raise CaptureSuggestionBindingStoreError("candidate state record is invalid")
        return state

    def _remove_orphan_temps(self, root_fd):
        try:
            names = os.listdir(root_fd)
        except OSError as exc:
            raise CaptureSuggestionBindingStoreError("candidate recovery scan failed") from exc
        for name in names:
            if not (name.startswith(".capture-suggestion-bindings-") and name.endswith(".tmp")):
                continue
            try:
                entry_stat = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            except OSError as exc:
                raise CaptureSuggestionBindingStoreError("candidate recovery inspection failed") from exc
            self._validate_private_file(entry_stat, "temporary")
            try:
                os.unlink(name, dir_fd=root_fd)
            except FileNotFoundError:
                continue
            except OSError as exc:
                raise CaptureSuggestionBindingStoreError("candidate recovery cleanup failed") from exc

    def _atomic_write(self, state, root_fd):
        raw = json.dumps(state, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        if len(raw) > MAX_BINDING_STATE_BYTES:
            raise CaptureSuggestionBindingStoreError("candidate state exceeds budget")
        fd = None
        temp_name = None
        try:
            for _ in range(8):
                temp_name = f".capture-suggestion-bindings-{secrets.token_hex(16)}.tmp"
                try:
                    fd = os.open(temp_name, os.O_CREAT | os.O_EXCL | os.O_WRONLY
                                 | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=root_fd)
                    break
                except FileExistsError:
                    continue
            if fd is None:
                raise OSError("unable to allocate unique candidate temp file")
            with os.fdopen(fd, "wb") as output:
                fd = None
                output.write(raw)
                output.flush()
                os.fsync(output.fileno())
            temp_stat = os.stat(temp_name, dir_fd=root_fd, follow_symlinks=False)
            self._validate_private_file(temp_stat, "temporary")
            os.replace(temp_name, "capture-suggestion-bindings.json",
                       src_dir_fd=root_fd, dst_dir_fd=root_fd)
            os.fsync(root_fd)
        except OSError as exc:
            raise CaptureSuggestionBindingStoreError("candidate state write failed") from exc
        finally:
            if fd is not None:
                os.close(fd)
            if temp_name is not None:
                try:
                    entry_stat = os.stat(temp_name, dir_fd=root_fd, follow_symlinks=False)
                    self._validate_private_file(entry_stat, "temporary")
                    os.unlink(temp_name, dir_fd=root_fd)
                except FileNotFoundError:
                    pass
                except CaptureSuggestionBindingStoreError:
                    raise
                except OSError:
                    pass

    @staticmethod
    def _record_key(binding):
        material = f"{binding.subject}\0{binding.source_event_id}".encode("utf-8")
        return hashlib.sha256(material).hexdigest()

    @staticmethod
    def _as_record(binding):
        return {"subject": binding.subject, "source_event_id": binding.source_event_id,
                "original_text_sha256": binding.original_text_sha256,
                "source_record_version": binding.source_record_version,
                "consent_id": binding.consent_id, "binding_id": binding.binding_id}

    def record(self, binding):
        if not isinstance(binding, TrustedCaptureSuggestionBinding):
            raise CaptureSuggestionBindingStoreError("candidate binding type is invalid")
        material = {"subject": binding.subject, "source_event_id": binding.source_event_id,
                    "original_text_sha256": binding.original_text_sha256,
                    "source_record_version": binding.source_record_version,
                    "consent_id": binding.consent_id}
        if (not isinstance(binding.subject, str) or not binding.subject or len(binding.subject) > 256
                or not isinstance(binding.source_event_id, str)
                or not _EVENT_ID.fullmatch(binding.source_event_id)
                or not isinstance(binding.original_text_sha256, str)
                or not _SHA256.fullmatch(binding.original_text_sha256)
                or not isinstance(binding.source_record_version, str)
                or not binding.source_record_version or len(binding.source_record_version) > 256
                or not isinstance(binding.consent_id, str)
                or not binding.consent_id or len(binding.consent_id) > 128):
            raise CaptureSuggestionBindingStoreError("candidate binding fields are invalid")
        expected_binding_id = hashlib.sha256(json.dumps(
            material, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")).hexdigest()
        if binding.binding_id != expected_binding_id:
            raise CaptureSuggestionBindingStoreError("candidate binding digest is invalid")
        try:
            root_fd = self._open_root()
        except CaptureSuggestionBindingStoreError:
            raise
        try:
            try:
                lock_name = ".capture-suggestion-bindings.lock"
                nofollow = getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
                try:
                    lock_fd = os.open(lock_name, os.O_CREAT | os.O_EXCL | os.O_RDWR | nofollow,
                                      0o600, dir_fd=root_fd)
                except FileExistsError:
                    lock_fd = os.open(lock_name, os.O_RDWR | nofollow, dir_fd=root_fd)
            except OSError as exc:
                raise CaptureSuggestionBindingStoreError("candidate lock unavailable") from exc
            try:
                self._validate_private_file(os.fstat(lock_fd), "lock")
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
                state = self._load(root_fd)
                self._remove_orphan_temps(root_fd)
                key = self._record_key(binding)
                record = self._as_record(binding)
                existing = state["records"].get(key)
                if existing is not None:
                    if existing != record:
                        raise CaptureSuggestionBindingConflict("source event already bound differently")
                    # A prior os.replace may have succeeded while its directory
                    # fsync failed. Replay must re-establish directory-entry
                    # durability before reporting a confirmed duplicate.
                    try:
                        os.fsync(root_fd)
                    except OSError as exc:
                        raise CaptureSuggestionBindingStoreError(
                            "candidate replay durability remains unknown") from exc
                    return binding, True
                state["records"][key] = record
                self._atomic_write(state, root_fd)
                return binding, False
            except OSError as exc:
                raise CaptureSuggestionBindingStoreError("candidate lock operation failed") from exc
            finally:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                finally:
                    os.close(lock_fd)
        finally:
            os.close(root_fd)

    def record_verified(self, authority, **source_claims):
        """Verify twice, then record metadata; the read/write gap is non-atomic.

        This candidate ledger is not an Inbox admission mechanism. A source
        edit or consent revocation after final verification can race this local
        metadata write; a frozen Core-owned transaction contract is required
        before any real Inbox integration.
        """
        binding = authority.resolve(**source_claims)
        if binding is None:
            return None, False
        return self.record(binding)
