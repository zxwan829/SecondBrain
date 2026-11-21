"""Candidate Linux Writer service. No production enablement is implied.

The service must be started as its already-provisioned, unprivileged Writer
identity. All configuration, mounts and filesystem properties are external
preconditions; failures in confinement are fatal before the first accept.
"""
from __future__ import annotations

import ctypes
import errno
import fcntl
import json
import os
import platform
import socket
import stat
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from .d090_authority_writer import (D090Rejected, D090RoleIds, StrictCreateOnlyWriter,
    _canonical, authority_peer_before_body, receive_bounded_json_without_fds)

_LIBC = ctypes.CDLL(None, use_errno=True)
_PR_SET_NO_NEW_PRIVS = 38
_PR_SET_SECCOMP = 22

class _Ruleset(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64)]

class _PathRule(ctypes.Structure):
    _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]

class _Filter(ctypes.Structure):
    _fields_ = [("code", ctypes.c_ushort), ("jt", ctypes.c_ubyte),
                ("jf", ctypes.c_ubyte), ("k", ctypes.c_uint32)]

class _Program(ctypes.Structure):
    _fields_ = [("len", ctypes.c_ushort), ("filter", ctypes.POINTER(_Filter))]

def _error(operation):
    code = ctypes.get_errno()
    raise OSError(code, operation)

def _landlock(root):
    # Linux generic syscall numbers, x86_64 only (enforced in initialize).
    abi = _LIBC.syscall(444, None, 0, 1)
    if abi < 3:
        raise RuntimeError("landlock_abi_3_required")
    attr = _Ruleset((1 << 15) - 1)
    ruleset = _LIBC.syscall(444, ctypes.byref(attr), ctypes.sizeof(attr), 0)
    if ruleset < 0:
        _error("landlock_create")
    try:
        fd = os.open(root, os.O_PATH | os.O_CLOEXEC)
        try:
            # READ_FILE, READ_DIR, WRITE_FILE, MAKE_REG and REFER only.
            rule = _PathRule((1 << 1) | (1 << 2) | (1 << 3) | (1 << 8) | (1 << 13), fd)
            if _LIBC.syscall(445, ruleset, 1, ctypes.byref(rule), 0):
                _error("landlock_add")
        finally:
            os.close(fd)
        if _LIBC.syscall(446, ruleset, 0):
            _error("landlock_restrict")
    finally:
        os.close(ruleset)
    return abi

def _seccomp():
    # x86_64 syscall allowlist. openat is special: write access is permitted
    # only with Linux O_TMPFILE; opening any named file for write is denied.
    # All other unlisted calls including chmod, rename, unlink, socket, fork,
    # openat2, io_uring and post-install prctl fail closed.
    allowed = {0, 1, 3, 5, 7, 9, 10, 11, 12, 13, 14, 15, 16, 23, 24,
               35, 44, 47, 55, 72, 74, 96, 102, 104, 107, 108, 158,
               202, 217, 228, 231, 262, 265, 271, 288, 302, 318, 334}
    load, jump, ret = 0x20, 0x15, 0x06
    deny, allow, kill = 0x00050000 | errno.EPERM, 0x7fff0000, 0x80000000
    p = [_Filter(load, 0, 0, 4), _Filter(jump, 1, 0, 0xc000003e),
         _Filter(ret, 0, 0, kill), _Filter(load, 0, 0, 0)]
    for nr in sorted(allowed):
        p += [_Filter(jump, 0, 1, nr), _Filter(ret, 0, 0, allow)]
    # Match openat (257); skip special case for other syscall numbers.
    # flags low word is argument 2, offset 32 in struct seccomp_data.
    # Reject named opens requesting write or truncation, but permit O_TMPFILE.
    # O_TMPFILE is 020000000 | O_DIRECTORY on Linux.
    tmpfile = 0o20200000
    write_mask = os.O_WRONLY | os.O_RDWR | os.O_TRUNC | os.O_CREAT | os.O_APPEND
    p += [_Filter(jump, 0, 8, 257), _Filter(load, 0, 0, 32),
          _Filter(0x54, 0, 0, tmpfile), _Filter(jump, 0, 1, tmpfile),
          _Filter(ret, 0, 0, allow), _Filter(load, 0, 0, 32),
          _Filter(0x54, 0, 0, write_mask), _Filter(jump, 0, 1, 0),
          _Filter(ret, 0, 0, allow), _Filter(ret, 0, 0, deny),
          _Filter(ret, 0, 0, deny)]
    array = (_Filter * len(p))(*p)
    prog = _Program(len(p), array)
    if _LIBC.prctl(_PR_SET_SECCOMP, 2, ctypes.byref(prog)):
        _error("seccomp_install")

def _check_caps():
    status = Path('/proc/self/status').read_text(encoding='ascii')
    values = dict(line.split(':', 1) for line in status.splitlines() if ':' in line)
    for name in ('CapEff', 'CapPrm', 'CapInh', 'CapAmb', 'CapBnd'):
        if int(values[name].strip(), 16):
            raise RuntimeError('writer_capabilities_not_empty')

def _check_fds(expected):
    # Do not allow bypass of the open policy using inherited writable FDs.
    # The temporary descriptor used by listdir is already closed here.
    for name in os.listdir('/proc/self/fd'):
        fd = int(name)
        try:
            info = os.fstat(fd)
            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        except OSError as exc:
            if exc.errno == errno.EBADF:
                continue
            raise
        if fd not in expected:
            raise RuntimeError('writer_unexpected_inherited_fd')
        if fd < 3 and not (stat.S_ISFIFO(info.st_mode) or stat.S_ISCHR(info.st_mode)):
            raise RuntimeError('writer_unsafe_standard_fd')

def _bind(path, socket_gid):
    parent = Path(path).parent
    info = parent.stat(follow_symlinks=False)
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or info.st_mode & 0o022):
        raise RuntimeError('unsafe_writer_socket_directory')
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM | socket.SOCK_CLOEXEC)
    try:
        listener.bind(path)  # Never unlink or replace an existing path.
        os.chown(path, -1, socket_gid, follow_symlinks=False)
        os.chmod(path, 0o660, follow_symlinks=False)
        listener.listen(8)
        return listener
    except BaseException:
        listener.close()
        raise

def initialize(config):
    if sys.platform != 'linux' or platform.machine().lower() not in ('x86_64', 'amd64'):
        raise RuntimeError('unsupported_writer_kernel_architecture')
    roles = D090RoleIds(**config['role_ids'])
    roles.validate()
    if (os.getuid(), os.geteuid(), os.getgid(), os.getegid()) != (
            roles.writer_uid, roles.writer_uid, roles.writer_gid, roles.writer_gid):
        raise RuntimeError('writer_identity_mismatch')
    _check_caps()
    public_fd = os.open(config['public_key_path'], os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(public_fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid not in (0, roles.authority_uid)
                or info.st_mode & 0o022):
            raise RuntimeError('writer_public_key_unsafe')
        public_bytes = stream.read(4097)
    if len(public_bytes) > 4096:
        raise RuntimeError('writer_public_key_too_large')
    pub = serialization.load_pem_public_key(public_bytes)
    if not isinstance(pub, Ed25519PublicKey):
        raise RuntimeError('writer_key_invalid')
    writer = StrictCreateOnlyWriter(config['knowledge_root'], pub, config['key_id'], config['target_map'], roles,
                                    readonly_gid=config['knowledge_read_gid'])
    listener = _bind(config['socket_path'], config['socket_gid'])
    try:
        _check_fds({0, 1, 2, writer.root_fd, listener.fileno()})
        if _LIBC.prctl(_PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0):
            _error('no_new_privs')
        abi = _landlock(config['knowledge_root'])
        _seccomp()
        return writer, listener, abi
    except BaseException:
        listener.close()
        writer.close()
        raise

def serve(config):
    writer, listener, _abi = initialize(config)
    try:
        while True:
            conn, _ = listener.accept()
            with conn:
                conn.settimeout(3)
                try:
                    authority_peer_before_body(conn, writer.role_ids.authority_uid, writer.role_ids.authority_gid)
                    request = receive_bounded_json_without_fds(conn)
                    nonce = request.get('health_nonce')
                    if set(request) == {'health_nonce'} and isinstance(nonce, str) and len(nonce) == 32 and all(c in '0123456789abcdef' for c in nonce):
                        # This branch can only execute after initialize has returned
                        # with Landlock and seccomp installed, in the real serve loop.
                        conn.sendall(_canonical({'health_nonce': nonce, 'status': 'ready'}) + b'\n')
                    else:
                        writer.handle_request(conn, request)
                except (D090Rejected, ValueError, OSError):
                    # No exception detail or content is returned to callers.
                    continue
    finally:
        listener.close()
        writer.close()

def main():
    # This candidate accepts only a fixed, pre-provisioned config file.
    if len(sys.argv) != 2:
        raise SystemExit('usage: python -m secondbrain_core.modules.d090_writer_service CONFIG')
    fd = os.open(sys.argv[1], os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(fd, encoding='utf-8') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise RuntimeError('writer_configuration_unsafe')
        config = json.load(stream)
    serve(config)

if __name__ == '__main__':
    main()
