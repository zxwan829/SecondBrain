"""Isolated Authority API candidate; no production bootstrap is implied.

Every dependency is Authority-owned.  The registry accepts user bytes only
through this independently authenticated origin.  A candidate provider must
use the trusted registration and snapshot stores, not trust Core assertions.
"""
from __future__ import annotations

import base64
import binascii
import json
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .d090_authority_ui import HTML, JS

from .d090_authority_writer import D090RecoveryRequired, D090Rejected, HumanProofUnavailable, _valid_id

_MAX_FRAME = 12 * 1024 * 1024


async def _body(request):
    payload = bytearray()
    async for part in request.stream():
        payload.extend(part)
        if len(payload) > _MAX_FRAME:
            raise HTTPException(413, 'Request too large')
    try:
        body = json.loads(payload)
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(400, 'Invalid request') from exc
    if not isinstance(body, dict):
        raise HTTPException(400, 'Invalid request')
    return body


def create_authority_app(auth, authority, snapshots, registry, candidate_builder, readiness, *, core_origin):
    """Construct the narrow API using already validated, Authority-owned dependencies.

    ``readiness`` must actively verify required boundaries, including the
    confined Writer.  A missing/failed check always returns 503.  This factory
    does not turn a generic socket existence check into a readiness proof.
    """
    confirmation = authority.browser_confirmation
    if (confirmation is None or confirmation._auth is not auth
            or snapshots.authority is not authority or not callable(candidate_builder)):
        raise ValueError('authority_dependencies_invalid')
    if not callable(readiness):
        raise ValueError('authority_readiness_required')
    if len(auth.allowed_origins) != 1:
        raise ValueError('authority_single_origin_required')
    def origin(value):
        parsed = urlsplit(value)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.path not in ('', '/')
                or parsed.query or parsed.fragment):
            raise ValueError('authority_https_origin_required')
        try:
            parsed.port
        except ValueError as exc:
            raise ValueError('authority_origin_invalid') from exc
        return parsed
    approval_origin = origin(next(iter(auth.allowed_origins)))
    business_origin = origin(core_origin)
    if approval_origin.hostname.lower() == business_origin.hostname.lower():
        raise ValueError('authority_hostname_must_be_independent')
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[approval_origin.hostname])

    @app.middleware('http')
    async def secure_headers(request, call_next):
        response = await call_next(request)
        response.headers['Content-Security-Policy'] = "default-src 'none'; script-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    def owner(request):
        auth.check_origin(request)
        return auth.require_owner(request)

    @app.get('/', response_class=HTMLResponse)
    def index():
        return HTMLResponse(HTML)

    @app.get('/authority.js')
    def script():
        return PlainTextResponse(JS, media_type='application/javascript')

    @app.get('/health')
    def health():
        try:
            ok = readiness() is True
        except Exception:
            ok = False
        if not ok:
            raise HTTPException(503, 'Not ready')
        return {'status': 'ready'}

    @app.post('/login')
    async def login(request: Request, response: Response):
        body = await _body(request)
        if set(body) != {'password'}:
            raise HTTPException(400, 'Invalid request')
        token = auth.login(request, body['password'])
        auth.set_cookie(response, request, token, auth.session_ttl)
        return {'authenticated': True}

    @app.post('/logout')
    def logout(request: Request, response: Response):
        owner(request)
        auth.logout(request)
        auth.clear_cookie(response, request)
        return {'authenticated': False}

    @app.post('/sources')
    async def register(request: Request):
        subject = owner(request)
        body = await _body(request)
        if set(body) != {'intent', 'raw_base64'} or body.get('intent') != 'register_source':
            raise HTTPException(400, 'Invalid request')
        try:
            raw = base64.b64decode(body['raw_base64'], validate=True)
            result = registry.register(raw, authenticated_subject=subject)
        except (ValueError, TypeError, binascii.Error, D090Rejected) as exc:
            raise HTTPException(400, 'Source rejected') from exc
        return result

    @app.post('/candidates')
    async def candidate(request: Request):
        owner(request)
        body = await _body(request)
        if set(body) != {'capture_id', 'target_id', 'content'}:
            raise HTTPException(400, 'Invalid request')
        if (not _valid_id(body.get('capture_id')) or not _valid_id(body.get('target_id'))
                or not isinstance(body.get('content'), str)):
            raise HTTPException(400, 'Invalid request')
        try:
            snapshot_id = candidate_builder(body['capture_id'], body['target_id'], body['content'])
            snapshot = snapshots.load(snapshot_id)
            binding = snapshots.binding(snapshot_id)
            if snapshot['capture_id'] != body['capture_id'] or snapshot['target_id'] != body['target_id']:
                raise D090Rejected('candidate_binding_mismatch')
            content = base64.b64decode(snapshot['content'], validate=True).decode('utf-8', 'strict')
            exact = confirmation.prepare(request, binding)
        except (D090Rejected, HumanProofUnavailable, ValueError, TypeError, UnicodeError) as exc:
            raise HTTPException(409, 'Candidate unavailable') from exc
        return {'snapshot_id': snapshot_id, 'binding': exact, 'content': content,
                'capture_id': snapshot['capture_id'], 'raw_ref': snapshot['raw_ref'],
                'raw_sha256': snapshot['raw_sha256'], 'review_ref': snapshot['review_ref'],
                'review_sha256': snapshot['review_sha256'], 'review_content': base64.b64decode(snapshot['review'], validate=True).decode('utf-8', 'strict'),
                'source_identity': snapshot['source_identity'], 'source_version': snapshot['source_version'],
                'target_id': snapshot['target_id'], 'target_filename': snapshot['target_filename'], 'target_scope': snapshot['target_scope']}

    @app.post('/confirm')
    async def confirm(request: Request):
        owner(request)
        body = await _body(request)
        if (set(body) != {'intent', 'snapshot_id', 'binding'}
                or body.get('intent') != 'promote_exact_preview' or not isinstance(body.get('binding'), dict)):
            raise HTTPException(403, 'Exact confirmation required')
        try:
            binding = snapshots.binding(body['snapshot_id'])
            exact = body['binding']
            if set(exact) != set(binding) | {'nonce', 'expires_at'} or any(exact.get(k) != v for k, v in binding.items()):
                raise D090Rejected('binding_mismatch')
            return snapshots.confirm(body['snapshot_id'], proof=request, nonce=exact['nonce'], expires_at=exact['expires_at'])
        except D090RecoveryRequired as exc:
            raise HTTPException(503, 'Recovery required') from exc
        except (D090Rejected, HumanProofUnavailable, ValueError, TypeError, KeyError) as exc:
            raise HTTPException(409, 'Confirmation rejected') from exc

    @app.post('/operation')
    async def operation(request: Request):
        owner(request)
        body = await _body(request)
        if set(body) != {'operation_id'} or not _valid_id(body.get('operation_id')):
            raise HTTPException(400, 'Invalid request')
        db = authority._connect()
        try:
            row = db.execute('SELECT state FROM grants WHERE operation_id=?', (body['operation_id'],)).fetchone()
        finally:
            db.close()
        if row is None:
            raise HTTPException(404, 'Operation unavailable')
        # A process may crash after dispatch and before persisting the result.
        # Never automatically repeat a Writer operation based on an unknown state.
        state = 'recovery_required' if row[0] in ('committing', 'recovery_required') else row[0]
        if state not in ('issued', 'revoked', 'committed', 'recovery_required'):
            raise HTTPException(503, 'Operation unavailable')
        return {'operation_id': body['operation_id'], 'state': state}

    return app
