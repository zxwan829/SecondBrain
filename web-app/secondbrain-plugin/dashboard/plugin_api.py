from fastapi import APIRouter
from pathlib import Path
from datetime import date
import re
router = APIRouter()
ROOT = Path('/secondbrain')
ALLOW = {
 '10-Review': ROOT/'10-Review', '20-Knowledge': ROOT/'20-Knowledge',
 '30-Projects': ROOT/'30-Projects', '40-Memory': ROOT/'40-Memory',
 '50-Journal': ROOT/'50-Journal'}
DENY = {'00-Inbox','90-Archive','90-Private','Private','KnowledgeAssets'}

def title_of(p):
 try:
  for line in p.read_text(errors='replace').splitlines():
   if line.startswith('# '): return line[2:].strip()
   if line.lower().startswith('title:'): return line.split(':',1)[1].strip().strip('"')
 except OSError: pass
 return p.stem

def proof():
 p=ALLOW['30-Projects']/'SecondBrain V1'/'00-CURRENT.md'
 return {'status':'ok','area':'30-Projects','title':title_of(p),'source_type':'project'}

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
