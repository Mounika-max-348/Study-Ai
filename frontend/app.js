/* ============================================================
   AI Study Companion — frontend app (vanilla JS, no build step)
   ============================================================ */

const API = ""; // same-origin; backend serves this file too

const state = {
  token: localStorage.getItem("sc_token") || null,
  user: JSON.parse(localStorage.getItem("sc_user") || "null"),
  spaces: [],
  projectsBySpace: {}, // spaceId -> [projects]
  currentSpaceId: null,
  currentProjectId: null,
  currentProject: null,
  route: "home", // home | project | analytics | admin
  projectTab: "overview",
  adminTab: "overview",
  quiz: null, // { attempt_id, questions:[], index, answers:{}, results:{} }
};

/* ---------------- API helper ---------------- */
async function api(method, path, body, isForm = false) {
  const headers = {};
  if (state.token) headers["Authorization"] = "Bearer " + state.token;
  let payload;
  if (isForm) {
    payload = body;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const res = await fetch(API + path, { method, headers, body: payload });
  let data = null;
  try { data = await res.json(); } catch (e) { /* empty body */ }
  if (!res.ok) {
    const msg = (data && (data.detail?.[0]?.msg || data.detail)) || res.statusText;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return data;
}

function fmtDate(iso) {
  try { return new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }); }
  catch { return iso; }
}

function escapeHtml(s) {
  return (s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function toast(msg, isError) {
  let el = document.getElementById("toast-el");
  if (!el) {
    el = document.createElement("div");
    el.id = "toast-el";
    el.style.cssText = "position:fixed;bottom:1.4rem;right:1.4rem;padding:.8em 1.1em;border-radius:6px;font-size:.85em;font-weight:600;z-index:999;box-shadow:0 4px 16px rgba(0,0,0,.15);max-width:340px;";
    document.body.appendChild(el);
  }
  el.style.background = isError ? "var(--danger)" : "var(--primary-dark)";
  el.style.color = "#fff";
  el.textContent = msg;
  el.style.display = "block";
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.style.display = "none"; }, 4200);
}

// Generic modal: shows a small card with title/subtitle, custom field HTML, and
// a submit handler. Returns nothing; the caller wires up submit via the fields.
function showModal({ title, subtitle, fieldsHtml, submitLabel, onSubmit }) {
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  overlay.innerHTML = `
    <div class="modal-card">
      <div class="modal-card__header">
        <h3>${escapeHtml(title)}</h3>
        ${subtitle ? `<p>${escapeHtml(subtitle)}</p>` : ""}
      </div>
      <form id="modal-form">
        <div class="modal-card__body">${fieldsHtml}</div>
        <div class="modal-card__actions">
          <button type="button" class="btn secondary btn-sm" id="modal-cancel">Cancel</button>
          <button type="submit" class="btn btn-sm" id="modal-submit">${escapeHtml(submitLabel)}</button>
        </div>
      </form>
    </div>
  `;
  document.body.appendChild(overlay);
  const close = () => overlay.remove();
  overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });
  overlay.querySelector("#modal-cancel").onclick = close;
  overlay.querySelector("#modal-form").onsubmit = async (e) => {
    e.preventDefault();
    const submitBtn = overlay.querySelector("#modal-submit");
    submitBtn.disabled = true;
    try {
      await onSubmit(new FormData(e.target), close);
    } catch (err) {
      toast(err.message, true);
      submitBtn.disabled = false;
    }
  };
  const firstInput = overlay.querySelector("input, textarea");
  if (firstInput) firstInput.focus();
}

/* ---------------- Auth ---------------- */
function initAuthScreen() {
  document.getElementById("tab-login").onclick = () => switchAuthTab("login");
  document.getElementById("tab-register").onclick = () => switchAuthTab("register");

  document.getElementById("login-form").onsubmit = async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    await doAuth("/auth/login", { email: f.get("email"), password: f.get("password") });
  };
  document.getElementById("register-form").onsubmit = async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    await doAuth("/auth/register", { email: f.get("email"), password: f.get("password"), full_name: f.get("full_name") });
  };
}

function switchAuthTab(tab) {
  document.getElementById("tab-login").classList.toggle("active", tab === "login");
  document.getElementById("tab-register").classList.toggle("active", tab === "register");
  document.getElementById("login-form").style.display = tab === "login" ? "block" : "none";
  document.getElementById("register-form").style.display = tab === "register" ? "block" : "none";
  document.getElementById("auth-error").innerHTML = "";
}

async function doAuth(path, body) {
  const errEl = document.getElementById("auth-error");
  errEl.innerHTML = "";
  try {
    const data = await api("POST", path, body);
    state.token = data.access_token;
    state.user = data.user;
    localStorage.setItem("sc_token", state.token);
    localStorage.setItem("sc_user", JSON.stringify(state.user));
    await boot();
  } catch (e) {
    errEl.innerHTML = `<div class="auth-error">${escapeHtml(e.message)}</div>`;
  }
}

function logout() {
  state.token = null; state.user = null;
  localStorage.removeItem("sc_token"); localStorage.removeItem("sc_user");
  document.getElementById("shell").style.display = "none";
  document.getElementById("auth-shell").style.display = "flex";
}

/* ---------------- Boot / shell ---------------- */
async function boot() {
  document.getElementById("auth-shell").style.display = "none";
  document.getElementById("shell").style.display = "flex";
  document.getElementById("user-line").textContent = state.user.full_name || state.user.email;
  document.getElementById("admin-link").style.display = state.user.is_admin ? "block" : "none";
  document.getElementById("admin-link").onclick = () => { state.route = "admin"; render(); };
  document.getElementById("global-analytics-link").onclick = () => { state.route = "analytics"; render(); };
  document.getElementById("logout-btn").onclick = logout;
  document.getElementById("new-space-btn").onclick = createSpaceFlow;

  await loadSpaces();
  state.route = "home";
  render();
}

async function loadSpaces() {
  state.spaces = await api("GET", "/spaces");
  for (const s of state.spaces) {
    state.projectsBySpace[s.id] = await api("GET", `/projects?space_id=${s.id}`);
  }
  renderSidebar();
}

function renderSidebar() {
  const nav = document.getElementById("space-nav");
  if (!state.spaces.length) {
    nav.innerHTML = `<p class="hint" style="padding:.6em">No spaces yet. Create one to start a learning journey.</p>`;
    return;
  }
  nav.innerHTML = state.spaces.map(s => `
    <div class="space-block">
      <div class="space-row" data-space="${s.id}">
        <span>${escapeHtml(s.name)}</span>
        <span class="hint" style="margin:0">+</span>
      </div>
      <div>
        ${(state.projectsBySpace[s.id] || []).map(p => `
          <div class="project-row ${state.currentProjectId === p.id ? "active" : ""}" data-project="${p.id}" data-space="${s.id}">
            ${escapeHtml(p.name)}
          </div>`).join("")}
      </div>
    </div>
  `).join("");

  nav.querySelectorAll(".space-row").forEach(el => {
    el.onclick = () => createProjectFlow(parseInt(el.dataset.space));
  });
  nav.querySelectorAll(".project-row").forEach(el => {
    el.onclick = () => openProject(parseInt(el.dataset.project));
  });
}

function createSpaceFlow() {
  showModal({
    title: "New space",
    subtitle: "A broad area you're studying, e.g. \"Machine Learning\" or \"AWS Certification\".",
    submitLabel: "Create space",
    fieldsHtml: `
      <div class="field">
        <label>Space name</label>
        <input name="name" placeholder="e.g. Machine Learning" required autocomplete="off">
      </div>
      <div class="field" style="margin-bottom:0">
        <label>Description (optional)</label>
        <input name="description" placeholder="One line about this space" autocomplete="off">
      </div>
    `,
    onSubmit: async (fd, close) => {
      const name = fd.get("name").trim();
      if (!name) return;
      await api("POST", "/spaces", { name, description: (fd.get("description") || "").trim() });
      close();
      toast("Space created");
      await loadSpaces();
    },
  });
}

function createProjectFlow(spaceId) {
  showModal({
    title: "New project",
    subtitle: "A focused learning goal inside this space, isolated from your other projects.",
    submitLabel: "Create project",
    fieldsHtml: `
      <div class="field">
        <label>Project name</label>
        <input name="name" placeholder="e.g. Understand Gradient Descent" required autocomplete="off">
      </div>
      <div class="field" style="margin-bottom:0">
        <label>Learning goal (optional)</label>
        <input name="goal" placeholder="What do you want to be able to do?" autocomplete="off">
      </div>
    `,
    onSubmit: async (fd, close) => {
      const name = fd.get("name").trim();
      if (!name) return;
      const p = await api("POST", "/projects", { space_id: spaceId, name, description: "", goal: (fd.get("goal") || "").trim() });
      close();
      toast("Project created");
      await loadSpaces();
      openProject(p.id);
    },
  });
}

async function openProject(projectId) {
  state.currentProjectId = projectId;
  state.route = "project";
  state.projectTab = "overview";
  renderSidebar();
  render();
}

/* ---------------- Router ---------------- */
function render() {
  document.getElementById("tabs").style.display = "none";
  document.getElementById("tabs").innerHTML = "";
  document.getElementById("topbar-actions").innerHTML = "";
  if (state.route === "home") return renderHome();
  if (state.route === "project") return renderProject();
  if (state.route === "analytics") return renderGlobalAnalytics();
  if (state.route === "admin") return renderAdmin();
}

document.querySelectorAll(".navlink").forEach(() => {}); // no-op, nav lives in sidebar now

/* ---------------- Home ---------------- */
// A small deterministic accent color per space, purely visual (project cards).
const CARD_ACCENTS = ["#3F6B4A", "#B8763A", "#3A6B85", "#8A6A2E", "#6B4A8A", "#4B7A5A"];
function accentFor(id) { return CARD_ACCENTS[id % CARD_ACCENTS.length]; }

async function renderHome() {
  document.getElementById("crumb").textContent = "";
  document.getElementById("page-title").textContent = "Home";
  const content = document.getElementById("content");
  content.innerHTML = `<div class="loading">Loading your progress…</div>`;

  const allProjects = Object.values(state.projectsBySpace).flat();
  if (!allProjects.length) {
    content.innerHTML = `
      <div class="home-hero">
        <h2>Your learning workspace</h2>
        <p>Create a space, then a project inside it, to start learning from your own material.</p>
      </div>
      <div class="empty-state">
        <h2>Nothing here yet</h2>
        <p>Create a space, then a project inside it, to start learning.</p>
        <button class="btn" id="empty-new-space">+ New space</button>
      </div>`;
    document.getElementById("empty-new-space").onclick = createSpaceFlow;
    return;
  }

  let global;
  try { global = await api("GET", "/analytics/global"); } catch (e) { global = null; }

  // "Continue learning": most recently created project, with its dashboard
  const mostRecent = allProjects[0];
  let dash = null;
  try { dash = await api("GET", `/projects/${mostRecent.id}/dashboard`); } catch (e) {}

  content.innerHTML = `
    <div class="grid-3" style="margin-bottom:1.4rem">
      <div class="panel stat"><div class="num">${global ? global.total_projects : allProjects.length}</div><div class="label">Projects</div></div>
      <div class="panel stat"><div class="num">${global ? global.average_mastery.toFixed(0) : 0}%</div><div class="label">Average mastery</div></div>
      <div class="panel stat"><div class="num">${global ? global.total_activity_events : 0}</div><div class="label">Learning events logged</div></div>
    </div>

    ${dash && dash.recommended_next_step ? `
      <div class="rec-banner">
        <div>
          <div class="rec-label">RECOMMENDED NEXT STEP · ${escapeHtml(mostRecent.name)}</div>
          <p>${escapeHtml(dash.recommended_next_step)}</p>
        </div>
      </div>` : ""}

    <div class="panel">
      <h3>Continue learning</h3>
      <div class="material-item">
        <div>
          <div class="material-name">${escapeHtml(mostRecent.name)}</div>
          <div class="material-meta">${escapeHtml(mostRecent.goal || mostRecent.description || "No goal set")}</div>
        </div>
        <button class="btn btn-sm" data-open="${mostRecent.id}">Open →</button>
      </div>
    </div>

    <h3 style="margin-top:1.4rem">All projects</h3>
    <div class="project-card-grid">
      ${allProjects.map(p => `
        <div class="project-card" style="--accent: ${accentFor(p.id)}">
          <div class="project-card__name">${escapeHtml(p.name)}</div>
          <div class="project-card__goal">${escapeHtml(p.goal || p.description || "No goal set yet")}</div>
          <button class="btn secondary btn-sm" data-open="${p.id}">Open</button>
        </div>`).join("")}
    </div>
  `;
  content.querySelectorAll("[data-open]").forEach(el => {
    el.onclick = () => openProject(parseInt(el.dataset.open));
  });
}

/* ---------------- Project workspace ---------------- */
const PROJECT_TABS = [
  ["overview", "Overview"],
  ["materials", "Materials"],
  ["tutor", "Tutor"],
  ["quiz", "Quiz"],
  ["mastery", "Mastery & Growth"],
  ["analytics", "Analytics"],
];

async function renderProject() {
  let project;
  try { project = await api("GET", `/projects/${state.currentProjectId}`); }
  catch (e) { toast(e.message, true); state.route = "home"; return render(); }
  state.currentProject = project;

  const space = state.spaces.find(s => s.id === project.space_id);
  document.getElementById("crumb").textContent = space ? space.name : "";
  document.getElementById("page-title").textContent = project.name;

  const tabsEl = document.getElementById("tabs");
  tabsEl.style.display = "flex";
  tabsEl.innerHTML = PROJECT_TABS.map(([key, label]) =>
    `<button class="tab ${state.projectTab === key ? "active" : ""}" data-tab="${key}">${label}</button>`
  ).join("");
  tabsEl.querySelectorAll(".tab").forEach(el => {
    el.onclick = () => { state.projectTab = el.dataset.tab; renderProjectTabContent(project); };
  });

  renderProjectTabContent(project);
}

function renderProjectTabContent(project) {
  document.querySelectorAll("#tabs .tab").forEach(el => el.classList.toggle("active", el.dataset.tab === state.projectTab));
  const fn = {
    overview: renderOverviewTab,
    materials: renderMaterialsTab,
    tutor: renderTutorTab,
    quiz: renderQuizTab,
    mastery: renderMasteryTab,
    analytics: renderProjectAnalyticsTab,
  }[state.projectTab];
  fn(project);
}

/* ---- Overview ---- */
async function renderOverviewTab(project) {
  const content = document.getElementById("content");
  content.innerHTML = `<div class="loading">Loading overview…</div>`;
  let dash;
  try { dash = await api("GET", `/projects/${project.id}/dashboard`); }
  catch (e) { content.innerHTML = `<div class="error-box">${escapeHtml(e.message)}</div>`; return; }

  content.innerHTML = `
    ${dash.recommended_next_step ? `
      <div class="rec-banner">
        <div><div class="rec-label">RECOMMENDED NEXT STEP</div><p>${escapeHtml(dash.recommended_next_step)}</p></div>
      </div>` : ""}
    <div class="grid-3" style="margin-bottom:1.2rem">
      <div class="panel stat"><div class="num">${dash.overall_progress}%</div><div class="label">Overall progress</div></div>
      <div class="panel stat"><div class="num">${dash.materials_ready}/${dash.materials_total}</div><div class="label">Materials ready</div></div>
      <div class="panel stat"><div class="num">${dash.areas_requiring_attention.length}</div><div class="label">Concepts needing attention</div></div>
    </div>
    <div class="grid-2">
      <div class="panel">
        <h3>Goal</h3>
        <p>${escapeHtml(project.goal || project.description || "No goal set yet.")}</p>
        <h3 style="margin-top:1.2em">Areas requiring attention</h3>
        ${dash.areas_requiring_attention.length ? dash.areas_requiring_attention.map(a => `
          <div class="mastery-row"><div class="mastery-name">${escapeHtml(a.concept)}</div>
            <div class="mastery-track"><div class="mastery-fill attention" style="width:${a.mastery}%"></div></div>
            <div class="mastery-pct">${a.mastery}%</div></div>`).join("")
          : `<p class="hint">Not enough evidence yet — try the Tutor or a quiz.</p>`}
      </div>
      <div class="panel">
        <h3>Recent activity</h3>
        ${dash.recent_activity.length ? dash.recent_activity.map(e => `
          <div class="material-item"><div class="material-name" style="font-weight:500">${escapeHtml(e.type.replace(/\./g," · "))}</div>
          <div class="material-meta">${fmtDate(e.created_at)}</div></div>`).join("")
          : `<p class="hint">No activity yet.</p>`}
      </div>
    </div>
  `;
}

/* ---- Materials: rendered as a library card-catalog index ---- */
async function renderMaterialsTab(project) {
  const content = document.getElementById("content");
  content.innerHTML = `
    <div class="upload-dropzone" id="dropzone">
      <p style="margin-bottom:.6em"><strong>Upload a PDF</strong> to add it to this project's library.</p>
      <input type="file" id="file-input" accept="application/pdf">
      <button class="btn btn-sm" id="pick-file-btn">Choose PDF file</button>
    </div>
    <div id="library-index"><div class="loading">Loading library…</div></div>
  `;
  document.getElementById("pick-file-btn").onclick = () => document.getElementById("file-input").click();
  document.getElementById("file-input").onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    try {
      await api("POST", `/projects/${project.id}/materials`, fd, true);
      toast("Added to library — processing in the background");
      e.target.value = "";
      loadMaterialsList(project.id, true);
    } catch (err) { toast(err.message, true); }
  };
  loadMaterialsList(project.id, true);
}

// A short, stable-looking "call number" derived from the material id + filename,
// purely a library-catalog visual touch (not used for anything functional).
function callNumber(m) {
  const ext = (m.filename.split(".").pop() || "pdf").slice(0, 3).toUpperCase();
  return `M-${String(m.id).padStart(3, "0")}·${ext}`;
}

let _materialsPollTimer = null;
async function loadMaterialsList(projectId, startPolling) {
  clearTimeout(_materialsPollTimer);
  let materials;
  try { materials = await api("GET", `/projects/${projectId}/materials`); }
  catch (e) { return; }

  const wrap = document.getElementById("library-index");
  if (!wrap) return; // navigated away

  const counts = { ready: 0, processing: 0, queued: 0, failed: 0 };
  materials.forEach(m => { if (counts[m.status] !== undefined) counts[m.status]++; });

  const summary = `
    <div class="library-index-summary">
      <div class="count-cell is-ready"><div class="n">${counts.ready}</div><div class="l">Ready</div></div>
      <div class="count-cell is-processing"><div class="n">${counts.processing + counts.queued}</div><div class="l">Processing</div></div>
      <div class="count-cell is-failed"><div class="n">${counts.failed}</div><div class="l">Failed</div></div>
      <div class="count-cell"><div class="n">${materials.length}</div><div class="l">Total</div></div>
    </div>
  `;

  wrap.innerHTML = materials.length ? `
    ${summary}
    <div class="library-grid">
      ${materials.map(m => `
        <div class="index-card" data-material-id="${m.id}">
          <div class="index-card__flag st-${m.status}"></div>
          <button class="index-card__delete" data-delete-id="${m.id}" title="Remove from library" aria-label="Remove ${escapeHtml(m.filename)}">✕</button>
          <div class="index-card__code">${callNumber(m)}</div>
          <div class="index-card__title">${escapeHtml(m.filename)}</div>
          <div class="index-card__meta">${m.page_count ? m.page_count + " pages · " : ""}${fmtDate(m.created_at)}</div>
          ${m.error_message ? `<div class="index-card__error">${escapeHtml(m.error_message)}</div>` : ""}
          <div class="index-card__status-row">
            <span class="index-card__status-text st-${m.status}">${m.status}</span>
          </div>
        </div>
      `).join("")}
    </div>
  ` : `${summary}<p class="hint">No materials in the library yet — upload a PDF above to get started.</p>`;

  wrap.querySelectorAll("[data-delete-id]").forEach(btn => {
    btn.onclick = async () => {
      const id = btn.getAttribute("data-delete-id");
      const card = wrap.querySelector(`.index-card[data-material-id="${id}"]`);
      const name = card ? card.querySelector(".index-card__title").textContent : "this material";
      if (!confirm(`Remove "${name}" from the library? This can't be undone.`)) return;
      try {
        await api("DELETE", `/projects/${projectId}/materials/${id}`);
        toast("Removed from library");
        loadMaterialsList(projectId, true);
      } catch (err) { toast(err.message, true); }
    };
  });

  const stillProcessing = materials.some(m => m.status === "queued" || m.status === "processing");
  if (state.projectTab === "materials" && stillProcessing) {
    _materialsPollTimer = setTimeout(() => loadMaterialsList(projectId, false), 2500);
  }
}

/* ---- Tutor: ChatGPT-style chat ---- */
async function renderTutorTab(project) {
  const content = document.getElementById("content");
  content.innerHTML = `
    <div class="tutor-shell">
      <div class="tutor-log" id="tutor-log"><div class="loading">Loading conversation…</div></div>
      <div class="tutor-input-wrap">
        <form class="tutor-input-row" id="tutor-form">
          <textarea id="tutor-input" placeholder="Ask about your material… (Enter to send, Shift+Enter for a new line)" rows="1" required></textarea>
          <button class="btn" type="submit" title="Send" aria-label="Send">↑</button>
        </form>
      </div>
    </div>
  `;
  const textarea = document.getElementById("tutor-input");
  const autoGrow = () => { textarea.style.height = "auto"; textarea.style.height = Math.min(textarea.scrollHeight, 128) + "px"; };
  textarea.addEventListener("input", autoGrow);
  textarea.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      document.getElementById("tutor-form").requestSubmit();
    }
  });

  let history = [];
  try { history = await api("GET", `/projects/${project.id}/tutor/history`); } catch (e) {}
  const log = document.getElementById("tutor-log");
  renderTutorLog(log, history);

  document.getElementById("tutor-form").onsubmit = async (e) => {
    e.preventDefault();
    const input = document.getElementById("tutor-input");
    const question = input.value.trim();
    if (!question) return;
    input.value = "";
    autoGrow();
    history.push({ role: "user", content: question, citations: [], insufficient_evidence: false, created_at: new Date().toISOString() });
    renderTutorLog(log, history);
    const thinkingId = "thinking-" + Date.now();
    log.insertAdjacentHTML("beforeend", `
      <div class="chat-row assistant" id="${thinkingId}">
        <div class="chat-avatar assistant">AI</div>
        <div class="chat-content"><div class="chat-bubble-text hint">Thinking…</div></div>
      </div>`);
    log.scrollTop = log.scrollHeight;
    try {
      const res = await api("POST", `/projects/${project.id}/tutor/ask`, { question });
      document.getElementById(thinkingId)?.remove();
      history.push({ role: "assistant", content: res.answer, citations: res.citations, insufficient_evidence: res.insufficient_evidence, created_at: new Date().toISOString() });
      renderTutorLog(log, history);
    } catch (err) {
      document.getElementById(thinkingId)?.remove();
      toast(err.message, true);
    }
  };
}

function renderTutorLog(log, history) {
  if (!history.length) {
    log.innerHTML = `<div class="empty-state"><p>Ask a question about your uploaded material to get started.</p></div>`;
    return;
  }
  log.innerHTML = history.map(m => `
    <div class="chat-row ${m.role} ${m.insufficient_evidence ? "insufficient" : ""}">
      <div class="chat-avatar ${m.role}">${m.role === "user" ? "You" : "AI"}</div>
      <div class="chat-content">
        <div class="chat-bubble-text">${escapeHtml(m.content).replace(/\n/g, "<br>")}</div>
        ${m.insufficient_evidence ? `<div class="chat-evidence-note">⚠ Not enough evidence in your materials to answer this reliably.</div>` : ""}
        ${(m.citations && m.citations.length) ? `<div class="chat-citations">${m.citations.map(c => `<span class="citation-chip">${escapeHtml(c.source)} · p.${c.page}</span>`).join("")}</div>` : ""}
      </div>
    </div>
  `).join("");
  log.scrollTop = log.scrollHeight;
}

/* ---- Quiz ---- */
async function renderQuizTab(project) {
  const content = document.getElementById("content");
  if (!state.quiz || state.quiz.projectId !== project.id) {
    content.innerHTML = `
      <div class="panel" style="max-width:420px">
        <h3>Start an adaptive quiz</h3>
        <p class="hint">Questions target your weakest concepts, using material from your uploaded documents.</p>
        <div class="field"><label>Number of questions</label><input type="number" id="num-q" value="5" min="1" max="10"></div>
        <button class="btn" id="start-quiz-btn">Start quiz</button>
      </div>`;
    document.getElementById("start-quiz-btn").onclick = async () => {
      const n = parseInt(document.getElementById("num-q").value) || 5;
      content.innerHTML = `<div class="loading">Generating your quiz…</div>`;
      try {
        const res = await api("POST", `/projects/${project.id}/quiz/start`, { num_questions: n });
        state.quiz = { projectId: project.id, attemptId: res.attempt_id, questions: res.questions, index: 0, results: {} };
        renderQuizQuestion(project);
      } catch (e) {
        content.innerHTML = `<div class="error-box">${escapeHtml(e.message)}</div><p class="hint">Make sure at least one material has finished processing (status "ready") on the Materials tab.</p>`;
      }
    };
    return;
  }
  renderQuizQuestion(project);
}

function renderQuizQuestion(project) {
  const content = document.getElementById("content");
  const q = state.quiz;
  if (q.index >= q.questions.length) return renderQuizSummary(project);
  const question = q.questions[q.index];

  content.innerHTML = `
    <div class="quiz-progress">Question ${q.index + 1} of ${q.questions.length}${question.concept ? " · " + escapeHtml(question.concept) : ""}</div>
    <div class="question-card">
      <div><span class="difficulty-tag">${question.difficulty}</span></div>
      <h3 style="margin-top:.5em">${escapeHtml(question.prompt)}</h3>
      <div id="answer-area">
        ${question.type === "mcq" ? question.options.map((opt, i) => `
          <button class="option-row" data-opt="${escapeHtml(opt)}">${escapeHtml(opt)}</button>
        `).join("") : `
          <textarea id="open-answer" rows="4" style="width:100%;padding:.7em;border:1px solid var(--border);border-radius:4px"></textarea>
          <button class="btn" id="submit-open" style="margin-top:.8em">Submit answer</button>
        `}
      </div>
      <div id="feedback-area"></div>
    </div>
  `;

  if (question.type === "mcq") {
    content.querySelectorAll(".option-row").forEach(btn => {
      btn.onclick = () => submitQuizAnswer(project, question, btn.dataset.opt, content);
    });
  } else {
    document.getElementById("submit-open").onclick = () => {
      const ans = document.getElementById("open-answer").value.trim();
      if (!ans) return;
      submitQuizAnswer(project, question, ans, content);
    };
  }
}

async function submitQuizAnswer(project, question, answer, content) {
  content.querySelectorAll(".option-row").forEach(b => b.disabled = true);
  const submitBtn = document.getElementById("submit-open");
  if (submitBtn) submitBtn.disabled = true;

  let result;
  try {
    result = await api("POST", `/projects/${project.id}/quiz/${state.quiz.attemptId}/answer`, {
      question_id: question.id, answer,
    });
  } catch (e) { toast(e.message, true); return; }

  state.quiz.results[question.id] = result;

  if (question.type === "mcq") {
    content.querySelectorAll(".option-row").forEach(b => {
      if (b.dataset.opt === question.correct_answer) b.classList.add("correct");
      else if (b.dataset.opt === answer) b.classList.add("incorrect");
    });
  }
  document.getElementById("feedback-area").innerHTML = `
    <div class="feedback-box ${result.is_correct ? "good" : "bad"}">
      <strong>${result.score != null ? Math.round(result.score) + "% · " : ""}${result.is_correct ? "Good understanding" : "Needs review"}</strong>
      <p style="margin:.4em 0 0">${escapeHtml(result.feedback)}</p>
    </div>
    <button class="btn" id="next-q-btn" style="margin-top:1em">
      ${state.quiz.index + 1 >= state.quiz.questions.length ? "See results" : "Next question →"}
    </button>
  `;
  document.getElementById("next-q-btn").onclick = () => {
    state.quiz.index += 1;
    renderQuizQuestion(project);
  };
}

async function renderQuizSummary(project) {
  const content = document.getElementById("content");
  content.innerHTML = `<div class="loading">Scoring your quiz…</div>`;
  let res;
  try { res = await api("POST", `/projects/${project.id}/quiz/${state.quiz.attemptId}/complete`); }
  catch (e) { content.innerHTML = `<div class="error-box">${escapeHtml(e.message)}</div>`; return; }

  content.innerHTML = `
    <div class="quiz-summary panel">
      <div class="hint">QUIZ COMPLETE</div>
      <div class="score">${Math.round(res.avg_score)}%</div>
      <p style="max-width:480px;margin:1em auto">${escapeHtml(res.recommendation)}</p>
      <button class="btn" id="retake-btn">Take another quiz</button>
      <button class="btn secondary" id="view-mastery-btn">View mastery</button>
    </div>
  `;
  document.getElementById("retake-btn").onclick = () => { state.quiz = null; renderQuizTab(project); };
  document.getElementById("view-mastery-btn").onclick = () => { state.quiz = null; state.projectTab = "mastery"; renderProjectTabContent(project); };
}

/* ---- Mastery & Growth ---- */
function masteryTier(score) {
  if (score >= 70) return "";
  if (score >= 40) return "tier-mid";
  return "tier-low";
}
const TREND_ICON = { improving: "↗", stable: "→", needs_attention: "↘" };

async function renderMasteryTab(project) {
  const content = document.getElementById("content");
  content.innerHTML = `<div class="loading">Loading mastery…</div>`;
  let mastery, growth, recs;
  try {
    [mastery, growth, recs] = await Promise.all([
      api("GET", `/projects/${project.id}/mastery`),
      api("GET", `/projects/${project.id}/growth`),
      api("GET", `/projects/${project.id}/recommendations`),
    ]);
  } catch (e) { content.innerHTML = `<div class="error-box">${escapeHtml(e.message)}</div>`; return; }

  content.innerHTML = `
    <div class="grid-2">
      <div class="panel">
        <h3>Concept mastery</h3>
        ${mastery.length ? mastery.map(c => `
          <div class="mastery-row">
            <div class="mastery-name">${escapeHtml(c.name)}</div>
            <div class="mastery-track"><div class="mastery-fill ${masteryTier(c.mastery_score)}" style="width:${c.mastery_score}%"></div></div>
            <div class="mastery-pct">${Math.round(c.mastery_score)}%</div>
          </div>
        `).join("") : `<p class="hint">No concepts tracked yet — upload material and take a quiz.</p>`}
      </div>
      <div class="panel">
        <h3>Growth</h3>
        ${growth.length ? growth.map(g => `
          <div class="mastery-row">
            <div class="mastery-name">${escapeHtml(g.concept)} <span class="trend-tag trend-${g.trend}">${TREND_ICON[g.trend] || ""} ${g.trend.replace("_", " ")}</span></div>
            <div class="mastery-track"><div class="mastery-fill ${masteryTier(g.mastery_score)}" style="width:${g.mastery_score}%"></div></div>
            <div class="mastery-pct">${Math.round(g.mastery_score)}%</div>
          </div>
        `).join("") : `<p class="hint">Not enough quiz evidence yet to show growth.</p>`}
      </div>
    </div>
    <div class="panel">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <h3>Recommendations</h3>
        <button class="btn btn-sm secondary" id="regen-rec-btn">Generate new</button>
      </div>
      ${recs.length ? recs.map(r => `
        <div class="material-item"><div><p style="margin:0">${escapeHtml(r.text)}</p><div class="material-meta">${fmtDate(r.created_at)}</div></div></div>
      `).join("") : `<p class="hint">No recommendations yet.</p>`}
    </div>
  `;
  document.getElementById("regen-rec-btn").onclick = async () => {
    try { await api("POST", `/projects/${project.id}/recommendations/generate`); toast("New recommendation generated"); renderMasteryTab(project); }
    catch (e) { toast(e.message, true); }
  };
}

/* ---- Project analytics ---- */
async function renderProjectAnalyticsTab(project) {
  const content = document.getElementById("content");
  content.innerHTML = `<div class="loading">Loading analytics…</div>`;
  let a;
  try { a = await api("GET", `/projects/${project.id}/analytics`); }
  catch (e) { content.innerHTML = `<div class="error-box">${escapeHtml(e.message)}</div>`; return; }

  content.innerHTML = `
    <div class="grid-3" style="margin-bottom:1.2rem">
      <div class="panel stat"><div class="num">${a.avg_quiz_score ?? "—"}${a.avg_quiz_score != null ? "%" : ""}</div><div class="label">Avg quiz score</div></div>
      <div class="panel stat"><div class="num">${a.ai_calls}</div><div class="label">AI calls made</div></div>
      <div class="panel stat"><div class="num">$${a.ai_estimated_cost_usd}</div><div class="label">Estimated AI cost</div></div>
    </div>
    <div class="grid-2">
      <div class="panel">
        <h3>Activity by type</h3>
        ${Object.entries(a.activity_by_type).length ? Object.entries(a.activity_by_type).map(([k, v]) => `
          <div class="material-item"><div class="material-name" style="font-weight:500">${escapeHtml(k.replace(/\./g, " · "))}</div><div>${v}</div></div>
        `).join("") : `<p class="hint">No activity yet.</p>`}
      </div>
      <div class="panel">
        <h3>Concept mastery snapshot</h3>
        ${a.concept_mastery.length ? a.concept_mastery.map(c => `
          <div class="mastery-row"><div class="mastery-name">${escapeHtml(c.concept)}</div>
          <div class="mastery-track"><div class="mastery-fill ${masteryTier(c.mastery)}" style="width:${c.mastery}%"></div></div>
          <div class="mastery-pct">${Math.round(c.mastery)}%</div></div>
        `).join("") : `<p class="hint">No concepts tracked yet.</p>`}
      </div>
    </div>
  `;
}

/* ---------------- Global analytics ---------------- */
async function renderGlobalAnalytics() {
  document.getElementById("crumb").textContent = "";
  document.getElementById("page-title").textContent = "Global analytics";
  const content = document.getElementById("content");
  content.innerHTML = `<div class="loading">Loading…</div>`;
  let g;
  try { g = await api("GET", "/analytics/global"); }
  catch (e) { content.innerHTML = `<div class="error-box">${escapeHtml(e.message)}</div>`; return; }

  content.innerHTML = `
    <div class="grid-3" style="margin-bottom:1.2rem">
      <div class="panel stat"><div class="num">${g.total_spaces}</div><div class="label">Spaces</div></div>
      <div class="panel stat"><div class="num">${g.total_projects}</div><div class="label">Projects</div></div>
      <div class="panel stat"><div class="num">${g.average_mastery}%</div><div class="label">Average mastery</div></div>
    </div>
    <div class="panel">
      <h3>Projects overview</h3>
      <table><thead><tr><th>Project</th><th>Space ID</th></tr></thead><tbody>
        ${g.projects_overview.map(p => `<tr><td>${escapeHtml(p.name)}</td><td>${p.space_id}</td></tr>`).join("")}
      </tbody></table>
    </div>
  `;
}

/* ---------------- Admin dashboard ---------------- */
const ADMIN_TABS = [["overview", "Overview"], ["users", "Users"], ["activity", "Activity"], ["ai", "AI usage"], ["health", "System health"]];

async function renderAdmin() {
  document.getElementById("crumb").textContent = "";
  document.getElementById("page-title").textContent = "Admin dashboard";
  const tabsEl = document.getElementById("tabs");
  tabsEl.style.display = "flex";
  tabsEl.innerHTML = ADMIN_TABS.map(([k, l]) => `<button class="tab ${state.adminTab === k ? "active" : ""}" data-atab="${k}">${l}</button>`).join("");
  tabsEl.querySelectorAll(".tab").forEach(el => {
    el.onclick = () => { state.adminTab = el.dataset.atab; renderAdmin(); };
  });

  const content = document.getElementById("content");
  content.innerHTML = `<div class="loading">Loading…</div>`;
  try {
    if (state.adminTab === "overview") {
      const o = await api("GET", "/admin/overview");
      content.innerHTML = `
        <div class="grid-3" style="margin-bottom:1.2rem">
          <div class="panel stat"><div class="num">${o.users}</div><div class="label">Users</div></div>
          <div class="panel stat"><div class="num">${o.projects}</div><div class="label">Projects</div></div>
          <div class="panel stat"><div class="num">${o.spaces}</div><div class="label">Spaces</div></div>
        </div>
        <div class="grid-2">
          <div class="panel">
            <h3>Materials</h3>
            <div class="material-item"><div>Total</div><div>${o.materials.total}</div></div>
            <div class="material-item"><div>In progress</div><div>${o.materials.in_progress}</div></div>
            <div class="material-item"><div>Failed</div><div>${o.materials.failed}</div></div>
          </div>
          <div class="panel">
            <h3>AI usage</h3>
            <div class="material-item"><div>Total calls</div><div>${o.ai_usage.total_calls}</div></div>
            <div class="material-item"><div>Failures</div><div>${o.ai_usage.failures}</div></div>
            <div class="material-item"><div>Avg latency</div><div>${o.ai_usage.avg_latency_ms} ms</div></div>
            <div class="material-item"><div>Estimated cost</div><div>$${o.ai_usage.estimated_cost_usd}</div></div>
          </div>
        </div>`;
    } else if (state.adminTab === "users") {
      const users = await api("GET", "/admin/users");
      content.innerHTML = `<div class="panel"><table><thead><tr><th>Email</th><th>Name</th><th>Projects</th><th>Admin</th><th>Joined</th></tr></thead><tbody>
        ${users.map(u => `<tr><td>${escapeHtml(u.email)}</td><td>${escapeHtml(u.full_name)}</td><td>${u.projects}</td><td>${u.is_admin ? "Yes" : ""}</td><td>${fmtDate(u.created_at)}</td></tr>`).join("")}
      </tbody></table></div>`;
    } else if (state.adminTab === "activity") {
      const events = await api("GET", "/admin/activity?limit=100");
      content.innerHTML = `<div class="panel"><table><thead><tr><th>Type</th><th>User</th><th>Project</th><th>When</th></tr></thead><tbody>
        ${events.map(e => `<tr><td>${escapeHtml(e.type)}</td><td>${e.user_id}</td><td>${e.project_id ?? "—"}</td><td>${fmtDate(e.created_at)}</td></tr>`).join("")}
      </tbody></table></div>`;
    } else if (state.adminTab === "ai") {
      const logs = await api("GET", "/admin/ai-usage?limit=100");
      content.innerHTML = `<div class="panel"><table><thead><tr><th>Feature</th><th>Model</th><th>Latency</th><th>Tokens in/out</th><th>Cost</th><th>OK</th><th>When</th></tr></thead><tbody>
        ${logs.map(l => `<tr><td>${escapeHtml(l.feature)}</td><td>${escapeHtml(l.model)}</td><td>${l.latency_ms}ms</td><td>${l.input_tokens}/${l.output_tokens}</td><td>$${l.estimated_cost_usd}</td><td>${l.success ? "✓" : "✗"}</td><td>${fmtDate(l.created_at)}</td></tr>`).join("")}
      </tbody></table></div>`;
    } else if (state.adminTab === "health") {
      const h = await api("GET", "/admin/system-health");
      content.innerHTML = `
        <div class="panel">
          <h3>Materials by status</h3>
          ${Object.entries(h.materials_by_status).map(([k, v]) => `<div class="material-item"><div>${escapeHtml(k)}</div><div>${v}</div></div>`).join("") || `<p class="hint">No materials yet.</p>`}
        </div>
        <div class="panel">
          <h3>Recent AI failures</h3>
          ${h.recent_ai_failures.length ? h.recent_ai_failures.map(f => `
            <div class="material-item"><div><div class="material-name">${escapeHtml(f.feature)}</div><div class="material-meta">${escapeHtml(f.error)}</div></div><div class="material-meta">${fmtDate(f.created_at)}</div></div>
          `).join("") : `<p class="hint">No AI failures recorded.</p>`}
        </div>`;
    }
  } catch (e) {
    content.innerHTML = `<div class="error-box">${escapeHtml(e.message)}</div>`;
  }
}

/* ---------------- Boot ---------------- */
initAuthScreen();
if (state.token && state.user) {
  boot().catch(() => logout());
}
