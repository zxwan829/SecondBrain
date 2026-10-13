(()=>{const sdk=window.__HERMES_PLUGIN_SDK__,reg=window.__HERMES_PLUGINS__;if(!sdk||!reg)throw new Error('SDK unavailable');const R=sdk.React,{useState,useEffect}=sdk.hooks;function App(){const[en,setEn]=useState(false),[d,setD]=useState(null),[err,setErr]=useState(false);useEffect(()=>{if(new URLSearchParams(location.search).get('sb_debug')!=='layout')return;const panel=document.createElement('section');panel.id='secondbrain-layout-diagnostic';panel.style.cssText='position:fixed;z-index:2147483647;inset:8px;max-height:calc(100vh - 16px);overflow:auto;padding:12px;background:#07101eee;color:#dce8ff;border:1px solid #7ea7ff;border-radius:8px;font:12px/1.45 monospace;white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word;max-width:100%;box-sizing:border-box;user-select:text';const title=document.createElement('strong');title.textContent='SecondBrain layout diagnostic';const copy=document.createElement('button');copy.textContent='Copy all diagnostic results';copy.style.cssText='display:block;margin:8px 0;padding:7px 10px;color:#07101e;background:#9fc1ff;border:0;border-radius:5px';const out=document.createElement('textarea');out.readOnly=true;out.style.cssText='display:block;width:100%;min-height:360px;max-width:100%;box-sizing:border-box;white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word;background:#0b1526;color:#dce8ff;border:1px solid #496b9e;padding:8px;font:12px/1.45 monospace';panel.append(title,copy,out);document.body.appendChild(panel);const f=(n,e)=>{if(!e)return{name:n,missing:true};const r=e.getBoundingClientRect(),c=getComputedStyle(e);return{name:n,top:r.top,height:r.height,display:c.display,position:c.position,paddingTop:c.paddingTop,marginTop:c.marginTop,transform:c.transform}};const q=x=>document.querySelector(x);const rows=[f('html',document.documentElement),f('body',document.body),f('#root',q('#root')),f('Hermes mobile header',q('header[class*=\"lg:hidden\"][class*=\"fixed\"][class*=\"top-0\"]')),f('Hermes mobile spacer',q('[aria-hidden].h-14')),f('Hermes content wrapper',q('#root .relative.z-2.flex.min-w-0')),f('SecondBrain plugin root',q('.sb-shell')),f('SecondBrain mobile header',q('.sb-nav-head'))];const hs=document.querySelector('header[class*=\"lg-hidden\"][class*=\"fixed\"][class*=\"top-0\"]'),sp=document.querySelector('[aria-hidden][class*=\"h-14\"][class*=\"lg-hidden\"]');const lines=['Mode: sb_debug=layout','CLIENT-SIDE ONLY','immersiveActive: '+(document.body.getAttribute('data-secondbrain-immersive')==='true'),'headerSelectorMatched: '+!!hs,'spacerSelectorMatched: '+!!sp,'overrideStyleInstalled: '+!!document.getElementById('secondbrain-host-overrides'),'expectedHeaderDisplay: none','actualHeaderDisplay: '+(hs?getComputedStyle(hs).display:'missing'),'expectedSpacerDisplay: none','actualSpacerDisplay: '+(sp?getComputedStyle(sp).display:'missing'), 'Current asset version: '+(q('.sb-shell')?.getAttribute('data-secondbrain-ui-build')||'unknown'),'', 'Current build marker: '+(q('.sb-shell')?.getAttribute('data-secondbrain-ui-build')||'unknown'),'Viewport: innerHeight='+innerHeight+' visualViewportHeight='+(visualViewport?visualViewport.height:'unknown')+' clientHeight='+document.documentElement.clientHeight,''];rows.forEach(x=>{lines.push('['+x.name+']');Object.keys(x).filter(k=>k!=='name').forEach(k=>lines.push(k+': '+x[k]));lines.push('')});const h=rows[7];lines.push('Top gap decomposition:','VIEWPORT_TOP: 0','SECOND_BRAIN_HEADER_TOP: '+(h.missing?'UNKNOWN':h.top),'ACTUAL_GAP_PX: '+(h.missing?'UNKNOWN':h.top));out.value=lines.join(String.fromCharCode(10));copy.onclick=()=>{if(navigator.clipboard&&navigator.clipboard.writeText)navigator.clipboard.writeText(out.value).catch(()=>{out.focus();out.select()});else{out.focus();out.select()}};return()=>panel.remove()},[]);useEffect(()=>{try{setEn(localStorage.getItem('secondbrain.locale')==='en')}catch(e){}document.body.classList.add('secondbrain-immersive');document.body.setAttribute('data-secondbrain-immersive','true');document.documentElement.setAttribute('data-secondbrain-active','true');const hostHeader=document.querySelector('header[class*=\"lg:hidden\"][class*=\"fixed\"][class*=\"top-0\"]'),hostSpacer=document.querySelector('[aria-hidden][class*=\"h-14\"][class*=\"lg:hidden\"]'),hostWrap=document.querySelector('#root .relative.z-2.flex.min-w-0');const oldHeader=hostHeader?hostHeader.getAttribute('style'):null,oldSpacer=hostSpacer?hostSpacer.getAttribute('style'):null,oldWrap=hostWrap?hostWrap.getAttribute('style'):null;if(hostHeader)hostHeader.style.setProperty('display','none','important');if(hostSpacer)hostSpacer.style.setProperty('display','none','important');if(hostWrap){hostWrap.style.setProperty('padding-top','0','important');hostWrap.style.setProperty('margin-top','0','important');hostWrap.style.setProperty('top','auto','important');hostWrap.style.setProperty('transform','none','important')}const z=document.createElement('style');z.id='secondbrain-host-overrides';z.textContent='body[data-secondbrain-immersive=\"true\"] header.fixed.top-0[class*=\"lg:hidden\"]{display:none!important}body[data-secondbrain-immersive=\"true\"] [aria-hidden].h-14{display:none!important}';document.head.appendChild(z);sdk.fetchJSON('/api/plugins/secondbrain/home').then(setD).catch(()=>setErr(true));return()=>{document.body.classList.remove('secondbrain-immersive');document.body.removeAttribute('data-secondbrain-immersive');document.documentElement.removeAttribute('data-secondbrain-active');if(hostHeader){if(oldHeader===null)hostHeader.removeAttribute('style');else hostHeader.setAttribute('style',oldHeader)}if(hostSpacer){if(oldSpacer===null)hostSpacer.removeAttribute('style');else hostSpacer.setAttribute('style',oldSpacer)}if(hostWrap){if(oldWrap===null)hostWrap.removeAttribute('style');else hostWrap.setAttribute('style',oldWrap)}const z=document.getElementById('secondbrain-host-overrides');if(z)z.remove()}},[]);const t=en?{lang:'EN',agent:'Agent Status',title:'Your workspace',desc:'A clear view of what is happening now',home:'Home',chat:'Chat',today:'Today',inbox:'Inbox',review:'Review',projects:'Projects',knowledge:'Knowledge',brief:'Brief',activity:'Activity',waiting:'Waiting for Me',recent:'Recent Knowledge',actions:'Quick Actions',loading:'Loading',error:'Something went wrong',empty:'No content',offline:'Not connected',online:'Online',available:'Connected'}:{lang:'中文',agent:'智能助手',title:'你的工作台',desc:'一眼掌握当前状态',home:'首页',chat:'对话',today:'今日',inbox:'收件箱',review:'待审核',projects:'项目',knowledge:'知识库',brief:'简报',activity:'动态',waiting:'待审核',recent:'最近知识',actions:'快捷操作',loading:'加载中',error:'暂时无法加载',empty:'暂无内容',offline:'尚未接入',online:'在线',available:'已接入'};function st(x){return x==='online'?t.online:x==='not_connected'?t.offline:x==='empty'?t.empty:x==='real'?t.available:x||''}function list(x){if(!x||!x.items||!x.items.length)return R.createElement('p',{className:'sb-card-empty'},t.empty);return R.createElement('ul',{className:'sb-card-list'},x.items.map((i,n)=>R.createElement('li',{key:n},i.title||'')))}function card(title,x){return R.createElement('section',{className:'sb-card'},R.createElement('div',{className:'sb-card-head'},R.createElement('h3',null,title),R.createElement('span',{className:'sb-card-status'},st(x&&x.status))),list(x))}function toggle(){const n=!en;setEn(n);try{localStorage.setItem('secondbrain.locale',n?'en':'zh-CN')}catch(e){}}const nav=['home','chat','today','inbox','review','projects','knowledge','brief','activity'];const aside=R.createElement('aside',{className:'sb-nav'},R.createElement('div',{className:'sb-nav-head'},R.createElement('h1',null,'SecondBrain'),R.createElement('button',{className:'sb-locale',onClick:toggle},t.lang)),nav.map(n=>R.createElement('button',{key:n,onClick:()=>{if(n==='chat')location.href='/chat'}},t[n])));let body=R.createElement('p',{className:'sb-state'},t.loading);if(err)body=R.createElement('p',{className:'sb-state'},t.error);if(d){const quick=R.createElement('section',{className:'sb-command-bar'},R.createElement('h3',null,t.actions),R.createElement('div',{className:'sb-actions'},R.createElement('button',{onClick:()=>location.href='/chat'},t.chat),R.createElement('button',{onClick:()=>location.href='/review'},t.review),R.createElement('button',{disabled:true},en?'Quick Capture':'快速收录'),R.createElement('button',{disabled:true},en?'New Journal Entry':'新建日记')));body=R.createElement('div',{className:'sb-grid'},card(t.agent,d.agent),card(t.today,d.today),card(t.waiting,d.review),card(t.projects,d.projects),card(t.recent,d.knowledge),card(t.brief,d.brief),card(t.activity,d.activity),quick)}const kpi=R.createElement('div',{className:'sb-kpi-row'},R.createElement('div',{className:'sb-kpi'},R.createElement('span',null,en?'Pending':'待审核'),R.createElement('strong',null,d&&d.review?d.review.pending_count||'—':'—'),R.createElement('small',null,en?'items awaiting review':'待审核条目')),R.createElement('div',{className:'sb-kpi'},R.createElement('span',null,t.projects),R.createElement('strong',null,d&&d.projects&&d.projects.items?d.projects.items.length:'—'),R.createElement('small',null,en?'active areas':'项目概览')),R.createElement('div',{className:'sb-kpi'},R.createElement('span',null,t.knowledge),R.createElement('strong',null,d&&d.knowledge&&d.knowledge.items?d.knowledge.items.length:'—'),R.createElement('small',null,en?'recent entries':'最近条目')),R.createElement('div',{className:'sb-kpi'},R.createElement('span',null,t.agent),R.createElement('strong',null,d&&d.agent&&d.agent.status==='online'?'●':'—'),R.createElement('small',null,d&&d.agent&&d.agent.status==='online'?t.online:t.offline)));const main=R.createElement('main',{className:'sb-main'},R.createElement('h2',null,t.title),R.createElement('p',null,t.desc),kpi,body);return R.createElement('div',{className:'sb-shell','data-secondbrain-ui-build':'2026-10-10-phase2b-0.9S-hostfix'},aside,main)}reg.register('secondbrain',App)})();
/* Additive Review view for the existing FE-4 plugin. Promote stays disabled. */
(() => {
  const DASHBOARD_API = "/api/plugins/secondbrain";
  const STYLE_ID = "sb-core-review-style";
  const DIALOG_ID = "sb-core-review-dialog";
  if (window.__SB_CORE_REVIEW_VIEW__) return;
  window.__SB_CORE_REVIEW_VIEW__ = true;

  let items = [];
  let statusNode;
  let listNode;
  let detailTitleNode;
  let detailMetaNode;
  let detailContentNode;
  let locked = true;

  const text = (zh, en) => localStorage.getItem("secondbrain.locale") === "en" ? en : zh;

  async function request(path, options = {}) {
    const response = await fetch(DASHBOARD_API + path, {
      credentials: "include",
      ...options,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    });
    let payload = {};
    try { payload = await response.json(); } catch {}
    if (!response.ok) {
      const error = new Error(payload.detail || ("Dashboard HTTP " + response.status));
      error.status = response.status;
      throw error;
    }
    return payload;
  }

  function addStyles() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent =
      "#" + DIALOG_ID + "{position:fixed;inset:0;z-index:2147483000;background:#050916d9;display:grid;place-items:center;padding:18px;color:#edf4ff;font:14px Inter,ui-sans-serif,system-ui,sans-serif}" +
      "#" + DIALOG_ID + "[hidden],#" + DIALOG_ID + " [hidden]{display:none!important}" +
      "#" + DIALOG_ID + " .sb-core-panel{width:min(980px,100%);max-height:min(88vh,900px);overflow:auto;background:#111a34;border:1px solid #34446b;border-radius:16px;box-shadow:0 28px 90px #0009;padding:20px}" +
      "#" + DIALOG_ID + " .sb-core-head{display:flex;justify-content:space-between;align-items:center;gap:12px;border-bottom:1px solid #2a385a;padding-bottom:12px}" +
      "#" + DIALOG_ID + " h2{margin:0;font-size:18px}#" + DIALOG_ID + " h3{margin:18px 0 6px;font-size:16px}" +
      "#" + DIALOG_ID + " button{border:1px solid #394a73;background:#192448;color:#e4ebff;border-radius:8px;padding:8px 11px;cursor:pointer}" +
      "#" + DIALOG_ID + " button:disabled{opacity:.48;cursor:not-allowed}" +
      "#" + DIALOG_ID + " .sb-core-status{color:#aab9d7;min-height:22px;margin:12px 0}" +
      "#" + DIALOG_ID + " input{flex:1;min-width:0;border:1px solid #35466c;border-radius:8px;background:#080f22;color:#eef3ff;padding:9px 10px}" +
      "#" + DIALOG_ID + " .sb-core-list{display:grid;grid-template-columns:minmax(220px,.8fr) minmax(0,1.2fr);gap:16px}" +
      "#" + DIALOG_ID + " .sb-core-rows{border-top:1px solid #2a3858;max-height:52vh;overflow:auto}" +
      "#" + DIALOG_ID + " .sb-core-item{width:100%;display:flex;flex-direction:column;align-items:flex-start;gap:5px;text-align:left;border:0!important;border-bottom:1px solid #2a3858!important;border-radius:0!important;background:transparent!important;padding:12px 4px!important}" +
      "#" + DIALOG_ID + " .sb-core-item[aria-current=true]{background:#202d50!important}" +
      "#" + DIALOG_ID + " .sb-core-item strong,#" + DIALOG_ID + " .sb-core-item small{overflow-wrap:anywhere}" +
      "#" + DIALOG_ID + " .sb-core-item small,#" + DIALOG_ID + " .sb-core-detail-meta{display:block;color:#92a2c4;font-size:12px}" +
      "#" + DIALOG_ID + " .sb-core-detail{min-width:0;border:1px solid #2a3858;border-radius:10px;padding:14px;background:#0c1429}" +
      "#" + DIALOG_ID + " .sb-core-content{white-space:pre-wrap;overflow-wrap:anywhere;max-height:48vh;overflow:auto;margin:12px 0 0;color:#e5ecfa;font:13px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace}" +
      "#" + DIALOG_ID + " .sb-core-note{color:#ffcf91;font-size:12px;line-height:1.5}" +
      "@media(max-width:700px){#" + DIALOG_ID + " .sb-core-list{grid-template-columns:1fr}#" + DIALOG_ID + " .sb-core-rows{max-height:30vh}}";
    document.head.appendChild(style);
  }

  function makeDialog() {
    const existing = document.getElementById(DIALOG_ID);
    if (existing) return existing;
    addStyles();
    const overlay = document.createElement("div");
    overlay.id = DIALOG_ID;
    overlay.hidden = true;
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("aria-labelledby", "sb-core-title");
    overlay.innerHTML = '<section class="sb-core-panel"><header class="sb-core-head"><h2 id="sb-core-title"></h2><div><button type="button" data-refresh hidden></button> <button type="button" data-close></button></div></header><p class="sb-core-status" aria-live="polite"></p><p class="sb-core-note"></p><div class="sb-core-list"><div class="sb-core-rows" role="list"></div><article class="sb-core-detail"><h3></h3><small class="sb-core-detail-meta"></small><pre class="sb-core-content"></pre></article></div></section>';
    overlay.querySelector("h2").textContent = text("待审核 · Review", "Review queue");
    overlay.querySelector("[data-close]").textContent = text("关闭", "Close");
    overlay.querySelector("[data-refresh]").textContent = text("刷新列表", "Refresh");
    overlay.querySelector(".sb-core-note").textContent = text(
      "Review 内容通过已登录的 Hermes Dashboard 会话读取；Promote 当前关闭，本视图仅供查看。",
      "Review content uses your authenticated Hermes Dashboard session. Promote is disabled; this view is read-only."
    );
    statusNode = overlay.querySelector(".sb-core-status");
    listNode = overlay.querySelector(".sb-core-rows");
    detailTitleNode = overlay.querySelector(".sb-core-detail h3");
    detailMetaNode = overlay.querySelector(".sb-core-detail-meta");
    detailContentNode = overlay.querySelector(".sb-core-content");
    overlay.querySelector("[data-close]").addEventListener("click", () => { overlay.hidden = true; });
    overlay.querySelector("[data-refresh]").addEventListener("click", loadItems);
    document.body.appendChild(overlay);
    setLocked(true);
    return overlay;
  }

  function setLocked(value) {
    locked = value;
    const dialog = document.getElementById(DIALOG_ID);
    if (!dialog) return;
    dialog.querySelector("[data-refresh]").hidden = value;
    if (value) {
      items = [];
      renderItems();
      detailTitleNode.textContent = text("登录后选择条目", "Sign in to select an item");
      detailMetaNode.textContent = "";
      detailContentNode.textContent = "";
    }
  }

  function renderItems() {
    if (!listNode) return;
    listNode.replaceChildren();
    if (!items.length) {
      const empty = document.createElement("p");
      empty.textContent = locked ? text("请登录 Dashboard 后加载 Review 列表。", "Sign in to Dashboard to load the Review list.") : text("暂无待审核条目", "No Review items");
      listNode.appendChild(empty);
      return;
    }
    for (const item of items) {
      const row = document.createElement("button");
      row.type = "button";
      row.className = "sb-core-item";
      row.setAttribute("role", "listitem");
      row.setAttribute("aria-current", "false");
      const title = document.createElement("strong");
      const filename = document.createElement("small");
      const state = document.createElement("small");
      title.textContent = item.title || item.target_filename;
      filename.textContent = item.target_filename || item.review_path;
      state.textContent = text("状态", "Status") + ": " + (item.status || "unknown");
      row.append(title, filename, state);
      row.addEventListener("click", () => loadDetail(item, row));
      listNode.appendChild(row);
    }
  }

  async function loadItems() {
    statusNode.textContent = text("正在读取 Review…", "Loading Review…");
    try {
      const data = await request("/review/items");
      items = Array.isArray(data.items) ? data.items : [];
      setLocked(false);
      statusNode.textContent = text(
        "已连接 Dashboard · " + items.length + " 条真实 Review · Promote 关闭",
        "Connected to Dashboard · " + items.length + " real Review items · Promote disabled"
      );
      renderItems();
      if (items.length) await loadDetail(items[0], listNode.firstElementChild);
    } catch (error) {
      items = [];
      renderItems();
      setLocked(true);
      statusNode.textContent = error.status === 401
        ? text("请先登录 Hermes Dashboard。", "Sign in to Hermes Dashboard to continue.")
        : error.message || text("Review 读取失败", "Could not load Review");
    }
  }

  async function loadDetail(item, row) {
    if (locked) return;
    for (const element of listNode.children) element.setAttribute("aria-current", "false");
    if (row) row.setAttribute("aria-current", "true");
    detailTitleNode.textContent = item.title || item.target_filename;
    detailMetaNode.textContent = text("正在读取内容…", "Loading content…");
    detailContentNode.textContent = "";
    try {
      const safePath = String(item.review_path).split("/").map(encodeURIComponent).join("/");
      const detail = await request("/review/items/" + safePath);
      detailMetaNode.textContent = detail.target_filename + " · " + text("状态", "Status") + ": " + (detail.status || "unknown");
      detailContentNode.textContent = detail.content || "";
    } catch (error) {
      detailMetaNode.textContent = error.status === 401
        ? text("Dashboard 会话已失效，请重新登录。", "Dashboard session expired; sign in again.")
        : error.message || text("无法读取条目详情", "Could not load the item detail");
      if (error.status === 401) setLocked(true);
    }
  }

  // Hermes session authentication is enforced by the plugin API on every read.

  async function openReview() {
    const dialog = makeDialog();
    dialog.hidden = false;
    await loadItems();
  }

  function attach() {
    const card = document.getElementById("waiting");
    const header = card && card.querySelector(".module-title");
    if (header) {
      addStyles();
      let button = header.querySelector("#sb-core-promote-open, #sb-core-review-open");
      if (!button) {
        button = document.createElement("button");
        button.id = "sb-core-review-open";
        button.type = "button";
        header.appendChild(button);
      }
      button.textContent = text("查看完整列表", "Open Review");
      if (button.dataset.sbCoreReviewBound !== "true") {
        button.dataset.sbCoreReviewBound = "true";
        button.addEventListener("click", (event) => {
          event.preventDefault();
          event.stopImmediatePropagation();
          openReview();
        }, true);
      }
    }
    for (const navButton of document.querySelectorAll(".nav-item")) {
      const label = navButton.querySelector(".nav-label");
      const value = label && label.textContent.trim();
      if (value !== "待审核" && value !== "Review") continue;
      if (navButton.dataset.sbReviewBound === "true") continue;
      navButton.dataset.sbReviewBound = "true";
      navButton.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopImmediatePropagation();
        openReview();
      }, true);
    }
  }

  new MutationObserver(attach).observe(document.documentElement, { childList: true, subtree: true });
  attach();
})();
