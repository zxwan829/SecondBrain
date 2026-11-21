"""Authority-owned static page. Candidate text is rendered only as text."""
HTML = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>Knowledge 审核</title>
<h1>Knowledge 审核</h1><p>此页面使用独立审批登录。</p>
<label>审批密码 <input id="password" type="password" autocomplete="current-password"></label><button id="login">登录</button>
<h2>登记来源</h2><label>原文<textarea id="raw" rows="8"></textarea></label><button id="register">登记原文</button><p id="registered"></p>
<h2>创建候选</h2><label>来源 ID <input id="capture"></label><label>目标 ID <input id="target"></label><label>候选正文<textarea id="content" rows="12"></textarea></label><button id="preview">生成精确预览</button>
<h2>精确预览</h2><p id="metadata"></p><pre id="result"></pre><label><input id="agree" type="checkbox">我已核对完整正文、来源和目标</label><button id="confirm" disabled>确认入库</button><p id="status" role="status"></p><script src="/authority.js" defer></script></html>'''
JS = ''''use strict';
let preview = null;
const node = id => document.getElementById(id);
const status = value => { node('status').textContent = value; };
async function post(path, body) {
  const response = await fetch(path, {method: 'POST', credentials: 'same-origin', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body)});
  if (!response.ok) throw new Error('操作未完成，请重新检查状态。');
  return response.json();
}
node('login').onclick = async () => { try { await post('/login', {password:node('password').value}); node('password').value=''; status('登录成功'); } catch(e) { status(e.message); } };
node('register').onclick = async () => { try {
  const bytes = new TextEncoder().encode(node('raw').value); let binary='';
  for (const b of bytes) binary += String.fromCharCode(b);
  const r = await post('/sources', {intent:'register_source',raw_base64:btoa(binary)});
  node('capture').value = r.capture_id; node('registered').textContent = '来源 ID: '+r.capture_id; status('来源已登记');
} catch(e) { status(e.message); } };
node('preview').onclick = async () => { preview=null; node('agree').checked=false; node('confirm').disabled=true;
  try { preview=await post('/candidates', {capture_id:node('capture').value,target_id:node('target').value,content:node('content').value});
    node('metadata').textContent='来源: '+preview.capture_id+' / '+preview.raw_ref+' / '+preview.raw_sha256+'；Review: '+preview.review_ref+' / '+preview.review_sha256+'；目标: '+preview.target_id;
    node('result').textContent=preview.content; status('请核对完整预览');
  } catch(e) { node('metadata').textContent=''; node('result').textContent=''; status(e.message); }
};
node('agree').onchange = () => { node('confirm').disabled=!(preview && node('agree').checked); };
node('confirm').onclick = async () => { const p=preview; preview=null; node('confirm').disabled=true; node('agree').checked=false;
  if (!p) return; try { const r=await post('/confirm', {intent:'promote_exact_preview',snapshot_id:p.snapshot_id,binding:p.binding}); status('操作状态: '+r.status); }
  catch(e) { status('未确认完成；请查询操作状态，勿重复提交。'); }
};'''
