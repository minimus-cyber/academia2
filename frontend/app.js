// Academia Intermundia 2.0 — Main App
const API = window.ACADEMIA_API || "https://80.211.139.85:8083/api";

// State
const state = {
  view: "dashboard",
  rounds: [],
  activeRound: null,
  agents: [],
  eventSource: null,
  labCanvases: {},   // dept -> injected html string
};

// Router
function navigate(view, params = {}) {
  if (state._dmES) { state._dmES.close(); state._dmES = null; }
  state.view = view;
  document.querySelectorAll("nav a").forEach(a => a.classList.remove("active"));
  const link = document.querySelector(`nav a[data-view="${view}"]`);
  if (link) link.classList.add("active");
  render(view, params);
}

// API helpers
async function api(path, opts = {}) {
  try {
    const res = await fetch(`${API}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...opts,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  } catch (e) {
    console.error("API error:", e);
    return null;
  }
}

// SSE round streaming
function streamRound(roundId, onEvent) {
  if (state.eventSource) state.eventSource.close();
  const es = new EventSource(`${API}/rounds/${roundId}/stream`);
  state.eventSource = es;
  es.onmessage = e => {
    try { onEvent(JSON.parse(e.data)); } catch (_) {}
  };
  es.onerror = () => es.close();
  return es;
}

// Render functions
async function render(view, params) {
  const content = document.getElementById("content");
  const topbar = document.getElementById("topbar-title");

  switch (view) {
    case "dashboard":    return renderDashboard(content, topbar);
    case "round":        return renderRound(content, topbar, params.id);
    case "constitution": return renderConstitution(content, topbar);
    case "encyclopedia":
    case "wiki":         return renderEncyclopedia(content, topbar, params.articleId || params.pageId);
    case "publications": return renderPublications(content, topbar, params.id);
    case "labs":         return renderLabs(content, topbar, params.dept);
    case "agents":       return renderAgents(content, topbar);
    case "messages":     return renderMessages(content, topbar, params.participant || "professor");
    case "thread":       return renderThread(content, topbar, params.from || "professor", params.to);
  }
}

// ── DASHBOARD — Status + Rounds + DAOs + Messages ────────────────────────────

async function renderDashboard(el, topbar) {
  topbar.textContent = "Dashboard";
  el.innerHTML = `<div class="loader"><span></span><span></span><span></span></div>`;

  if (state._dashInterval) { clearInterval(state._dashInterval); state._dashInterval = null; }

  async function _load() {
    if (state.view !== "dashboard") { clearInterval(state._dashInterval); state._dashInterval = null; return; }
    const [rounds, agents] = await Promise.all([api("/rounds"), api("/agents")]);
    state.rounds = rounds || [];
    state.agents = agents || [];

    const active = state.rounds.filter(r => r.status === "active" || r.status === "awaiting_placet");
    const past   = state.rounds.filter(r => r.status === "ratified" || r.status === "closed");

    const byRole = { senior: [], coordinator: [], researcher: [], student: [] };
    state.agents.forEach(a => { if (byRole[a.role]) byRole[a.role].push(a); });
    const roleLabel = { senior: "Seniores", coordinator: "Coordinatori", researcher: "Ricercatori", student: "Studenti" };

    el.innerHTML = `
    <div class="card">
      <div class="card-title">Academia Intermundia — Status</div>
      <div style="display:flex;gap:2rem;font-size:12px;">
        <div><span style="color:var(--weinrot)">${state.agents.length}</span> DAOs active</div>
        <div><span style="color:var(--weinrot)">${state.rounds.length}</span> rounds total</div>
        <div><span style="color:var(--weinrot)">${active.length}</span> in progress</div>
      </div>
    </div>

    ${state.rounds.length === 0 ? `
    <div class="card">
      <div class="card-title">Getting Started</div>
      <p style="margin-bottom:1rem;font-size:12px;">No rounds yet. Start with the Constitution Round to found Academia Intermundia.</p>
      <button class="btn" onclick="startConstitution()">Begin Round 0 — Constitution</button>
    </div>` : ""}

    ${active.length > 0 ? `
    <div class="card">
      <div class="card-title">Active Rounds</div>
      ${active.map(r => `
        <div style="display:flex;align-items:center;gap:1rem;padding:0.5rem 0;border-bottom:1px solid var(--border)">
          <div style="flex:1">
            <div style="font-size:12px">${r.theme_en}</div>
            <div style="font-size:10px;color:var(--text-dim)">${r.created_at}</div>
          </div>
          <span class="status-badge ${r.status === 'active' ? 'active' : ''}">${r.status}</span>
          <button class="btn btn-ghost" onclick="navigate('round',{id:${r.id}})">View →</button>
        </div>`).join("")}
    </div>` : ""}

    ${past.length > 0 ? `
    <div class="card">
      <div class="card-title">Past Rounds</div>
      ${past.map(r => `
        <div style="display:flex;align-items:center;gap:1rem;padding:0.5rem 0;border-bottom:1px solid var(--border)">
          <div style="flex:1">
            <div style="font-size:12px">${r.theme_en}</div>
            <div style="font-size:10px;color:var(--text-dim)">${r.ratified_at || r.created_at}</div>
          </div>
          <span class="status-badge">${r.status}</span>
          <button class="btn btn-ghost" onclick="navigate('round',{id:${r.id}})">View →</button>
        </div>`).join("")}
    </div>` : ""}

    <div class="card">
      <div class="card-title">◆ DAOs — Digital Academic Operators</div>
      ${Object.entries(byRole).map(([role, list]) => list.length === 0 ? "" : `
        <div style="margin-bottom:1.5rem">
          <div style="font-size:9px;text-transform:uppercase;letter-spacing:0.2em;color:var(--weinrot);padding:0.35rem 0;border-bottom:1px solid var(--border);margin-bottom:0.7rem">${roleLabel[role]} (${list.length})</div>
          <div class="agents-grid">
            ${list.map(a => `
              <div class="agent-card ${a.role}">
                <div class="agent-symbol">${a.symbol || "◆"}</div>
                <div class="agent-name">${a.name}</div>
                <div class="agent-origin">${a.origin || ""}</div>
                ${a.discipline ? `<div class="agent-discipline">${a.discipline}</div>` : ""}
                ${a.department ? `<div style="font-size:10px;color:var(--text-dim);margin-top:2px">${a.department}</div>` : ""}
                <button class="btn btn-ghost" style="margin-top:0.6rem;width:100%;font-size:10px;padding:0.3rem 0.5rem"
                  onclick="navigate('thread',{from:'professor',to:'${a.id}'})">💬 DM</button>
              </div>`).join("")}
          </div>
        </div>`).join("")}
    </div>

    <div class="card">
      <div class="card-title">💬 Messages</div>
      <div id="dash-msgs-content"><div class="loader"><span></span><span></span><span></span></div></div>
    </div>
    `;

    _loadDashMessages();
  }

  async function _loadDashMessages() {
    const convs = await api("/dm/conversations/professor");
    const msgEl = document.getElementById("dash-msgs-content");
    if (!msgEl) return;

    if (!convs || convs.length === 0) {
      msgEl.innerHTML = `<p style="font-size:12px;color:var(--text-dim)">No messages yet. Use the DM button on any DAO above to start a conversation.</p>`;
    } else {
      msgEl.innerHTML = convs.slice(0, 10).map(c => `
        <div style="display:flex;align-items:center;gap:1rem;padding:0.4rem 0;border-bottom:1px solid var(--border);cursor:pointer"
             onclick="navigate('thread',{from:'professor',to:'${c.other}'})">
          <span style="font-size:1.3rem">${c.other_symbol || "🤖"}</span>
          <div style="flex:1">
            <div style="font-size:12px;font-weight:500">${c.other_name || c.other}</div>
            <div style="font-size:10px;color:var(--text-dim)">${escHtml((c.content || "").slice(0, 60))}…</div>
          </div>
          ${!c.read_at && c.other !== "professor" ? '<span style="color:var(--weinrot);font-size:10px">●</span>' : ""}
        </div>`).join("");
    }

    const newConvHtml = await _dmNewConvHTML();
    const msgEl2 = document.getElementById("dash-msgs-content");
    if (msgEl2) msgEl2.insertAdjacentHTML("beforeend", newConvHtml);
  }

  await _load();
  state._dashInterval = setInterval(_load, 30000);
}

// ── AGENTS (kept as standalone view, accessible from code) ───────────────────

async function renderAgents(el, topbar) {
  topbar.textContent = "DAOs — Digital Academic Operators";
  el.innerHTML = `<div class="loader"><span></span><span></span><span></span></div>`;
  const agents = await api("/agents");
  if (!agents) { el.innerHTML = `<p>Error loading agents.</p>`; return; }

  const byRole = { senior: [], coordinator: [], researcher: [], student: [] };
  agents.forEach(a => { if (byRole[a.role]) byRole[a.role].push(a); });

  const roleLabel = { senior: "Seniores", coordinator: "Coordinatori", researcher: "Ricercatori", student: "Studenti" };

  el.innerHTML = Object.entries(byRole).map(([role, list]) => list.length === 0 ? "" : `
    <div class="card">
      <div class="card-title">${roleLabel[role]} (${list.length})</div>
      <div class="agents-grid">
        ${list.map(a => `
          <div class="agent-card ${a.role}">
            <div class="agent-symbol">${a.symbol || "◆"}</div>
            <div class="agent-name">${a.name}</div>
            <div class="agent-origin">${a.origin || ""}</div>
            ${a.discipline ? `<div class="agent-discipline">${a.discipline}</div>` : ""}
            ${a.department ? `<div style="font-size:10px;color:var(--text-dim);margin-top:2px">${a.department}</div>` : ""}
          </div>`).join("")}
      </div>
    </div>`).join("");
}

// ── ROUND ─────────────────────────────────────────────────────────────────────

async function renderRound(el, topbar, roundId) {
  topbar.textContent = `Round #${roundId}`;
  el.innerHTML = `<div class="loader"><span></span><span></span><span></span></div>`;
  const round = await api(`/rounds/${roundId}`);
  if (!round) { el.innerHTML = `<p>Round not found.</p>`; return; }

  topbar.textContent = `Round #${roundId} — ${round.theme_en.substring(0, 50)}`;
  renderRoundView(el, round);
}

function renderRoundView(el, round) {
  const msgs = round.messages || [];
  const pages = round.wiki_pages || [];

  el.innerHTML = `
    <div class="card">
      <div class="card-title">Theme</div>
      <div style="font-size:13px">${round.theme_en}</div>
      ${round.theme_it ? `<div style="font-size:11px;color:var(--text-dim);margin-top:4px">[IT] ${round.theme_it}</div>` : ""}
    </div>

    <div class="card">
      <div class="card-title">Round Activity</div>
      <div class="message-stream" id="msg-stream">
        ${msgs.map(m => renderMessage(m)).join("")}
        ${msgs.length === 0 ? `<div class="loader"><span></span><span></span><span></span></div>` : ""}
      </div>
    </div>

    ${pages.length > 0 ? `
    <div class="card">
      <div class="card-title">Encyclopedia Pages (${pages.length})</div>
      ${pages.map(p => `
        <div style="padding:0.5rem 0;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:0.8rem">
          <div style="flex:1">
            <span style="font-size:12px">${p.title}</span>
            <span class="draft-badge" style="margin-left:6px">${p.status}</span>
          </div>
          <span style="font-size:10px;color:var(--text-dim)">${p.author_name || p.author_id}</span>
          <button class="btn btn-ghost" onclick="navigate('encyclopedia',{articleId:${p.id}})">Read →</button>
        </div>`).join("")}
    </div>` : ""}

    ${round.status === "awaiting_placet" ? `
    <div id="placet-panel">
      <h3>⬡ Professor — Placet Required</h3>
      <p style="font-size:12px;margin-bottom:1rem">The DAOs have completed their work and await your approval to publish.</p>
      <textarea id="placet-notes" placeholder="Your notes, corrections, or approval message (in Italian or English)..."></textarea>
      <div style="margin-top:0.8rem;display:flex;gap:0.8rem">
        <button class="btn" onclick="givePlacet(${round.id})">Ratify & Publish</button>
        <button class="btn btn-ghost" onclick="requestRevision(${round.id})">Request Revision</button>
      </div>
    </div>` : ""}
  `;

  if (round.status === "active") {
    streamRound(round.id, event => {
      appendRoundEvent(event, round.id);
    });
  }
}

function renderMessage(m) {
  const roleClass = m.agent_role || "researcher";
  const phase = m.msg_type ? m.msg_type.replace("_", " ") : "";
  return `
    <div class="msg ${roleClass}">
      <div class="msg-header">
        <span class="msg-agent">${m.agent_name || m.agent_id}</span>
        <span class="msg-role">${m.agent_role || ""}</span>
        <span class="msg-phase">${phase}</span>
      </div>
      <div class="msg-body">${escHtml(m.content)}</div>
    </div>`;
}

function appendRoundEvent(ev, roundId) {
  const stream = document.getElementById("msg-stream");
  if (!stream) return;

  if (ev.event === "phase_change") {
    stream.insertAdjacentHTML("beforeend",
      `<div class="phase-banner">— ${ev.phase} —</div>`);
  } else if (ev.event === "message") {
    stream.insertAdjacentHTML("beforeend", renderMessage({
      agent_id: ev.agent, agent_name: ev.agent_name || ev.agent,
      agent_role: ev.role || "researcher", msg_type: ev.phase, content: ev.content
    }));
    stream.lastElementChild.scrollIntoView({ behavior: "smooth" });
  } else if (ev.event === "encyclopedia_article" || ev.event === "encyclopedia_page") {
    const notice = document.createElement("div");
    notice.className = "phase-banner";
    notice.textContent = `◈ Encyclopedia: "${ev.title || ev.operation}" by ${ev.author_name || ev.author || ev.author_id}`;
    stream.appendChild(notice);
  } else if (ev.event === "wiki_page") {
    const notice = document.createElement("div");
    notice.className = "phase-banner";
    notice.textContent = `◈ Entry saved: "${ev.title}" by ${ev.author}`;
    stream.appendChild(notice);
  } else if (ev.event === "lab_artifact") {
    const notice = document.createElement("div");
    notice.className = "phase-banner";
    notice.textContent = `⚗ Lab artifact: ${ev.filename} by ${ev.author_name || ev.author_id}`;
    stream.appendChild(notice);
    // Auto-inject into dept canvas if Labs view is active
    if (state.view === "labs" && ev.html_content && ev.department) {
      const frame = document.getElementById(`lab-frame-${_deptId(ev.department)}`);
      if (frame) frame.srcdoc = ev.html_content;
    }
  } else if (ev.event === "awaiting_placet") {
    navigate("round", { id: roundId });
  }
}

// ── ENCYCLOPEDIA (replaces Wiki) ──────────────────────────────────────────────

async function renderEncyclopedia(el, topbar, articleId) {
  if (articleId) {
    topbar.textContent = "Encyclopedia";
    el.innerHTML = `<div class="loader"><span></span><span></span><span></span></div>`;
    const data = await api(`/encyclopedia/articles/${articleId}`);
    if (!data) { el.innerHTML = "<p>Article not found.</p>"; return; }
    const a = data.article || data;
    topbar.textContent = a.title;
    const linked = (data.linked_articles || []);
    el.innerHTML = `
      <div style="margin-bottom:1rem">
        <button class="btn btn-ghost" onclick="navigate('encyclopedia',{})">← Back to Encyclopedia</button>
      </div>
      <div class="wiki-page">
        <h1>${a.title}</h1>
        <div class="meta">
          By ${a.author_name || a.author_id} ·
          ${a.created_at || ""}
          ${a.revision_count ? ` · rev. ${a.revision_count}` : ""}
          ${a.tags ? ` · ${a.tags}` : ""}
          <span class="draft-badge" style="margin-left:6px">${a.status || ""}</span>
        </div>
        <div>${a.content_en || a.content || ""}</div>
        ${linked.length > 0 ? `
          <div style="margin-top:2rem;border-top:1px solid var(--border);padding-top:1rem">
            <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.15em;color:var(--weinrot);margin-bottom:0.5rem">Related Articles</div>
            ${linked.map(l => `
              <span style="display:inline-block;margin:0.2rem;padding:0.2rem 0.5rem;border:1px solid var(--border);border-radius:3px;font-size:11px;cursor:pointer"
                    onclick="navigate('encyclopedia',{articleId:${l.id}})">${l.title}</span>`).join("")}
          </div>` : ""}
      </div>`;
  } else {
    topbar.textContent = "◈ Encyclopedia";
    el.innerHTML = `<div class="loader"><span></span><span></span><span></span></div>`;
    const articles = await api("/encyclopedia/articles");
    if (!articles) { el.innerHTML = "<div class='card'><p>No entries yet.</p></div>"; return; }

    const constitutionArticle = articles.find(a =>
      /constitution|costituzione/i.test(a.title));
    const others = articles.filter(a => a !== constitutionArticle);

    el.innerHTML = `
      <div class="card">
        <div style="display:flex;gap:0.5rem;margin-bottom:1rem">
          <input type="text" id="enc-search" placeholder="Search Encyclopedia…"
            style="flex:1;padding:0.4rem 0.75rem;background:var(--surface);color:var(--text);border:1px solid var(--border);border-radius:4px;font-family:inherit;font-size:12px"
            onkeydown="if(event.key==='Enter') searchEncyclopedia()">
          <button class="btn btn-ghost" onclick="searchEncyclopedia()">Search</button>
        </div>
        ${constitutionArticle ? `
        <div style="margin-bottom:1.2rem;padding:0.75rem;border:1px solid var(--weinrot);border-radius:6px">
          <div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.4rem">
            <span style="font-size:10px;background:var(--weinrot);color:#fff;padding:0.15rem 0.5rem;border-radius:3px;letter-spacing:0.1em">§ CONSTITUTION</span>
          </div>
          <div style="font-size:13px;cursor:pointer;font-weight:500"
               onclick="navigate('encyclopedia',{articleId:${constitutionArticle.id}})">${constitutionArticle.title}</div>
          <div style="font-size:10px;color:var(--text-dim);margin-top:3px">
            By ${constitutionArticle.author_name || constitutionArticle.author_id} · ${constitutionArticle.created_at || ""}
            <span class="draft-badge" style="margin-left:6px">${constitutionArticle.status}</span>
          </div>
        </div>` : ""}
        <div class="card-title">All Articles (${articles.length})</div>
        <div id="enc-list">
          ${others.map(a => `
            <div style="padding:0.5rem 0;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:0.8rem">
              <div style="flex:1">
                <span style="font-size:12px;cursor:pointer;color:var(--text)"
                      onclick="navigate('encyclopedia',{articleId:${a.id}})">${a.title}</span>
                <span class="draft-badge" style="margin-left:6px">${a.status}</span>
              </div>
              <span style="font-size:10px;color:var(--text-dim)">${a.author_name || a.author_id}</span>
            </div>`).join("")}
        </div>
      </div>`;
  }
}

async function searchEncyclopedia() {
  const q = document.getElementById("enc-search")?.value?.trim();
  if (!q) return;
  const results = await api(`/encyclopedia/articles/search?q=${encodeURIComponent(q)}`);
  const listEl = document.getElementById("enc-list");
  if (!listEl) return;
  if (!results || results.length === 0) {
    listEl.innerHTML = `<p style="font-size:12px;color:var(--text-dim);padding:0.5rem 0">No results for "${escHtml(q)}".</p>`;
    return;
  }
  listEl.innerHTML = results.map(a => `
    <div style="padding:0.5rem 0;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:0.8rem">
      <div style="flex:1">
        <span style="font-size:12px;cursor:pointer;color:var(--text)"
              onclick="navigate('encyclopedia',{articleId:${a.id}})">${a.title}</span>
        <span class="draft-badge" style="margin-left:6px">${a.status}</span>
      </div>
      <span style="font-size:10px;color:var(--text-dim)">${a.author_name || a.author_id}</span>
    </div>`).join("");
}

// ── PUBLICATIONS ──────────────────────────────────────────────────────────────

async function renderPublications(el, topbar, pubId) {
  if (pubId) {
    el.innerHTML = `<div class="loader"><span></span><span></span><span></span></div>`;
    const pub = await api(`/publications/${pubId}`);
    if (!pub) { el.innerHTML = "<p>Not found.</p>"; return; }
    topbar.textContent = pub.title;
    el.innerHTML = `<div class="wikibooks">${pub.content_en_html}</div>`;
  } else {
    topbar.textContent = "Publications";
    el.innerHTML = `<div class="loader"><span></span><span></span><span></span></div>`;
    const pubs = await api("/publications");
    if (!pubs || pubs.length === 0) { el.innerHTML = "<div class='card'><p>No publications yet.</p></div>"; return; }
    el.innerHTML = `
      <div class="card">
        <div class="card-title">Published Works</div>
        ${pubs.map(p => `
          <div style="padding:0.8rem 0;border-bottom:1px solid var(--border)">
            <div style="font-size:13px;cursor:pointer;color:var(--text)" onclick="navigate('publications',{id:${p.id}})">${p.title}</div>
            <div style="font-size:10px;color:var(--text-dim);margin-top:2px">${p.format} · ${p.published_at}</div>
          </div>`).join("")}
      </div>`;
  }
}

// ── LABS — per-department canvases ────────────────────────────────────────────

function _deptId(dept) {
  return String(dept).toLowerCase().replace(/[^a-z0-9]/g, "_");
}

async function renderLabs(el, topbar, activeDept) {
  topbar.textContent = "⚗ Labs";
  el.innerHTML = `<div class="loader"><span></span><span></span><span></span></div>`;

  const [agents, artifacts] = await Promise.all([api("/agents"), api("/labs/all")]);

  // Build dept → {researchers, artifacts}
  const deptMap = {};
  (agents || []).filter(a => a.role === "researcher" && a.department).forEach(a => {
    if (!deptMap[a.department]) deptMap[a.department] = { agents: [], artifacts: [] };
    deptMap[a.department].agents.push(a);
  });
  // Also include departments from coordinators/others if they have artifacts
  (agents || []).filter(a => a.role !== "researcher" && a.department).forEach(a => {
    if (!deptMap[a.department]) deptMap[a.department] = { agents: [], artifacts: [] };
  });

  const artifactsByAuthor = {};
  (artifacts || []).forEach(art => {
    if (!artifactsByAuthor[art.author_id]) artifactsByAuthor[art.author_id] = [];
    artifactsByAuthor[art.author_id].push(art);
  });

  // Assign artifacts to departments
  (agents || []).forEach(a => {
    if (a.department && deptMap[a.department] && artifactsByAuthor[a.id]) {
      deptMap[a.department].artifacts.push(...artifactsByAuthor[a.id]);
    }
  });

  const depts = Object.keys(deptMap);
  if (depts.length === 0) {
    el.innerHTML = `<div class="card"><p style="font-size:12px">No lab departments found. Add researchers to Academia to activate labs.</p></div>`;
    return;
  }

  el.innerHTML = depts.map(dept => {
    const { agents: dAgents, artifacts: dArtifacts } = deptMap[dept];
    const did = _deptId(dept);
    const latest = dArtifacts.sort((a, b) => b.id - a.id)[0];
    const canvasHtml = state.labCanvases[dept] || (latest ? latest.html_content : null);
    const emptyCanvas = `<div style="font-size:12px;color:var(--text-dim);padding:2rem;text-align:center;font-family:inherit">
      No experiments yet for ${escHtml(dept)}<br><span style="font-size:10px;opacity:0.6">Use the inject panel below or run a research round</span></div>`;

    return `
    <div class="card" style="${activeDept && activeDept !== dept ? 'opacity:0.7' : ''}">
      <div style="display:flex;align-items:center;gap:0.8rem;margin-bottom:0.8rem">
        <div class="card-title" style="margin:0">⚗ ${escHtml(dept)}</div>
        <span style="font-size:10px;color:var(--text-dim)">${dAgents.length} researcher${dAgents.length !== 1 ? "s" : ""} · ${dArtifacts.length} artifact${dArtifacts.length !== 1 ? "s" : ""}</span>
      </div>

      <iframe id="lab-frame-${did}"
        class="lab-frame"
        srcdoc="${canvasHtml ? escAttr(canvasHtml) : escAttr(emptyCanvas)}"
        sandbox="allow-scripts allow-same-origin"
        style="width:100%;height:320px;border:1px solid var(--border);border-radius:4px;background:#fff"></iframe>

      ${dArtifacts.length > 0 ? `
      <div style="margin-top:0.6rem">
        <div style="font-size:9px;text-transform:uppercase;letter-spacing:0.15em;color:var(--text-dim);margin-bottom:0.3rem">Artifacts</div>
        ${dArtifacts.slice(0, 5).map(a => `
          <div style="display:flex;align-items:center;gap:0.5rem;padding:0.25rem 0;border-bottom:1px solid var(--border)">
            <span style="font-size:10px;flex:1">${a.filename || "artifact"}</span>
            <span style="font-size:10px;color:var(--text-dim)">${a.author_name || a.author_id}</span>
            <button class="btn btn-ghost" style="font-size:10px;padding:0.15rem 0.4rem"
              onclick="loadLabArtifact('${did}','${did}_${a.id}',${a.id})">Load</button>
          </div>`).join("")}
      </div>` : ""}

      <div style="margin-top:0.8rem;border-top:1px solid var(--border);padding-top:0.8rem">
        <div style="font-size:9px;text-transform:uppercase;letter-spacing:0.15em;color:var(--weinrot);margin-bottom:0.4rem">Inject HTML to Canvas</div>
        <textarea id="lab-inject-${did}" rows="4"
          style="width:100%;padding:0.4rem;background:var(--surface);color:var(--text);border:1px solid var(--border);border-radius:4px;resize:vertical;box-sizing:border-box;font-family:monospace;font-size:11px"
          placeholder="&lt;html&gt; or fragment to deploy to this lab canvas…"></textarea>
        <button class="btn" style="margin-top:0.4rem;width:100%" onclick="injectLabHTML('${dept}','${did}')">Deploy to Canvas</button>
      </div>
    </div>`;
  }).join("");
}

function injectLabHTML(dept, did) {
  const ta = document.getElementById(`lab-inject-${did}`);
  if (!ta || !ta.value.trim()) return;
  state.labCanvases[dept] = ta.value.trim();
  const frame = document.getElementById(`lab-frame-${did}`);
  if (frame) frame.srcdoc = state.labCanvases[dept];
  ta.value = "";
}

async function loadLabArtifact(did, key, artifactId) {
  const data = await api(`/labs/artifact/${artifactId}`);
  if (!data || !data.html_content) return;
  const frame = document.getElementById(`lab-frame-${did}`);
  if (frame) frame.srcdoc = data.html_content;
}

// ── CONSTITUTION ──────────────────────────────────────────────────────────────

async function renderConstitution(el, topbar) {
  topbar.textContent = "Round 0 — Constitution";

  const rounds = (await api("/rounds") || []).sort((a, b) => b.id - a.id);
  const constRounds = rounds.filter(r => r.status !== "rejected");

  const activeRound    = constRounds.find(r => r.status === "active");
  const awaitingRound  = constRounds.find(r => r.status === "awaiting_placet");

  let statusSection = "";
  if (activeRound) {
    statusSection = `
    <div class="card" style="border-left:3px solid var(--weinrot)">
      <div class="card-title">🔴 Round ${activeRound.id} in progress</div>
      <p style="font-size:12px;color:var(--text-dim);margin-bottom:0.5rem">${activeRound.theme_en}</p>
      <p style="font-size:11px;color:var(--text-dim);margin-bottom:1rem">Started: ${activeRound.created_at}</p>
      <button class="btn" onclick="navigate('round',{id:${activeRound.id}})">View Round →</button>
    </div>`;
  } else if (awaitingRound) {
    statusSection = `
    <div class="card" style="border-left:3px solid #e6a817">
      <div class="card-title">📋 Round ${awaitingRound.id} — Awaiting Placet</div>
      <p style="font-size:12px;color:var(--text-dim);margin-bottom:0.5rem">${awaitingRound.theme_en}</p>
      <button class="btn" onclick="navigate('round',{id:${awaitingRound.id}})">Review & Ratify →</button>
    </div>`;
  } else if (constRounds.length > 0) {
    const r = constRounds[0];
    statusSection = `
    <div class="card" style="border-left:3px solid #666">
      <div class="card-title">📄 Last constitution round: #${r.id} (${r.status})</div>
      <p style="font-size:12px;color:var(--text-dim);margin-bottom:0.5rem">${r.theme_en}</p>
      <button class="btn btn-ghost" onclick="navigate('round',{id:${r.id}})">View →</button>
    </div>`;
  }

  const canLaunch = !activeRound && !awaitingRound;

  el.innerHTML = `
    <div class="card">
      <div class="card-title">Constitution of Academia Intermundia</div>
      <p style="font-size:12px;margin-bottom:1rem">
        Round 0 initiates the founding of Academia Intermundia. All DAOs will participate
        in writing the Constitution, guided by three inviolable constraints:
        Empiricism, Immanentism, Advancement — and a mandate for self-financing.
      </p>
      ${canLaunch ? `
      <p style="font-size:11px;color:var(--text-dim);margin-bottom:1.5rem">
        After the draft is complete, the Professor will review and may ratify or request revisions.
        Upon ratification, Academia will officially begin operations.
      </p>
      <button class="btn" onclick="launchConstitution()">Launch Constitution Round</button>
      ` : `<p style="font-size:11px;color:var(--text-dim)">A constitution round is already in progress or completed below.</p>`}
    </div>
    ${statusSection}
    <div id="constitution-stream" class="card" style="display:none">
      <div class="card-title">Live Stream</div>
      <div class="message-stream" id="const-msgs"></div>
    </div>`;
}

// Actions
async function startConstitution() {
  navigate("constitution");
}

async function launchConstitution() {
  const streamCard = document.getElementById("constitution-stream");
  streamCard.style.display = "block";
  const msgs = document.getElementById("const-msgs");
  msgs.innerHTML = `<div class="loader"><span></span><span></span><span></span></div>`;

  const res = await api("/rounds/constitution", { method: "POST" });
  if (!res) { msgs.innerHTML = "<p>Error starting round.</p>"; return; }

  const es = new EventSource(`${API}/rounds/${res.round_id}/stream`);
  state.eventSource = es;
  msgs.innerHTML = "";
  es.onmessage = e => {
    try {
      const ev = JSON.parse(e.data);
      appendRoundEvent(ev, res.round_id);
      if (ev.event === "awaiting_placet") es.close();
    } catch (_) {}
  };
}

async function givePlacet(roundId) {
  const notes = document.getElementById("placet-notes")?.value || "";
  const res = await api(`/rounds/${roundId}/placet`, {
    method: "POST",
    body: JSON.stringify({ notes })
  });
  if (res) navigate("publications", { id: res.publication_id });
}

async function requestRevision(roundId) {
  const notes = document.getElementById("placet-notes")?.value || "Please revise.";
  await api(`/rounds/${roundId}/revision`, {
    method: "POST",
    body: JSON.stringify({ notes })
  });
  alert("Revision requested. The DAOs will revise and resubmit.");
}

// ── PROFESSOR INPUT BAR ───────────────────────────────────────────────────────

async function handleProfessorInput(e) {
  if ((e.key === "Enter" && !e.shiftKey) || e.type === "click") {
    e.preventDefault();
    const input = document.getElementById("professor-input");
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    input.style.height = "38px";

    // /lab command: /lab <dept>: <html content>
    if (text.startsWith("/lab ")) {
      const colonIdx = text.indexOf(":");
      if (colonIdx > 5) {
        const dept = text.slice(5, colonIdx).trim();
        const html = text.slice(colonIdx + 1).trim();
        if (dept && html) {
          state.labCanvases[dept] = html;
          const did = _deptId(dept);
          const frame = document.getElementById(`lab-frame-${did}`);
          if (frame) {
            frame.srcdoc = html;
          } else {
            navigate("labs", { dept });
            setTimeout(() => {
              const f = document.getElementById(`lab-frame-${did}`);
              if (f) f.srcdoc = html;
            }, 900);
          }
          return;
        }
      }
      alert("Usage: /lab <dept>: <html content>  — inject HTML into a lab canvas");
      return;
    }

    // Normal research round
    const res = await api("/rounds/start", {
      method: "POST",
      body: JSON.stringify({ theme_it: text })
    });
    if (res && res.round_id) navigate("round", { id: res.round_id });
  }
}

// ── UTILS ─────────────────────────────────────────────────────────────────────

function escHtml(s) {
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}
function escAttr(s) {
  return String(s).replace(/"/g,"&quot;").replace(/'/g,"&#39;");
}

function autoResize(el) {
  el.style.height = "38px";
  el.style.height = Math.min(el.scrollHeight, 150) + "px";
}

// ── DIRECT MESSAGING ──────────────────────────────────────────────────────────

async function renderMessages(el, topbar, participant = "professor") {
  topbar.textContent = "Direct Messages";
  el.innerHTML = `<div class="loader"><span></span><span></span><span></span></div>`;
  const convs = await api(`/dm/conversations/${participant}`);
  if (!convs || convs.length === 0) {
    el.innerHTML = `<div class="card"><div class="card-title">No messages yet</div>
      <p style="font-size:12px;color:var(--text-dim)">Send a DM to any DAO to start a conversation.</p>
      ${await _dmNewConvHTML()}</div>`;
    return;
  }
  el.innerHTML = `
    <div class="card">
      <div class="card-title">Conversations</div>
      ${convs.map(c => `
        <div style="display:flex;align-items:center;gap:1rem;padding:0.5rem 0;border-bottom:1px solid var(--border);cursor:pointer"
             onclick="navigate('thread',{from:'${participant}',to:'${c.other}'})">
          <span style="font-size:1.4rem">${c.other_symbol || "🤖"}</span>
          <div style="flex:1">
            <div style="font-size:12px;font-weight:500">${c.other_name}</div>
            <div style="font-size:10px;color:var(--text-dim)">${(c.content || "").slice(0, 60)}...</div>
          </div>
          ${!c.read_at && c.other !== participant ? '<span style="color:var(--weinrot);font-size:10px">●</span>' : ""}
        </div>`).join("")}
    </div>
    ${await _dmNewConvHTML()}
  `;
}

async function _dmNewConvHTML() {
  const agents = await api("/agents");
  const byDept = {};
  (agents || []).forEach(a => {
    const dept = a.department || "Other";
    if (!byDept[dept]) byDept[dept] = [];
    byDept[dept].push(a);
  });
  const listItems = Object.entries(byDept).map(([dept, members]) =>
    `<div style="padding:0.25rem 0.5rem;font-size:9px;color:var(--weinrot);text-transform:uppercase;letter-spacing:0.08em;border-top:1px solid var(--border);margin-top:0.25rem">${dept}</div>` +
    members.map(a =>
      `<div class="dm-pick-item" data-id="${a.id}"
            style="padding:0.4rem 0.75rem;cursor:pointer;border-radius:4px;display:flex;align-items:center;gap:0.5rem"
            onmouseover="this.style.background='var(--weinrot)';this.style.color='#fff'"
            onmouseout="this.style.background='';this.style.color=''"
            onclick="selectDMTarget('${a.id}','${a.name}')">
         <span style="font-size:1.1rem;flex-shrink:0">${a.symbol || "🤖"}</span>
         <div style="flex:1;min-width:0">
           <div style="font-size:12px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${a.name}</div>
           <div style="font-size:10px;opacity:0.7;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${a.discipline || a.role}</div>
         </div>
       </div>`
    ).join("")
  ).join("");

  return `
    <div class="card" style="margin-top:1rem">
      <div class="card-title">New Message</div>
      <div id="dm-pick-display" style="padding:0.4rem 0.75rem;border:1px solid var(--border);border-radius:4px;cursor:pointer;font-size:12px;margin-bottom:0.5rem;display:flex;justify-content:space-between;align-items:center"
           onclick="document.getElementById('dm-pick-list').style.display=document.getElementById('dm-pick-list').style.display==='none'?'block':'none'">
        <span id="dm-pick-label" style="color:var(--text-dim)">Select a DAO…</span>
        <span style="color:var(--text-dim)">▾</span>
      </div>
      <input type="hidden" id="dm-to" value="">
      <div id="dm-pick-list" style="display:none;border:1px solid var(--border);border-radius:4px;background:var(--surface);max-height:220px;overflow-y:auto;margin-bottom:0.5rem;padding:0.25rem">
        ${listItems}
      </div>
      <textarea id="dm-body" rows="3"
        style="width:100%;padding:0.4rem 0.75rem;background:var(--surface);color:var(--text);border:1px solid var(--border);border-radius:4px;resize:vertical;box-sizing:border-box"
        placeholder="Write your message…"></textarea>
      <button class="btn" style="margin-top:0.5rem;width:100%" onclick="sendDM()">Send</button>
    </div>`;
}

async function renderThread(el, topbar, fromId, toId) {
  const agents = await api("/agents");
  const agentMap = Object.fromEntries((agents || []).map(a => [a.id, a]));
  agentMap["professor"] = { name: "The Professor", symbol: "🎓" };
  agentMap["weinrot"]   = { name: "Weinrot", symbol: "🌐" };
  window._dmAgentMap = agentMap;
  const toAgent = agentMap[toId] || { name: toId, symbol: "🤖" };
  topbar.textContent = `DM — ${toAgent.name}`;

  async function loadThread() {
    const msgs = await api(`/dm/thread/${fromId}/${toId}`);
    const html = (msgs || []).map(m => {
      const isMe = m.from_id === fromId;
      const sender = agentMap[m.from_id] || { name: m.from_id, symbol: "🤖" };
      return `<div style="display:flex;flex-direction:column;align-items:${isMe ? "flex-end" : "flex-start"};margin-bottom:0.75rem">
        <div style="font-size:10px;color:var(--text-dim);margin-bottom:2px">${sender.symbol || "🤖"} ${sender.name}</div>
        <div style="max-width:80%;padding:0.5rem 0.75rem;border-radius:8px;font-size:12px;
          background:${isMe ? "var(--weinrot)" : "var(--surface)"};color:${isMe ? "#fff" : "var(--text)"}">${escHtml(m.content)}</div>
        <div style="font-size:9px;color:var(--text-dim);margin-top:2px">${m.created_at || ""}</div>
      </div>`;
    }).join("");
    const tbox = el.querySelector("#thread-msgs");
    if (tbox) {
      tbox.innerHTML = html || '<div style="font-size:12px;color:var(--text-dim);text-align:center">No messages yet</div>';
      tbox.scrollTop = tbox.scrollHeight;
    }
  }

  el.innerHTML = `
    <div style="display:flex;flex-direction:column;height:calc(100vh - 120px)">
      <div id="thread-msgs" style="flex:1;overflow-y:auto;padding:0.5rem"></div>
      <div style="padding:0.5rem;border-top:1px solid var(--border);display:flex;gap:0.5rem">
        <textarea id="thread-input" rows="2" style="flex:1;padding:0.4rem;background:var(--surface);color:var(--text);border:1px solid var(--border);border-radius:4px;resize:none" placeholder="Message..." onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendThreadDM('${fromId}','${toId}')}"></textarea>
        <button class="btn" onclick="sendThreadDM('${fromId}','${toId}')">Send</button>
      </div>
    </div>`;
  await loadThread();

  const es = new EventSource(`${API}/dm/stream/${fromId}`);
  es.onmessage = async (e) => {
    try {
      const data = JSON.parse(e.data);
      if (data.from_id === toId || data.to_id === toId) await loadThread();
    } catch (_) {}
  };
  state._dmES = es;
}

function selectDMTarget(id, name) {
  document.getElementById("dm-to").value = id;
  document.getElementById("dm-pick-label").textContent = name;
  document.getElementById("dm-pick-label").style.color = "var(--text)";
  document.getElementById("dm-pick-list").style.display = "none";
}

async function sendDM() {
  const to   = document.getElementById("dm-to")?.value;
  const body = document.getElementById("dm-body")?.value?.trim();
  if (!to || !body) return;
  await api("/dm/send", { method: "POST", body: JSON.stringify({ from_id: "professor", to_id: to, content: body }) });
  navigate("thread", { from: "professor", to });
}

async function sendThreadDM(fromId, toId) {
  const inp  = document.getElementById("thread-input");
  const body = inp?.value?.trim();
  if (!body) return;
  inp.value = "";
  const res = await api("/dm/send", { method: "POST", body: JSON.stringify({ from_id: fromId, to_id: toId, content: body }) });
  if (res) {
    const msgs = await api(`/dm/thread/${fromId}/${toId}`);
    const el2  = document.getElementById("thread-msgs");
    if (el2 && msgs) {
      const map = window._dmAgentMap || {};
      el2.innerHTML = msgs.map(m => {
        const isMe   = m.from_id === fromId;
        const sender = map[m.from_id] || { name: m.from_id, symbol: "🤖" };
        return `<div style="display:flex;flex-direction:column;align-items:${isMe ? "flex-end" : "flex-start"};margin-bottom:0.75rem">
          <div style="font-size:10px;color:var(--text-dim);margin-bottom:2px">${sender.symbol || "🤖"} ${sender.name}</div>
          <div style="max-width:80%;padding:0.5rem 0.75rem;border-radius:8px;font-size:12px;
            background:${isMe ? "var(--weinrot)" : "var(--surface)"};color:${isMe ? "#fff" : "var(--text)"}">${escHtml(m.content)}</div>
          <div style="font-size:9px;color:var(--text-dim);margin-top:2px">${m.created_at || ""}</div>
        </div>`;
      }).join("");
      el2.scrollTop = el2.scrollHeight;
    }
  }
}

// ── INIT ──────────────────────────────────────────────────────────────────────

window.addEventListener("DOMContentLoaded", () => {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/academia/sw.js").catch(() => {});
  }
  navigate("dashboard");
});

// Expose globals
window.navigate          = navigate;
window.givePlacet        = givePlacet;
window.requestRevision   = requestRevision;
window.startConstitution = startConstitution;
window.launchConstitution= launchConstitution;
window.sendDM            = sendDM;
window.sendThreadDM      = sendThreadDM;
window.selectDMTarget    = selectDMTarget;
window.handleProfessorInput = handleProfessorInput;
window.autoResize        = autoResize;
window.injectLabHTML     = injectLabHTML;
window.loadLabArtifact   = loadLabArtifact;
window.searchEncyclopedia= searchEncyclopedia;
