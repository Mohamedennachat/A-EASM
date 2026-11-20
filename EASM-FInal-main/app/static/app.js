const $ = (id) => document.getElementById(id);
const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmtDate = (s) => s ? new Date(s).toLocaleString() : "-";
const sevBadge = (s) => `<span class="badge sev-${esc(s || 'none')}">${esc(s || 'n/a')}</span>`;

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m; } catch (e) {} throw new Error(m); }
  return r.status === 204 ? null : r.json();
}
function toast(msg, kind) {
  const t = el("div", "toast " + (kind || ""), esc(msg));
  $("toast").appendChild(t);
  setTimeout(() => t.remove(), 4200);
}

// ── tabs ──────────────────────────────────────────────────────────
const loaders = {};
document.querySelectorAll("#tabs button").forEach(b => b.onclick = () => {
  document.querySelectorAll("#tabs button").forEach(x => x.classList.remove("active"));
  document.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
  b.classList.add("active");
  const tab = b.dataset.tab;
  $(tab).classList.add("active");
  if (loaders[tab]) loaders[tab]();
});

// ── overview ──────────────────────────────────────────────────────
async function loadOverview() {
  const o = await api("/api/overview");
  const c = o.counts || {};
  const cards = [
    ["Active targets", c.active_domains, ""],
    ["Findings", c.findings, ""],
    ["Critical / High", c.crit_high, c.crit_high > 0 ? "alert" : "ok"],
    ["Assets discovered", c.assets, ""],
    ["Scans run", c.scans, ""],
  ];
  $("statCards").innerHTML = cards.map(([l, v, k]) =>
    `<div class="card ${k}"><div class="v">${v ?? 0}</div><div class="l">${l}</div></div>`).join("");

  // services pills
  $("services").innerHTML = Object.entries(o.services || {}).map(([n, up]) =>
    `<span class="pill"><span class="dot ${up ? 'up' : 'down'}"></span>${esc(n)}</span>`).join("");

  // last scan
  const ls = o.last_scan;
  $("lastScan").innerHTML = ls ? `
    <div style="display:flex;gap:26px;flex-wrap:wrap;align-items:center">
      <div><span class="muted">When</span><br>${fmtDate(ls.scan_timestamp)}</div>
      <div><span class="muted">New findings</span><br><b style="font-size:18px">${ls.new_findings_count ?? 0}</b></div>
      <div><span class="muted">Alert</span><br>${ls.requires_alert ? '<span class="alerted">🔔 FIRED</span>' : '<span class="suppressed">suppressed (no new)</span>'}</div>
      <div><span class="muted">Severity mix</span><br>
        ${sevBadge('critical')} ${ls.critical_count ?? 0} &nbsp; ${sevBadge('high')} ${ls.high_count ?? 0} &nbsp;
        ${sevBadge('medium')} ${ls.medium_count ?? 0} &nbsp; <span class="tag">XSS ${ls.confirmed_xss_count ?? 0}</span>
        <span class="tag">SQLi ${ls.confirmed_sqli_count ?? 0}</span> <span class="tag">certs⏳ ${ls.expiring_soon_count ?? 0}</span></div>
    </div>` : '<div class="empty">No scans yet - hit “Run Scan”.</div>';
  renderPipeline(o.stages, -1, false);
}

function renderPipeline(stages, idx, running) {
  stages = stages || [];
  $("pipeline").innerHTML = stages.map((s, i) => {
    let cls = "stage";
    if (running && i === idx) cls += " active";
    else if (idx >= stages.length || (running && i < idx) || (!running && idx === stages.length)) cls += " done";
    return `<div class="${cls}"><div class="n">${String(i + 1).padStart(2, '0')}</div><div class="t">${esc(s)}</div></div>`;
  }).join("");
}

// ── live scan status polling ──────────────────────────────────────
let pollTimer = null;
async function pollStatus() {
  let st;
  try { st = await api("/api/scan/status"); } catch (e) { return; }
  const btn = $("runBtn");
  if (st.running) {
    btn.disabled = true; btn.classList.add("running"); btn.textContent = "● Scanning…";
    renderPipeline(st.stages, st.stage_index, true);
    const pct = Math.round((st.stage_index / st.stages.length) * 100);
    $("scanStatus").innerHTML =
      `Running · stage ${Math.min(st.stage_index + 1, st.stages.length)}/${st.stages.length} · ${st.elapsed}s elapsed`
      + `<div class="bar"><div style="width:${Math.max(6, pct)}%"></div></div>`;
  } else {
    btn.disabled = false; btn.classList.remove("running"); btn.textContent = "▶ Run Scan";
    if (window._wasRunning) {  // just finished
      window._wasRunning = false;
      toast("Scan complete", "ok");
      loadOverview();
      if (document.querySelector("#tabs button.active").dataset.tab !== "overview") {
        const t = document.querySelector("#tabs button.active").dataset.tab; if (loaders[t]) loaders[t]();
      }
    }
    $("scanStatus").innerHTML = st.last_error ? `<span style="color:var(--red)">Last error: ${esc(st.last_error)}</span>` : "";
  }
  window._wasRunning = st.running || window._wasRunning;
}

$("runBtn").onclick = async () => {
  const watch = $("watchToggle") && $("watchToggle").checked;
  try {
    await api("/api/scan/run" + (watch ? "?watch=1" : ""), { method: "POST" });
    window._wasRunning = true;
    toast(watch ? "Scan started - watch the nodes animate on the n8n canvas" : "Scan started - watch the pipeline below", "ok");
    pollStatus();
  } catch (e) { toast("Could not start scan: " + e.message, "err"); }
};

if ($("watchToggle")) $("watchToggle").onchange = (e) => {
  if (e.target.checked)
    toast("Watch mode: open the workflow in n8n, click 'Execute workflow' to arm it, then Run Scan", "ok");
};

// ── targets ───────────────────────────────────────────────────────
loaders.targets = async () => {
  const d = await api("/api/domains");
  $("domainsTable").innerHTML = d.length ? `<table><thead><tr>
    <th>Domain</th><th>Status</th><th>Priority</th><th>Last scanned</th><th></th></tr></thead><tbody>` +
    d.map(r => `<tr>
      <td class="mono">${esc(r.domain)}</td>
      <td class="s-${r.status}">${r.status === 'active' ? '● active' : '○ inactive'}</td>
      <td>${r.priority}</td>
      <td class="muted">${r.last_scanned ? fmtDate(r.last_scanned) : '-'}</td>
      <td style="text-align:right">
        <button class="act" onclick="toggleDom('${esc(r.domain)}')">${r.status === 'active' ? 'Disable' : 'Enable'}</button>
        <button class="act" onclick="delDom('${esc(r.domain)}')">Remove</button></td>
    </tr>`).join("") + "</tbody></table>"
    : '<div class="empty">No targets. Add one above.</div>';
};
window.toggleDom = async (dom) => { try { await api(`/api/domains/${encodeURIComponent(dom)}/toggle`, { method: "POST" }); loaders.targets(); } catch (e) { toast(e.message, "err"); } };
window.delDom = async (dom) => { if (!confirm("Remove " + dom + "?")) return; try { await api(`/api/domains/${encodeURIComponent(dom)}`, { method: "DELETE" }); loaders.targets(); } catch (e) { toast(e.message, "err"); } };
$("addBtn").onclick = async () => {
  const v = $("newDomain").value.trim();
  if (!v) return;
  try { await api("/api/domains", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ domain: v }) }); $("newDomain").value = ""; toast("Added " + v, "ok"); loaders.targets(); }
  catch (e) { toast(e.message, "err"); }
};

// ── findings ──────────────────────────────────────────────────────
loaders.findings = async () => {
  const f = await api("/api/findings");
  $("findingsCount").textContent = `(${f.length})`;
  $("findingsTable").innerHTML = f.length ? `<table><thead><tr>
    <th>Severity</th><th>Cat</th><th>Host</th><th>Finding</th><th>Status</th><th>Seen×</th><th>First seen</th></tr></thead><tbody>` +
    f.map(r => `<tr>
      <td>${sevBadge(r.severity)}</td>
      <td><span class="tag">${esc(r.category)}</span></td>
      <td class="mono">${esc(r.host)}</td>
      <td>${esc(r.title)}</td>
      <td>${r.times_seen <= 1 ? '<span class="new">NEW</span>' : '<span class="muted">known</span>'}</td>
      <td>${r.times_seen}</td>
      <td class="muted">${fmtDate(r.first_seen)}</td>
    </tr>`).join("") + "</tbody></table>"
    : '<div class="empty">No findings yet.</div>';
};

// ── assets ────────────────────────────────────────────────────────
loaders.assets = async () => {
  const a = await api("/api/assets");
  $("assetsTable").innerHTML = a.length ? `<table><thead><tr>
    <th>Host</th><th>IP</th><th>Port</th><th>Scheme</th><th>Status</th><th>Title</th><th>Server</th><th>Source</th></tr></thead><tbody>` +
    a.map(r => `<tr>
      <td class="mono">${esc(r.host)}</td><td class="mono">${esc(r.ip)}</td><td>${r.port || ''}</td>
      <td>${esc(r.scheme)}</td><td>${r.status_code || ''}</td><td>${esc(r.title)}</td>
      <td>${esc(r.webserver)}</td><td><span class="tag">${esc(r.source)}</span></td>
    </tr>`).join("") + "</tbody></table>"
    : '<div class="empty">No assets yet - run a scan.</div>';
};

// ── certs ─────────────────────────────────────────────────────────
loaders.certs = async () => {
  const c = await api("/api/certs");
  $("certsTable").innerHTML = c.length ? `<table><thead><tr>
    <th>Host</th><th>Common name</th><th>Issuer</th><th>Expires</th><th>Days left</th><th>Status</th></tr></thead><tbody>` +
    c.map(r => `<tr>
      <td class="mono">${esc(r.host)}</td><td>${esc(r.common_name)}</td><td class="muted">${esc(r.issuer)}</td>
      <td class="muted">${esc((r.not_after || '').slice(0, 10))}</td>
      <td>${r.days_until_expiry == null ? '-' : r.days_until_expiry}</td>
      <td>${r.is_expired ? '<span class="badge sev-critical">expired</span>' : r.expiring_soon ? '<span class="badge sev-high">expiring</span>' : '<span class="badge sev-low">ok</span>'}</td>
    </tr>`).join("") + "</tbody></table>"
    : '<div class="empty">No certificates yet.</div>';
};

// ── history (diff engine viz) ─────────────────────────────────────
const fmtDur = (s) => s == null ? "-" : (s < 60 ? s + "s" : Math.floor(s / 60) + "m " + (s % 60) + "s");

loaders.history = async () => {
  const h = await api("/api/scans");
  const max = Math.max(1, ...h.map(r => r.new_findings_count || 0));
  $("historyTable").innerHTML = h.length ? `<p class="muted">Click a scan to see what it scanned, how long it took, and everything it found.</p><table><thead><tr>
    <th>Scan time</th><th>Duration</th><th>New</th><th></th><th>Crit</th><th>High</th><th>Med</th><th>XSS</th><th>SQLi</th><th>Certs⏳</th><th>Alert</th><th></th></tr></thead><tbody>` +
    h.map(r => `<tr style="cursor:pointer" onclick="openScan(${r.id})">
      <td class="muted">${fmtDate(r.scan_timestamp)}</td>
      <td>${fmtDur(r.duration_seconds)}</td>
      <td><b>${r.new_findings_count ?? 0}</b></td>
      <td><span class="barmini" style="width:${Math.round((r.new_findings_count || 0) / max * 90)}px"></span></td>
      <td>${r.critical_count}</td><td>${r.high_count}</td><td>${r.medium_count}</td>
      <td>${r.confirmed_xss_count}</td><td>${r.confirmed_sqli_count}</td><td>${r.expiring_soon_count}</td>
      <td>${r.requires_alert ? '<span class="alerted">🔔 fired</span>' : '<span class="suppressed">suppressed</span>'}</td>
      <td class="muted">view ›</td>
    </tr>`).join("") + "</tbody></table>"
    : '<div class="empty">No scan history yet.</div>';
};

window.closeModal = () => $("modal").classList.remove("show");
window.openScan = async (id) => {
  const m = $("modal"), b = $("modalBody");
  b.innerHTML = '<div class="empty">Loading…</div>'; m.classList.add("show");
  try { b.innerHTML = renderScanDetail(await api(`/api/scans/${id}`)); }
  catch (e) { b.innerHTML = `<div class="empty">Error: ${esc(e.message)}</div>`; }
};
function renderScanDetail(d) {
  const s = d.summary;
  const tbl = (title, cols, rows, render) => rows && rows.length
    ? `<h4>${title} <span class="muted">(${rows.length})</span></h4><table><thead><tr>${cols.map(c => `<th>${c}</th>`).join('')}</tr></thead><tbody>${rows.map(render).join('')}</tbody></table>` : '';
  return `
    <div class="modal-head">
      <h2>Scan detail</h2>
      <div class="modal-meta">
        <div><span class="muted">When</span><br>${fmtDate(s.scan_timestamp)}</div>
        <div><span class="muted">Duration</span><br><b style="font-size:17px">${fmtDur(s.duration_seconds)}</b></div>
        <div><span class="muted">New findings</span><br><b style="font-size:17px">${s.new_findings_count ?? 0}</b></div>
        <div><span class="muted">Alert</span><br>${s.requires_alert ? '<span class="alerted">🔔 fired</span>' : '<span class="suppressed">suppressed (no new)</span>'}</div>
      </div>
      <div class="modal-sev">${sevBadge('critical')} ${s.critical_count} &nbsp; ${sevBadge('high')} ${s.high_count} &nbsp; ${sevBadge('medium')} ${s.medium_count} &nbsp;
        <span class="tag">XSS ${s.confirmed_xss_count}</span> <span class="tag">SQLi ${s.confirmed_sqli_count}</span>
        <span class="tag">certs scanned ${s.total_certs_scanned}</span> <span class="tag">certs⏳ ${s.expiring_soon_count}</span></div>
    </div>
    <div class="modal-section"><h4>Scanned <span class="muted">${d.hosts_scanned.length} host(s) · ${d.assets.length} live asset(s)</span></h4>
      <div class="chips">${d.hosts_scanned.map(h => `<span class="chip">${esc(h)}</span>`).join('') || '<span class="muted">-</span>'}</div></div>
    ${tbl('Vulnerabilities (nuclei)', ['Severity', 'Host', 'Finding', 'URL'], d.vulnerabilities, v => `<tr><td>${sevBadge(v.severity)}</td><td class="mono">${esc(v.host)}</td><td>${esc(v.template_name || v.template_id)}</td><td class="mono" style="font-size:11px">${esc((v.url || '').slice(0, 60))}</td></tr>`)}
    ${tbl('SQL injection', ['URL', 'Param', 'DBMS', 'Technique'], d.sqli, x => `<tr><td class="mono">${esc(x.url)}</td><td>${esc(x.parameter)}</td><td>${esc(x.dbms)}</td><td>${esc(x.technique)}</td></tr>`)}
    ${tbl('XSS', ['URL', 'Param', 'Type'], d.xss, x => `<tr><td class="mono">${esc(x.url)}</td><td>${esc(x.parameter)}</td><td>${esc(x.xss_type)}</td></tr>`)}
    ${tbl('Certificates', ['Host', 'Common name', 'Expires', 'Days', 'Status'], d.certificates, c => `<tr><td class="mono">${esc(c.host)}</td><td>${esc(c.common_name)}</td><td class="muted">${esc((c.not_after || '').slice(0, 10))}</td><td>${c.days_until_expiry == null ? '-' : c.days_until_expiry}</td><td>${c.is_expired ? '<span class="badge sev-critical">expired</span>' : c.expiring_soon ? '<span class="badge sev-high">expiring</span>' : '<span class="badge sev-low">ok</span>'}</td></tr>`)}
    ${tbl('Discovered assets', ['Host', 'IP', 'Port', 'Title', 'Server', 'Source'], d.assets, a => `<tr><td class="mono">${esc(a.host)}</td><td class="mono">${esc(a.ip)}</td><td>${a.port || ''}</td><td>${esc((a.title || '').slice(0, 40))}</td><td>${esc(a.webserver)}</td><td><span class="tag">${esc(a.source)}</span></td></tr>`)}
  `;
}

loaders.overview = loadOverview;

// ── boot ──────────────────────────────────────────────────────────
loadOverview();
pollStatus();
pollTimer = setInterval(pollStatus, 2500);

// deep-link: /?scan=ID opens that scan's detail directly
const _sp = new URLSearchParams(location.search);
if (_sp.get("scan")) { const t = document.querySelector('[data-tab="history"]'); if (t) t.click(); openScan(parseInt(_sp.get("scan"))); }
