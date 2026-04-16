// Academia Intermundia 2.0 — Main App
const API = window.ACADEMIA_API || "https://80.211.139.85:8083/api";

// State
const state = {
  view: "dashboard",
  rounds: [],
  activeRound: null,
  agents: [],
  eventSource: null,
};

// Router
function navigate(view, params = {}) {
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
    case "dashboard": return renderDashboard(content, topbar);
    case "round": return renderRound(content, topbar, params.id);
    case "constitution": return renderConstitution(content, topbar);
    case "wiki": return renderWiki(content, topbar, params.pageId);
    case "publications": return renderPublications(content, topbar, params.id);
    case "labs": return renderLabs(content, topbar, params.roundId);
    case "agents": return renderAgents(content, topbar);
  }
}

async function renderDashboard(el, topbar) {
  topbar.textContent = "Dashboard";
  el.innerHTML = `<div class="loader"><span></span><span></span><span></span></div>`;
  const [rounds, agents] = await Promise.all([api("/rounds"), api("/agents")]);
  state.rounds = rounds || [];
  state.agents = agents || [];

  const active = state.rounds.filter(r => r.status === "active" || r.status === "awaiting_placet");
  const past = state.rounds.filter(r => r.status === "ratified" || r.status === "closed");

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
  `;
}

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
      <div class="card-title">Wiki Pages (${pages.length})</div>
      ${pages.map(p => `
        <div style="padding:0.5rem 0;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:0.8rem">
          <div style="flex:1">
            <span style="font-size:12px">${p.title}</span>
            <span class="draft-badge" style="margin-left:6px">${p.status}</span>
          </div>
          <span style="font-size:10px;color:var(--text-dim)">${p.author_name || p.author_id}</span>
          <button class="btn btn-ghost" onclick="navigate('wiki',{pageId:${p.id}})">Read →</button>
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

  // If round is active, start streaming
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
  } else if (ev.event === "wiki_page") {
    const notice = document.createElement("div");
    notice.className = "phase-banner";
    notice.textContent = `Wiki page saved: "${ev.title}" by ${ev.author}`;
    stream.appendChild(notice);
  } else if (ev.event === "awaiting_placet") {
    navigate("round", { id: roundId });
  }
}

async function renderWiki(el, topbar, pageId) {
  if (pageId) {
    topbar.textContent = "Wiki";
    el.innerHTML = `<div class="loader"><span></span><span></span><span></span></div>`;
    const page = await api(`/wiki/${pageId}`);
    if (!page) { el.innerHTML = "<p>Page not found.</p>"; return; }
    topbar.textContent = page.title;
    el.innerHTML = `
      <div class="wiki-page">
        <h1>${page.title}</h1>
        <div class="meta">
          By ${page.author_name || page.author_id} ·
          ${page.created_at} ·
          <span class="draft-badge">${page.status}</span>
        </div>
        <div>${page.content_en}</div>
      </div>`;
  } else {
    topbar.textContent = "Wiki";
    el.innerHTML = `<div class="loader"><span></span><span></span><span></span></div>`;
    const pages = await api("/wiki");
    if (!pages) { el.innerHTML = "<p>No pages yet.</p>"; return; }
    el.innerHTML = `
      <div class="card">
        <div class="card-title">All Wiki Pages (${pages.length})</div>
        ${pages.map(p => `
          <div style="padding:0.5rem 0;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:0.8rem">
            <div style="flex:1">
              <span style="font-size:12px;cursor:pointer;color:var(--text)" onclick="navigate('wiki',{pageId:${p.id}})">${p.title}</span>
              <span class="draft-badge" style="margin-left:6px">${p.status}</span>
            </div>
            <span style="font-size:10px;color:var(--text-dim)">${p.author_name || p.author_id}</span>
          </div>`).join("")}
      </div>`;
  }
}

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

async function renderLabs(el, topbar, roundId) {
  topbar.textContent = "Labs";
  el.innerHTML = `<div class="loader"><span></span><span></span><span></span></div>`;
  const path = roundId ? `/labs/${roundId}` : "/labs/all";
  const artifacts = await api(path);
  if (!artifacts || artifacts.length === 0) {
    el.innerHTML = "<div class='card'><p>No lab artifacts yet.</p></div>"; return;
  }
  el.innerHTML = artifacts.map(a => `
    <div class="card">
      <div class="card-title">${a.filename}</div>
      <div style="font-size:10px;color:var(--text-dim);margin-bottom:0.8rem">by ${a.author_name || a.author_id}</div>
      <iframe class="lab-frame" srcdoc="${escAttr(a.html_content)}" sandbox="allow-scripts allow-same-origin"></iframe>
    </div>`).join("");
}

async function renderConstitution(el, topbar) {
  topbar.textContent = "Round 0 — Constitution";
  el.innerHTML = `
    <div class="card">
      <div class="card-title">Constitution of Academia Intermundia</div>
      <p style="font-size:12px;margin-bottom:1rem">
        Round 0 initiates the founding of Academia Intermundia. All DAOs will participate
        in writing the Constitution, guided by three inviolable constraints:
        Empiricism, Immanentism, Advancement — and a mandate for self-financing.
      </p>
      <p style="font-size:11px;color:var(--text-dim);margin-bottom:1.5rem">
        After the draft is complete, the Professor will review and may ratify or request revisions.
        Upon ratification, Academia will officially begin operations.
      </p>
      <button class="btn" onclick="launchConstitution()">Launch Constitution Round</button>
    </div>
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

// Professor input bar
async function handleProfessorInput(e) {
  if ((e.key === "Enter" && !e.shiftKey) || e.type === "click") {
    e.preventDefault();
    const input = document.getElementById("professor-input");
    const theme = input.value.trim();
    if (!theme) return;
    input.value = "";
    input.style.height = "38px";

    const res = await api("/rounds/start", {
      method: "POST",
      body: JSON.stringify({ theme_it: theme })
    });
    if (res && res.round_id) navigate("round", { id: res.round_id });
  }
}

// Utils
function escHtml(s) {
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}
function escAttr(s) {
  return String(s).replace(/"/g,"&quot;").replace(/'/g,"&#39;");
}

// Auto-resize textarea
function autoResize(el) {
  el.style.height = "38px";
  el.style.height = Math.min(el.scrollHeight, 150) + "px";
}

// Init
window.addEventListener("DOMContentLoaded", () => {
  // PWA install
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/academia/sw.js").catch(() => {});
  }
  navigate("dashboard");
});

// Expose globals
window.navigate = navigate;
window.givePlacet = givePlacet;
window.requestRevision = requestRevision;
window.startConstitution = startConstitution;
window.launchConstitution = launchConstitution;
window.handleProfessorInput = handleProfessorInput;
window.autoResize = autoResize;
