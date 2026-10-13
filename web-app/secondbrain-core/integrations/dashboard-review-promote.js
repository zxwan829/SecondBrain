/* Additive Review view for the existing FE-4 plugin. Promote stays disabled. */
(() => {
  const DASHBOARD_ORIGIN = "https://zxwan520.com:63012";
  const CORE = "https://zxwan520.com:63013/api/promote";
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
  let unlockFormNode;
  let passphraseNode;
  let locked = true;

  const text = (zh, en) => localStorage.getItem("secondbrain.locale") === "en" ? en : zh;

  async function request(path, options = {}) {
    const response = await fetch(CORE + path, {
      credentials: "include",
      mode: "cors",
      ...options,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    });
    let payload = {};
    try { payload = await response.json(); } catch {}
    if (!response.ok) {
      const error = new Error(payload.detail || ("Core HTTP " + response.status));
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
      "#" + DIALOG_ID + " .sb-core-unlock{display:flex;gap:8px;margin:10px 0 16px}" +
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
    overlay.innerHTML = '<section class="sb-core-panel"><header class="sb-core-head"><h2 id="sb-core-title"></h2><div><button type="button" data-lock hidden></button> <button type="button" data-close></button></div></header><p class="sb-core-status" aria-live="polite"></p><form class="sb-core-unlock"><input type="password" autocomplete="current-password" required><button type="submit"></button></form><p class="sb-core-note"></p><div class="sb-core-list"><div class="sb-core-rows" role="list"></div><article class="sb-core-detail"><h3></h3><small class="sb-core-detail-meta"></small><pre class="sb-core-content"></pre></article></div></section>';
    overlay.querySelector("h2").textContent = text("待审核 · Review", "Review queue");
    overlay.querySelector("[data-close]").textContent = text("关闭", "Close");
    overlay.querySelector("[data-lock]").textContent = text("锁定 Core", "Lock Core");
    overlay.querySelector(".sb-core-unlock button").textContent = text("解锁 Core", "Unlock Core");
    overlay.querySelector(".sb-core-unlock input").placeholder = text("Core 专属解锁口令", "Core-only passphrase");
    overlay.querySelector(".sb-core-note").textContent = text(
      "Review 内容通过 Core 会话读取；Promote 当前关闭，本视图仅供查看。",
      "Review content is read through the Core session. Promote is disabled; this view is read-only."
    );
    statusNode = overlay.querySelector(".sb-core-status");
    listNode = overlay.querySelector(".sb-core-rows");
    detailTitleNode = overlay.querySelector(".sb-core-detail h3");
    detailMetaNode = overlay.querySelector(".sb-core-detail-meta");
    detailContentNode = overlay.querySelector(".sb-core-content");
    unlockFormNode = overlay.querySelector(".sb-core-unlock");
    passphraseNode = overlay.querySelector(".sb-core-unlock input");
    overlay.querySelector("[data-close]").addEventListener("click", () => { overlay.hidden = true; });
    overlay.querySelector("[data-lock]").addEventListener("click", lockCore);
    unlockFormNode.addEventListener("submit", unlock);
    document.body.appendChild(overlay);
    setLocked(true);
    return overlay;
  }

  function setLocked(value) {
    locked = value;
    const dialog = document.getElementById(DIALOG_ID);
    if (!dialog) return;
    unlockFormNode.hidden = value;
    dialog.querySelector("[data-lock]").hidden = value;
    if (value) {
      items = [];
      renderItems();
      detailTitleNode.textContent = text("解锁后选择条目", "Unlock Core to select an item");
      detailMetaNode.textContent = "";
      detailContentNode.textContent = "";
    }
  }

  function renderItems() {
    if (!listNode) return;
    listNode.replaceChildren();
    if (!items.length) {
      const empty = document.createElement("p");
      empty.textContent = locked ? text("解锁后加载 Review 列表。", "Unlock Core to load the Review list.") : text("暂无待审核条目", "No Review items");
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
    if (location.origin !== DASHBOARD_ORIGIN) {
      statusNode.textContent = text("请通过 Dashboard HTTPS 入口使用 Core。", "Open this page through the Dashboard HTTPS endpoint.");
      return;
    }
    statusNode.textContent = text("正在读取 Core Review…", "Loading Core Review…");
    try {
      const data = await request("/review/items");
      items = Array.isArray(data.items) ? data.items : [];
      setLocked(false);
      statusNode.textContent = text(
        "已连接 Core · " + items.length + " 条真实 Review · Promote 关闭",
        "Connected to Core · " + items.length + " real Review items · Promote disabled"
      );
      renderItems();
      if (items.length) await loadDetail(items[0], listNode.firstElementChild);
    } catch (error) {
      items = [];
      renderItems();
      setLocked(true);
      statusNode.textContent = error.status === 401
        ? text("请先输入 Core 解锁口令。", "Unlock Core to continue.")
        : error.message || text("Core 连接失败", "Core connection failed");
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
        ? text("Core 会话已失效，请重新解锁。", "Core session expired; unlock again.")
        : error.message || text("无法读取条目详情", "Could not load the item detail");
      if (error.status === 401) setLocked(true);
    }
  }

  async function unlock(event) {
    event.preventDefault();
    if (location.origin !== DASHBOARD_ORIGIN) return;
    const button = unlockFormNode.querySelector("button");
    button.disabled = true;
    const passphrase = passphraseNode.value;
    passphraseNode.value = "";
    try {
      await request("/auth/unlock", { method: "POST", body: JSON.stringify({ passphrase }) });
      await loadItems();
    } catch (error) {
      statusNode.textContent = error.message || text("解锁失败", "Unlock failed");
    } finally {
      passphraseNode.value = "";
      button.disabled = false;
    }
  }

  async function lockCore() {
    try {
      await request("/auth/lock", { method: "POST", body: "{}" });
      setLocked(true);
      statusNode.textContent = text("Core 已锁定。", "Core locked.");
    } catch (error) {
      statusNode.textContent = error.message || text("锁定失败", "Could not lock Core");
    }
  }

  async function openReview() {
    const dialog = makeDialog();
    dialog.hidden = false;
    await loadItems();
  }

  function attach() {
    if (location.origin !== DASHBOARD_ORIGIN) return;
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
