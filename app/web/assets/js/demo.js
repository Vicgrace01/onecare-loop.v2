(() => {
  "use strict";
  const API = "/api/v1/demo";
  const $ = (id) => document.getElementById(id);
  const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
  const canonical = [
    "SCREEN_POSITIVE", "REFERRAL_CREATED", "FACILITY_ACCEPTED",
    "APPOINTMENT_BOOKED", "CLINICAL_ENCOUNTER_COMPLETED", "CLINICAL_DISPOSITION_RETURNED",
  ];
  const labels = {
    SCREEN_POSITIVE: "Screening recorded",
    REFERRAL_CREATED: "Referral created",
    FACILITY_ACCEPTED: "Receiving hospital accepted",
    APPOINTMENT_BOOKED: "Appointment booked",
    CLINICAL_ENCOUNTER_COMPLETED: "Attendance attested",
    CONFIRMATORY_TEST_RECORDED: "Confirmatory assessment recorded",
    CLINICAL_DISPOSITION_RETURNED: "Clinician disposition returned",
    FOLLOWUP_DUE: "Follow-up plan scheduled",
  };
  const captions = {
    SCREEN_POSITIVE: "A community pharmacy records a positive blood-pressure screen with consent.",
    REFERRAL_CREATED: "A referral is created with an urgency-based deadline and explicit unknown eligibility.",
    FACILITY_ACCEPTED: "The receiving hospital accepts the referral and becomes the accountable owner.",
    APPOINTMENT_BOOKED: "An appointment is booked and a simulated patient notification is recorded.",
    CLINICAL_ENCOUNTER_COMPLETED: "The assigned clinician records attendance. The handoff is attributable.",
    CONFIRMATORY_TEST_RECORDED: "A clinician records a repeat blood-pressure assessment before returning an outcome.",
    CLINICAL_DISPOSITION_RETURNED: "The clinician returns a documented disposition and next step.",
    FOLLOWUP_DUE: "A follow-up plan is scheduled, so the journey does not end at the first visit.",
  };
  let lastRun = null;
  let animationSequence = 0;
  const sleep = (ms) => new Promise((resolve) => window.setTimeout(resolve, reduceMotion ? 0 : ms));
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

  async function request(path, options = {}) {
    const response = await fetch(`${API}${path}`, {
      ...options,
      headers: { ...(options.body ? {"Content-Type":"application/json"} : {}), ...(options.headers || {}) },
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = body.detail || body.message || `Request failed (${response.status})`;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return body;
  }

  function status(label, state = "ready") {
    const el = $("jd-status"); el.textContent = label; el.dataset.state = state;
  }
  function caption(message) {
    const el = $("jd-caption"); el.textContent = message; el.classList.add("show");
    window.clearTimeout(caption.timer);
    caption.timer = window.setTimeout(() => el.classList.remove("show"), 3000);
  }
  function setPanel(name) {
    document.querySelectorAll(".jd-panel").forEach((panel) => panel.classList.toggle("is-active", panel.id === `jd-${name}`));
  }
  function resetView() {
    document.querySelectorAll(".jd-stage").forEach((node) => node.classList.remove("done", "active"));
    document.querySelectorAll(".jd-stage-line").forEach((line) => line.classList.remove("done"));
    document.querySelectorAll(".jd-operation").forEach((node) => { node.classList.remove("done"); node.querySelector(".jd-operation-state").textContent = "PENDING"; });
    ["jd-systolic","jd-diastolic","jd-screen-ref","jd-facility","jd-owner","jd-appointment","jd-patient-ref","jd-patient-state","jd-confirmatory","jd-disposition","jd-followup","jd-events-count","jd-notifications-count","jd-run-reference"].forEach((id) => $(id).textContent = "—");
    $("jd-screen-result").textContent = "Waiting for screening"; $("jd-screen-result").className = "jd-inline-state";
    $("jd-confirmatory-method").textContent = "NOT RECORDED"; $("jd-confirmatory-method").classList.remove("done");
    $("jd-chain-state").textContent = "NOT RUN"; $("jd-chain-state").className = "jd-chain-pending";
    $("jd-chain-detail").textContent = "Cryptographic verification will run after closure";
    $("jd-eligibility").textContent = "UNKNOWN";
    $("jd-timeline").innerHTML = '<div class="jd-timeline-empty">Replaying the recorded event history…</div>';
    $("jd-message-list").innerHTML = '<div class="jd-message-placeholder">Patient-facing updates will appear here as the case progresses.</div>';
    $("jd-progress-label").textContent = "Awaiting first event";
    setPanel("");
  }
  function doneStage(eventType) {
    const index = canonical.indexOf(eventType);
    if (index < 0) return;
    const stage = document.querySelector(`.jd-stage[data-stage="${eventType}"]`);
    stage?.classList.remove("active"); stage?.classList.add("done");
    const lines = document.querySelectorAll(".jd-stage-line");
    if (lines[index]) lines[index].classList.add("done");
    const nextType = canonical[index + 1];
    if (nextType) document.querySelector(`.jd-stage[data-stage="${nextType}"]`)?.classList.add("active");
    $("jd-progress-label").textContent = `${Math.min(index + 1, 6)} of 6 core journey steps recorded`;
  }
  function appendMessage(text, meta) {
    const list = $("jd-message-list");
    list.querySelector(".jd-message-placeholder")?.remove();
    const node = document.createElement("div"); node.className = "jd-message";
    node.textContent = text;
    const small = document.createElement("span"); small.className = "jd-message-meta"; small.textContent = meta;
    node.append(small); list.append(node); list.scrollTop = list.scrollHeight;
  }
  function appendTimeline(event, index) {
    const timeline = $("jd-timeline"); timeline.querySelector(".jd-timeline-empty")?.remove();
    const item = document.createElement("div"); item.className = "jd-event"; item.style.animationDelay = `${index * 35}ms`;
    const title = document.createElement("strong"); title.textContent = labels[event.event_type] || event.event_type;
    const actor = document.createElement("small"); actor.textContent = `${event.actor_role} · ${new Date(event.occurred_at).toLocaleString()}`;
    const hash = document.createElement("code"); hash.textContent = `${String(event.event_hash || "").slice(0, 12)}…`;
    item.append(title, actor, hash); timeline.append(item); timeline.scrollLeft = timeline.scrollWidth;
  }
  function setOperation(name) {
    const node = document.querySelector(`.jd-operation[data-op="${name}"]`);
    if (!node) return;
    node.classList.add("done"); node.querySelector(".jd-operation-state").textContent = "RECORDED";
  }
  async function animateRun(data) {
    const sequence = ++animationSequence;
    resetView();
    const screen = data.screening || {};
    $("jd-patient-ref").textContent = data.patient_reference || "Synthetic patient";
    $("jd-patient-state").textContent = "Synthetic case created";
    $("jd-facility").textContent = data.facility || "Receiving hospital";
    $("jd-screen-ref").textContent = (data.patient_reference || "DEMO").slice(0, 15);
    $("jd-eligibility").textContent = "UNKNOWN";
    const events = data.events || [];
    const total = events.length;
    for (let index = 0; index < total; index += 1) {
      if (sequence !== animationSequence) return;
      const event = events[index];
      const type = event.event_type;
      appendTimeline(event, index);
      $("jd-events-count").textContent = String(index + 1);
      caption(captions[type] || labels[type] || type);
      if (type === "SCREEN_POSITIVE") {
        setPanel("pharmacy"); $("jd-systolic").textContent = String(screen.systolic ?? "—");
        $("jd-diastolic").textContent = String(screen.diastolic ?? "—");
        $("jd-screen-result").textContent = `POSITIVE · ${screen.urgency || "urgent"} pathway`;
        $("jd-screen-result").classList.add("is-positive"); doneStage(type);
        appendMessage("Your screening result needs clinical assessment. A referral has been started.", "SIMULATED PATIENT UPDATE");
        $("jd-patient-state").textContent = "Screened · referral being arranged";
      } else if (type === "REFERRAL_CREATED") {
        setPanel("patient"); doneStage(type);
        appendMessage("A receiving hospital has been selected. Eligibility has not been verified against a live payer system.", "SIMULATED PATIENT UPDATE");
        $("jd-patient-state").textContent = "Referral created";
      } else if (type === "FACILITY_ACCEPTED") {
        setPanel("hospital"); doneStage(type); setOperation("accepted");
        $("jd-owner").textContent = "Hospital coordinator owns the referral";
        $("jd-patient-state").textContent = "Hospital accepted the referral";
      } else if (type === "APPOINTMENT_BOOKED") {
        setPanel("hospital"); doneStage(type); setOperation("booked");
        $("jd-appointment").textContent = data.appointment?.start ? new Date(data.appointment.start).toLocaleString() : "Appointment recorded";
        appendMessage(`Your appointment has been booked for ${$("jd-appointment").textContent}.`, "SIMULATED PATIENT UPDATE");
        $("jd-patient-state").textContent = "Appointment booked";
      } else if (type === "CLINICAL_ENCOUNTER_COMPLETED") {
        setPanel("hospital"); doneStage(type); setOperation("attended");
        appendMessage("Attendance was recorded by the assigned clinician.", "SIMULATED PATIENT UPDATE");
        $("jd-patient-state").textContent = "Attendance recorded";
      } else if (type === "CONFIRMATORY_TEST_RECORDED") {
        setPanel("clinician");
        $("jd-confirmatory").textContent = `${data.confirmatory?.systolic ?? "—"}/${data.confirmatory?.diastolic ?? "—"} mmHg`;
        $("jd-confirmatory-method").textContent = "REPEAT OFFICE"; $("jd-confirmatory-method").classList.add("done");
      } else if (type === "CLINICAL_DISPOSITION_RETURNED") {
        setPanel("clinician"); doneStage(type);
        $("jd-disposition").textContent = data.disposition?.outcome?.replaceAll("_", " ") || "Clinical review completed";
        $("jd-followup").textContent = "30-day BP reassessment";
        appendMessage("Your clinician has recorded the assessment and the next planned step.", "SIMULATED PATIENT UPDATE");
        $("jd-patient-state").textContent = "Clinical outcome recorded";
      } else if (type === "FOLLOWUP_DUE") {
        setPanel("clinician"); $("jd-followup").textContent = data.follow_up_due ? new Date(data.follow_up_due).toLocaleDateString() : "30-day follow-up";
        appendMessage(`A follow-up plan is scheduled for ${$("jd-followup").textContent}.`, "SIMULATED PATIENT UPDATE");
        $("jd-patient-state").textContent = "Follow-up plan scheduled";
      }
      await sleep(620);
    }
    if (sequence !== animationSequence) return;
    $("jd-events-count").textContent = String(data.chain?.event_count ?? total);
    $("jd-notifications-count").textContent = String(data.notification_count ?? 0);
    $("jd-chain-state").textContent = data.chain?.verified ? "VERIFIED" : "NOT VERIFIED";
    $("jd-chain-state").className = data.chain?.verified ? "jd-chain-verified" : "jd-chain-failed";
    $("jd-chain-detail").textContent = data.chain?.verified ? `${data.chain?.signed_count ?? total} signatures and event hashes verified` : "The recorded chain did not pass verification";
    $("jd-run-reference").textContent = `${data.patient_reference || "DEMO"} · ${data.run_id || "RUN"}`;
    $("jd-notice").innerHTML = `<strong>Prototype boundary:</strong> This run uses synthetic patient, staff and clinical data. Notification records are simulated; no SMS or WhatsApp message is sent. Eligibility remains unknown because no live NHIA/DHIN lookup is connected. The demo does not claim real patient outcomes, treatment adherence, clinical benefit or financial savings.`;
    $("jd-progress-label").textContent = data.chain?.verified ? "All 6 core steps recorded · chain verified" : "Journey recorded · verification failed";
    setPanel(""); caption(data.chain?.verified ? "The synthetic journey is complete. Its signed event chain has verified successfully." : "The journey ended, but the chain did not verify.");
    status(data.chain?.verified ? "LOOP CLOSED · VERIFIED" : "CHAIN VERIFICATION FAILED", data.chain?.verified ? "done" : "ready");
    $("jd-start").disabled = false; $("jd-start").textContent = "＋ Run another synthetic case";
    $("jd-replay").disabled = false;
  }
  async function start() {
    if ($("jd-start").disabled) return;
    $("jd-start").disabled = true; $("jd-replay").disabled = true;
    $("jd-start").textContent = "Creating synthetic case…"; status("CREATING REAL TEST RECORDS", "running");
    try {
      const data = await request("/run", { method: "POST", body: "{}" });
      lastRun = data;
      await animateRun(data);
    } catch (error) {
      status("DEMO COULD NOT RUN", "ready"); caption(error.message);
      $("jd-notice").textContent = `The demo did not complete: ${error.message}. Check that DEMO_MODE_ENABLED is true and all four synthetic reviewer accounts are provisioned.`;
      $("jd-start").disabled = false; $("jd-start").textContent = "↻ Try demo again";
      $("jd-replay").disabled = !lastRun;
    }
  }
  async function replay() {
    if (!lastRun) return;
    $("jd-replay").disabled = true; $("jd-start").disabled = true;
    status("REPLAYING RECORDED RUN", "running");
    await animateRun(lastRun);
  }
  async function loadInfo() {
    try {
      const data = await request("/info");
      const notice = $("jd-notice");
      if (!data.enabled) {
        notice.textContent = data.notice || "The demonstration is currently disabled on this deployment.";
        $("jd-credential-list").innerHTML = '<div class="jd-credential-note">Reviewer accounts are not enabled here. Set DEMO_MODE_ENABLED=true and configure four separate synthetic staff accounts before sharing this URL with judges.</div>';
        status("DEMO NOT ENABLED", "ready"); return;
      }
      $("jd-start").disabled = false;
      if (data.credentials_visible) {
        $("jd-credential-list").innerHTML = (data.roles || []).map((item) => `<div class="jd-credential"><strong>${esc(item.label)} · ${esc(item.role)}</strong><code>${esc(item.email)}</code><code>${esc(item.password)}</code><small>Open the homepage → Sign in securely → use these synthetic credentials.</small></div>`).join("");
      } else {
        $("jd-credential-list").innerHTML = `<div class="jd-credential-note">Reviewer accounts are enabled but passwords are hidden on this page. ${esc(data.notice || "") } Set DEMO_SHOW_CREDENTIALS=true only in the isolated synthetic challenge deployment to display them here. The passwords are not included in frontend code.</div>`;
      }
      notice.innerHTML = `<strong>Synthetic environment:</strong> ${esc(data.notice || "No live messaging, payer or emergency service is contacted.")} Credentials shown here, when enabled, grant access only to the seeded synthetic workspaces. Do not reuse these passwords outside the challenge deployment.`;
    } catch (error) {
      $("jd-notice").textContent = `Could not load demo configuration: ${error.message}`;
      $("jd-credential-list").innerHTML = '<div class="jd-credential-note">The API did not return reviewer configuration. The automatic demo remains disabled until this is corrected.</div>';
      status("CONFIGURATION UNAVAILABLE", "ready");
    }
  }
  $("jd-start").addEventListener("click", start);
  $("jd-replay").addEventListener("click", replay);
  loadInfo();
})();
