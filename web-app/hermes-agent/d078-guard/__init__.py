"""Hermes v0.22.2 SecondBrain security hooks."""
import json
import os
import secrets
import shlex
from pathlib import Path


APPROVAL_PREFIX = "SECONDBRAIN_TERMINAL_APPROVAL_V1:"
_EXECUTION_TOOLS = {"terminal", "process_manage", "execute_code"}
_READ_TOOLS = {"read_file", "search_files", "list_directory", "directory_tree", "find_files",
               "file_info", "list_files", "glob_files"}
_WRITE_TOOLS = {"write_file", "patch", "edit_file", "append_file", "delete_file", "move_file",
                "copy_file", "rename_file"}
_PATH_KEYS = {"path", "file_path", "directory", "root", "target", "source", "cwd", "workdir"}
_SENSITIVE_NAMES = {"config.yaml", "config.yml", ".env", "auth.json", "auth.lock", "state.db",
                    "sessions.db", "gateway.db", "api_server.env", "credentials.json", "secrets.json",
                    "memory.md", "user.md"}
_PROTECTED_DIRS = {"sessions", "pending", "logs", "memories", "auth", "credentials", "secrets",
                   "memory", "vault", "pairing", "browser-profile", "mcp-tokens"}
_GLOBAL_SECRET_DIRS = {".ssh", ".aws", ".gnupg", ".docker", ".kube"}
_GLOBAL_SECRET_NAMES = {".env", ".env.local", ".env.production", "id_rsa", "id_ed25519",
                        "credentials", "credentials.json", "secrets.json", "auth.json", "token.json"}
_GLOBAL_SECRET_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}
_EXECUTABLE_WRAPPERS = {"sh", "bash", "zsh", "fish", "dash", "ksh", "csh", "tcsh", "python",
                        "python2", "python3", "pypy", "node", "ruby", "perl", "php", "eval",
                        "env", "busybox", "xargs"}
_APPROVAL_ARG_MAX = 12_000


def _hermes_homes():
    values = [os.environ.get("HERMES_HOME", ""), str(Path.home() / ".hermes")]
    roots = []
    for value in values:
        if not value:
            continue
        try:
            path = Path(value).expanduser().resolve(strict=False)
            if path not in roots:
                roots.append(path)
        except (OSError, RuntimeError, ValueError):
            continue
    return roots


def _under(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _under_casefold(path, root):
    """Path containment with case-folded components for cross-platform profile layouts."""
    path_parts = tuple(part.casefold() for part in path.parts)
    root_parts = tuple(part.casefold() for part in root.parts)
    return len(path_parts) >= len(root_parts) and path_parts[:len(root_parts)] == root_parts


def _contains_private_component(path, home):
    if not _under_casefold(path, home):
        return False
    relative = path.parts[len(home.parts):]
    protected = _PROTECTED_DIRS | _SENSITIVE_NAMES
    return any(part.casefold() in protected for part in relative)


def _contains_global_secret_component(path):
    for part in path.parts:
        folded = part.casefold()
        if folded in _GLOBAL_SECRET_DIRS or folded in _GLOBAL_SECRET_NAMES:
            return True
        if Path(folded).suffix in _GLOBAL_SECRET_SUFFIXES:
            return True
    return False


def _global_secret_roots():
    home = Path.home().resolve(strict=False)
    roots = [home / name for name in _GLOBAL_SECRET_DIRS]
    roots.extend((Path("/run/secrets"), Path("/var/run/secrets")))
    return [root.resolve(strict=False) for root in roots]


def _protected_targets(home):
    targets = [home / name for name in _PROTECTED_DIRS]
    targets.extend(home / name for name in _SENSITIVE_NAMES)
    return targets


def _resolve(raw, cwd):
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        return None
    try:
        expanded = os.path.expandvars(os.path.expanduser(raw))
        candidate = Path(expanded)
        if not candidate.is_absolute():
            candidate = cwd / candidate
        return candidate.resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return None


def _path_values(value, key=""):
    if isinstance(value, dict):
        for child_key, child in value.items():
            yield from _path_values(child, str(child_key).lower())
    elif isinstance(value, list):
        for child in value:
            yield from _path_values(child, key)
    elif key in _PATH_KEYS and isinstance(value, str):
        yield value


def path_guard(tool_name, args, *, hermes_home=None, cwd=None):
    """Block model reads of Hermes-owned state and direct Skills writes.

    Canonical path checks cover relative paths, traversal and symlink targets. Search roots that
    contain a protected subtree are blocked so glob/content search cannot enumerate around it.
    """
    name = str(tool_name or "")
    if name not in _READ_TOOLS | _WRITE_TOOLS:
        return None
    homes = [Path(hermes_home).expanduser().resolve(strict=False)] if hermes_home else _hermes_homes()
    base = Path(cwd or os.getcwd()).expanduser().resolve(strict=False)
    paths = list(_path_values(args if isinstance(args, dict) else {}))
    if not paths:
        return "BLOCKED: file operation has no reviewable path (path_guard_missing)."
    for raw in paths:
        resolved = _resolve(raw, base)
        if resolved is None:
            return "BLOCKED: file path could not be safely resolved (path_guard_invalid)."
        for home in homes:
            in_home = _under_casefold(resolved, home)
            private_component = _contains_private_component(resolved, home)
            ancestor_of_home = _under_casefold(home, resolved)
            if name in _WRITE_TOOLS:
                skills_roots = (home / "skills", home / "Skills")
                if any(_under_casefold(resolved, root.resolve(strict=False)) for root in skills_roots):
                    return "BLOCKED: use Hermes skill_manage so skills.write_approval can stage this change (skills_write_gate)."
            if (private_component or _contains_global_secret_component(resolved)
                    or (name in _READ_TOOLS and ancestor_of_home)
                    or (name in _READ_TOOLS and any(_under_casefold(root, resolved)
                                                    for root in _global_secret_roots()))):
                return "BLOCKED: Hermes Session, state, configuration, credential, and pending paths are private (hermes_private_path)."
            if name in _WRITE_TOOLS and in_home and any(
                    _under_casefold(resolved, target) for target in _protected_targets(home)):
                return "BLOCKED: Hermes-owned paths cannot be changed by generic file tools (hermes_state_write)."
    return None


def _ambiguous_execution(tool_name, args):
    if not isinstance(args, dict):
        return "tool arguments are not structured"
    if tool_name == "terminal":
        allowed = {"command", "background", "timeout", "workdir", "pty", "notify", "heartbeat",
                   "persist_on_release"}
        if set(args) - allowed:
            return "terminal contains arguments outside the pinned Hermes tool contract"
        command = args.get("command")
        if not isinstance(command, str) or not command.strip() or len(command) > _APPROVAL_ARG_MAX:
            return "terminal command is missing or exceeds the review limit"
        workdir = args.get("workdir")
        if not isinstance(workdir, str) or not workdir or not Path(workdir).is_absolute():
            return "terminal requires an explicit absolute workdir so approval shows the execution directory"
        if os.path.normpath(workdir) != workdir or str(Path(workdir).resolve(strict=False)) != workdir:
            return "terminal workdir must be canonical so the approval path matches the local execution cwd"
        try:
            if _terminal_backend_type() != "local":
                return "terminal backend remaps workdirs; this profile cannot display the effective execution cwd"
        except Exception:
            return "terminal backend could not be verified for an exact execution cwd"
        try:
            tokens = list(shlex.shlex(command, posix=True, punctuation_chars=";&|<>"))
        except ValueError:
            return "terminal command could not be parsed for review"
        if any(token and all(char in ";&|<>" for char in token) for token in tokens):
            return "shell command chains and redirections require a separate explicit command"
        if "$" in command or "`" in command or "\n" in command or "\r" in command:
            return "dynamic shell expansion and multiline commands cannot be reviewed as one exact action"
        executable = Path(tokens[0]).name.lower() if tokens else ""
        if executable in _EXECUTABLE_WRAPPERS:
            return "interpreters and shell wrappers are not accepted as a single reviewable terminal action"
        if any(Path(token).suffix.lower() in {".sh", ".bash", ".zsh", ".py", ".js", ".rb", ".pl"}
               for token in tokens[1:]):
            return "indirect script execution cannot be reviewed as a single exact action"
    elif tool_name == "process_manage":
        if set(args) - {"action", "session_id", "data", "timeout", "offset", "limit"}:
            return "process_manage contains arguments outside the pinned Hermes tool contract"
        if args.get("action") not in {"list", "poll", "log", "wait", "kill", "write", "submit", "close", "handoff"}:
            return "process_manage action is missing or unsupported"
        if args.get("action") != "list" and (not isinstance(args.get("session_id"), str) or not args["session_id"]):
            return "process_manage requires the target session_id for approval"
    elif tool_name == "execute_code":
        if set(args) - {"code", "reset"}:
            return "execute_code contains arguments outside the pinned Hermes tool contract"
        if not isinstance(args.get("code"), str) or not args["code"].strip():
            return "execute_code requires non-empty code for approval"
        if "reset" in args and not isinstance(args["reset"], bool):
            return "execute_code reset must be boolean"
    try:
        encoded = json.dumps(args, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError):
        return "tool arguments could not be serialized for review"
    if len(encoded) > _APPROVAL_ARG_MAX:
        return "tool arguments exceed the review limit"
    return None


def _terminal_backend_type():
    from tools.terminal_tool import _get_env_config
    return _get_env_config().get("env_type")


def _approval_mode_bypass():
    """YOLO or approval-off settings must never downgrade this gate to auto-allow."""
    try:
        from tools.approval import _yolo_active
        from tools.approval_context import _get_approval_mode
        return bool(_yolo_active()) or _get_approval_mode() == "off"
    except Exception:
        return True


def _pre_tool_call(tool_name=None, args=None, **kwargs):
    name = str(tool_name or "")
    arguments = args if isinstance(args, dict) else {}
    if name in _EXECUTION_TOOLS:
        if _approval_mode_bypass():
            return {"action": "block", "message": "BLOCKED: terminal approval policy is unavailable or disabled (approval_policy_unavailable)."}
        reason = _ambiguous_execution(name, arguments)
        if reason:
            return {"action": "block", "message": "BLOCKED: " + reason + " (terminal_review_ambiguous)."}
        request = {"schema": 1, "tool": name, "arguments": arguments}
        message = APPROVAL_PREFIX + json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        # A fresh key prevents Hermes' session/always allowlist cache from matching a later call.
        return {"action": "approve", "message": message,
                "rule_key": "secondbrain-terminal:" + secrets.token_hex(24)}
    blocked = path_guard(name, arguments)
    if blocked:
        return {"action": "block", "message": blocked}
    return None


def pre_tool_call(tool_name=None, args=None, **kwargs):
    """Keep guarded tools fail-closed even if path/policy inspection raises unexpectedly."""
    name = str(tool_name or "")
    try:
        return _pre_tool_call(tool_name, args, **kwargs)
    except Exception:
        if name in _EXECUTION_TOOLS:
            return {"action": "block", "message": "BLOCKED: terminal approval policy could not be evaluated (approval_policy_unavailable)."}
        if name in _READ_TOOLS | _WRITE_TOOLS:
            return {"action": "block", "message": "BLOCKED: file path policy could not be evaluated (path_guard_unavailable)."}
        return None


def register(ctx):
    ctx.register_hook("pre_tool_call", pre_tool_call)
