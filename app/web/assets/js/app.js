/* OneCare Loop web client. Same-origin API; bearer tokens stay in sessionStorage. */
(() => {
  const API = "/api/v1";
  const root = document.getElementById("app");
  const toastRegion = document.getElementById("toast-region");
  // Some privacy-focused browsers or opaque-origin previews deny Web Storage.
  // Use tab-memory storage as a safe fallback rather than failing the entire app.
  const storage = (() => {
    try { return window.sessionStorage; }
    catch (_) {
      const values = new Map();
      return {
        getItem: (key) => values.has(key) ? values.get(key) : null,
        setItem: (key, value) => values.set(key, String(value)),
        removeItem: (key) => values.delete(key),
      };
    }
  })();
  const state = { token: storage.getItem("onecare_access_token") || "", user: null, view: "overview", queue: [], organisations: [], staff: [], patientReceipt: null };

  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
  const dateTime = (value) => value ? new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "—";
  const dateInputValue = (date) => {
    const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
    return local.toISOString().slice(0, 16);
  };
  const titleCase = (value) => String(value || "").replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
  const initials = (value) => String(value || "OC").split(/[\s@._-]+/).filter(Boolean).slice(0, 2).map((x) => x[0].toUpperCase()).join("");
  const role = () => state.user?.role || "guest";
  const isAdmin = () => role() === "admin";
  const canHospital = () => ["admin", "hospital", "clinician"].includes(role());
  const canPharmacy = () => ["pharmacy", "pmv"].includes(role());

  function loopIllustration(extraClass = "") {
    return `<div class="oc-loop-art ${extraClass}" aria-hidden="true"><svg viewBox="0 0 400 400" role="presentation">
      <defs><radialGradient id="ocLoopGlow" cx="50%" cy="50%" r="50%"><stop offset="0%" stop-color="#2DD4A8" stop-opacity=".35"/><stop offset="100%" stop-color="#2DD4A8" stop-opacity="0"/></radialGradient></defs>
      <path class="arc a1" pathLength="100" d="M200 100 A100 100 0 0 1 286.6 150"/>
      <path class="arc a2" pathLength="100" d="M286.6 150 A100 100 0 0 1 286.6 250"/>
      <path class="arc a3" pathLength="100" d="M286.6 250 A100 100 0 0 1 200 300"/>
      <path class="arc a4" pathLength="100" d="M200 300 A100 100 0 0 1 113.4 250"/>
      <path class="arc a5" pathLength="100" d="M113.4 250 A100 100 0 0 1 113.4 150"/>
      <path class="arc a6" pathLength="100" d="M113.4 150 A100 100 0 0 1 200 100"/>
      <circle class="node n1" cx="200" cy="100" r="9"/><circle class="node n2" cx="286.6" cy="150" r="9"/>
      <circle class="node n3" cx="286.6" cy="250" r="9"/><circle class="node n4" cx="200" cy="300" r="9"/>
      <circle class="node n5" cx="113.4" cy="250" r="9"/><circle class="node n6" cx="113.4" cy="150" r="9"/>
      <circle class="center-glow" cx="200" cy="200" r="24" fill="url(#ocLoopGlow)"/>
      <g class="center-mark"><rect x="196" y="184" width="8" height="32" rx="2" fill="#E8EEF4"/><rect x="184" y="196" width="32" height="8" rx="2" fill="#E8EEF4"/></g>
    </svg></div>`;
  }

  function renderLanding() {
    root.innerHTML = `<div class="oc-landing">
      <canvas class="oc-particle-canvas" data-oc-particles aria-hidden="true"></canvas>
      <header class="oc-landing-top">
        <div class="oc-brand"><svg class="oc-brand-mark" viewBox="0 0 36 36" fill="none" aria-hidden="true"><circle cx="18" cy="18" r="15" stroke="#2DD4A8" stroke-width="2.4" stroke-dasharray="23 9" stroke-linecap="round"/><path d="M18 10v16M10 18h16" stroke="#E8EEF4" stroke-width="2.6" stroke-linecap="round"/></svg><span>onecare<span class="oc-dot">.</span>loop</span></div>
        <nav class="oc-top-actions" aria-label="Account access"><button class="btn btn-outline" data-auth="login" data-magnetic>Sign in</button><button class="btn btn-primary" data-auth="register" data-magnetic>Create patient account</button></nav>
      </header>
      <main class="oc-landing-main">
        <section class="oc-landing-copy">
          <div class="oc-eyebrow">POPULATION HEALTH · NIGERIA</div>
          <h1>Every patient deserves a <em>closed loop.</em></h1>
          <p class="oc-landing-lede">A positive screening result should lead somewhere. OneCare Loop connects community screening, referral, hospital acceptance, clinical review and follow-up—with accountable handoffs and a verifiable record of what happened.</p>
          <div class="oc-landing-cta"><a class="btn btn-primary" href="/demo" data-magnetic>Watch the full automatic demo <span aria-hidden="true">▶</span></a><button class="btn btn-outline" data-auth="login" data-magnetic>Open care workspace <span aria-hidden="true">→</span></button><button class="btn btn-outline" data-auth="patient" data-magnetic>Patient care receipt</button></div>
          <div class="oc-stage-list" aria-label="Care journey stages">
            <div class="oc-stage" style="animation-delay:680ms"><span>01</span>Screening</div><div class="oc-stage" style="animation-delay:770ms"><span>02</span>Referral</div><div class="oc-stage" style="animation-delay:860ms"><span>03</span>Acceptance</div>
            <div class="oc-stage" style="animation-delay:950ms"><span>04</span>Appointment</div><div class="oc-stage" style="animation-delay:1040ms"><span>05</span>Clinical review</div><div class="oc-stage" style="animation-delay:1130ms"><span>06</span>Follow-up</div>
          </div>
          <div class="oc-landing-trust"><span class="oc-trust-chip">Human clinical decisions</span><span class="oc-trust-chip">Named referral ownership</span><span class="oc-trust-chip">Tamper-evident event history</span></div>
        </section>
        <section class="oc-loop-visual" aria-label="OneCare Loop six-stage care journey">
          ${loopIllustration()}
          <div class="oc-loop-caption">One patient · One accountable journey</div>
        </section>
      </main>
      <footer class="oc-landing-footer"><span>ONECARE LOOP · HYPERTENSION CARE COORDINATION</span><span>Prototype · Clinical decisions remain with licensed professionals</span></footer>
    </div>`;
    window.OneCareMotion?.refresh(root);
  }

  function renderJourneyRing(events = []) {
    const types = new Set(events.map((event) => event.event_type));
    const stages = [
      { label: "Screened", keys: ["SCREEN_POSITIVE", "SCREEN_NEGATIVE", "SCREENING_INCONCLUSIVE"] },
      { label: "Referred", keys: ["REFERRAL_CREATED"] },
      { label: "Accepted", keys: ["FACILITY_ACCEPTED"] },
      { label: "Booked", keys: ["APPOINTMENT_BOOKED"] },
      { label: "Seen", keys: ["CLINICAL_ENCOUNTER_COMPLETED"] },
      { label: "Outcome", keys: ["CLINICAL_DISPOSITION_RETURNED"] },
    ];
    const failureStage = {
      REFERRAL_DECLINED: 1, FACILITY_UNAVAILABLE: 2, REFERRAL_REDIRECTED: 1,
      PATIENT_UNREACHABLE: 2, PATIENT_DECLINED: 1, APPOINTMENT_MISSED: 3,
      PATIENT_REQUESTED_RESCHEDULE: 3, FOLLOWUP_OVERDUE: 5,
    };
    const lastType = events.at(-1)?.event_type;
    const brokenIndex = Object.hasOwn(failureStage, lastType) ? failureStage[lastType] : -1;
    let currentIndex = stages.findIndex((stage) => !stage.keys.some((key) => types.has(key)));
    if (currentIndex < 0) currentIndex = stages.length - 1;
    const doneThrough = stages.map((stage) => stage.keys.some((key) => types.has(key)));
    const markup = stages.map((stage, index) => {
      const done = doneThrough[index];
      const status = brokenIndex === index ? "broken" : done ? "done" : index === currentIndex ? "current" : "";
      const connector = index < stages.length - 1 ? `<span class="oc-journey-connector ${done ? "done" : ""}" aria-hidden="true"></span>` : "";
      return `<div class="oc-journey-step ${status}" aria-label="${esc(stage.label)}: ${done ? "completed" : status === "broken" ? "interrupted" : "pending"}"><span class="oc-journey-node">${done ? "✓" : status === "broken" ? "!" : index + 1}</span><span class="oc-journey-label">${esc(stage.label)}</span></div>${connector}`;
    }).join("");
    const note = brokenIndex >= 0 ? `Latest recorded exception: ${titleCase(lastType)}. Review the case history for the recovery action.`
      : events.length ? `Progress is based on recorded care events. ${types.has("CONFIRMATORY_TEST_RECORDED") ? "Confirmatory assessment recorded." : ""}`
      : "No care events have been recorded yet.";
    return `<section class="oc-journey-panel"><div class="oc-journey-head"><strong>Your care journey</strong><span>${events.length} recorded event(s)</span></div><div class="oc-journey-steps">${markup}</div><p class="oc-journey-note">${esc(note)}</p></section>`;
  }

  function toast(message, type = "") {
    const node = document.createElement("div");
    node.className = `toast ${type}`;
    node.textContent = message;
    toastRegion.append(node);
    window.setTimeout(() => node.remove(), 4200);
  }

  async function api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
    if (state.token) headers.set("Authorization", `Bearer ${state.token}`);
    const response = await fetch(`${API}${path}`, { ...options, headers });
    const type = response.headers.get("content-type") || "";
    const data = type.includes("application/json") ? await response.json() : await response.text();
    if (!response.ok) {
      if (response.status === 401 && state.token) {
        clearAuth();
        renderAuth();
      }
      let detail = data?.detail ?? data?.message ?? data;
      if (detail && typeof detail === "object") detail = detail.message || JSON.stringify(detail);
      throw new Error(detail || `Request failed (${response.status})`);
    }
    return data;
  }

  function clearAuth() {
    state.token = "";
    state.user = null;
    storage.removeItem("onecare_access_token");
  }

  function saveAuth(data) {
    state.token = data.access_token;
    state.user = data.user;
    storage.setItem("onecare_access_token", state.token);
    state.view = "overview";
    renderShell();
    loadView("overview");
  }

  function authStory() {
    return `<section class="auth-story">
      <div class="brand"><span class="brand-mark">+</span><span>onecare<span style="color:#2DD4A8">.</span>loop</span></div>
      <div><div class="eyebrow" style="color:#2DD4A8">CARE THAT CLOSES THE LOOP</div>
        <h1>A referral should never disappear between the pharmacy and the hospital.</h1>
        <p>OneCare Loop helps care teams coordinate hypertension screening, referrals, attendance and clinical follow-up—with a verifiable record of every step.</p>
        ${loopIllustration("oc-auth-ring")}
        <div class="auth-facts"><div class="auth-fact">01<br>Screen with consent</div><div class="auth-fact">02<br>Coordinate the referral</div><div class="auth-fact">03<br>Verify what happened</div></div>
      </div>
      <p class="small">Care coordination software · Clinical decisions remain with licensed professionals.</p>
    </section>`;
  }

  function renderAuth(mode = "login", message = "") {
    const patientMode = mode === "patient";
    const registerMode = mode === "register";
    root.innerHTML = `<div class="auth-screen">${authStory()}<section class="auth-panel"><div class="auth-card">
      <div class="eyebrow">${patientMode ? "PATIENT PORTAL" : "SECURE WORKSPACE"}</div>
      <h2>${patientMode ? "Access your care receipt" : registerMode ? "Create a patient account" : "Welcome back"}</h2>
      <p class="muted">${patientMode ? "Request a one-time code using the phone number recorded during screening." : registerMode ? "Public registration creates a patient account only. Staff access is provisioned by an administrator." : "Sign in to your OneCare Loop workspace."}</p>
      ${message ? `<div class="notice info">${esc(message)}</div>` : ""}
      ${patientMode ? `<form id="otp-request-form"><div class="field"><label for="otp-phone">Phone number</label><input id="otp-phone" name="phone" type="tel" autocomplete="tel" placeholder="+2348012345678" required></div><button class="btn btn-primary btn-block" type="submit">Request one-time code</button></form>
        <form id="otp-verify-form" class="hide" style="margin-top:18px"><div class="field"><label for="otp-code">Six-digit code</label><input id="otp-code" name="code" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6}" maxlength="6" required></div><button class="btn btn-dark btn-block" type="submit">Verify and open receipt</button></form>
        <div class="auth-footer"><a href="#" data-auth="login">Staff sign in</a></div>` : registerMode ? `<form id="register-form"><div class="field"><label for="display-name">Full name</label><input id="display-name" name="display_name" autocomplete="name" required minlength="2"></div><div class="field"><label for="register-email">Email address</label><input id="register-email" name="email" type="email" autocomplete="email" required></div><div class="field"><label for="register-password">Password</label><input id="register-password" name="password" type="password" minlength="12" autocomplete="new-password" required><span class="field-hint">Use at least 12 characters.</span></div><button class="btn btn-primary btn-block" type="submit">Create patient account</button></form><div class="auth-footer"><a href="#" data-auth="login">Already have an account? Sign in</a> · <a href="#" data-auth="patient">Patient OTP portal</a></div>` : `<form id="login-form"><div class="field"><label for="login-email">Email address</label><input id="login-email" name="email" type="email" autocomplete="username" required></div><div class="field"><label for="login-password">Password</label><input id="login-password" name="password" type="password" autocomplete="current-password" required></div><button class="btn btn-primary btn-block" type="submit">Sign in securely</button></form><div class="auth-footer"><a href="#" data-auth="register">Create patient account</a> · <a href="#" data-auth="patient">Patient portal</a></div>`}
      <div class="footer-note">This prototype is for controlled testing. Do not enter real patient information until clinical, privacy and security approvals are complete.</div>
    </div></section></div>`;
    window.OneCareMotion?.refresh(root);
  }

  const navItems = [
    { id: "overview", label: "Overview", icon: "◫", roles: ["admin", "hmo", "pharmacy", "pmv", "hospital", "clinician", "patient"] },
    { id: "screening", label: "New screening", icon: "+", roles: ["pharmacy", "pmv"] },
    { id: "queue", label: "Care queue", icon: "▤", roles: ["admin", "hospital", "clinician"] },
    { id: "alerts", label: "Red-flag alerts", icon: "!", roles: ["admin", "hospital", "clinician"] },
    { id: "organisations", label: "Organisations & staff", icon: "⌂", roles: ["admin"] },
    { id: "audit", label: "Audit & FHIR", icon: "◇", roles: ["admin", "hospital", "clinician", "pharmacy", "pmv", "patient"] },
    { id: "patient", label: "My care receipt", icon: "♡", roles: ["patient"] },
  ];

  function renderShell() {
    const visible = navItems.filter((item) => item.roles.includes(role()));
    root.innerHTML = `<div class="shell"><aside class="sidebar" id="sidebar"><div class="brand"><span class="brand-mark">+</span><span>onecare<span style="color:#8de0b7">.</span>loop</span></div>
      <div class="side-label">Workspace · ${esc(role())}</div><nav class="side-nav">${visible.map((item) => `<button class="nav-btn ${state.view === item.id ? "active" : ""}" data-view="${item.id}"><span class="nav-icon">${item.icon}</span>${item.label}</button>`).join("")}</nav>
      <div class="sidebar-foot"><div class="user-chip"><div class="avatar">${esc(initials(state.user?.email || role()))}</div><div class="user-meta"><strong>${esc(state.user?.email || "Signed in")}</strong><small>${esc(role())}${state.user?.organisation_id ? " · organisation assigned" : ""}</small></div></div><button class="btn btn-outline btn-block" style="margin-top:13px;background:transparent;color:#d5e4dc;border-color:#426052" data-action="logout">Sign out</button></div></aside>
      <section class="main-area"><header class="topbar"><div class="row"><button class="btn btn-outline mobile-menu" data-action="menu" aria-label="Open navigation">☰</button><h1 id="page-title">Overview</h1></div><div class="top-actions"><span class="pill green role-pill">${esc(role())}</span><span class="small muted">OneCare Loop · v2</span></div></header><main class="content" id="main" tabindex="-1"><div class="boot">Loading workspace…</div></main></section></div>`;
    window.OneCareMotion?.refresh(root);
  }

  function pageIntro(eyebrow, title, description, right = "") {
    return `<div class="page-intro"><div><div class="eyebrow">${esc(eyebrow)}</div><h2>${esc(title)}</h2><p>${esc(description)}</p></div>${right ? `<div class="toolbar">${right}</div>` : ""}</div>`;
  }

  function metricCard(label, value, note, icon = "") {
    const countAttribute = typeof value === "number" && Number.isFinite(value) ? ` data-count-to="${value}"` : "";
    return `<div class="card metric-card"><div class="row between"><span class="small muted">${esc(label)}</span><span class="nav-icon">${icon}</span></div><div class="metric"${countAttribute}>${countAttribute ? "0" : esc(value)}</div><div class="metric-note">${esc(note)}</div></div>`;
  }

  async function loadView(view) {
    state.view = view;
    document.querySelectorAll(".nav-btn").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
    const target = document.getElementById("main");
    if (!target) return;
    target.innerHTML = `<div class="boot">Loading ${esc(view)}…</div>`;
    const titles = { overview: "Overview", screening: "New screening", queue: "Care queue", alerts: "Red-flag alerts", organisations: "Organisations & staff", audit: "Audit & FHIR", patient: "My care receipt" };
    document.getElementById("page-title").textContent = titles[view] || "OneCare Loop";
    try {
      const render = async () => {
        if (view === "overview") await renderOverview(target);
        else if (view === "screening") await renderScreening(target);
        else if (view === "queue") await renderQueue(target);
        else if (view === "alerts") await renderAlerts(target);
        else if (view === "organisations") await renderOrganisations(target);
        else if (view === "audit") await renderAudit(target);
        else if (view === "patient") await renderPatientPortal(target);
        else target.innerHTML = `<div class="empty">This workspace is not available for the current role.</div>`;
      };
      if (document.startViewTransition) {
        const transition = document.startViewTransition(render);
        await transition.finished.catch(() => {});
      } else {
        await render();
      }
      window.OneCareMotion?.refresh(target);
    } catch (error) {
      target.innerHTML = `<div class="notice danger">${esc(error.message)}</div><button class="btn btn-outline" data-action="reload-view">Try again</button>`;
    }
  }

  async function renderOverview(target) {
    const who = role();
    if (who === "patient") return renderPatientPortal(target);
    if (who === "pharmacy" || who === "pmv") {
      target.innerHTML = `${pageIntro("COMMUNITY CARE", "Welcome to your screening desk", "Record a screening with consent, then refer eligible positive results to a registered hospital.", `<button class="btn btn-primary" data-view="screening">＋ New screening</button>`)}
        <div class="grid three">${metricCard("Your organisation", esc(state.user.organisation_id || "Not assigned"), "Organisation-scoped access", "⌂")}${metricCard("Screening threshold", "140/90", "Positive screen threshold used by this configured prototype", "+")}${metricCard("Referral record", "Verifiable", "Each transition appends a signed audit event", "◇")}</div>
        <div class="notice info">OneCare Loop records screening and coordinates referrals. It does not diagnose hypertension or prescribe treatment. Follow your approved clinical protocol and escalate emergency symptoms through your facility's established emergency pathway.</div>`;
      return;
    }
    if (who === "hmo") {
      const data = await api("/metrics");
      target.innerHTML = `${pageIntro("PAYER VIEW", "Care-loop performance", "Referral closure and service coordination. No invented reimbursement or recovered-value estimates.")}
        <div class="grid four">${metricCard("Patients referred", data.total_patients ?? 0, "Distinct screened patients", "◎")}${metricCard("Referrals", data.total_referrals ?? 0, "Recorded referral episodes", "▤")}${metricCard("Closed loops", data.closed_loops ?? 0, "Disposition returned", "✓")}${metricCard("Closure rate", `${((data.closure_rate || 0) * 100).toFixed(1)}%`, "Of recorded referrals", "↗")}</div>
        <div class="grid two" style="margin-top:16px"><section class="card"><h3>Time to disposition</h3><div class="metric">${data.median_hours_to_disposition == null ? "—" : `${esc(data.median_hours_to_disposition)}h`}</div><p class="small muted">Median time from screening to clinician disposition.</p></section><section class="card"><h3>Failure events</h3>${renderFailureCounts(data.failure_breakdown)}</section></div>
        <div class="notice info">${esc(data.financial_value_note || "Financial value is not configured.")}</div>`;
      return;
    }
    if (who === "admin") {
      const [metrics, orgs, attention] = await Promise.all([api("/metrics"), api("/organisations"), api("/hospital/attention")]);
      state.organisations = orgs.organisations || [];
      target.innerHTML = `${pageIntro("NETWORK CONTROL", "Good to see you", "Monitor care coordination and administer participating organisations.", `<button class="btn btn-primary" data-view="organisations">Manage organisations</button>`)}
        <div class="grid four">${metricCard("Patients referred", metrics.total_patients ?? 0, "Distinct patients with referrals", "◎")}${metricCard("Total referrals", metrics.total_referrals ?? 0, "Referral episodes", "▤")}${metricCard("Closed loops", metrics.closed_loops ?? 0, "Clinical disposition recorded", "✓")}${metricCard("Closure rate", `${((metrics.closure_rate || 0) * 100).toFixed(1)}%`, "Of recorded referrals", "↗")}</div>
        <div class="grid two" style="margin-top:16px"><section class="card"><div class="card-head"><div><h3>Failure events</h3><p>Recorded care interruptions that need attention.</p></div><span class="pill amber">Operations</span></div>${renderFailureCounts(metrics.failure_breakdown)}</section>
        <section class="card"><div class="card-head"><div><h3>Participating organisations</h3><p>${state.organisations.length} registered</p></div><button class="btn btn-outline btn-small" data-view="organisations">View all</button></div>${state.organisations.slice(0, 5).map((o) => `<div class="row between" style="padding:9px 0;border-bottom:1px solid var(--line)"><div><strong>${esc(o.name)}</strong><div class="small muted">${esc(o.lga || "LGA not set")}</div></div><span class="pill blue">${esc(o.type)}</span></div>`).join("") || `<div class="empty">No organisations yet. Add a pharmacy or hospital to begin.</div>`}</section></div>
        <div class="footer-note">Metrics are operational counts from recorded referrals. They are not a clinical quality rating or payer claim.</div>`;
      return;
    }
    if (who === "hospital" || who === "clinician") {
      const [queue, attention] = await Promise.all([api("/hospital/queue"), who === "hospital" ? api("/hospital/attention") : Promise.resolve(null)]);
      state.queue = queue.queue || [];
      target.innerHTML = `${pageIntro("HOSPITAL OPERATIONS", who === "clinician" ? "Clinical review worklist" : "Referral coordination", who === "clinician" ? "Review encounters assigned to your facility and return a documented disposition." : "Accept incoming referrals, book appointments and record attendance.", `<button class="btn btn-outline" data-view="queue">Refresh queue</button>`)}
        <div class="grid three">${metricCard("Open work items", state.queue.length, "Visible within your organisation", "▤")}${metricCard("Urgent / emergency", state.queue.filter((r) => ["urgent", "emergency"].includes(r.urgency)).length, "Prioritise per approved protocol", "!")}${metricCard("SLA breached", state.queue.filter((r) => r.sla_breached).length, "Requires operational follow-up", "◷")}</div>
        ${who === "hospital" ? renderAttentionPanel(attention) : ""}
        <section class="card" style="margin-top:16px"><div class="card-head"><div><h3>Current worklist</h3><p>Latest actionable referrals assigned to your account or facility.</p></div><button class="btn btn-primary btn-small" data-view="queue">Open care queue</button></div>${state.queue.length ? state.queue.slice(0, 5).map(queueMini).join("") : `<div class="empty"><strong>No open work items</strong>New referrals will appear here when routed to your facility.</div>`}</section>`;
      return;
    }
    target.innerHTML = `${pageIntro("WORKSPACE", "Overview", "Your role does not currently have an overview panel.")}`;
  }

  function renderAttentionPanel(attention) {
    if (!attention) return "";
    const overdue = attention.overdue || [];
    const unassigned = attention.unassigned || [];
    return `<section class="card" style="margin-top:16px"><div class="card-head"><div><h3>Operational attention</h3><p>Exceptions requiring a named human owner. This panel does not make clinical decisions.</p></div><span class="pill ${overdue.length ? "red" : unassigned.length ? "amber" : "green"}">${overdue.length + unassigned.length} item(s)</span></div>
      <div class="grid two"><div><h4>Overdue SLA exceptions</h4>${overdue.length ? overdue.map((item) => `<div class="row between" style="padding:8px 0;border-bottom:1px solid var(--line)"><div><strong class="small">Referral ${esc(String(item.referral_id).slice(0, 8))}…</strong><div class="small muted">${esc(titleCase(item.reason_code))} · owner ${item.owner_user_id ? esc(String(item.owner_user_id).slice(0, 8)) + "…" : "unassigned"}</div></div><span class="pill red">Overdue</span></div>`).join("") : `<p class="small muted">No open SLA exceptions.</p>`}</div>
      <div><h4>Unassigned referrals</h4>${unassigned.length ? unassigned.map((item) => `<div class="row between" style="padding:8px 0;border-bottom:1px solid var(--line)"><div><strong class="small">Referral ${esc(String(item.id).slice(0, 8))}…</strong><div class="small muted">${esc(titleCase(item.status))} · due ${esc(dateTime(item.sla_deadline))}</div></div><span class="pill amber">Unassigned</span></div>`).join("") : `<p class="small muted">No unassigned active referrals.</p>`}</div></div>
      <p class="field-hint">Run the scheduled <code>escalate-overdue</code> command to process deadline breaches. The web app does not run a background scheduler by itself.</p></section>`;
  }

  function renderFailureCounts(counts = {}) {
    const entries = Object.entries(counts || {});
    if (!entries.length) return `<p class="small muted">No failure events recorded.</p>`;
    return entries.map(([name, count]) => `<div class="row between" style="padding:8px 0;border-bottom:1px solid var(--line)"><span class="small">${esc(titleCase(name))}</span><span class="pill red">${esc(count)}</span></div>`).join("");
  }

  function queueMini(referral) {
    return `<div class="row between" style="padding:10px 0;border-bottom:1px solid var(--line)"><div><strong class="small">${esc(referral.patient_id.slice(0, 8))}…</strong><div class="small muted">${esc(titleCase(referral.status))} · ${esc(dateTime(referral.sla_deadline))}</div></div><span class="pill ${referral.urgency === "emergency" ? "red" : referral.urgency === "urgent" ? "amber" : "green"}">${esc(referral.urgency)}</span></div>`;
  }

  async function renderScreening(target) {
    if (!canPharmacy()) throw new Error("A pharmacy or PMV account is required.");
    const orgs = await api("/organisations");
    state.organisations = orgs.organisations || [];
    const hospitals = state.organisations.filter((item) => item.type === "hospital");
    target.innerHTML = `${pageIntro("PHARMACY / PMV", "Record a blood-pressure screening", "Capture minimum necessary information, confirm consent and create a referral for a positive screen.")}
      <div class="split"><section class="card"><div class="row between"><div><h3>Screening record</h3><p class="small muted">Protocol: HTN-PROTOCOL-v1</p></div><span class="pill green">Consent required</span></div>
        <form id="screening-form"><div class="form-grid">
          <div class="field span-2"><label for="patient-name">Patient name (optional)</label><input id="patient-name" name="display_name" maxlength="120" autocomplete="off"></div>
          <div class="field"><label for="patient-phone">Phone number</label><input id="patient-phone" name="phone" type="tel" placeholder="+2348012345678" required></div>
          <div class="field"><label for="patient-age">Age band</label><select id="patient-age" name="age_band"><option value="">Not recorded</option><option>18-29</option><option>30-39</option><option>40-49</option><option>50-59</option><option>60+</option></select></div>
          <div class="field"><label for="insurance">Coverage category</label><select id="insurance" name="insurance_type"><option value="unknown">Not known</option><option value="nhia">NHIA (unverified)</option><option value="private">Private (unverified)</option><option value="self_pay">Self-pay</option><option value="donor">Donor-supported</option></select><span class="field-hint">No live eligibility check is connected.</span></div>
          <div class="field"><label for="language">Preferred language</label><select id="language" name="preferred_language"><option value="en">English</option><option value="pcm">Nigerian Pidgin</option><option value="ig">Igbo</option><option value="ha">Hausa</option><option value="yo">Yorùbá</option></select></div>
          <div class="field"><label for="sbp">Systolic (mmHg)</label><input id="sbp" name="systolic" type="number" min="40" max="300" value="150" required></div>
          <div class="field"><label for="dbp">Diastolic (mmHg)</label><input id="dbp" name="diastolic" type="number" min="20" max="200" value="95" required></div>
          <div class="field span-2"><label for="symptoms">Symptoms (optional; comma-separated codes)</label><input id="symptoms" name="symptoms" placeholder="chest_pain, severe_headache"><span class="field-hint">Recognised red flags include chest_pain, one_sided_weakness, vision_loss, severe_headache and shortness_of_breath.</span></div>
          <div class="field span-2"><label for="facility">Receiving hospital</label><select id="facility" name="facility_id" required><option value="">Choose a registered hospital</option>${hospitals.map((item) => `<option value="${esc(item.id)}">${esc(item.name)}${item.lga ? ` · ${esc(item.lga)}` : ""}</option>`).join("")}</select>${hospitals.length ? "" : `<span class="field-hint">No hospital registered yet. Ask the administrator to add one.</span>`}</div>
        </div>
        <label class="check-row"><input type="checkbox" name="consent" required><span>I confirm that the patient has been informed and has consented to screening, referral, necessary follow-up and the stated handling of their information. Consent can be withdrawn.</span></label>
        <div class="notice warning">A severe reading or red-flag symptom requires immediate action under your facility's approved emergency protocol. This software does not dispatch emergency services.</div>
        <button class="btn btn-primary btn-block" type="submit" ${hospitals.length ? "" : "disabled"}>Save screening and create referral</button></form></section>
        <aside class="stack"><section class="card"><h3>Decision support reference</h3><p class="small muted">Prototype thresholds; confirm these against your approved local clinical protocol.</p><div class="row between" style="margin:13px 0"><span>Positive screening</span><span class="pill amber">≥140 / ≥90</span></div><div class="row between" style="margin:13px 0"><span>Urgent band</span><span class="pill red">≥160 / ≥100</span></div><div class="row between" style="margin:13px 0"><span>Red-flag band</span><span class="pill red">≥180 / ≥120</span></div></section>
        <section class="card"><h3>What happens next?</h3><div class="event-list"><div class="event"><span class="event-dot"></span><div><h4>Screening recorded</h4><p>Measurements and consent reference are recorded securely.</p></div></div><div class="event"><span class="event-dot"></span><div><h4>Referral opened</h4><p>The receiving hospital gets a work item.</p></div></div><div class="event"><span class="event-dot"></span><div><h4>Care is tracked</h4><p>Acceptance, appointment, attendance and outcome are appended to the audit history.</p></div></div></div></section></aside></div><div id="screening-result" style="margin-top:16px"></div>`;
  }

  async function renderQueue(target) {
    if (!canHospital()) throw new Error("A hospital, clinician or administrator account is required.");
    const [queueResponse, organisationsResponse, attention] = await Promise.all([
      api("/hospital/queue"), api("/organisations"), role() === "clinician" ? Promise.resolve(null) : api("/hospital/attention"),
    ]);
    state.queue = queueResponse.queue || [];
    state.organisations = organisationsResponse.organisations || [];
    const hospitals = state.organisations.filter((item) => item.type === "hospital");
    target.innerHTML = `${pageIntro("CARE COORDINATION", role() === "clinician" ? "Clinical review worklist" : "Hospital referral queue", "Work only on patients referred to your organisation. All accepted actions create a signed audit event.", `<button class="btn btn-outline" data-action="reload-view">↻ Refresh</button>`)}
      ${role() === "clinician" ? "" : renderAttentionPanel(attention)}
      ${state.queue.length ? `<div class="grid two">${state.queue.map((item) => queueCard(item, hospitals)).join("")}</div>` : `<div class="empty"><strong>No actionable referrals</strong>There are no queue items assigned to your organisation at this time.</div>`}
      <div class="footer-note">Patient identifiers are shortened in the worklist. Open only the minimum information needed for the care task. Emergency alerts are recorded only; external dispatch is not connected.</div>`;
    await loadCliniciansIntoForms();
  }

  function queueCard(item, hospitals) {
    const urgencyClass = item.urgency === "emergency" ? "red" : item.urgency === "urgent" ? "amber" : "green";
    let actions = `<p class="small muted">No action available for this role and state.</p>`;
    if (role() === "hospital" || role() === "admin") {
      if (item.status === "REFERRAL_CREATED") actions = `<div class="action-grid"><button class="btn btn-primary" data-action="accept-referral" data-id="${esc(item.id)}">Accept referral</button><button class="btn btn-outline" data-action="show-decline" data-id="${esc(item.id)}">Decline / redirect</button></div><div id="decline-${esc(item.id)}" class="hide" style="margin-top:12px"><div class="field"><label>Reason</label><input class="control" id="reason-${esc(item.id)}" value="capacity_unavailable"></div><div class="field"><label>Redirect to (optional)</label><select class="control" id="redirect-${esc(item.id)}"><option value="">Do not redirect now</option>${hospitals.filter((h) => h.id !== item.facility_id).map((h) => `<option value="${esc(h.id)}">${esc(h.name)}</option>`).join("")}</select></div><button class="btn btn-danger btn-small" data-action="decline-referral" data-id="${esc(item.id)}">Confirm decline</button></div>`;
      else if (["REFERRAL_DECLINED", "FACILITY_UNAVAILABLE"].includes(item.status)) actions = `<form data-form="redirect-referral" data-id="${esc(item.id)}"><div class="field"><label>Choose an alternative receiving hospital</label><select class="control" name="facility_id" required><option value="">Select hospital</option>${hospitals.filter((h) => h.id !== item.facility_id).map((h) => `<option value="${esc(h.id)}">${esc(h.name)}</option>`).join("")}</select></div><button class="btn btn-primary btn-block" type="submit">Redirect referral</button></form>`;
      else if (item.status === "FACILITY_ACCEPTED") actions = `<form data-form="book-appointment" data-id="${esc(item.id)}"><div class="form-grid"><div class="field"><label>Appointment start</label><input class="control" type="datetime-local" name="slot_start" required value="${dateInputValue(new Date(Date.now() + 86400000))}"></div><div class="field"><label>Appointment end</label><input class="control" type="datetime-local" name="slot_end" required value="${dateInputValue(new Date(Date.now() + 86400000 + 1800000))}"></div></div><button class="btn btn-primary btn-block" type="submit">Book appointment</button></form>`;
      else if (["APPOINTMENT_MISSED", "PATIENT_REQUESTED_RESCHEDULE"].includes(item.status)) actions = `<form data-form="book-appointment" data-id="${esc(item.id)}"><p class="small muted">A new appointment will be appended; the prior missed/reschedule event remains in the history.</p><div class="form-grid"><div class="field"><label>New start</label><input class="control" type="datetime-local" name="slot_start" required value="${dateInputValue(new Date(Date.now() + 86400000))}"></div><div class="field"><label>New end</label><input class="control" type="datetime-local" name="slot_end" required value="${dateInputValue(new Date(Date.now() + 86400000 + 1800000))}"></div></div><button class="btn btn-primary btn-block" type="submit">Rebook appointment</button></form>`;
      else if (item.status === "APPOINTMENT_BOOKED") actions = `<form data-form="attest-attendance" data-id="${esc(item.id)}"><div class="field"><label>Assigned clinician</label><select class="control" name="clinician_id" data-facility="${esc(item.facility_id)}" required><option value="">Loading clinicians…</option></select></div><div class="field"><label>Encounter note (optional)</label><input class="control" name="notes" maxlength="4000" placeholder="Attendance recorded"></div><button class="btn btn-primary btn-block" type="submit">Confirm attendance</button></form><div class="row" style="margin-top:9px"><button class="btn btn-outline btn-small" data-action="mark-missed" data-id="${esc(item.id)}">Mark appointment missed</button><button class="btn btn-outline btn-small" data-action="mark-unreachable" data-id="${esc(item.id)}">Mark unreachable</button></div>`;
    }
    if (role() === "clinician" && item.status === "CLINICAL_ENCOUNTER_COMPLETED") {
      actions = item.confirmatory_test_recorded
        ? `<div class="notice">Confirmatory assessment recorded. You may now return the clinical disposition.</div><form data-form="return-disposition" data-id="${esc(item.id)}" data-patient="${esc(item.patient_id)}"><div class="field"><label>Clinical disposition outcome</label><select class="control" name="outcome" required><option value="clinical_review_completed">Clinical review completed</option><option value="treatment_started">Treatment initiated by clinician</option><option value="further_investigation">Further investigation required</option><option value="specialist_referral">Specialist referral advised</option><option value="no_change">No change to current plan</option></select></div><div class="field"><label>Clinician-documented next step</label><textarea class="control textarea" name="next_step" required minlength="2" maxlength="2000" placeholder="Record the clinician-approved plan and follow-up instruction"></textarea></div><button class="btn btn-primary btn-block" type="submit">Sign and return disposition</button></form>`
        : `<form data-form="confirmatory-assessment" data-id="${esc(item.id)}"><div class="eyebrow">CONFIRMATORY REVIEW</div><p class="small muted">Record the confirmatory method chosen by the clinician. This prototype does not diagnose or select treatment.</p><div class="field"><label>Assessment method</label><select class="control" name="method"><option value="repeat_office">Repeat office blood pressure</option><option value="home_monitoring">Home blood-pressure monitoring</option><option value="ambulatory_monitoring">Ambulatory blood-pressure monitoring</option><option value="not_indicated">Not indicated for this case</option></select></div><div class="form-grid" data-confirmatory-readings><div class="field"><label>Systolic (mmHg)</label><input class="control" name="systolic" type="number" min="40" max="300" required></div><div class="field"><label>Diastolic (mmHg)</label><input class="control" name="diastolic" type="number" min="20" max="200" required></div></div><div class="field"><label>Clinical note / reason</label><textarea class="control textarea" name="note" maxlength="1000" placeholder="Document context or why confirmatory testing is not indicated"></textarea></div><button class="btn btn-primary btn-block" type="submit">Record confirmatory assessment</button></form>`;
    }
    return `<article class="card" data-queue-card="${esc(item.id)}"><div class="card-head"><div><div class="row"><h3>Referral ${esc(item.id.slice(0, 8))}…</h3><span class="pill ${urgencyClass}">${esc(item.urgency)}</span></div><p>Patient ${esc(item.patient_id.slice(0, 8))}… · ${esc(titleCase(item.status))}</p></div>${item.escalated_at ? `<span class="pill red">Escalated</span>` : item.sla_breached ? `<span class="pill red">SLA breached</span>` : `<span class="pill gray">Within SLA</span>`}</div>
      <div class="grid two" style="gap:8px;margin-bottom:13px"><div><div class="small muted">Recorded BP</div><strong>${item.details_redacted ? "Redacted" : `${esc(item.systolic ?? "—")}/${esc(item.diastolic ?? "—")} mmHg`}</strong></div><div><div class="small muted">SLA deadline</div><strong class="small">${esc(dateTime(item.sla_deadline))}</strong></div></div>
      <div class="small muted" style="margin-bottom:10px">${item.unassigned ? "Unassigned · awaiting a responsible owner" : `Owner: ${esc(item.owner_role || "assigned staff")}`}</div>
      <div class="action-card">${actions}${(role() === "hospital" || role() === "admin") && !["CLINICAL_DISPOSITION_RETURNED", "PATIENT_DECLINED"].includes(item.status) ? `<form data-form="assign-referral-owner" data-id="${esc(item.id)}" style="margin-top:12px"><div class="field"><label>Reassign responsible clinician (optional)</label><select class="control" name="owner_user_id" data-facility="${esc(item.facility_id)}"><option value="">Keep current owner</option></select></div><button class="btn btn-outline btn-small" type="submit">Assign case owner</button></form>` : ""}</div><div class="row between" style="margin-top:12px"><button class="btn btn-outline btn-small" data-action="history" data-id="${esc(item.id)}">View verified history</button><button class="btn btn-outline btn-small" data-action="messages" data-id="${esc(item.id)}">Care team messages</button></div><div id="detail-${esc(item.id)}" style="margin-top:10px"></div></article>`;
  }

  async function renderAlerts(target) {
    const response = await api("/red-flags");
    const alerts = response.alerts || [];
    target.innerHTML = `${pageIntro("SAFETY OPERATIONS", "Red-flag alerts", "Review and acknowledge recorded alerts. The current prototype does not dispatch ambulances or page external responders.")}
      <div class="notice warning">Simulation only: alerts are recorded in the system. Acknowledgement is not emergency response. Follow the facility's established emergency escalation protocol.</div>
      ${alerts.length ? `<div class="grid two">${alerts.map((alert) => `<section class="card"><div class="card-head"><div><h3>Emergency flag · ${esc(alert.id.slice(0, 8))}…</h3><p>Referral ${esc(alert.referral_id.slice(0, 8))}…</p></div><span class="pill ${alert.acknowledged_at ? "green" : "red"}">${alert.acknowledged_at ? "Acknowledged" : "Open"}</span></div><p class="small">Reason: ${esc(titleCase(alert.reason_code))}</p><p class="small muted">Created ${esc(dateTime(alert.created_at))}</p>${alert.acknowledged_at ? `<p class="small muted">Acknowledged ${esc(dateTime(alert.acknowledged_at))}</p>` : `<form data-form="ack-alert" data-id="${esc(alert.id)}"><div class="field"><label>Acknowledgement note</label><input class="control" name="note" maxlength="1000" placeholder="Reviewed and escalated via facility protocol"></div><button class="btn btn-primary btn-small" type="submit">Acknowledge alert</button></form>`}</section>`).join("")}</div>` : `<div class="empty"><strong>No open red-flag alerts</strong>New qualifying screenings will create a tracked alert.</div>`}`;
  }

  async function renderOrganisations(target) {
    if (!isAdmin()) throw new Error("Administrator access is required.");
    const response = await api("/organisations");
    state.organisations = response.organisations || [];
    target.innerHTML = `${pageIntro("ADMINISTRATION", "Organisations and staff", "Register a participating organisation, then provision role-specific accounts. Public registration cannot create staff or administrator accounts.")}
      <div class="grid two"><section class="card"><div class="card-head"><div><h3>Register organisation</h3><p>Each staff account must match its organisation type.</p></div></div><form id="organisation-form"><div class="field"><label>Organisation name</label><input class="control" name="name" minlength="2" maxlength="160" required></div><div class="form-grid"><div class="field"><label>Type</label><select class="control" name="type" required><option value="pharmacy">Pharmacy</option><option value="pmv">PMV</option><option value="hospital">Hospital</option><option value="hmo">HMO</option><option value="donor">Donor</option><option value="chw">Community health worker organisation</option></select></div><div class="field"><label>LGA (optional)</label><input class="control" name="lga" maxlength="100"></div></div><button class="btn btn-primary" type="submit">Create organisation</button></form></section>
      <section class="card"><div class="card-head"><div><h3>Provision staff access</h3><p>Only an administrator can create staff accounts.</p></div><span class="pill green">Controlled access</span></div><form id="staff-form"><div class="field"><label>Staff email</label><input class="control" type="email" name="email" required></div><div class="field"><label>Temporary password</label><input class="control" type="password" name="password" minlength="12" required><span class="field-hint">At least 12 characters. Share securely and ask staff to rotate it.</span></div><div class="field"><label>Role</label><select class="control" name="role"><option value="pharmacy">Pharmacy staff</option><option value="pmv">PMV staff</option><option value="hospital">Hospital staff</option><option value="clinician">Clinician</option><option value="hmo">HMO</option></select></div><div class="field"><label>Organisation</label><select class="control" name="organisation_id" required><option value="">Select organisation</option>${state.organisations.map((o) => `<option value="${esc(o.id)}" data-type="${esc(o.type)}">${esc(o.name)} · ${esc(o.type)}</option>`).join("")}</select></div><button class="btn btn-primary" type="submit">Provision staff account</button></form><div id="staff-created" style="margin-top:12px"></div></section></div>
      <section class="card" style="margin-top:16px"><div class="card-head"><div><h3>Registered organisations</h3><p>${state.organisations.length} organisation(s)</p></div><button class="btn btn-outline btn-small" data-action="reload-view">Refresh</button></div>${state.organisations.length ? `<div class="table-wrap"><table><thead><tr><th>Name</th><th>Type</th><th>LGA</th><th>Identifier</th></tr></thead><tbody>${state.organisations.map((o) => `<tr><td><strong>${esc(o.name)}</strong></td><td><span class="pill blue">${esc(o.type)}</span></td><td>${esc(o.lga || "—")}</td><td class="mono">${esc(o.id)}</td></tr>`).join("")}</tbody></table></div>` : `<div class="empty">No organisations registered.</div>`}</section>`;
  }

  async function renderAudit(target) {
    target.innerHTML = `${pageIntro("VERIFIABLE RECORDS", "Audit and interoperability", "Verify a patient's event chain or export an authorised FHIR R4 care bundle.")}
      <div class="grid two"><section class="card"><h3>Verify patient event chain</h3><p class="small muted">Enter a patient identifier available to your authorised organisation. Patient users can verify only their own record.</p><form id="verify-form"><div class="field"><label>Patient ID</label><input class="control" name="patient_id" required minlength="1"></div><button class="btn btn-primary" type="submit">Verify chain</button></form><div id="verify-result" style="margin-top:14px"></div></section>
      <section class="card"><h3>FHIR R4 export</h3><p class="small muted">Generate a patient-scoped collection bundle. Export is permission-checked and omits direct identifiers.</p><form id="fhir-form"><div class="field"><label>Patient ID</label><input class="control" name="patient_id" required></div><button class="btn btn-outline" type="submit">Generate FHIR bundle</button></form><div id="fhir-result" style="margin-top:14px"></div></section></div>
      <div class="notice info">A hash chain is tamper-evident, not tamper-proof. Database administrators or compromised signing infrastructure remain part of the trust boundary. Production use requires independent key management and external anchoring.</div>`;
  }

  async function renderPatientPortal(target) {
    if (role() !== "patient") throw new Error("Patient account required.");
    const [receipt, followups, notifications] = await Promise.all([
      api("/patients/me/receipt"), api(`/patients/${encodeURIComponent(state.user.patient_id)}/followups`), api("/patients/me/notifications"),
    ]);
    state.patientReceipt = receipt;
    const events = receipt.events || [];
    target.innerHTML = `${pageIntro("PATIENT PORTAL", "Your care receipt", "A private view of the care journey recorded for you. You can review the history, verify the chain and acknowledge that you have read it.", `<button class="btn btn-outline" data-action="logout">Sign out</button>`)}
      ${renderJourneyRing(events)}
      <div class="grid three"><section class="card"><div class="small muted">Audit chain</div><div class="metric" style="font-size:24px">${receipt.verified ? "Verified" : "Broken"}</div><span class="pill ${receipt.verified ? "green" : "red"}">${receipt.verified ? "Integrity check passed" : "Integrity check failed"}</span></section><section class="card"><div class="small muted">Recorded events</div><div class="metric">${events.length}</div><div class="metric-note">Chronological care events</div></section><section class="card"><div class="small muted">Follow-up plans</div><div class="metric">${(followups.plans || []).length}</div><div class="metric-note">Current state: ${esc(titleCase(followups.current_state || "Not available"))}</div></section></div>
      <div class="grid two" style="margin-top:16px"><section class="card"><div class="card-head"><div><h3>Your care journey</h3><p>Each item is appended to the signed event ledger.</p></div><span class="pill ${receipt.verified ? "green" : "red"}">${receipt.verified ? "Verified" : "Check failed"}</span></div>
        ${events.length ? `<div class="event-list">${events.map((event) => `<div class="event"><span class="event-dot"></span><div><h4>${esc(event.headline || titleCase(event.event_type))}</h4><p>${esc(dateTime(event.occurred_at))} · ${esc(titleCase(event.actor_role))}</p>${event.details_redacted ? `<p class="small muted">Details are unavailable after consent revocation.</p>` : event.payload?.urgency ? `<p class="small">Referral urgency: ${esc(event.payload.urgency)}</p>` : ""}<span class="mono">Event ${esc(event.seq)} · ${esc(String(event.event_hash || "").slice(0, 16))}…</span></div></div>`).join("")}</div>` : `<div class="empty">No events are available for this patient record.</div>`}
        <div class="toolbar" style="margin-top:14px"><button class="btn btn-primary" data-action="ack-receipt">I have read this receipt</button><button class="btn btn-danger" data-action="revoke-consent">Withdraw consent</button></div></section>
        <aside class="stack"><section class="card"><h3>Follow-up plans</h3>${(followups.plans || []).length ? followups.plans.map((plan) => `<div class="row between" style="padding:10px 0;border-bottom:1px solid var(--line)"><div><strong class="small">${esc(titleCase(plan.plan_type))}</strong><div class="small muted">${esc(dateTime(plan.due_date))}</div></div><span class="pill ${plan.status === "met" ? "green" : plan.status === "pending" ? "amber" : "gray"}">${esc(plan.status)}</span></div>`).join("") : `<p class="small muted">No follow-up plan has been recorded.</p>`}</section>
        <section class="card"><h3>Notifications</h3>${(notifications.notifications || []).length ? notifications.notifications.map((n) => `<div style="padding:9px 0;border-bottom:1px solid var(--line)"><div class="row between"><strong class="small">${esc(titleCase(n.template_id))}</strong><span class="pill gray">${esc(n.status)}</span></div><p class="small muted">${esc(dateTime(n.created_at))}</p><p class="small">${esc(n.body)}</p></div>`).join("") : `<p class="small muted">No notification records.</p>`}<p class="field-hint">Notification delivery is simulated in this prototype.</p></section></aside></div>
      <div class="footer-note">This receipt is an operational record, not a diagnosis or treatment recommendation. For urgent symptoms, seek in-person emergency care through local services.</div>`;
  }

  async function loadStaffForHospital() {
    const orgId = state.user?.organisation_id;
    if (!orgId) return [];
    const response = await api(`/organisations/${encodeURIComponent(orgId)}/staff`);
    return response.staff || [];
  }

  async function loadCliniciansIntoForms() {
    if (role() !== "hospital" && role() !== "admin") return;
    const selects = [...document.querySelectorAll('select[name="clinician_id"], select[name="owner_user_id"]')];
    if (!selects.length) return;
    await Promise.all(selects.map(async (select) => {
      try {
        const orgId = select.dataset.facility || state.user?.organisation_id;
        if (!orgId) throw new Error("No hospital organisation is assigned");
        const response = await api(`/organisations/${encodeURIComponent(orgId)}/staff`);
        const clinicians = (response.staff || []).filter((person) => person.role === "clinician");
        const placeholder = select.name === "owner_user_id" ? "Keep current owner" : "Select assigned clinician";
        select.innerHTML = `<option value="">${placeholder}</option>${clinicians.map((person) => `<option value="${esc(person.id)}">${esc(person.email || person.id)} · ${esc(person.id.slice(0, 8))}</option>`).join("")}`;
        if (!clinicians.length && select.name === "clinician_id") select.innerHTML = `<option value="">No clinician provisioned for this organisation</option>`;
      } catch (error) { select.innerHTML = `<option value="">${esc(error.message)}</option>`; }
    }));
  }

  async function refreshQueue() { await loadView("queue"); await loadCliniciansIntoForms(); }

  async function handleScreening(form) {
    const values = Object.fromEntries(new FormData(form).entries());
    if (!form.elements.consent.checked) throw new Error("Consent must be confirmed before screening.");
    if (!values.facility_id) throw new Error("Choose a registered hospital.");
    const symptoms = values.symptoms.split(",").map((item) => item.trim()).filter(Boolean);
    const result = await api("/screenings", { method: "POST", body: JSON.stringify({
      patient: { display_name: values.display_name || null, age_band: values.age_band || null, insurance_type: values.insurance_type, phone: values.phone, preferred_language: values.preferred_language },
      consent: { version: "1.0", scopes: ["screening", "referral", "follow_up", "notifications"] },
      screening: { systolic: Number(values.systolic), diastolic: Number(values.diastolic), symptoms, protocol_version: "HTN-PROTOCOL-v1" },
    }) });
    if (result.result !== "positive") {
      document.getElementById("screening-result").innerHTML = `<section class="card"><span class="pill green">Screening recorded</span><h3 style="margin-top:10px">${esc(titleCase(result.result))}</h3><p class="small muted">No referral was created because the recorded result was not positive.</p><div class="mono">Patient ${esc(result.patient_id)} · Event ${esc(result.event?.event_hash || "")}</div></section>`;
      toast("Screening saved. No referral was required by the configured rule.", "success");
      form.reset();
      return;
    }
    const referral = await api("/referrals", { method: "POST", body: JSON.stringify({ screening_id: result.screening_id, facility_id: values.facility_id }) });
    document.getElementById("screening-result").innerHTML = `<section class="card"><div class="row between"><h3>Screening and referral recorded</h3><span class="pill ${referral.urgency === "emergency" ? "red" : referral.urgency === "urgent" ? "amber" : "green"}">${esc(referral.urgency)}</span></div><div class="grid two" style="margin-top:12px"><div><div class="small muted">Patient identifier</div><strong class="mono">${esc(result.patient_id)}</strong></div><div><div class="small muted">Referral identifier</div><strong class="mono">${esc(referral.referral_id)}</strong></div></div><div class="notice info">Eligibility: ${esc(referral.eligibility?.decision || "unknown")} · simulated / unverified. Patient notification: ${esc(referral.notification?.status || "not issued")}</div><button class="btn btn-outline btn-small" data-action="history" data-id="${esc(referral.referral_id)}">View event history</button><div id="detail-${esc(referral.referral_id)}"></div></section>`;
    toast("Referral created and audit event appended.", "success");
    form.reset();
  }

  async function handleOrganisation(form) {
    const data = Object.fromEntries(new FormData(form).entries());
    const created = await api("/organisations", { method: "POST", body: JSON.stringify(data) });
    toast(`Organisation created: ${created.name}`, "success");
    await loadView("organisations");
  }

  async function handleProvision(form) {
    const data = Object.fromEntries(new FormData(form).entries());
    const created = await api("/auth/provision", { method: "POST", body: JSON.stringify(data) });
    const result = document.getElementById("staff-created");
    result.innerHTML = `<div class="notice"><strong>Staff account provisioned.</strong><br>Email: ${esc(created.email || data.email)}<br>Role: ${esc(created.role)}<br>User ID (needed for audit assignment): <span class="mono">${esc(created.id)}</span></div>`;
    toast("Staff account provisioned.", "success");
    form.reset();
  }

  async function handleQueueAction(action, id) {
    if (action === "accept-referral") {
      await api(`/hospital/referrals/${id}/accept`, { method: "POST", body: "{}" });
      toast("Referral accepted.", "success"); await refreshQueue(); return;
    }
    if (action === "decline-referral") {
      const reason = document.getElementById(`reason-${id}`)?.value || "capacity_unavailable";
      const redirect = document.getElementById(`redirect-${id}`)?.value || null;
      await api(`/hospital/referrals/${id}/decline`, { method: "POST", body: JSON.stringify({ reason_code: reason, redirect_facility_id: redirect }) });
      toast("Referral decline recorded.", "success"); await refreshQueue(); return;
    }
    if (action === "mark-missed" || action === "mark-unreachable") {
      const reason = action === "mark-missed" ? "appointment_not_attended" : "contact_attempt_unsuccessful";
      const suffix = action === "mark-missed" ? "appointments/missed" : "unreachable";
      await api(`/hospital/referrals/${id}/${suffix}`, { method: "POST", body: JSON.stringify({ reason_code: reason }) });
      toast("Failure event recorded for care follow-up.", "success"); await refreshQueue(); return;
    }
  }

  async function handleHistory(id) {
    const detail = document.getElementById(`detail-${id}`);
    if (!detail) return;
    detail.innerHTML = `<p class="small muted">Loading verified history…</p>`;
    try {
      const response = await api(`/referrals/${id}/history`);
      detail.innerHTML = `<div class="notice ${response.chain_verified ? "" : "danger"}">Chain ${response.chain_verified ? "verified" : "verification failed"} · ${response.events.length} related event(s).</div><div class="event-list">${response.events.map((event) => `<div class="event"><span class="event-dot"></span><div><h4>${esc(titleCase(event.event_type))}</h4><p>${esc(dateTime(event.occurred_at))} · ${esc(titleCase(event.actor_role))}</p>${event.details_redacted ? `<p class="small muted">Details redacted.</p>` : ""}<span class="mono">${esc(event.event_hash)}</span></div></div>`).join("")}</div>`;
    } catch (error) { detail.innerHTML = `<div class="notice danger">${esc(error.message)}</div>`; }
  }

  async function handleMessages(id) {
    const detail = document.getElementById(`detail-${id}`);
    if (!detail) return;
    const response = await api(`/referrals/${id}/messages`);
    detail.innerHTML = `<div class="action-card"><h4>Care team thread</h4>${(response.messages || []).length ? response.messages.map((message) => `<p class="small" style="padding:7px 0;border-bottom:1px solid var(--line)">${esc(message.body)}<br><span class="muted">${esc(dateTime(message.created_at))}</span></p>`).join("") : `<p class="small muted">No messages recorded yet.</p>`}<form data-form="send-message" data-id="${esc(id)}"><div class="field"><label>New coordination message</label><textarea class="control textarea" name="body" maxlength="2000" required></textarea></div><button class="btn btn-outline btn-small" type="submit">Append message to history</button></form></div>`;
  }

  async function handleVerify(form) {
    const patientId = new FormData(form).get("patient_id").trim();
    const result = await api(`/audit/patients/${encodeURIComponent(patientId)}/verify`);
    const box = document.getElementById("verify-result");
    box.innerHTML = `<div class="notice ${result.ok ? "" : "danger"}"><strong>${result.ok ? "Event chain verified" : "Verification failed"}</strong><br>${esc(result.events)} events · ${esc(result.reason || "No integrity error reported")}</div><div class="mono">Head hash: ${esc(result.head_hash || "—")}</div>`;
  }

  async function handleFhir(form) {
    const patientId = new FormData(form).get("patient_id").trim();
    const result = await api(`/fhir/patients/${encodeURIComponent(patientId)}/bundle`);
    const box = document.getElementById("fhir-result");
    box.innerHTML = `<div class="notice">FHIR R4 bundle generated · ${esc(result.total || result.entry?.length || 0)} resource(s).</div><button class="btn btn-outline btn-small" data-action="download-fhir">Download JSON bundle</button>`;
    state.latestFhir = result;
  }

  async function handlePatientAction(action) {
    if (action === "ack-receipt") {
      await api("/patients/me/receipt/acknowledge", { method: "POST", body: "{}" });
      toast("Receipt acknowledgement recorded.", "success"); await loadView("patient");
    } else if (action === "revoke-consent") {
      const accepted = window.confirm("Withdraw consent and destroy the patient data key? Encrypted personal and clinical details will no longer be readable. This action cannot be undone.");
      if (!accepted) return;
      await api(`/patients/${encodeURIComponent(state.user.patient_id)}/consent/revoke`, { method: "POST", body: JSON.stringify({ reason: "patient_request" }) });
      clearAuth(); renderAuth("patient", "Consent was withdrawn. Your patient account has been disabled and the personal data key was destroyed.");
    }
  }

  async function handleFollowUpSchedule(referralId, patientId, form) {
    const data = Object.fromEntries(new FormData(form).entries());
    await api(`/patients/${encodeURIComponent(patientId)}/followups`, { method: "POST", body: JSON.stringify({ due_date: new Date(data.due_date).toISOString(), plan_type: data.plan_type }) });
    toast("Follow-up plan recorded.", "success"); await refreshQueue();
  }

  async function handleDisposition(form) {
    const data = Object.fromEntries(new FormData(form).entries());
    const id = form.dataset.id;
    const patientId = form.dataset.patient;
    await api(`/hospital/referrals/${id}/disposition`, { method: "POST", body: JSON.stringify({ outcome: data.outcome, next_step: data.next_step }) });
    toast("Clinician disposition signed and returned.", "success");
    await loadView("queue");
    const main = document.getElementById("main");
    const followup = document.createElement("section");
    followup.className = "card";
    followup.style.marginTop = "16px";
    followup.innerHTML = `<h3>Schedule next follow-up</h3><p class="small muted">The referral disposition is saved. Create a longitudinal follow-up plan for this patient.</p><form id="followup-form" data-patient="${esc(patientId)}"><div class="form-grid"><div class="field"><label>Due date and time</label><input class="control" type="datetime-local" name="due_date" required value="${dateInputValue(new Date(Date.now() + 30 * 86400000))}"></div><div class="field"><label>Follow-up type</label><select class="control" name="plan_type"><option value="30_day">30-day review</option><option value="7_day">7-day review</option><option value="repeat_assessment">Repeat assessment</option><option value="bp_control_check">BP control check</option></select></div></div><button class="btn btn-primary" type="submit">Create follow-up plan</button></form>`;
    main.prepend(followup);
  }

  function setBusy(button, busy, label = "Working…") {
    if (!button) return;
    if (busy) { button.dataset.originalText = button.textContent; button.textContent = label; button.disabled = true; }
    else { button.textContent = button.dataset.originalText || button.textContent; button.disabled = false; }
  }

  root.addEventListener("click", async (event) => {
    const authLink = event.target.closest("[data-auth]");
    if (authLink) { event.preventDefault(); renderAuth(authLink.dataset.auth); return; }
    const viewButton = event.target.closest("[data-view]");
    if (viewButton) { if (viewButton.dataset.view === "screening" || viewButton.dataset.view === "queue" || viewButton.dataset.view === "organisations") await loadView(viewButton.dataset.view); else await loadView(viewButton.dataset.view); document.getElementById("sidebar")?.classList.remove("open"); return; }
    const actionButton = event.target.closest("[data-action]");
    if (!actionButton) return;
    const action = actionButton.dataset.action;
    try {
      if (action === "logout") { clearAuth(); renderLanding(); }
      else if (action === "menu") document.getElementById("sidebar")?.classList.toggle("open");
      else if (action === "reload-view") await loadView(state.view);
      else if (action === "download-fhir") {
        const blob = new Blob([JSON.stringify(state.latestFhir || {}, null, 2)], { type: "application/fhir+json" });
        const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = "onecare-fhir-r4-bundle.json"; link.click(); URL.revokeObjectURL(url);
      }
      else if (action === "accept-referral" || action === "decline-referral" || action === "mark-missed" || action === "mark-unreachable") await handleQueueAction(action, actionButton.dataset.id);
      else if (action === "show-decline") document.getElementById(`decline-${actionButton.dataset.id}`)?.classList.toggle("hide");
      else if (action === "history") await handleHistory(actionButton.dataset.id);
      else if (action === "messages") await handleMessages(actionButton.dataset.id);
      else if (action === "ack-alert") { await api(`/red-flags/${actionButton.dataset.id}/acknowledge`, { method: "POST", body: JSON.stringify({ note: "Reviewed by authorised facility staff" }) }); toast("Alert acknowledgement recorded.", "success"); await loadView("alerts"); }
      else if (action === "ack-receipt" || action === "revoke-consent") await handlePatientAction(action);
    } catch (error) { toast(error.message, "error"); }
  });

  root.addEventListener("submit", async (event) => {
    const form = event.target;
    event.preventDefault();
    const button = form.querySelector('button[type="submit"]');
    setBusy(button, true);
    try {
      if (form.id === "login-form") {
        const data = Object.fromEntries(new FormData(form).entries());
        saveAuth(await api("/auth/login", { method: "POST", body: JSON.stringify(data) }));
      } else if (form.id === "register-form") {
        const data = Object.fromEntries(new FormData(form).entries());
        saveAuth(await api("/auth/register", { method: "POST", body: JSON.stringify(data) }));
      } else if (form.id === "otp-request-form") {
        const data = Object.fromEntries(new FormData(form).entries());
        const response = await api("/patients/otp/request", { method: "POST", body: JSON.stringify(data) });
        document.getElementById("otp-verify-form")?.classList.remove("hide");
        if (response.development_code) toast(`Development-only OTP: ${response.development_code}`, "success");
        else toast(response.message || "If registered, a code will be issued.");
      } else if (form.id === "otp-verify-form") {
        const data = Object.fromEntries(new FormData(form).entries());
        data.phone = document.getElementById("otp-phone").value;
        saveAuth(await api("/patients/otp/verify", { method: "POST", body: JSON.stringify(data) }));
      } else if (form.id === "screening-form") await handleScreening(form);
      else if (form.id === "organisation-form") await handleOrganisation(form);
      else if (form.id === "staff-form") await handleProvision(form);
      else if (form.id === "verify-form") await handleVerify(form);
      else if (form.id === "fhir-form") await handleFhir(form);
      else if (form.dataset.form === "book-appointment") {
        const data = Object.fromEntries(new FormData(form).entries());
        const start = new Date(data.slot_start); const end = new Date(data.slot_end);
        if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || end <= start) throw new Error("Appointment end must be after the start time.");
        await api(`/hospital/referrals/${form.dataset.id}/appointments`, { method: "POST", body: JSON.stringify({ slot_start: start.toISOString(), slot_end: end.toISOString() }) });
        toast("Appointment booked.", "success"); await refreshQueue();
      } else if (form.dataset.form === "attest-attendance") {
        const data = Object.fromEntries(new FormData(form).entries());
        await api(`/hospital/referrals/${form.dataset.id}/attendance`, { method: "POST", body: JSON.stringify(data) });
        toast("Attendance recorded.", "success"); await refreshQueue();
      } else if (form.dataset.form === "confirmatory-assessment") {
        const data = Object.fromEntries(new FormData(form).entries());
        data.systolic = data.systolic === undefined || data.systolic === "" ? null : Number(data.systolic);
        data.diastolic = data.diastolic === undefined || data.diastolic === "" ? null : Number(data.diastolic);
        await api(`/hospital/referrals/${form.dataset.id}/confirmatory-assessment`, { method: "POST", body: JSON.stringify(data) });
        toast("Confirmatory assessment recorded.", "success"); await refreshQueue();
      } else if (form.dataset.form === "assign-referral-owner") {
        const data = Object.fromEntries(new FormData(form).entries());
        if (!data.owner_user_id) throw new Error("Choose a staff member before assigning the referral.");
        await api(`/hospital/referrals/${form.dataset.id}/assign`, { method: "POST", body: JSON.stringify(data) });
        toast("Referral owner updated.", "success"); await refreshQueue();
      } else if (form.dataset.form === "redirect-referral") {
        const data = Object.fromEntries(new FormData(form).entries());
        if (!data.facility_id) throw new Error("Choose an alternative receiving hospital.");
        await api(`/hospital/referrals/${form.dataset.id}/redirect`, { method: "POST", body: JSON.stringify(data) });
        toast("Referral redirected to the new hospital.", "success"); await refreshQueue();
      } else if (form.dataset.form === "return-disposition") await handleDisposition(form);
      else if (form.dataset.form === "ack-alert") {
        const data = Object.fromEntries(new FormData(form).entries());
        await api(`/red-flags/${form.dataset.id}/acknowledge`, { method: "POST", body: JSON.stringify(data) });
        toast("Alert acknowledgement recorded.", "success"); await loadView("alerts");
      } else if (form.dataset.form === "send-message") {
        const data = Object.fromEntries(new FormData(form).entries());
        await api(`/referrals/${form.dataset.id}/messages`, { method: "POST", body: JSON.stringify(data) });
        toast("Message appended to the case history.", "success"); await handleMessages(form.dataset.id);
      } else if (form.id === "followup-form") await handleFollowUpSchedule(null, form.dataset.patient, form);
    } catch (error) { toast(error.message, "error"); }
    finally { setBusy(button, false); }
  });

  root.addEventListener("change", (event) => {
    if (event.target.name === "method" && event.target.form?.dataset.form === "confirmatory-assessment") {
      const readings = event.target.form.querySelector("[data-confirmatory-readings]");
      const disabled = event.target.value === "not_indicated";
      if (readings) {
        readings.querySelectorAll("input").forEach((input) => { input.required = !disabled; input.disabled = disabled; if (disabled) input.value = ""; });
      }
      const note = event.target.form.elements.note;
      if (note) note.required = disabled;
    }
    if (event.target.name === "role" && event.target.form?.id === "staff-form") {
      const orgSelect = event.target.form.elements.organisation_id;
      const desired = event.target.value === "clinician" ? "hospital" : event.target.value;
      [...orgSelect.options].forEach((option) => { if (option.dataset.type) option.hidden = option.dataset.type !== desired; });
      if (orgSelect.selectedOptions[0]?.dataset.type !== desired) orgSelect.value = "";
    }
  });

  async function boot() {
    if (!state.token) { renderLanding(); return; }
    try {
      state.user = await api("/auth/me");
      renderShell();
      await loadView("overview");
      if (state.view === "queue") await loadCliniciansIntoForms();
    } catch (error) {
      clearAuth(); renderAuth("login", "Your session expired. Please sign in again.");
    }
  }
  boot();
})();
