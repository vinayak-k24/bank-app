/* FinGuard 360 SPA. All AI/API text is escaped before rendering. */
(function () {
  "use strict";

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const usd = (v, d = 0) => (v < 0 ? "-$" : "$") + Math.abs(Number(v)).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const PAGE_NAMES = { command: "Command Center", payments: "Live Payments & Scam Guard", documents: "Loan & Document Desk", compliance: "Compliance & AML Studio", coach: "Personal Financial Coach" };

  const store = { page: "command", persona: "CUST-101", personas: [], state: null, device: "new", scanFile: null, lastDoc: null, chatHistory: [], seenTx: new Set() };

  async function api(path, opts = {}) {
    const init = { method: opts.method || "GET", headers: {} };
    if (opts.json !== undefined) { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(opts.json); init.method = opts.method || "POST"; }
    if (opts.form) { init.body = opts.form; init.method = "POST"; }
    const res = await fetch(path, init);
    if (!res.ok) {
      let msg = res.statusText;
      try { const j = await res.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch (_) { /* keep statusText */ }
      throw new Error(msg);
    }
    return res.json();
  }

  function toast(msg) {
    const t = $("#toast"); t.textContent = msg; t.classList.add("show");
    clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove("show"), 2800);
  }
  function guard(fn) { return async (...a) => { try { await fn(...a); } catch (e) { console.error(e); toast("⚠ " + e.message); } }; }

  // ---------------- Navigation & persona ----------------
  function go(page) {
    store.page = page;
    $$(".tab").forEach(t => t.classList.toggle("active", t.dataset.page === page));
    $$(".page").forEach(p => p.classList.toggle("active", p.id === "page-" + page));
    $("#copilotCtx").textContent = "Context: " + PAGE_NAMES[page];
    loadSuggestions();
    if (page === "command") refreshCommand();
    if (page === "payments") refreshFeed();
    if (page === "coach") refreshCoach();
    if (page === "documents" && !store.lastDoc) setStep(-1);
    window.scrollTo({ top: 0 });
  }

  function persona() { return store.personas.find(p => p.customer_id === store.persona) || {}; }

  function onPersonaChange() {
    const p = persona(), sc = p.scenario || {};
    const isAml = p.risk_tier === "Critical-AML";
    const initials = p.name.split(/\s+/).filter(w => /^[A-Za-z]/.test(w)).slice(0, 2).map(w => w[0]).join("");

    // Shared banner
    const banner = $("#personaBanner");
    banner.classList.toggle("aml", isAml);
    banner.innerHTML = `<span class="avatar">${esc(initials)}</span><div><b>${esc(p.name)}</b> <span class="muted">· ${esc(p.customer_id)} · ${esc(sc.banner || p.segment)}</span><div class="small muted">${esc(sc.story || "")}</div></div>
      <span class="pill ${isAml ? "bad" : p.risk_tier === "Low" ? "ok" : "warn"}" style="margin-left:auto">Risk: ${esc(p.risk_tier)}</span><span class="pill neutral">KYC: ${esc(p.kyc_status)}</span>`;

    // Page 2: preload this persona's payment scenario, filter the feed
    $("#payFrom").value = p.name + " (" + p.customer_id + ")";
    const payees = { "CUST-101": ["Metro Utilities", "AWS Cloud", "Landlord - R. Mehta"], "SME-202": ["NetCorp Supplies", "NetCorp Billing LLC", "Global Freight"], "AML-303": ["Transit Account B", "Global Traders C"] }[p.customer_id] || [];
    $("#payees").innerHTML = payees.concat(["Offshore Transit Ltd"]).map(x => `<option value="${esc(x)}">`).join("");
    if (sc.payment) {
      $("#payRecipient").value = sc.payment.recipient;
      $("#payAmount").value = sc.payment.amount_usd;
      store.device = sc.payment.new_device ? "new" : "trusted";
      $$("#deviceSeg button").forEach(b => b.classList.toggle("on", b.dataset.v === store.device));
    }
    store.seenTx.clear();
    $("#holdBox").innerHTML = ""; $("#scanResult").innerHTML = ""; setScanFile(null);
    refreshFeed();

    // Page 3: reset the desk and point to this persona's document
    store.lastDoc = null; setStep(-1);
    $("#docPreview").innerHTML = `<div class="empty">No document uploaded</div>`; $("#docName").textContent = "";
    $("#docFields").innerHTML = `<div class="empty">—</div>`; $("#docSignals").innerHTML = "";
    $("#docVerdict").innerHTML = `<div class="empty">—</div>`; $("#offerBox").innerHTML = "";
    $("#docHint").textContent = sc.document_hint || "Or drag a PDF onto the preview.";
    const rec = p.default_document;
    $("#docClean").className = "btn" + (rec === "clean" ? " primary" : "");
    $("#docTampered").className = "btn" + (rec === "tampered" ? " primary" : "");
    $("#claimClean").className = "btn" + (sc.default_claim === "claim_clean" ? " primary" : "");
    $("#claimInflated").className = "btn" + (sc.default_claim === "claim_inflated" ? " primary" : "");

    // Page 4: say whether this persona is the case subject
    $("#amlNote").textContent = sc.aml_note || "";
    $("#amlNote").className = "alert small " + (isAml ? "bad" : "warn");

    // Page 1 + 5 + copilot
    if (store.state) renderRecs(store.state.recommendations);
    refreshBriefing();
    store._productsFor = null;
    refreshCoach();
    loadSuggestions();
  }

  // ---------------- Shared state / Command Center ----------------
  function applyState(s) {
    const prev = store.state && store.state.kpis;
    store.state = s;
    const k = s.kpis;
    const set = (id, v, key) => { const e = $(id); e.textContent = v; if (prev && key && prev[key] !== k[key]) { e.classList.remove("bump"); void e.offsetWidth; e.classList.add("bump"); } };
    set("#kpi-tx", k.transactions_monitored.toLocaleString(), "transactions_monitored");
    set("#kpi-fraud", k.fraud_blocked_count, "fraud_blocked_count");
    $("#kpi-fraud-usd").textContent = usd(k.fraud_blocked_usd) + " protected";
    set("#kpi-loans", k.loans_pending, "loans_pending");
    set("#kpi-aml", k.open_aml_cases, "open_aml_cases");
    $("#kpi-alerts").textContent = k.open_alerts + " open alerts";
    set("#kpi-savings", usd(k.projected_savings_usd), "projected_savings_usd");
    set("#kpi-intercept", k.interception_rate_pct + "%", "interception_rate_pct");
    $("#kpi-falsehold").textContent = k.false_hold_hours + "h";
    $("#kpi-falsehold-sub").textContent = k.false_hold_hours_delta_pct + "% with chat step-up";
    $("#kpi-fpr").textContent = k.false_positive_rate_pct + "%";
    $("#kpi-confirmed").textContent = k.holds_confirmed_by_customer + " holds confirmed via OTP today";
    $("#kpi-compliance").textContent = k.compliance_score_pct + "%";
    $("#kpi-claims").textContent = k.claims_pending + " claims in Claims AI";
    if (s.ai_mode) $("#aiMode").textContent = "AI: " + s.ai_mode;
    renderRecs(s.recommendations);
    Charts.savings($("#savingsChart"), s.savings_series, s.interventions);
    refreshDashboard();
  }

  // Customer id used for API calls (global view acts as Aarav for customer-only actions)
  function pid() { return store.persona === "ALL" ? null : store.persona; }
  function actingPid() { return pid() || ((persona().scenario || {}).acts_as) || "CUST-101"; }

  const TONE = { ok: "#16a34a", warn: "#d97706", bad: "#dc2626", ai: "#7c3aed", blue: "#2563eb" };
  const fmtVal = (v, f) => f === "usd" ? usd(v) : f === "pct" ? v + "%" : f === "pct2" ? v + "%" : f === "bps" ? "+" + v + " bps" : String(v);

  let dashSeq = 0;
  async function refreshDashboard() {
    const seq = ++dashSeq;
    const q = pid() ? `?persona_id=${encodeURIComponent(pid())}` : "";
    let d;
    try { d = await api("/api/dashboard" + q); } catch (e) { console.error(e); return; }
    if (seq !== dashSeq) return;  // a newer refresh is in flight

    $("#gcpBar").innerHTML = `<b>Google Cloud fabric:</b>` + d.services.map(s => `<span class="gcp-pill"><i style="background:${TONE[s.tone] || TONE.ok}"></i>${esc(s.name)} <span class="mode">${esc(s.mode)}</span></span>`).join("");

    $("#divisions").innerHTML = d.divisions.map(v => `<div class="card division ${esc(v.tone)}">
      <div class="row between"><span class="icon">${esc(v.icon)}</span><span class="pill ${esc(v.tone)}">${v.health}% health</span></div>
      <b>${esc(v.name)}</b><div class="small muted">${esc(v.hub)}</div>
      <div class="mini-grid">${v.metrics.map(([k, val]) => `<div><span>${esc(k)}</span>${esc(val)}</div>`).join("")}
        <div><span>Open alerts</span><b class="${v.open_alerts ? "warn" : "ok"}">${v.open_alerts}</b></div><div><span>Status</span>${esc(v.status)}</div></div></div>`).join("");

    $("#rankedBadge").textContent = d.ranked_alerts.length + " open · " + usd(d.exposure_total_usd);
    $("#rankedTable").innerHTML = `<thead><tr><th>Entity</th><th>Risk</th><th>AI score</th><th>SLA window</th><th>Exposure</th><th>Rule</th><th></th></tr></thead><tbody>` +
      (d.ranked_alerts.length ? d.ranked_alerts.map(a => `<tr class="${a.severity === "critical" ? "crit" : "warn"}">
        <td><b>${esc(a.entity)}</b><div class="small muted">${esc(a.ref)} · ${esc(a.division)}</div></td>
        <td><span class="pill ${a.severity === "critical" ? "bad" : "warn"}">${esc(a.risk_type)}</span><div class="small muted">${esc(a.risk_note)}</div></td>
        <td><div class="small muted">${esc(a.score_label)}</div><b class="aitext">${(a.score * 100).toFixed(0)}%</b></td>
        <td>${esc(a.sla)}</td><td><b>${usd(a.exposure_usd)}</b></td><td class="small">${esc(a.rule)}</td>
        <td><button class="btn primary sm" data-goto="${esc(a.page)}" data-persona="${esc(a.customer_id)}">Open →</button></td></tr>`).join("")
        : `<tr><td colspan="7" class="empty">✓ No open alerts for this view</td></tr>`) + "</tbody>";

    const a = d.analytics;
    $("#analyticsNote").textContent = d.analytics_note;
    const legend = segs => `<div class="donut-legend">${segs.map(([l, p, c]) => `<div><span><i style="background:${esc(c)}"></i>${esc(l)}</span><b>${p}%</b></div>`).join("")}</div>`;
    $("#donutDocs").innerHTML = `<div class="dn"></div>` + legend(a.doc_readiness.segments);
    Charts.donut($("#donutDocs .dn"), a.doc_readiness.segments, a.doc_readiness.center, a.doc_readiness.caption);
    $("#docFacts").innerHTML = a.doc_readiness.facts.map(([k, v]) => `<div><span>${esc(k)}:</span> <b>${esc(v)}</b></div>`).join("");
    $("#donutTeam").innerHTML = `<div class="dn"></div>` + legend(a.investigators.segments);
    Charts.donut($("#donutTeam .dn"), a.investigators.segments, a.investigators.center, a.investigators.caption);
    $("#teamInsight").innerHTML = `<span class="ai-label">✨ Gemini insight</span> <span class="aitext">${esc(a.investigators.insight)}</span>`;
    $("#threats").innerHTML = a.threats.map((t, i) => `<div class="spark"><div class="row between"><span>${esc(t.title)}</span><span class="pill ${t.tone === "ai" ? "ai" : esc(t.tone)}">${esc(t.badge)}</span></div><b>${esc(t.value)}</b><svg viewBox="0 0 120 28" data-spark="${i}"></svg><div class="muted" style="font-size:11px">${esc(t.note)}</div></div>`).join("");
    a.threats.forEach((t, i) => Charts.spark($(`#threats [data-spark="${i}"]`), t.series, TONE[t.tone] || TONE.ok));

    $("#exposureTotal").textContent = "Open exposure: " + usd(d.exposure_total_usd);
    $("#exposureTable").innerHTML = `<thead><tr><th>File / TX</th><th>SLA</th><th>Verification progress</th><th>Exposure</th><th>Risk</th><th>AI confidence</th></tr></thead><tbody>` +
      d.exposure_table.map(e => {
        const tone = e.status === "open" ? (e.severity === "critical" ? "bad" : "warn") : "ok";
        return `<tr class="${e.status === "open" ? "" : "done"}"><td><b>${esc(e.ref)}</b> <span class="small muted">${esc(e.entity)}</span></td><td class="small">${esc(e.sla)}</td>
        <td><div class="progress"><div style="width:${Number(e.progress)}%;background:${TONE[tone]}"></div></div><span class="small muted">${esc(e.progress_label)} (${Number(e.progress)}%)</span></td>
        <td><b>${usd(e.exposure_usd)}</b></td><td><span class="pill ${tone}">${e.status === "open" ? esc(e.risk_type) : e.status === "cleared" ? "Cleared" : "Resolved"}</span></td>
        <td class="aitext"><b>${(e.score * 100).toFixed(1)}%</b></td></tr>`;
      }).join("") + "</tbody>";

    $("#impactKpis").innerHTML = d.impact.map(m => `<div><div class="small muted">${esc(m.label)}</div><div class="v" style="color:${TONE[m.tone] || TONE.blue}">${esc(fmtVal(m.value, m.fmt))}</div><div class="small muted">${esc(m.note)}</div></div>`).join("");
  }

  async function refreshState() { applyState(await api("/api/state")); }

  async function refreshCommand() {
    await refreshState();
    await refreshBriefing();
  }

  async function refreshBriefing() {
    try {
      const b = await api(`/api/command/briefing?persona_id=${encodeURIComponent(store.persona)}`);
      $("#greeting").textContent = b.greeting;
      $("#briefing").textContent = b.briefing;
    } catch (e) { console.error(e); }
  }

  function renderRecs(recs) {
    const focus = (persona().scenario || {}).focus_recs || [];
    const rank = id => { const i = focus.indexOf(id); return i < 0 ? 99 : i; };
    const ordered = recs.slice().sort((a, b) => rank(a.id) - rank(b.id));
    const who = store.persona === "ALL" ? "" : (persona().name || "").split(" ")[0];
    $("#recs").innerHTML = ordered.map((r, i) => {
      const done = r.status === "resolved", growth = r.kind === "growth";
      const cls = done ? "resolved" : growth ? "growth" : esc(r.severity);
      const pill = done ? `<span class="pill ok">✓ ${growth ? "Launched" : "Resolved"}</span>` : growth ? `<span class="pill ai">Growth opportunity</span>` : `<span class="pill ${r.severity === "critical" ? "bad" : "warn"}">${esc(r.severity)}</span>`;
      return `<div class="card rec ${cls} ${i === 0 && !done ? "focus" : ""}">
        <div class="row between">${pill}${i === 0 && who ? `<span class="pill neutral">Related to ${esc(who)}</span>` : ""}</div>
        <b>${esc(r.title)}</b><span class="small muted">${esc(r.detail)}</span>
        <div class="rec-meta">${(r.meta || []).map(([k, v]) => `<div><span class="muted">${esc(k)}</span><b>${esc(v)}</b></div>`).join("")}</div>
        <div class="small muted">Grounded in: ${esc(r.grounding || "")}</div>
        <div class="row">
          <button class="btn ${growth ? "ai-btn" : "primary"} sm" data-exec="${esc(r.id)}" ${done ? "disabled" : ""}>${growth ? "Launch AI Offers" : "Execute Action"}</button>
          <button class="btn sm" data-goto="${esc(r.page)}">Open →</button>
        </div>
      </div>`;
    }).join("");
  }

  const executeRec = guard(async id => {
    const r = await api(`/api/command/actions/${encodeURIComponent(id)}/execute`, { method: "POST" });
    applyState(r.state);
    toast(r.changed ? "✓ Action executed. Alerts and savings updated." : "Already resolved");
    await refreshBriefing();
  });

  function listen() {
    if (!("speechSynthesis" in window)) return toast("Speech is not supported in this browser");
    if (speechSynthesis.speaking) { speechSynthesis.cancel(); $("#listenBtn").textContent = "🔊 Listen to Briefing"; return; }
    const u = new SpeechSynthesisUtterance($("#briefing").textContent);
    u.rate = 1.02; u.onend = () => { $("#listenBtn").textContent = "🔊 Listen to Briefing"; };
    $("#listenBtn").textContent = "⏹ Stop";
    speechSynthesis.speak(u);
  }

  // ---------------- Page 2: Payments ----------------
  function riskColor(p) { return p >= 75 ? "var(--red)" : p >= 40 ? "var(--amber)" : "var(--green)"; }
  function statusPill(e) {
    const m = { on_hold: ["bad", "On hold"], blocked: ["bad", "Blocked"], completed: [e.decision === "CONFIRMED_BY_CUSTOMER" ? "ok" : e.decision === "APPROVED_WITH_WARNING" ? "warn" : "ok", e.decision === "CONFIRMED_BY_CUSTOMER" ? "Confirmed" : "Approved"] }[e.status] || ["neutral", e.status];
    return `<span class="pill ${m[0]}">${m[1]}</span>`;
  }
  function renderFeed(feed) {
    if (!feed.length) { $("#feed").innerHTML = `<div class="empty">Waiting for transactions…</div>`; return; }
    $("#feed").innerHTML = feed.map(e => {
      const fresh = !store.seenTx.has(e.tx_id);
      return `<div class="tx ${e.status === "on_hold" ? "hold" : ""} ${fresh ? "new" : ""}">
        <div><div class="row"><b>${usd(e.amount_usd, 2)}</b> → ${esc(e.recipient)} ${statusPill(e)} ${e.new_device ? '<span class="pill warn">New device</span>' : ""}</div>
        <div class="small muted">${esc(e.tx_id)} · ${esc(e.customer_id)} · ${esc(e.ts.slice(11))} · Pub/Sub</div></div>
        <div><div class="row between small"><span class="muted">Vertex AI risk</span><b style="color:${riskColor(e.risk_pct)}">${e.risk_pct}%</b></div>
        <div class="riskbar"><div data-w="${e.risk_pct}" style="background:${riskColor(e.risk_pct)};width:${fresh ? 0 : e.risk_pct}%"></div></div></div>
      </div>`;
    }).join("");
    requestAnimationFrame(() => $$("#feed .riskbar > div").forEach(b => { b.style.width = b.dataset.w + "%"; }));
    feed.forEach(e => store.seenTx.add(e.tx_id));
    renderHold(feed.find(e => e.status === "on_hold"));
  }
  function renderHold(e) {
    if (!e) { $("#holdBox").innerHTML = ""; return; }
    $("#holdBox").innerHTML = `<div class="alert bad flash" style="margin-bottom:12px">
      <div class="row between"><b>⛔ ${usd(e.amount_usd)} to ${esc(e.recipient)} paused at ${e.risk_pct}% risk</b><span class="pill ok">Account not frozen</span></div>
      <p class="small" style="margin:6px 0"><span class="ai-label">✨ Gemini</span> ${esc(e.explanation)}</p>
      <div class="small">${e.factors.slice(1).map(f => `<span class="pill neutral">${esc(f.factor)} +${Math.round(f.weight * 100)}</span>`).join(" ")}</div>
      <div class="row mt"><button class="btn success sm" data-hold="confirm" data-tx="${esc(e.tx_id)}">Verify via OTP - it's me</button><button class="btn danger sm" data-hold="block" data-tx="${esc(e.tx_id)}">Block Payment</button><button class="btn sm" data-chat="Why was this payment held?">Ask Copilot</button></div>
    </div>`;
  }
  async function refreshFeed() {
    const sel = store.persona, p = pid();
    const feed = await api("/api/payments/feed" + (p ? `?customer_id=${encodeURIComponent(p)}` : ""));
    if (sel === store.persona) renderFeed(feed);  // ignore stale responses after a persona switch
  }

  const sendPayment = guard(async ev => {
    ev.preventDefault();
    const btn = $("#sendBtn"); btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Scoring…';
    try {
      const e = await api("/api/payments", { json: { customer_id: actingPid(), recipient: $("#payRecipient").value, amount_usd: Number($("#payAmount").value), new_device: store.device === "new" } });
      await refreshFeed(); await refreshState();
      toast(e.status === "on_hold" ? `Held for confirmation (${e.risk_pct}% risk)` : `Approved (${e.risk_pct}% risk)`);
    } finally { btn.disabled = false; btn.textContent = "Send Live Payment"; }
  });

  const resolveHold = guard(async (tx, action) => {
    const e = await api(`/api/payments/${encodeURIComponent(tx)}/resolve`, { json: { action } });
    await refreshFeed(); await refreshState();
    toast(action === "confirm" ? "✓ Verified by OTP. Payment released." : `✓ Blocked ${e.tx_id}. Savings updated.`);
  });

  function setScanFile(f) { store.scanFile = f; $("#dropzone").textContent = f ? "📎 " + f.name : "Drop an invoice image/PDF here or click to choose"; }

  const scanInvoice = guard(async () => {
    const btn = $("#scanBtn"); btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Gemini Vision scanning…';
    try {
      const fd = new FormData(); if (store.scanFile) fd.append("file", store.scanFile);
      const r = await api("/api/scam/scan", { form: fd });
      await sleep(500);
      const find = field => (r.findings || []).find(f => f.field === field) || {};
      const acct = find("Bank account"), dom = find("Sender domain"), lang = find("Language");
      $("#scanResult").innerHTML = `
        <div class="alert ${r.verdict === "LOOKS_LEGIT" ? "ok" : "bad"}"><b>${r.verdict === "LOOKS_LEGIT" ? "✓ Looks legitimate" : "⚠ Scam likely"} · ${esc(r.risk_pct)}% risk</b><div class="small">${esc(r.summary)}</div></div>
        <div class="invoice mt">
          <div class="row between"><b>${esc(r.vendor || "Invoice")}</b><span class="muted">${esc(r.invoice_number || "")}</span></div>
          <div>From: <span class="${dom.found ? "hl" : ""}">${esc(dom.found || "-")}</span></div>
          <div>Pay to account: <span class="${acct.found ? "hl" : ""}">${esc(acct.found || "-")}</span> <span class="muted small">(verified: ${esc(acct.expected || "-")})</span></div>
          <div>Amount: <b>${r.amount_usd ? usd(r.amount_usd, 2) : "-"}</b></div>
          ${lang.found ? `<div class="mt small"><span class="hl-w">${esc(lang.found)}</span></div>` : ""}
        </div>
        <ul class="small">${(r.findings || []).map(f => `<li><b class="${f.severity === "critical" ? "bad" : "warn"}">${esc(f.field)}:</b> ${esc(f.note)}</li>`).join("")}</ul>
        <div class="row"><button class="btn danger" id="blockScamBtn">Block Scam</button><button class="btn" id="otpBtn">Verify via OTP</button></div>`;
    } finally { btn.disabled = false; btn.textContent = "Scan Suspicious Invoice"; }
  });

  const blockScam = guard(async () => {
    const r = await api("/api/scam/block", { method: "POST" });
    applyState(r.state);
    $("#scanResult").insertAdjacentHTML("afterbegin", `<div class="alert ok" style="margin-bottom:10px">✓ Scam blocked. Vendor alerted, and the payment instruction was quarantined.</div>`);
    $("#blockScamBtn").disabled = true;
    toast(r.changed ? "✓ Scam blocked. Command Center updated." : "Already blocked");
  });

  // ---------------- Page 3: Documents ----------------
  function setStep(i, failAt) {
    $$("#stepper .step").forEach((s, n) => {
      s.className = "step" + (n < i ? " done" : n === i ? (failAt === n ? " fail" : " active") : "");
      if (failAt === n && n <= i) s.className = "step fail";
    });
  }

  function renderPreview(r, file) {
    $("#docName").textContent = r.filename;
    if (file) {
      const url = URL.createObjectURL(file);
      $("#docPreview").innerHTML = file.type === "application/pdf" ? `<embed class="pdf-frame" src="${url}" type="application/pdf" />` : `<img src="${url}" alt="Uploaded document" style="max-width:100%" />`;
      return;
    }
    const f = r.extracted_fields;
    const table = `<table>${r.lines.map(l => `<tr class="${l.tampered ? "tampered" : ""}"><td>${esc(l.date)}</td><td>${esc(l.desc)}${l.tampered ? " ⚠" : ""}</td><td style="text-align:right">${usd(l.amount_usd, 2)}</td></tr>`).join("")}</table>`;
    if (r.doc_type === "claim") {
      $("#docPreview").innerHTML = `
        <div class="row between"><b>${esc(f.repair_vendor)} · Tax Invoice</b><span class="muted">${esc(f.invoice_number)}</span></div>
        <div class="muted">Bill to: ${esc(f.claimant)} · ${esc(f.invoice_date)}</div>
        <div class="small" style="margin-top:6px">Claim ${esc(r.claim_id)} · ${esc(f.incident)}</div>${table}`;
      return;
    }
    $("#docPreview").innerHTML = `
      <div class="row between"><b>FinGuard Bank · Account Statement</b><span class="muted">${esc(f.statement_period)}</span></div>
      <div class="muted">${esc(f.account_holder)} · ${esc(f.account_number)}</div>${table}
      <div class="row between mt"><span class="muted">Ending balance</span><b>${usd(f.ending_balance_usd, 2)}</b></div>`;
  }

  const analyzeDoc = guard(async (kind, file) => {
    store.lastDoc = null;
    $("#offerBox").innerHTML = ""; $("#docVerdict").innerHTML = `<div class="empty"><span class="spinner"></span></div>`;
    $("#docFields").innerHTML = ""; $("#docSignals").innerHTML = "";
    setStep(0); await sleep(350);
    const fd = new FormData(); fd.append("kind", kind);
    const isClaim = kind.startsWith("claim");
    fd.append("customer_id", kind === "clean" || kind === "claim_clean" ? "CUST-101" : "SME-202");
    if (file) fd.append("file", file);
    const req = api("/api/documents/analyze", { form: fd });
    setStep(1);
    const r = await req;
    store.lastDoc = r;
    renderPreview(r, file);

    const labels = { account_holder: "Account holder", account_number: "Account no.", statement_period: "Period", avg_monthly_deposits_usd: "Avg monthly deposits", ending_balance_usd: "Ending balance", ocr_confidence: "OCR confidence",
      claimant: "Claimant", incident: "Incident", repair_vendor: "Repair vendor", invoice_number: "Invoice no.", claimed_amount_usd: "Claimed amount", invoice_date: "Invoice date" };
    const fields = Object.entries(r.extracted_fields);
    if (r.policy) fields.unshift(["policy", `${r.policy.policy_id} · ${r.policy.cover}`]);
    $("#docFields").innerHTML = fields.map(([k, v]) => `<div class="fieldrow"><span class="k">${esc(labels[k] || (k === "policy" ? "Policy" : k))}</span><span class="v">${typeof v === "number" ? (k === "ocr_confidence" ? (v * 100).toFixed(1) + "%" : usd(v, 2)) : esc(v)}</span></div>`).join("");
    const rows = $$("#docFields .fieldrow");
    for (const row of rows) { row.classList.add("in"); await sleep(1000 / rows.length); }
    if (r.tamper_signals.length) $("#docSignals").innerHTML = `<div class="alert bad small"><b>Tamper signals</b><ul style="margin:4px 0 0;padding-left:18px">${r.tamper_signals.map(s => `<li>${esc(s)}</li>`).join("")}</ul></div>`;

    setStep(2); await sleep(500);
    const lc = r.ledger_check, ok = r.verdict === "INSTANT_PRE_APPROVED" || r.verdict === "AUTO_APPROVED";
    const unit = lc.unit || "";
    const flagged = isClaim
      ? `<button class="btn primary" id="routeClaimBtn" data-kind="${esc(r.kind)}">Route to Adjuster</button><button class="btn sm" data-chat="Why was claim CL-7741 routed to an adjuster?">Ask Copilot</button>`
      : `<button class="btn primary" id="requestProofBtn">Request Tax/GST Proof</button><button class="btn sm" data-chat="Why was Apex Mfg's bank statement flagged?">Ask Copilot</button>`;
    $("#docVerdict").innerHTML = `
      <div class="compare"><div><div class="small muted">${esc(lc.declared_label)}</div><div class="big ${ok ? "ok" : "bad"}">${usd(lc.declared_usd)}${unit}</div></div>
      <div><div class="small muted">${esc(lc.ledger_label)}</div><div class="big">${usd(lc.ledger_usd)}${unit}</div></div></div>
      <div class="alert ${ok ? "ok" : "bad flash"} mt"><b>${ok ? "✓ Match: verified" : `⚠ Discrepancy Alert: ${lc.variance_pct > 0 ? "+" : ""}${lc.variance_pct}% vs ledger`}</b><div class="small">Risk score ${r.risk_score}/100 · limit ±${lc.limit_pct}% · ${esc(lc.source)}</div></div>
      ${isClaim ? `<div class="row mt small"><span class="pill neutral">Max supportable payout ${usd(r.payout_usd)}</span><span class="pill neutral">Deductible ${usd(r.policy.deductible_usd)}</span></div>` : ""}
      <div class="card ai mt" style="padding:12px"><span class="ai-label">✨ Gemini summary</span><p class="small aitext" style="margin:4px 0 0">${esc(r.summary)}</p></div>
      ${ok ? "" : `<div class="policy hit mt"><div class="small muted">Vertex AI Search citation</div><b>${esc(r.policy_citation.doc_id)}</b> · ${esc(r.policy_citation.title)}<div class="small">${esc(r.policy_citation.clause)}</div></div>`}
      <div class="row mt">${ok ? "" : flagged}</div>`;
    setStep(4, ok ? undefined : 3);
    if (ok && isClaim) renderPayout(r);
    else if (ok) renderOffer(r.offer);
  });

  function renderPayout(r) {
    $("#offerBox").innerHTML = `<div class="card" style="border-color:#abefc6"><div class="row between">
      <div><span class="pill ok">✓ Claim auto-approved</span><h2 style="margin-top:8px">${usd(r.payout_usd, 2)} payout</h2><div class="small muted">${esc(r.claim_id)} · ${esc(r.policy.cover)} · after ${usd(r.policy.deductible_usd)} deductible</div></div>
      <button class="btn success" id="payoutBtn" data-kind="${esc(r.kind)}">Release Payout</button></div></div>`;
  }

  const routeClaim = guard(async kind => {
    const r = await api(`/api/claims/${encodeURIComponent(kind)}/route`, { method: "POST" });
    applyState(r.state);
    const b = $("#routeClaimBtn"); if (b) { b.disabled = true; b.textContent = "✓ Routed to adjuster"; }
    toast(r.changed ? `✓ ${r.claim_id} routed to adjuster. ${usd(r.avoided_usd)} overpayment avoided.` : "Already routed");
  });

  const releasePayout = guard(async kind => {
    const r = await api(`/api/claims/${encodeURIComponent(kind)}/payout`, { method: "POST" });
    applyState(r.state);
    const b = $("#payoutBtn"); if (b) { b.disabled = true; b.textContent = "✓ Paid"; }
    toast(`✓ ${usd(r.payout_usd, 2)} released for ${r.claim_id}`);
  });

  const renderOffer = guard(async offer => {
    $("#offerBox").innerHTML = `<div class="card" style="border-color:#abefc6">
      <div class="row between"><div><span class="pill ok">✓ Instant Pre-Approval</span><h2 class="mt" style="margin-top:8px">${usd(offer.limit_usd)} at ${offer.apr_pct}% APR</h2></div>
      <div style="min-width:260px;flex:1;max-width:420px"><label class="field">Loan term: <b id="termVal">${offer.term_months} months</b><input type="range" id="termSlider" min="12" max="36" step="1" value="${offer.term_months}" /></label>
      <div class="row between mt"><span class="muted">Monthly payment</span><b id="emi" style="font-size:20px">–</b></div><div class="row between small muted"><span>Total interest</span><span id="interest">–</span></div></div>
      <button class="btn primary">Accept Offer</button></div></div>`;
    const update = guard(async () => {
      const t = Number($("#termSlider").value);
      $("#termVal").textContent = t + " months";
      const q = await api("/api/loans/quote", { json: { amount_usd: offer.limit_usd, apr_pct: offer.apr_pct, term_months: t } });
      $("#emi").textContent = usd(q.monthly_payment_usd, 2); $("#interest").textContent = usd(q.total_interest_usd, 2);
    });
    $("#termSlider").addEventListener("input", update);
    update();
  });

  const requestProof = guard(async () => {
    const r = await api("/api/loans/request-proof", { method: "POST" });
    applyState(r.state);
    $("#requestProofBtn").disabled = true; $("#requestProofBtn").textContent = "✓ GST proof requested";
    toast("Loan paused pending Tax/GST proof. Command Center updated.");
  });

  // ---------------- Page 4: Compliance ----------------
  const POS = { A: [210, 60], B: [360, 190], C: [210, 320], D: [60, 190] };
  function drawNet(t) {
    const svg = $("#netmap"); svg.innerHTML = "";
    const NS = "http://www.w3.org/2000/svg";
    const mk = (n, a, p) => { const e = document.createElementNS(NS, n); for (const k in a) e.setAttribute(k, a[k]); (p || svg).appendChild(e); return e; };
    const defs = mk("defs", {}); const m = mk("marker", { id: "arr", viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: "auto-start-reverse" }, defs);
    mk("path", { d: "M0,0 L10,5 L0,10 z", fill: "#dc2626" }, m);
    const hot = t && t.loop_detected;
    const edges = t ? t.transfers : [{ from: "A", to: "B" }, { from: "B", to: "C" }, { from: "C", to: "D" }, { from: "D", to: "A" }];
    edges.forEach((e, i) => {
      const [x1, y1] = POS[e.from], [x2, y2] = POS[e.to];
      const dx = x2 - x1, dy = y2 - y1, len = Math.hypot(dx, dy), ux = dx / len, uy = dy / len;
      const sx = x1 + ux * 40, sy = y1 + uy * 40, ex = x2 - ux * 44, ey = y2 - uy * 44;
      const cx = (sx + ex) / 2 - uy * 24, cy = (sy + ey) / 2 + ux * 24;
      const p = mk("path", { d: `M${sx},${sy} Q${cx},${cy} ${ex},${ey}`, class: "edge" + (hot ? " hot" : ""), "marker-end": hot ? "url(#arr)" : "" });
      if (hot) { p.style.opacity = 0; setTimeout(() => { p.style.transition = "opacity .4s"; p.style.opacity = 1; }, 350 * i); }
      if (t) { const lb = mk("text", { x: cx, y: cy, "text-anchor": "middle", "font-size": 11, "font-weight": 600, fill: hot ? "#dc2626" : "#667085" }); lb.textContent = usd(e.amount_usd / 1000) + "k"; }
    });
    const nodes = t ? t.nodes : [{ id: "A", name: "Shell Co. A" }, { id: "B", name: "Transit Account B" }, { id: "C", name: "Global Traders C" }, { id: "D", name: "Holding Co. D" }];
    nodes.forEach(n => {
      const [x, y] = POS[n.id]; const g = mk("g", { class: "node" + (hot ? " hot" : "") });
      mk("circle", { cx: x, cy: y, r: 36 }, g);
      const a = mk("text", { x, y: y - 2, "text-anchor": "middle", "font-size": 18, "font-weight": 700, fill: hot ? "#dc2626" : "#101828" }, g); a.textContent = n.id;
      const b = mk("text", { x, y: y + 14, "text-anchor": "middle", "font-size": 9.5, fill: "#667085" }, g); b.textContent = n.name.split(" ").slice(0, 2).join(" ");
    });
  }

  const traceCase = guard(async () => {
    const btn = $("#traceBtn"); btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Querying BigQuery…';
    try {
      const t = await api(`/api/aml/cases/${encodeURIComponent($("#caseSelect").value)}/trace`);
      drawNet(t);
      $("#traceMeta").textContent = `${t.span_hours}h · anomaly ${Math.round(t.anomaly_score * 100)}%`;
      $("#traceSummary").innerHTML = `<div class="alert bad small"><b>${usd(t.circular_volume_usd)} circular loop detected</b> across ${t.nodes.length} accounts in ${t.span_hours}h (window ${t.window_hours}h). 0 supporting invoices. Source: ${esc(t.source)}.</div>`;
      $("#policies").innerHTML = t.rules.map(r => `
        <div class="policy hit"><div class="row between"><b>${esc(r.doc_id)}</b><span class="pill ai">${Math.round(r.confidence * 100)}% match</span></div>
        <div class="small" style="margin:4px 0">${esc(r.title)}</div><div class="small muted">${esc(r.clause)}</div>
        <ul class="small" style="margin:6px 0 0;padding-left:18px">${r.criteria.map(c => `<li class="${c.met ? "bad" : "muted"}">${c.met ? "✗ Broken: " : "○ "}${esc(c.label)}</li>`).join("")}</ul>
        <div class="conf"><div data-w="${Math.round(r.confidence * 100)}"></div></div></div>`).join("");
      requestAnimationFrame(() => $$("#policies .conf > div").forEach(b => { b.style.width = b.dataset.w + "%"; }));
    } finally { btn.disabled = false; btn.textContent = "Trace Money Flow"; }
  });

  const draftSar = guard(async () => {
    if (!$("#policies .policy")) await traceCase();
    const ed = $("#sarEditor"), btn = $("#draftSarBtn");
    btn.disabled = true; ed.textContent = ""; ed.classList.add("streaming"); $("#sarStatus").textContent = "Gemini drafting…";
    try {
      const res = await fetch(`/api/aml/cases/${encodeURIComponent($("#caseSelect").value)}/sar/stream`);
      if (!res.ok || !res.body) throw new Error("SAR stream failed");
      const reader = res.body.getReader(), dec = new TextDecoder();
      for (;;) { const { value, done } = await reader.read(); if (done) break; ed.textContent += dec.decode(value, { stream: true }); ed.scrollTop = ed.scrollHeight; }
      $("#sarStatus").textContent = "draft ready for sign-off"; $("#submitSarBtn").disabled = false;
    } finally { ed.classList.remove("streaming"); btn.disabled = false; }
  });

  const submitSar = guard(async () => {
    const text = $("#sarEditor").innerText.trim();
    if (!text) return toast("Draft the SAR first");
    if (!confirm("Sign off as Alex, freeze the 4 ring accounts and submit this SAR?")) return;
    const r = await api(`/api/aml/cases/${encodeURIComponent($("#caseSelect").value)}/sar/submit`, { json: { text, officer: "Alex" } });
    applyState(r.state);
    $("#sarStatus").textContent = "submitted " + r.submitted_at.slice(11); $("#submitSarBtn").disabled = true;
    toast(`✓ SAR submitted. ${r.accounts_frozen.length} accounts frozen.`);
  });

  // ---------------- Page 5: Coach ----------------
  let coachTimer;
  const refreshCoach = guard(async () => {
    const delay = Number($("#delaySlider").value), exp = Number($("#expenseSlider").value);
    $("#delayVal").textContent = delay + " days"; $("#expenseVal").textContent = usd(exp);
    if (!pid()) {
      $("#coachUnavailable").classList.remove("hidden"); $("#coachBody").classList.add("hidden");
      $("#coachUnavailable").textContent = "Personal coaching is per customer. Pick Aarav Sharma or Apex Manufacturing from the persona switcher.";
      return;
    }
    const fc = await api(`/api/coach/${encodeURIComponent(store.persona)}/forecast?delay_days=${delay}&extra_expense_usd=${exp}`);
    $("#coachUnavailable").classList.toggle("hidden", fc.available);
    $("#coachBody").classList.toggle("hidden", !fc.available);
    if (!fc.available) { $("#coachUnavailable").textContent = "⚠ " + fc.reason; return; }
    $("#walletBal").textContent = usd(fc.balance_usd, 2);
    $("#walletName").textContent = fc.name + " · safety buffer " + usd(fc.low_threshold_usd);
    const d = fc.dip;
    $("#dipText").textContent = d.detected
      ? `Your balance is predicted to fall below ${usd(fc.low_threshold_usd)} on ${d.first_low_date} and stay low for ${d.gap_days} days (lowest ${usd(d.lowest_balance_usd)} on ${d.lowest_date}) until "${fc.pending_inflow.label}" arrives.`
      : "No cash-flow dip predicted in the next 30 days.";
    Charts.forecast($("#forecastChart"), fc.history, fc.forecast, fc.low_threshold_usd);
    if (!store._productsFor || store._productsFor !== store.persona) {
      store._productsFor = store.persona;
      const ps = await api(`/api/coach/${encodeURIComponent(store.persona)}/products`);
      $("#products").innerHTML = ps.map(p => `<div class="card"><div class="row between"><b>${esc(p.title)}</b><span class="pill ${p.eligible ? "ok" : "neutral"}">${p.eligible ? "Pre-qualified" : "Not eligible"}</span></div>
        <div style="font-size:22px;font-weight:700;margin:6px 0">${p.apr_pct}% ${p.kind === "credit" ? "APR" : "APY"}</div><p class="small muted">${esc(p.terms)}</p>
        <button class="btn primary" data-elig="${esc(p.product_id)}">Check Eligibility &amp; Terms</button></div>`).join("");
      $("#eligibilityBox").innerHTML = "";
    }
  });

  const checkEligibility = guard(async pid => {
    $("#eligibilityBox").innerHTML = `<div class="card ai"><span class="spinner aitext"></span> Vertex AI Search + Gemini personalizing…</div>`;
    const r = await api("/api/coach/eligibility", { json: { customer_id: store.persona, product_id: pid, delay_days: Number($("#delaySlider").value), extra_expense_usd: Number($("#expenseSlider").value) } });
    $("#eligibilityBox").innerHTML = `<div class="card ai"><div class="row between"><span class="ai-label">✨ Personalized for you · ${esc(r.product.title)}</span><span class="pill ${r.eligible ? "ok" : "neutral"}">${r.eligible ? "Eligible" : "Not eligible"}</span></div>
      <p class="aitext">${esc(r.explanation)}</p>
      ${r.suggested_draw_usd ? `<div class="row"><span class="pill neutral">Suggested draw ${usd(r.suggested_draw_usd)}</span><span class="pill neutral">Est. interest ${usd(r.estimated_interest_usd, 2)}</span><span class="pill ok">$0 overdraft fees</span></div>` : ""}
      <p class="small muted">Grounded terms: ${esc(r.grounded_terms)}</p></div>`;
  });

  // ---------------- Copilot ----------------
  const loadSuggestions = guard(async () => {
    const s = await api(`/api/copilot/suggestions?page=${store.page}&persona_id=${encodeURIComponent(store.persona)}`);
    $("#chips").innerHTML = s.map(q => `<button class="chip" data-chat="${esc(q)}">${esc(q)}</button>`).join("");
  });

  function addMsg(role, text) {
    const d = document.createElement("div"); d.className = "msg " + role; d.textContent = text;
    $("#chat").appendChild(d); $("#chat").scrollTop = $("#chat").scrollHeight; return d;
  }

  const askCopilot = guard(async text => {
    text = text.trim(); if (!text) return;
    $("#drawer").classList.add("open");
    addMsg("user", text);
    const pending = addMsg("bot", "…");
    const r = await api("/api/copilot/chat", { json: { message: text, page: store.page, persona_id: store.persona, history: store.chatHistory.slice(-6) } });
    pending.textContent = r.reply;
    store.chatHistory.push({ role: "user", content: text }, { role: "assistant", content: r.reply });
  });

  // ---------------- Wiring ----------------
  function wire() {
    $("#tabs").addEventListener("click", e => { const t = e.target.closest(".tab"); if (t) go(t.dataset.page); });
    $("#personaSelect").addEventListener("change", e => { store.persona = e.target.value; onPersonaChange(); toast("Persona: " + persona().name); });
    $("#listenBtn").addEventListener("click", listen);
    $("#resetDemo").addEventListener("click", guard(async () => { applyState(await api("/api/state/reset", { method: "POST" })); store.seenTx.clear(); $("#scanResult").innerHTML = ""; $("#holdBox").innerHTML = ""; $("#sarEditor").textContent = ""; $("#sarStatus").textContent = "not started"; store.lastDoc = null; await refreshCommand(); toast("Demo reset"); }));

    document.addEventListener("click", e => {
      const g = e.target.closest("[data-goto]");
      if (g) {
        const target = g.dataset.persona;
        if (target && target !== store.persona && store.personas.some(p => p.customer_id === target)) {
          store.persona = target; $("#personaSelect").value = target; onPersonaChange();
        }
        return go(g.dataset.goto);
      }
      if (e.target.closest("#routeClaimBtn")) return routeClaim(e.target.closest("#routeClaimBtn").dataset.kind);
      if (e.target.closest("#payoutBtn")) return releasePayout(e.target.closest("#payoutBtn").dataset.kind);
      const sr = e.target.closest("[data-hit]");
      if (sr) {
        const h = store.searchHits[Number(sr.dataset.hit)];
        $("#searchResults").classList.add("hidden"); $("#searchInput").value = "";
        if (h.persona && h.persona !== store.persona) { store.persona = h.persona; $("#personaSelect").value = h.persona; onPersonaChange(); }
        return go(h.page);
      }
      if (!e.target.closest("#searchWrap")) $("#searchResults").classList.add("hidden");
      const x = e.target.closest("[data-exec]"); if (x) return executeRec(x.dataset.exec);
      const h = e.target.closest("[data-hold]"); if (h) return resolveHold(h.dataset.tx, h.dataset.hold);
      const c = e.target.closest("[data-chat]"); if (c) return askCopilot(c.dataset.chat);
      const el = e.target.closest("[data-elig]"); if (el) return checkEligibility(el.dataset.elig);
      if (e.target.closest("#blockScamBtn")) return blockScam();
      if (e.target.closest("#otpBtn")) return toast("OTP sent to the customer's registered mobile");
      if (e.target.closest("#requestProofBtn")) return requestProof();
    });

    $("#payForm").addEventListener("submit", sendPayment);
    $("#deviceSeg").addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return; store.device = b.dataset.v; $$("#deviceSeg button").forEach(x => x.classList.toggle("on", x === b)); });

    const dz = $("#dropzone"), sf = $("#scanFile");
    dz.addEventListener("click", () => sf.click());
    sf.addEventListener("change", () => setScanFile(sf.files[0] || null));
    dz.addEventListener("dragover", e => { e.preventDefault(); dz.classList.add("over"); });
    dz.addEventListener("dragleave", () => dz.classList.remove("over"));
    dz.addEventListener("drop", e => { e.preventDefault(); dz.classList.remove("over"); setScanFile(e.dataTransfer.files[0] || null); });
    $("#scanBtn").addEventListener("click", scanInvoice);

    $("#docClean").addEventListener("click", () => analyzeDoc("clean"));
    $("#docTampered").addEventListener("click", () => analyzeDoc("tampered"));
    $("#claimClean").addEventListener("click", () => analyzeDoc("claim_clean"));
    $("#claimInflated").addEventListener("click", () => analyzeDoc("claim_inflated"));

    // Global search
    let st;
    $("#searchInput").addEventListener("input", e => {
      clearTimeout(st);
      const q = e.target.value.trim();
      st = setTimeout(guard(async () => {
        const box = $("#searchResults");
        if (q.length < 2) { box.classList.add("hidden"); return; }
        store.searchHits = await api(`/api/search?q=${encodeURIComponent(q)}`);
        box.innerHTML = store.searchHits.length
          ? store.searchHits.map((h, i) => `<button data-hit="${i}"><span class="pill neutral">${esc(h.type)}</span> <b>${esc(h.title)}</b><div class="small muted">${esc(h.sub)}</div></button>`).join("")
          : `<div class="empty small">No matches</div>`;
        box.classList.remove("hidden");
      }), 180);
    });

    // Bell: inject a live high-risk Pub/Sub event for the active (or default) customer
    $("#bellBtn").addEventListener("click", guard(async () => {
      const sc = (persona().scenario || {}).payment || { recipient: "Offshore Transit Ltd", amount_usd: 48500, new_device: true };
      const e = await api("/api/payments", { json: { customer_id: actingPid(), recipient: sc.recipient, amount_usd: sc.amount_usd, new_device: sc.new_device } });
      await refreshState();
      toast(`🔔 Pub/Sub: ${usd(e.amount_usd)} to ${e.recipient} scored ${e.risk_pct}% → ${e.status === "on_hold" ? "held" : "approved"}`);
      if (store.page === "payments") refreshFeed();
    }));
    $("#docFile").addEventListener("change", e => { const f = e.target.files[0]; if (f) analyzeDoc("auto", f); e.target.value = ""; });
    const pv = $("#docPreview");
    pv.addEventListener("dragover", e => { e.preventDefault(); });
    pv.addEventListener("drop", e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) analyzeDoc("auto", f); });

    $("#traceBtn").addEventListener("click", traceCase);
    $("#draftSarBtn").addEventListener("click", draftSar);
    $("#submitSarBtn").addEventListener("click", submitSar);
    $$(".toolbar button").forEach(b => b.addEventListener("click", () => { $("#sarEditor").focus(); document.execCommand(b.dataset.cmd); }));

    ["#delaySlider", "#expenseSlider"].forEach(id => $(id).addEventListener("input", () => { clearTimeout(coachTimer); coachTimer = setTimeout(refreshCoach, 60); }));

    $("#copilotFab").addEventListener("click", () => $("#drawer").classList.toggle("open"));
    $("#closeDrawer").addEventListener("click", () => $("#drawer").classList.remove("open"));
    $("#chatForm").addEventListener("submit", e => { e.preventDefault(); const v = $("#chatInput").value; $("#chatInput").value = ""; askCopilot(v); });

    let rt; window.addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(() => { if (store.state) Charts.savings($("#savingsChart"), store.state.savings_series, store.state.interventions); if (store.page === "coach") refreshCoach(); }, 150); });

    // Live stream: background low-risk traffic while on the payments page
    setInterval(guard(async () => { if (store.page !== "payments" || document.hidden) return; await api("/api/payments/tick" + (pid() ? `?customer_id=${encodeURIComponent(pid())}` : ""), { method: "POST" }); await refreshFeed(); }), 4000);
  }

  async function init() {
    $("#today").textContent = new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" });
    wire();
    drawNet(null);
    store.personas = await api("/api/personas");
    $("#personaSelect").innerHTML = store.personas.map(p => `<option value="${esc(p.customer_id)}">${esc(p.short)}</option>`).join("");
    $("#personaSelect").value = store.persona;
    onPersonaChange();
    await refreshCommand();
  }

  init().catch(e => { console.error(e); toast("⚠ Backend not reachable: " + e.message); });
})();
