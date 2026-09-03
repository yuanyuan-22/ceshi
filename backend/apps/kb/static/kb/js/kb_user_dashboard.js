let currentUserRole = "guest";
let currentEntityId = null;
let currentEntityPayload = null;
let currentUploadId = null;
let entityListCache = [];

const UPLOAD_STATUS_LABELS = {
  NEW: "新上传",
  PARSED: "已抽取候选",
  REVIEWED: "已审核",
  BUILD: "已构建",
};

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function showLoginPanel() {
  const panel = document.getElementById("kb_login_panel");
  if (panel) panel.style.display = "flex";
}

function hideLoginPanel() {
  const panel = document.getElementById("kb_login_panel");
  if (panel) panel.style.display = "none";
}

function formatUploadStatus(status) {
  const key = String(status || "").toUpperCase();
  return UPLOAD_STATUS_LABELS[key] || status || "";
}

function setRoleBadge(role) {
  const badge = document.getElementById("kbUserRoleBadge");
  const manageBtn = document.getElementById("kbManageEntry");
  if (badge) {
    if (role === "admin") badge.textContent = "管理员";
    else if (role === "user") badge.textContent = "普通用户";
    else badge.textContent = "访客";
  }
  if (manageBtn) manageBtn.style.display = role === "admin" ? "inline-flex" : "none";
}

function setUploadStatus(text, kind = "waiting") {
  const el = document.getElementById("kbUploadStatus");
  if (!el) return;
  el.textContent = text;
  el.className = `status-box ${kind}`;
}

function setUploadPreview(text) {
  const el = document.getElementById("kbUploadPreview");
  if (el) el.textContent = text || "暂无上传预览";
}

function setEntityMeta(payload) {
  const el = document.getElementById("kbSelectedEntityMeta");
  if (!el) return;
  if (!payload) {
    el.textContent = "尚未选择术语条目";
    return;
  }

  const langs = Object.keys(payload.langs || {}).filter(Boolean).join(", ");
  el.innerHTML = `
    <div><strong>术语:</strong> ${escapeHtml(((payload.langs || {}).zh || {}).term || payload.canonical_key || payload.entity_key || "")}</div>
    <div><strong>规范名:</strong> ${escapeHtml(payload.canonical_key || "")}</div>
    <div><strong>分类:</strong> ${escapeHtml(payload.category || "unknown")}</div>
    <div><strong>来源:</strong> ${escapeHtml(payload.source || "")}</div>
    <div><strong>语言:</strong> ${escapeHtml(langs || "-")}</div>
  `;
}

function renderUploadList(items) {
  const container = document.getElementById("kbUploadList");
  if (!container) return;

  if (!items.length) {
    container.innerHTML = '<div class="empty-box">暂无上传记录</div>';
    return;
  }

  container.innerHTML = items
    .map((item) => {
      const selected = currentUploadId === item.id ? " selected" : "";
      return `
        <button type="button" class="list-item${selected}" onclick="selectUpload(${item.id})">
          <div class="list-title">#${item.id} · ${escapeHtml(formatUploadStatus(item.status || ""))}</div>
          <div class="list-meta">
            类型: ${escapeHtml(item.file_type || "txt")}<br/>
            时间: ${escapeHtml(item.created_at || "")}
          </div>
          <div class="list-meta" style="margin-top:8px; color:#334155;">${escapeHtml(item.content_preview || "")}</div>
        </button>
      `;
    })
    .join("");
}

function renderEntities(items) {
  const container = document.getElementById("kbEntityList");
  if (!container) return;

  if (!items.length) {
    container.innerHTML = '<div class="empty-box">暂无可展示术语</div>';
    return;
  }

  container.innerHTML = items
    .map((item) => {
      const selected = currentEntityId === item.id ? " selected" : "";
      const title = item.zh_term || item.canonical_key || item.entity_key || `#${item.id}`;
      return `
        <button type="button" class="list-item${selected}" onclick="selectEntity(${item.id})">
          <div class="list-title">${escapeHtml(title)}</div>
          <div class="list-meta">
            规范名: ${escapeHtml(item.canonical_key || item.entity_key || "")}<br/>
            分类: ${escapeHtml(item.category || "unknown")}<br/>
            语言: ${escapeHtml((item.langs_present || []).join(", ") || "-")}
          </div>
        </button>
      `;
    })
    .join("");
}

function renderTermCards(cards) {
  const container = document.getElementById("kbTermCards");
  if (!container) return;

  if (!cards || !cards.length) {
    container.innerHTML = '<div class="empty-box">暂无术语卡片</div>';
    return;
  }

  container.innerHTML = cards
    .map(
      (card) => `
        <div class="term-card">
          <div class="term-head">
            <div class="term-main">${escapeHtml(card.term || "未命名术语")}</div>
            <span class="term-tag">${escapeHtml(card.lang || "")}</span>
          </div>
          <div class="term-explain">${escapeHtml(card.explain || "") || "暂无说明"}</div>
        </div>
      `
    )
    .join("");
}

function clearEntityPanel() {
  currentEntityPayload = null;
  setEntityMeta(null);
  renderTermCards([]);
}

async function parseResponse(res) {
  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return res.json();
  }
  const text = await res.text();
  return { error: text || `HTTP ${res.status}` };
}

async function ensureOk(res) {
  const data = await parseResponse(res);
  if (!res.ok) {
    throw new Error(data.error || data.detail || `请求失败，${res.status}`);
  }
  return data;
}

async function kbLogin() {
  const username = document.getElementById("kb_login_user").value.trim();
  const password = document.getElementById("kb_login_pwd").value.trim();
  const errorEl = document.getElementById("kb_login_error");

  if (!username || !password) {
    errorEl.textContent = "请输入用户名和密码。";
    return;
  }

  try {
    const res = await fetch("/api/auth/login/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const data = await ensureOk(res);
    localStorage.setItem("jwt_access", data.access);
    localStorage.setItem("jwt_refresh", data.refresh);
    errorEl.textContent = "";
    hideLoginPanel();
    await initKBUserPage();
  } catch (error) {
    errorEl.textContent = error.message || "登录失败。";
  }
}

async function kbRegister() {
  const username = document.getElementById("kb_login_user").value.trim();
  const password = document.getElementById("kb_login_pwd").value.trim();
  const errorEl = document.getElementById("kb_login_error");

  if (!username || !password) {
    errorEl.textContent = "请输入用户名和密码。";
    return;
  }

  try {
    const res = await fetch("/api/auth/register/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    await ensureOk(res);
    errorEl.style.color = "#15803d";
    errorEl.textContent = "注册成功，请继续登录。";
  } catch (error) {
    errorEl.style.color = "#e11d48";
    errorEl.textContent = error.message || "注册失败。";
  }
}

async function kbUpload() {
  if (currentUserRole === "guest") {
    window.location.href = "/login/";
    return;
  }

  const fileInput = document.getElementById("kb_file");
  const textArea = document.getElementById("kb_text");
  const file = fileInput.files[0];
  const text = textArea.value.trim();

  if (!file && !text) {
    alert("请上传文件或输入文本。");
    return;
  }

  setUploadStatus("正在上传...", "info");

  try {
    let res;
    if (file) {
      const form = new FormData();
      form.append("file", file);
      res = await authFetch("/api/kb/upload/", { method: "POST", body: form });
    } else {
      res = await authFetch("/api/kb/upload/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
    }

    const data = await ensureOk(res);
    currentUploadId = data.upload_id;
    setUploadStatus(`上传成功，记录 #${data.upload_id}`, "success");
    setUploadPreview(data.content_preview || "上传成功，但没有可预览文本。");
    fileInput.value = "";
    textArea.value = "";
    await loadUploads();
  } catch (error) {
    setUploadStatus(error.message || "上传失败。", "error");
  }
}

async function loadUploads() {
  try {
    const res = await authFetch("/api/kb/upload_list/", { method: "GET" });
    const data = await ensureOk(res);
    renderUploadList(data || []);
  } catch (error) {
    setUploadStatus(error.message || "加载上传记录失败。", "error");
  }
}

async function selectUpload(uploadId) {
  currentUploadId = uploadId;
  try {
    const res = await authFetch(`/api/kb/uploads/${uploadId}/`, { method: "GET" });
    const data = await ensureOk(res);
    setUploadPreview(data.content || data.content_preview || "暂无上传预览");
    await loadUploads();
  } catch (error) {
    setUploadStatus(error.message || "加载上传详情失败。", "error");
  }
}

async function loadEntities() {
  try {
    const res = await authFetch("/api/kb/entities/", { method: "GET" });
    const data = await ensureOk(res);
    entityListCache = data || [];
    filterTerms();
    if (!currentEntityId && entityListCache.length) {
      await selectEntity(entityListCache[0].id);
    }
  } catch (error) {
    clearEntityPanel();
    const container = document.getElementById("kbEntityList");
    if (container) container.innerHTML = `<div class="empty-box">${escapeHtml(error.message || "加载术语失败。")}</div>`;
  }
}

function filterTerms() {
  const keyword = String(document.getElementById("kbTermSearch")?.value || "").trim().toLowerCase();
  const items = !keyword
    ? entityListCache
    : entityListCache.filter((item) => {
        const haystack = [
          item.zh_term,
          item.canonical_key,
          item.entity_key,
          item.category,
          ...(item.langs_present || []),
        ]
          .join(" ")
          .toLowerCase();
        return haystack.includes(keyword);
      });
  renderEntities(items);
}

async function selectEntity(entityId) {
  currentEntityId = entityId;
  filterTerms();

  try {
    const res = await authFetch(`/api/kb/entities/${entityId}/`, { method: "GET" });
    const data = await ensureOk(res);
    currentEntityPayload = data;
    setEntityMeta(data);
    renderTermCards(data.term_cards || []);
    filterTerms();
  } catch (error) {
    clearEntityPanel();
  }
}

async function initKBUserPage() {
  currentUserRole = "guest";
  currentEntityId = null;
  currentEntityPayload = null;
  currentUploadId = null;
  entityListCache = [];

  setRoleBadge(currentUserRole);
  clearEntityPanel();
  setUploadPreview("暂无上传预览");
  setUploadStatus("等待上传", "waiting");

  const token = getToken();
  if (!token) {
    window.location.href = "/login/";
    return;
  }

  try {
    const res = await authFetch("/api/auth/me/", { method: "GET" });
    const me = await ensureOk(res);
    currentUserRole = me.is_staff || me.is_superuser ? "admin" : "user";
    setRoleBadge(currentUserRole);
    hideLoginPanel();
    await Promise.all([loadUploads(), loadEntities()]);
  } catch (error) {
    window.location.href = "/login/";
  }
}

window.kbLogin = kbLogin;
window.kbRegister = kbRegister;
window.hideLoginPanel = hideLoginPanel;
window.kbUpload = kbUpload;
window.selectEntity = selectEntity;
window.selectUpload = selectUpload;
window.filterTerms = filterTerms;

document.addEventListener("DOMContentLoaded", () => {
  initKBUserPage();
});
