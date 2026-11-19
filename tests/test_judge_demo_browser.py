from pathlib import Path
import shutil

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def test_judge_demo_runs_and_replays_eight_backend_events_without_fabricated_values():
    html = (ROOT / "app/web/demo.html").read_text(encoding="utf-8")
    css = (ROOT / "app/web/assets/css/demo.css").read_text(encoding="utf-8")
    js = (ROOT / "app/web/assets/js/demo.js").read_text(encoding="utf-8")
    motion = (ROOT / "app/web/assets/js/heritage-motion.js").read_text(encoding="utf-8")
    fixture = {
        "enabled": True, "synthetic_only": True, "credentials_visible": True,
        "notice": "Synthetic accounts only; messages are simulated.",
        "roles": [
            {"label": "Community pharmacy", "role": "pharmacy", "email": "demo.pharmacy@onecareloop.com", "password": "Demo-Pharmacy-Pass-2026!"},
            {"label": "Hospital coordinator", "role": "hospital", "email": "demo.hospital@onecareloop.com", "password": "Demo-Hospital-Pass-2026!"},
            {"label": "Assigned clinician", "role": "clinician", "email": "demo.clinician@onecareloop.com", "password": "Demo-Clinician-Pass-2026!"},
            {"label": "HMO reviewer", "role": "hmo", "email": "demo.hmo@onecareloop.com", "password": "Demo-HMO-Reviewer-Pass-2026!"},
        ],
    }
    event_types = [
        "SCREEN_POSITIVE", "REFERRAL_CREATED", "FACILITY_ACCEPTED", "APPOINTMENT_BOOKED",
        "CLINICAL_ENCOUNTER_COMPLETED", "CONFIRMATORY_TEST_RECORDED",
        "CLINICAL_DISPOSITION_RETURNED", "FOLLOWUP_DUE",
    ]
    payload = {
        "run_id": "demo-run-1", "synthetic_only": True, "patient_reference": "DEMO-12345678",
        "patient_id": "12345678-1234-1234-1234-123456789012", "referral_id": "ref-1",
        "facility": "OneCare Demo Hospital", "screening": {"systolic": 168, "diastolic": 104, "urgency": "urgent"},
        "appointment": {"start": "2026-11-20T09:00:00+00:00", "end": "2026-11-20T09:30:00+00:00"},
        "confirmatory": {"method": "repeat_office", "systolic": 158, "diastolic": 98},
        "disposition": {"outcome": "clinical_review_completed"}, "follow_up_due": "2026-12-20T09:00:00+00:00",
        "notification_count": 3, "notification_provider_called": False,
        "chain": {"verified": True, "event_count": 8, "signed_count": 8},
        "events": [
            {"seq": i + 1, "event_type": event_type, "actor_role": role,
             "occurred_at": f"2026-11-19T10:{i:02d}:00+00:00", "event_hash": f"hash-{i+1:02d}-abcdefghijklmnop"}
            for i, (event_type, role) in enumerate(zip(event_types, ["pharmacy", "pharmacy", "hospital", "hospital", "hospital", "clinician", "clinician", "clinician"]))
        ],
    }
    with sync_playwright() as playwright:
        executable = shutil.which("chromium") or shutil.which("chromium-browser")
        options = {"headless": True, "args": ["--no-sandbox", "--disable-dev-shm-usage"]}
        if executable:
            options["executable_path"] = executable
        browser = playwright.chromium.launch(**options)
        page = browser.new_page(viewport={"width": 1440, "height": 1100}, reduced_motion="reduce")
        page.set_content(html)
        page.add_style_tag(content=css)
        page.evaluate("""(fixture) => {
          window.__demoCalls = [];
          window.fetch = async (url, options = {}) => {
            window.__demoCalls.push({url: String(url), method: options.method || 'GET'});
            const payload = String(url).endsWith('/info') ? fixture.info : fixture.run;
            return new Response(JSON.stringify(payload), {status: 200, headers: {'Content-Type':'application/json'}});
          };
        }""", {"info": fixture, "run": payload})
        page.add_script_tag(content=motion)
        page.add_script_tag(content=js)
        page.get_by_role("button", name="Start full demo").wait_for(state="visible")
        page.get_by_role("button", name="Start full demo").click()
        page.get_by_text("LOOP CLOSED · VERIFIED").wait_for(timeout=10000)
        assert page.locator(".jd-stage.done").count() == 6
        assert page.locator(".jd-event").count() == 8
        assert page.locator(".jd-credential").count() == 4
        assert page.locator("#jd-confirmatory").inner_text() == "158/98 mmHg"
        assert page.locator("#jd-chain-state").inner_text() == "VERIFIED"
        assert "no SMS" in page.locator("#jd-notice").inner_text()
        assert "₦6,000" not in page.content()
        calls_before_replay = page.evaluate("window.__demoCalls.length")
        page.get_by_role("button", name="Replay animation").click()
        page.get_by_text("LOOP CLOSED · VERIFIED").wait_for(timeout=10000)
        assert page.evaluate("window.__demoCalls.length") == calls_before_replay
        assert page.locator(".jd-event").count() == 8
        browser.close()
