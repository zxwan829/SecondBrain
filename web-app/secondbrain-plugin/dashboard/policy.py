from pathlib import Path
ALLOWED_AREAS={"20-Knowledge":Path("/secondbrain/20-Knowledge"),"30-Projects":Path("/secondbrain/30-Projects"),"40-Memory":Path("/secondbrain/40-Memory"),"50-Journal":Path("/secondbrain/50-Journal")}
DENIED_AREAS={"00-Inbox","10-Review","90-Archive","90-Private","Private","KnowledgeAssets"}
def proof():
 area="30-Projects"; root=ALLOWED_AREAS[area]; target=(root/"SecondBrain V1"/"00-CURRENT.md").resolve()
 if root.resolve() not in target.parents: raise PermissionError("policy denied")
 text=target.read_text(errors="replace"); title=next((x[2:].strip() for x in text.splitlines() if x.startswith("# ")),"SecondBrain V1 — 00-CURRENT")
 return {"status":"ok","area":area,"title":title,"source_type":"project"}
def policy_probe(area): return {"status":"denied","reason":"policy"} if area in DENIED_AREAS or area not in ALLOWED_AREAS else {"status":"allowed"}
