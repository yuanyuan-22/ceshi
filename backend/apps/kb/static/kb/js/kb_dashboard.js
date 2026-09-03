let currentUserRole = "admin"; // 管理台默认按管理员对待；initKB 会用 /api/auth/me/ 再次确认
let currentEntityId = null;
let currentEntityPayload = null;
let currentUploadId = null;
let currentUploadPayload = null;
let currentCandidateId = null;
let currentCandidatePayload = null;
let entityListCache = [];
let candidateListCache = [];

const CANDIDATE_STATUS_LABELS = {
  PENDING: "待审核",
  APPROVED: "已批准",
  REJECTED: "已驳回",
};

const EXTRACTION_METHOD_LABELS = {
  structured_block: "结构化导入",
  key_value_block: "键值导入",
  heuristic_free_text: "自由文本抽取",
  manual_review_required: "待人工整理",
};

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatCandidateStatus(status) {
  const key = String(status || "").toUpperCase();
  return CANDIDATE_STATUS_LABELS[key] || status || "";
}

function formatExtractionMethod(method) {
  const key = String(method || "");
  return EXTRACTION_METHOD_LABELS[key] || method || "未知";
}

function showLoginPanel() {
  const panel = document.getElementById("kb_login_panel");
  if (panel) panel.style.display = "flex";
}

function hideLoginPanel() {
  const panel = document.getElementById("kb_login_panel");
  if (panel) panel.style.display = "none";
}

function setRoleBadge(role) {
  const badge = document.getElementById("kbRoleBadge");
  if (!badge) return;
  badge.textContent = role === "admin" ? "管理员" : role === "user" ? "普通用户" : "访客";
}

function setUploadListTitle(role) {
  const title = document.getElementById("kbUploadListTitle");
  if (!title) return;
  title.textContent = role === "admin" ? "全部上传记录" : "我的上传记录";
}

function setUploadStatus(text) {
  const el = document.getElementById("uploadStatus");
  if (el) el.textContent = text;
}

function setBuildStatus(text) {
  const el = document.getElementById("kbBuildStatus");
  if (el) el.textContent = text;
}

function setCandidateStatus(text, kind = "waiting") {
  const el = document.getElementById("kbCandidateStatus");
  if (!el) return;
  el.textContent = text;
  el.className = `status-box ${kind}`;
}

function setUploadPreview(text) {
  const el = document.getElementById("kbUploadPreview");
  if (el) el.textContent = text || "暂无上传预览";
}

function setEntityJson(payload, label) {
  const labelEl = document.getElementById("selectedEntityLabel");
  const pre = document.getElementById("kbEntityJson");
  if (labelEl) labelEl.textContent = label || "尚未选择实体";
  if (pre) pre.textContent = payload ? JSON.stringify(payload, null, 2) : "";
}

function setEntityEditor(payload) {
  const editor = document.getElementById("kbEntityEditor");
  if (!editor) return;
  editor.value = payload ? JSON.stringify(payload, null, 2) : "";
}

function setCandidateEditor(payload, label = "尚未选择候选实体") {
  const labelEl = document.getElementById("selectedCandidateLabel");
  const editor = document.getElementById("kbCandidateEditor");
  if (labelEl) labelEl.textContent = label;
  if (editor) editor.value = payload ? JSON.stringify(payload, null, 2) : "";
  populateCandidateForm(payload || null);
}

function setCandidateReviewNotes(value) {
  const notes = document.getElementById("kbCandidateReviewNotes");
  if (notes) notes.value = value || "";
}

function setCandidateEvidence(value) {
  const pre = document.getElementById("kbCandidateEvidence");
  if (pre) pre.textContent = value || "";
}

function getPrimaryCandidateLang(payload) {
  const langs = (payload && payload.langs) || {};
  if (langs.zh) return "zh";
  const firstLang = Object.keys(langs).find((lang) => langs[lang]);
  return firstLang || "zh";
}

function populateCandidateForm(payload) {
  const lang = getPrimaryCandidateLang(payload);
  const langs = (payload && payload.langs) || {};
  const block = langs[lang] || {};

  const termEl = document.getElementById("kbCandidateTerm");
  const canonicalEl = document.getElementById("kbCandidateCanonical");
  const categoryEl = document.getElementById("kbCandidateCategory");
  const aliasesEl = document.getElementById("kbCandidateAliases");
  const definitionEl = document.getElementById("kbCandidateDefinition");
  const notesEl = document.getElementById("kbCandidateNotes");

  if (termEl) termEl.value = block.term || "";
  if (canonicalEl) canonicalEl.value = (payload && payload.canonical_key) || "";
  if (categoryEl) categoryEl.value = (payload && payload.category) || "";
  if (aliasesEl) aliasesEl.value = ((block.aliases || []).join(", ")) || "";
  if (definitionEl) definitionEl.value = block.definition || "";
  if (notesEl) notesEl.value = block.notes || "";
}

function clearCandidateForm() {
  populateCandidateForm({
    category: "",
    canonical_key: "",
    langs: {
      zh: {
        term: "",
        aliases: [],
        definition: "",
        notes: "",
      },
    },
  });
}

function buildCandidatePayloadFromForm(basePayload) {
  const payload = JSON.parse(JSON.stringify(basePayload || {}));
  const lang = getPrimaryCandidateLang(payload);
  if (!payload.langs) payload.langs = {};
  if (!payload.langs[lang]) {
    payload.langs[lang] = {
      term: "",
      aliases: [],
      definition: "",
      symptoms: "",
      diagnosis: "",
      treatment: "",
      notes: "",
    };
  }

  const block = payload.langs[lang];
  const termEl = document.getElementById("kbCandidateTerm");
  const canonicalEl = document.getElementById("kbCandidateCanonical");
  const categoryEl = document.getElementById("kbCandidateCategory");
  const aliasesEl = document.getElementById("kbCandidateAliases");
  const definitionEl = document.getElementById("kbCandidateDefinition");
  const notesEl = document.getElementById("kbCandidateNotes");

  const termValue = (termEl?.value || "").trim();
  const canonicalValue = (canonicalEl?.value || "").trim();
  const categoryValue = (categoryEl?.value || "").trim();
  const aliasesValue = String(aliasesEl?.value || "").trim();
  const definitionValue = (definitionEl?.value || "").trim();
  const notesValue = (notesEl?.value || "").trim();

  if (termValue) block.term = termValue;
  if (aliasesValue) {
    block.aliases = aliasesValue
      .split(/[;,，；]+/)
      .map((item) => item.trim())
      .filter(Boolean);
  }
  if (definitionValue) block.definition = definitionValue;
  if (notesValue) block.notes = notesValue;
  if (canonicalValue) payload.canonical_key = canonicalValue;
  if (categoryValue) payload.category = categoryValue;

  if (!block.term && payload.canonical_key && payload.canonical_key !== "待人工整理") {
    block.term = payload.canonical_key;
    if (termEl) termEl.value = block.term;
  }

  if (!payload.source) {
    payload.source = currentUploadPayload?.source_name || currentCandidatePayload?.payload?.source || "manual";
  }
  if (!payload.entity_key) {
    const seed = payload.canonical_key || block.term || `candidate_${currentCandidateId || "new"}`;
    payload.entity_key = `kb_${seed}`.replace(/\s+/g, "_");
  }

  return payload;
}

function renderUploadTrace(payload) {
  const meta = document.getElementById("kbUploadTraceMeta");
  const entities = document.getElementById("kbUploadTraceEntities");
  const content = document.getElementById("kbUploadTraceContent");

  if (!meta || !entities || !content) return;

  if (!payload) {
    meta.innerHTML = "尚未选择上传记录";
    entities.innerHTML = "";
    content.textContent = "暂无原始内容";
    return;
  }

  meta.innerHTML = `
    <div><strong>上传记录:</strong> #${escapeHtml(payload.id)}</div>
    <div><strong>状态:</strong> ${escapeHtml(payload.status || "")}</div>
    <div><strong>上传用户:</strong> ${escapeHtml(payload.uploaded_by || "未登录")}</div>
    <div><strong>文件类型:</strong> ${escapeHtml(payload.file_type || "")}</div>
    <div><strong>文件名:</strong> ${escapeHtml(payload.file_name || "文本直传")}</div>
    <div><strong>来源:</strong> ${escapeHtml(payload.source_name || "")}</div>
    <div><strong>候选数:</strong> ${escapeHtml(payload.candidate_count || 0)}（待审核 ${escapeHtml(payload.pending_candidate_count || 0)}）</div>
    <div><strong>已批准候选:</strong> ${escapeHtml(payload.approved_candidate_count || 0)}</div>
    <div><strong>创建时间:</strong> ${escapeHtml(payload.created_at || "")}</div>
    <div><strong>更新时间:</strong> ${escapeHtml(payload.updated_at || "")}</div>
  `;

  const relatedEntities = payload.related_entities || [];
  const relatedCandidates = payload.related_candidates || [];
  const blocks = [];

  if (relatedCandidates.length) {
    blocks.push(`
      <div style="font-size:12px; color:#64748b; margin-bottom:6px;">该上传抽取出的候选实体</div>
      <div style="display:flex; flex-wrap:wrap; gap:8px; margin-bottom:10px;">
        ${relatedCandidates
          .map(
            (item) => `
              <button
                type="button"
                class="btn btn-secondary"
                onclick="selectCandidate(${item.id})"
                style="font-size:12px;"
              >
                ${escapeHtml(item.label || `#${item.id}`)} · ${escapeHtml(formatCandidateStatus(item.status || ""))}
              </button>
            `
          )
          .join("")}
      </div>
    `);
  }

  if (relatedEntities.length) {
    blocks.push(`
      <div style="font-size:12px; color:#64748b; margin-bottom:6px;">该上传最终关联的正式实体</div>
      <div style="display:flex; flex-wrap:wrap; gap:8px;">
        ${relatedEntities
          .map(
            (item) => `
              <button
                type="button"
                class="btn btn-secondary"
                onclick="selectEntity(${item.id})"
                style="font-size:12px;"
              >
                ${escapeHtml(item.canonical_key || item.entity_key || `#${item.id}`)}
              </button>
            `
          )
          .join("")}
      </div>
    `);
  }

  entities.innerHTML = blocks.length ? blocks.join("") : '<div class="empty-box">当前上传还没有候选实体或正式实体</div>';
  content.textContent = payload.content || "该上传没有可展示的原始文本。";
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
      const selectedStyle = currentUploadId === item.id ? "border-color:#2563eb;background:#eff6ff;" : "";
      const processButton = currentUserRole === "admin"
        ? `<button class="btn btn-secondary" style="margin-top:8px;" onclick="processUpload(${item.id})">抽取候选实体</button>`
        : "";
      return `
        <div style="border:1px solid #e2e8f0; border-radius:8px; padding:8px; margin-bottom:8px; ${selectedStyle}">
          <div style="display:flex; justify-content:space-between; gap:8px; align-items:center;">
            <strong>#${item.id}</strong>
            <span style="font-size:12px; color:#475569;">${escapeHtml(item.status || "")}</span>
          </div>
          <div style="font-size:12px; color:#64748b; margin-top:4px;">
            类型: ${escapeHtml(item.file_type || "txt")}<br/>
            上传用户: ${escapeHtml(item.uploaded_by || "-")}<br/>
            时间: ${escapeHtml(item.created_at || "")}
          </div>
          <div style="font-size:12px; color:#334155; margin-top:6px; white-space:pre-wrap;">${escapeHtml(item.content_preview || "")}</div>
          <div style="display:flex; gap:8px; flex-wrap:wrap;">${processButton}</div>
        </div>
      `;
    })
    .join("");
}

function renderEntities(items) {
  const container = document.getElementById("kbEntities");
  if (!container) return;
  if (!items.length) {
    container.innerHTML = '<div class="empty-box">暂无实体</div>';
    return;
  }
  container.innerHTML = items
    .map((item) => {
      const isSelected = currentEntityId === item.id;
      return `
        <button
          type="button"
          onclick="selectEntity(${item.id})"
          style="
            width:100%;
            text-align:left;
            border:1px solid ${isSelected ? "#2563eb" : "#dbe2ea"};
            background:${isSelected ? "#eff6ff" : "#fff"};
            border-radius:8px;
            padding:8px;
            margin-bottom:8px;
            cursor:pointer;
          "
        >
          <div style="font-weight:600;">${escapeHtml(item.zh_term || item.canonical_key || item.entity_key)}</div>
          <div style="font-size:12px; color:#64748b; margin-top:2px;">${escapeHtml(item.entity_key || "")}</div>
          <div style="font-size:12px; color:#475569; margin-top:4px;">
            分类: ${escapeHtml(item.category || "unknown")} | 语言: ${escapeHtml((item.langs_present || []).join(", "))}
          </div>
        </button>
      `;
    })
    .join("");
}

function renderCandidates(items) {
  const container = document.getElementById("kbCandidates");
  if (!container) return;
  if (!items.length) {
    container.innerHTML = '<div class="empty-box">暂无候选实体</div>';
    return;
  }
  container.innerHTML = items
    .map((item) => {
      const isSelected = currentCandidateId === item.id;
      return `
        <button
          type="button"
          onclick="selectCandidate(${item.id})"
          style="
            width:100%;
            text-align:left;
            border:1px solid ${isSelected ? "#2563eb" : "#dbe2ea"};
            background:${isSelected ? "#eff6ff" : "#fff"};
            border-radius:8px;
            padding:8px;
            margin-bottom:8px;
            cursor:pointer;
          "
        >
          <div style="display:flex; justify-content:space-between; gap:8px;">
            <strong>${escapeHtml(item.label || `#${item.id}`)}</strong>
            <span style="font-size:12px; color:#475569;">${escapeHtml(formatCandidateStatus(item.status || ""))}</span>
          </div>
          <div style="font-size:12px; color:#64748b; margin-top:4px;">
            方式: ${escapeHtml(formatExtractionMethod(item.extraction_method || ""))} | 置信度: ${Number(item.confidence || 0).toFixed(2)}
          </div>
        </button>
      `;
    })
    .join("");
}

function renderTermCards(cards) {
  const container = document.getElementById("kbTermCardsPreview");
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

function clearEntityPanels() {
  currentEntityPayload = null;
  setEntityJson(null, "尚未选择实体");
  setEntityEditor(null);
  renderTermCards([]);
}

function clearUploadTrace() {
  currentUploadId = null;
  currentUploadPayload = null;
  renderUploadTrace(null);
}

function clearCandidatePanels() {
  currentCandidatePayload = null;
  setCandidateEditor(null);
  clearCandidateForm();
  setCandidateReviewNotes("");
  setCandidateEvidence("");
  setCandidateStatus("尚未选择候选实体", "waiting");
}

function toggleControls(role) {
  const isAuthenticated = role === "admin" || role === "user";
  const isAdmin = role === "admin";
  const hasSelectedEntity = Boolean(currentEntityId);
  const hasSelectedCandidate = Boolean(currentCandidateId);

  ["kb_file", "kb_text", "kbUploadBtn"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.disabled = !isAuthenticated;
  });

  ["translateEntityBtn", "saveEntityBtn", "deleteEntityBtn"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.disabled = !isAdmin || !hasSelectedEntity;
  });

  ["buildMultilangBtn", "generateTrainingDataBtn"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.disabled = !isAdmin;
  });

  ["saveCandidateBtn", "approveCandidateBtn", "rejectCandidateBtn"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.disabled = !isAdmin || !hasSelectedCandidate;
  });

  const entityEditor = document.getElementById("kbEntityEditor");
  if (entityEditor) entityEditor.disabled = !isAdmin || !hasSelectedEntity;

  const candidateEditor = document.getElementById("kbCandidateEditor");
  if (candidateEditor) candidateEditor.disabled = !isAdmin || !hasSelectedCandidate;

  const candidateNotes = document.getElementById("kbCandidateReviewNotes");
  if (candidateNotes) candidateNotes.disabled = !isAdmin || !hasSelectedCandidate;

  [
    "kbCandidateTerm",
    "kbCandidateCanonical",
    "kbCandidateCategory",
    "kbCandidateAliases",
    "kbCandidateDefinition",
    "kbCandidateNotes",
  ].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.disabled = !isAdmin || !hasSelectedCandidate;
  });
}

async function parseResponse(res) {
  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) return res.json();
  const text = await res.text();
  return { error: text || `HTTP ${res.status}` };
}

async function ensureOk(res) {
  const data = await parseResponse(res);
  if (!res.ok) throw new Error(data.error || data.detail || `请求失败：${res.status}`);
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
    await initKB();
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
  // 只依据真实 token 判断登录态；currentUserRole 由异步 /api/auth/me/ 设置，
  // 若在其返回前点击上传会误判为 guest 并跳转登录页，因此这里不再依赖它。
  if (!getToken()) {
    setUploadStatus("登录状态已失效，请重新登录后再上传。");
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

  setUploadStatus("正在上传...");
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
    setUploadStatus(`上传成功，记录 #${data.upload_id}`);
    setUploadPreview(data.content_preview || "上传成功，但没有预览文本。");
    fileInput.value = "";
    textArea.value = "";
    await loadUploadList();
  } catch (error) {
    setUploadStatus(error.message || "上传失败。");
  }
}

async function loadUploadList() {
  try {
    const res = await authFetch("/api/kb/upload_list/", { method: "GET" });
    const data = await ensureOk(res);
    renderUploadList(data || []);
  } catch (error) {
    setUploadStatus(error.message || "加载上传记录失败。");
  }
}

async function processUpload(uploadId) {
  if (currentUserRole !== "admin") {
    alert("只有管理员可以抽取候选实体。");
    return;
  }
  setUploadStatus(`正在抽取 #${uploadId} 的候选实体...`);
  try {
    const res = await authFetch(`/api/kb/process/${uploadId}/`, { method: "POST" });
    const data = await ensureOk(res);
    setUploadStatus(`抽取完成，候选实体 ${data.candidate_count || 0} 个`);
    currentUploadId = uploadId;
    await loadUploadList();
    await viewUploadDetail(uploadId, false);
  } catch (error) {
    setUploadStatus(error.message || "抽取失败。");
  }
}

function readCandidateEditorPayload() {
  const editor = document.getElementById("kbCandidateEditor");
  try {
    const raw = (editor?.value || "").trim();
    if (!raw) return buildCandidatePayloadFromForm(currentCandidatePayload?.payload || {});
    return buildCandidatePayloadFromForm(JSON.parse(raw));
  } catch (error) {
    if (currentCandidatePayload?.payload) {
      return buildCandidatePayloadFromForm(currentCandidatePayload.payload);
    }
    throw new Error("候选实体 JSON 格式错误，请检查。");
  }
}

async function persistCurrentCandidate(showSuccess = true) {
  if (currentUserRole !== "admin") throw new Error("只有管理员可以编辑候选实体。");
  if (!currentCandidateId) throw new Error("请先选择一个候选实体。");

  const payload = readCandidateEditorPayload();
  payload.review_notes = document.getElementById("kbCandidateReviewNotes").value || "";

  const res = await authFetch(`/api/kb/candidates/${currentCandidateId}/`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await ensureOk(res);
  currentCandidatePayload = data;
  setCandidateEditor(data.payload || {}, `当前候选: ${data.label || currentCandidateId}`);
  setCandidateReviewNotes(data.review_notes || "");
  setCandidateEvidence(data.evidence_text || "");
  if (showSuccess) setCandidateStatus(`候选实体 ${data.label || currentCandidateId} 已保存`, "success");
  await loadCandidateList(currentUploadId);
  return data;
}

async function saveCurrentCandidate() {
  try {
    await persistCurrentCandidate(true);
  } catch (error) {
    setCandidateStatus(error.message || "保存候选实体失败。", "error");
  }
}

async function approveCurrentCandidate() {
  if (currentUserRole !== "admin") {
    alert("只有管理员可以批准候选实体。");
    return;
  }
  if (!currentCandidateId) {
    alert("请先选择一个候选实体。");
    return;
  }
  setCandidateStatus("正在批准当前候选...", "info");
  try {
    await persistCurrentCandidate(false);
    const reviewNotes = document.getElementById("kbCandidateReviewNotes").value || "";
    const res = await authFetch(`/api/kb/candidates/${currentCandidateId}/approve/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ review_notes: reviewNotes }),
    });
    const data = await ensureOk(res);
    setCandidateStatus(`已批准并写入 KB，实体 ID ${data.entity_id}`, "success");
    await loadUploadList();
    await viewUploadDetail(currentUploadId, false);
    await loadEntities();
    if (data.entity_id) {
      currentEntityId = data.entity_id;
      await selectEntity(data.entity_id);
    }
  } catch (error) {
    setCandidateStatus(error.message || "批准候选实体失败。", "error");
  }
}

async function rejectCurrentCandidate() {
  if (currentUserRole !== "admin") {
    alert("只有管理员可以驳回候选实体。");
    return;
  }
  if (!currentCandidateId) {
    alert("请先选择一个候选实体。");
    return;
  }
  setCandidateStatus("正在驳回当前候选...", "info");
  try {
    await persistCurrentCandidate(false);
    const reviewNotes = document.getElementById("kbCandidateReviewNotes").value || "";
    const res = await authFetch(`/api/kb/candidates/${currentCandidateId}/reject/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ review_notes: reviewNotes }),
    });
    await ensureOk(res);
    setCandidateStatus("候选实体已驳回。", "success");
    await loadUploadList();
    await viewUploadDetail(currentUploadId, false);
  } catch (error) {
    setCandidateStatus(error.message || "驳回候选实体失败。", "error");
  }
}

async function translateSelectedEntity() {
  if (currentUserRole !== "admin") {
    alert("只有管理员可以翻译实体。");
    return;
  }
  if (!currentEntityId) {
    alert("请先选择一个实体。");
    return;
  }
  setBuildStatus("正在翻译当前实体...");
  try {
    const res = await authFetch(`/api/kb/translate/${currentEntityId}/`, { method: "POST" });
    await ensureOk(res);
    setBuildStatus("当前实体翻译完成。");
    await selectEntity(currentEntityId);
  } catch (error) {
    setBuildStatus(error.message || "实体翻译失败。");
  }
}

async function saveCurrentEntity() {
  if (currentUserRole !== "admin") {
    alert("只有管理员可以编辑实体。");
    return;
  }
  if (!currentEntityId) {
    alert("请先选择一个实体。");
    return;
  }
  const editor = document.getElementById("kbEntityEditor");
  let payload;
  try {
    payload = JSON.parse(editor.value);
  } catch (error) {
    setBuildStatus("当前实体 JSON 格式错误，无法保存。");
    return;
  }
  setBuildStatus("正在保存当前实体...");
  try {
    const res = await authFetch(`/api/kb/entities/${currentEntityId}/`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await ensureOk(res);
    currentEntityId = data.id;
    currentEntityPayload = data;
    setBuildStatus(`实体 ${data.entity_key} 已保存。`);
    setEntityJson(data, `当前实体: ${data.entity_key}`);
    setEntityEditor(data);
    renderTermCards(data.term_cards || []);
    await loadEntities();
  } catch (error) {
    setBuildStatus(error.message || "保存实体失败。");
  }
}

async function deleteCurrentEntity() {
  if (currentUserRole !== "admin") {
    alert("只有管理员可以删除实体。");
    return;
  }
  if (!currentEntityId || !currentEntityPayload) {
    alert("请先选择一个实体。");
    return;
  }
  const confirmed = window.confirm(`确认删除实体 ${currentEntityPayload.entity_key || currentEntityId} 吗？`);
  if (!confirmed) return;
  setBuildStatus("正在删除当前实体...");
  try {
    const deletingId = currentEntityId;
    const res = await authFetch(`/api/kb/entities/${deletingId}/`, { method: "DELETE" });
    const data = await ensureOk(res);
    currentEntityId = null;
    currentEntityPayload = null;
    clearEntityPanels();
    setBuildStatus(`实体 ${data.entity_key || deletingId} 已删除。`);
    await loadEntities();
  } catch (error) {
    setBuildStatus(error.message || "删除实体失败。");
  }
}

async function buildMultilang() {
  if (currentUserRole !== "admin") {
    alert("只有管理员可以构建 KB。");
    return;
  }
  setBuildStatus("正在构建 KB 检索文件...");
  try {
    const res = await authFetch("/api/kb/build_multilang/", { method: "POST" });
    const data = await ensureOk(res);
    setBuildStatus(`构建完成: ${data.entities_count} 个实体，${data.chunks_count} 个检索块。`);
  } catch (error) {
    setBuildStatus(error.message || "构建失败。");
  }
}

async function generateTrainingData() {
  if (currentUserRole !== "admin") {
    alert("只有管理员可以生成训练数据。");
    return;
  }
  setBuildStatus("正在生成训练数据...");
  try {
    const res = await authFetch("/api/kb/generate_training_data/", { method: "POST" });
    const data = await ensureOk(res);
    const sampleCount = data.stats?.num_all_samples ?? "-";
    setBuildStatus(`训练数据生成完成，总样本数: ${sampleCount}`);
  } catch (error) {
    setBuildStatus(error.message || "训练数据生成失败。");
  }
}

async function loadEntities() {
  try {
    const res = await authFetch("/api/kb/entities/", { method: "GET" });
    const data = await ensureOk(res);
    entityListCache = data || [];
    renderEntities(entityListCache);
  } catch (error) {
    setBuildStatus(error.message || "加载实体列表失败。");
  }
}

async function selectEntity(entityId) {
  try {
    const res = await authFetch(`/api/kb/entities/${entityId}/`, { method: "GET" });
    const data = await ensureOk(res);
    currentEntityId = data.id;
    currentEntityPayload = data;
    setEntityJson(data, `当前实体: ${data.entity_key || entityId}`);
    setEntityEditor(data);
    renderTermCards(data.term_cards || []);
    renderEntities(entityListCache); // 刷新列表高亮
    toggleControls(currentUserRole);
  } catch (error) {
    setBuildStatus(error.message || "加载实体详情失败。");
  }
}

async function loadCandidateList(uploadId) {
  try {
    const query = uploadId ? `?upload_id=${encodeURIComponent(uploadId)}` : "";
    const res = await authFetch(`/api/kb/candidates/${query}`, { method: "GET" });
    const data = await ensureOk(res);
    candidateListCache = data || [];
    renderCandidates(candidateListCache);
  } catch (error) {
    setCandidateStatus(error.message || "加载候选实体失败。", "error");
  }
}

function kbLoadEntities() { loadEntities(); }
function kbLoadCandidates() { loadCandidateList(); }

async function selectCandidate(candidateId) {
  try {
    const res = await authFetch(`/api/kb/candidates/${candidateId}/`, { method: "GET" });
    const data = await ensureOk(res);
    currentCandidateId = data.id;
    currentCandidatePayload = data;
    setCandidateEditor(data.payload || {}, `当前候选: ${data.label || candidateId}`);
    setCandidateReviewNotes(data.review_notes || "");
    setCandidateEvidence(data.evidence_text || "");
    setCandidateStatus(`已选择候选 ${data.label || candidateId}`, "info");
    renderCandidates(candidateListCache); // 刷新列表高亮
    toggleControls(currentUserRole);
  } catch (error) {
    setCandidateStatus(error.message || "加载候选详情失败。", "error");
  }
}

async function viewUploadDetail(uploadId, scroll = true) {
  try {
    const res = await authFetch(`/api/kb/uploads/${uploadId}/`, { method: "GET" });
    const data = await ensureOk(res);
    currentUploadId = data.id;
    currentUploadPayload = data;
    renderUploadTrace(data);
    await loadCandidateList(uploadId);
    if (scroll) {
      const trace = document.getElementById("kbUploadTraceMeta");
      if (trace) trace.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  } catch (error) {
    setUploadStatus(error.message || "加载上传详情失败。");
  }
}
function syncCandidateEditorFromForm() {
  const editor = document.getElementById("kbCandidateEditor");
  if (!editor) return;
  const payload = buildCandidatePayloadFromForm(currentCandidatePayload?.payload || {});
  editor.value = JSON.stringify(payload, null, 2);
}

async function initKB() {
  // 管理台就是管理员后台：能进到这个页面的前提就是管理员。
  // 这里不再有“访客”概念，只做两件事：确认已登录、确认是管理员。
  currentEntityId = null;
  currentEntityPayload = null;
  currentUploadId = null;
  currentUploadPayload = null;
  currentCandidateId = null;
  currentCandidatePayload = null;
  entityListCache = [];
  candidateListCache = [];
  setUploadPreview("暂无上传预览");
  clearEntityPanels();
  clearUploadTrace();
  clearCandidatePanels();
  renderCandidates([]);

  const token = getToken();
  if (!token) {
    // 完全没登录才回登录页；这是唯一合理的跳转。
    window.location.href = "/login/";
    return;
  }
  try {
    const res = await authFetch("/api/auth/me/", { method: "GET" });
    const me = await ensureOk(res);
    // 普通用户不该进管理台，送去用户入口 library；其余都是管理员。
    if (!(me.is_staff || me.is_superuser)) {
      window.location.href = "/kb/library/";
      return;
    }
    currentUserRole = "admin";
    setRoleBadge(currentUserRole);
    setUploadListTitle(currentUserRole);
    toggleControls(currentUserRole);
    await Promise.all([loadUploadList(), loadEntities()]);
  } catch (error) {
    // me 接口失败（如 token 失效）：交给 authFetch 的登出逻辑，不在这里硬跳。
    console.error("initKB error", error);
    setUploadStatus("加载失败，请重新登录后重试。");
  }
}

window.kbLogin = kbLogin;
window.kbRegister = kbRegister;
window.hideLoginPanel = hideLoginPanel;
window.kbUpload = kbUpload;
window.processUpload = processUpload;
window.viewUploadDetail = viewUploadDetail;
window.kbLoadEntities = kbLoadEntities;
window.kbLoadCandidates = kbLoadCandidates;
window.selectEntity = selectEntity;
window.selectCandidate = selectCandidate;
window.translateSelectedEntity = translateSelectedEntity;
window.saveCurrentEntity = saveCurrentEntity;
window.deleteCurrentEntity = deleteCurrentEntity;
window.saveCurrentCandidate = saveCurrentCandidate;
window.approveCurrentCandidate = approveCurrentCandidate;
window.rejectCurrentCandidate = rejectCurrentCandidate;
window.buildMultilang = buildMultilang;
window.generateTrainingData = generateTrainingData;

document.addEventListener("DOMContentLoaded", () => {
  [
    "kbCandidateTerm",
    "kbCandidateCanonical",
    "kbCandidateCategory",
    "kbCandidateAliases",
    "kbCandidateDefinition",
    "kbCandidateNotes",
  ].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("input", syncCandidateEditorFromForm);
  });
  initKB();
});
