import hashlib
import os
import re
import stat
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import APIRouter, HTTPException, Request

router = APIRouter()
ROOT = Path('/secondbrain')
REVIEW_ROOT = ROOT / '10-Review'
# Exact public origin from the production Dashboard HTTPS reverse-proxy rule.
DASHBOARD_ORIGIN = 'https://zxwan520.com:63012'
ALLOW = {
 '10-Review': ROOT/'10-Review', '20-Knowledge': ROOT/'20-Knowledge',
 '30-Projects': ROOT/'30-Projects', '40-Memory': ROOT/'40-Memory',
 '50-Journal': ROOT/'50-Journal'}
DENY = {'00-Inbox','90-Archive','90-Private','Private','KnowledgeAssets'}


def require_dashboard_session(request):
    """Require the verified Hermes session attached by its auth middleware."""
    if getattr(request.app.state, 'auth_required', False) is not True:
        raise HTTPException(status_code=403, detail='Authenticated Dashboard mode required')
    session = getattr(request.state, 'session', None)
    user_id = getattr(session, 'user_id', '') if session else ''
    if not user_id or getattr(session, 'provider', '') != 'basic':
        raise HTTPException(status_code=401, detail='Dashboard login required')
    if getattr(session, 'expires_at', 0) <= datetime.now(timezone.utc).timestamp():
        raise HTTPException(status_code=401, detail='Dashboard session expired')
    origin = request.headers.get('origin', '').rstrip('/')
    if origin:
        # Compare against the public TLS origin. request.base_url can reflect the
        # internal HTTP hop when DSM terminates TLS before Hermes.
        if origin != DASHBOARD_ORIGIN:
            raise HTTPException(status_code=403, detail='Same-origin request required')
    else:
        # Fetch does not guarantee Origin on same-origin GET. Accept browser
        # metadata that identifies the exact same-origin fetch; never use it as
        # identity, which still comes only from Hermes' verified session above.
        fetch_site = request.headers.get('sec-fetch-site', '').lower()
        referer = request.headers.get('referer', '')
        try:
            parsed_referer = urlsplit(referer)
            referer_origin = f'{parsed_referer.scheme}://{parsed_referer.netloc}'
        except ValueError:
            referer_origin = ''
        if fetch_site == 'cross-site' or (
                fetch_site != 'same-origin' and referer_origin != DASHBOARD_ORIGIN):
            raise HTTPException(status_code=403, detail='Same-origin request required')
    return user_id


def read_review(review_root, review_path):
    """Read one regular Markdown file below Review without following links."""
    if (not isinstance(review_path, str) or not review_path or '\\' in review_path
            or '\x00' in review_path or review_path.startswith('/')):
        raise FileNotFoundError
    parts = review_path.split('/')
    if any(part in {'', '.', '..'} for part in parts):
        raise FileNotFoundError
    root_fd = os.open(review_root, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0)
                      | getattr(os, 'O_NOFOLLOW', 0))
    current_fd = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            next_fd = os.open(part, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0)
                              | getattr(os, 'O_NOFOLLOW', 0), dir_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd
        file_fd = os.open(parts[-1], os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0),
                          dir_fd=current_fd)
        try:
            if not stat.S_ISREG(os.fstat(file_fd).st_mode):
                raise FileNotFoundError
            chunks = []
            while True:
                chunk = os.read(file_fd, 65536)
                if not chunk:
                    return b''.join(chunks)
                chunks.append(chunk)
        finally:
            os.close(file_fd)
    except OSError as exc:
        raise FileNotFoundError from exc
    finally:
        os.close(current_fd)
        os.close(root_fd)


def review_status(content):
    try:
        lines = content.decode('utf-8').splitlines()
    except UnicodeDecodeError:
        return 'unknown'
    if not lines or lines[0].strip() != '---':
        return 'unknown'
    for line in lines[1:]:
        if line.strip() == '---':
            break
        match = re.match(r"^(review_status|status):\s*['\"]?([^'\"]+)['\"]?\s*$", line)
        if match:
            return match.group(2).strip()
    return 'unknown'

def title_of(p):
 try:
  for line in p.read_text(errors='replace').splitlines():
   if line.startswith('# '): return line[2:].strip()
   if line.lower().startswith('title:'): return line.split(':',1)[1].strip().strip('"')
 except OSError: pass
 return p.stem

def proof():
 return {'status':'ok','area':'30-Projects','title':'SecondBrain V1 — Current State','source_type':'project'}

def list_items(root, limit=5):
 if not root.exists(): return []
 files=sorted([p for p in root.rglob('*') if p.is_file() and not any(x in p.parts for x in ['90-Private','Private','90-Archive'])], key=lambda p:p.stat().st_mtime, reverse=True)
 return [{'title':title_of(p),'updated':int(p.stat().st_mtime)} for p in files[:limit]]

@router.get('/proof')
def secondbrain_proof(): return proof()

@router.get('/policy-probe/{area}')
def policy_probe(area: str):
 return {'status':'denied','reason':'policy'} if area in DENY or area not in ALLOW else {'status':'allowed'}

@router.get('/home')
def secondbrain_home():
 today_path=ALLOW['50-Journal']/(date.today().isoformat()+'.md')
 today={'status':'empty'} if not today_path.exists() else {'status':'real','date':date.today().isoformat(),'title':title_of(today_path)}
 review_items=list_items(ALLOW['10-Review'],5)
 project_items=[{'title':x['title'],'updated':x['updated']} for x in list_items(ALLOW['30-Projects'],5)]
 knowledge_items=list_items(ALLOW['20-Knowledge'],5)
 return {'status':'ok','agent':{'status':'online'},'today':today,'review':{'status':'real' if review_items else 'empty','pending_count':len(review_items),'items':review_items},'projects':{'status':'real' if project_items else 'empty','items':project_items},'knowledge':{'status':'real' if knowledge_items else 'empty','items':knowledge_items},'brief':{'status':'not_connected'},'activity':{'status':'not_connected','items':[]}}


@router.get('/review/items')
def list_review_items(request: Request):
    require_dashboard_session(request)
    items = []
    for current, dirs, files in os.walk(REVIEW_ROOT, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not os.path.islink(os.path.join(current, d)))
        for name in sorted(files):
            if not name.lower().endswith('.md'):
                continue
            absolute = os.path.join(current, name)
            if os.path.islink(absolute):
                continue
            relative = os.path.relpath(absolute, REVIEW_ROOT).replace(os.sep, '/')
            try:
                content = read_review(REVIEW_ROOT, relative)
            except (FileNotFoundError, PermissionError):
                continue
            decoded = content.decode('utf-8', errors='replace')
            title = next((line[2:].strip() for line in decoded.splitlines()
                          if line.startswith('# ')), Path(name).stem)
            items.append({
                'review_path': relative,
                'review_sha256': hashlib.sha256(content).hexdigest(),
                'target_filename': name,
                'title': title,
                'status': review_status(content),
            })
    return {'status': 'ok', 'items': items}


@router.get('/review/items/{review_path:path}')
def get_review_item(request: Request, review_path: str):
    require_dashboard_session(request)
    try:
        content = read_review(REVIEW_ROOT, review_path)
    except (FileNotFoundError, PermissionError):
        raise HTTPException(status_code=404, detail='Review item not found')
    decoded = content.decode('utf-8', errors='replace')
    title = next((line[2:].strip() for line in decoded.splitlines()
                  if line.startswith('# ')), Path(review_path).name)
    return {
        'status': review_status(content),
        'review_path': review_path,
        'review_sha256': hashlib.sha256(content).hexdigest(),
        'target_filename': Path(review_path).name,
        'title': title,
        'content': decoded,
    }
