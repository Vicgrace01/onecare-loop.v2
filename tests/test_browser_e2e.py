from pathlib import Path
import shutil

import pytest
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]


def test_browser_ui_login_and_screening_flow_with_api_contract_mock():
    """Exercise real DOM events in Chromium; API behaviour is covered by HTTP tests."""
    html = '<div id="app"></div><div id="toast-region" class="toast-region"></div>'
    css = (ROOT / "app/web/assets/css/app.css").read_text(encoding="utf-8") + (ROOT / "app/web/assets/css/heritage.css").read_text(encoding="utf-8")
    motion_js = (ROOT / "app/web/assets/js/heritage-motion.js").read_text(encoding="utf-8")
    js = (ROOT / "app/web/assets/js/app.js").read_text(encoding="utf-8")

    mock_fetch = r"""
      window.__mockCalls = [];
      window.__activeUser = null;
      window.fetch = async (input, options = {}) => {
        const url = String(input);
        const method = (options.method || 'GET').toUpperCase();
        const body = options.body ? JSON.parse(options.body) : {};
        window.__mockCalls.push({url, method, body});
        let payload = {};
        if (url.endsWith('/auth/login') && method === 'POST') {
          const isPharmacy = body.email.startsWith('pharmacy@');
          window.__activeUser = {
            id: isPharmacy ? 'pharmacy-user' : 'admin-user', email: body.email,
            role: isPharmacy ? 'pharmacy' : 'admin',
            organisation_id: isPharmacy ? 'pharmacy-org' : null, patient_id: null
          };
          payload = {access_token: 'browser-ui-test-token', token_type: 'bearer', expires_in: 3600,
            user: window.__activeUser};
        } else if (url.endsWith('/auth/me')) {
          payload = window.__activeUser;
        } else if (url.endsWith('/metrics')) {
          payload = {total_patients: 2, total_referrals: 2, closed_loops: 1,
            closure_rate: 0.5, failure_breakdown: {}, financial_value_note: 'Not configured'};
        } else if (url.endsWith('/organisations')) {
          payload = {organisations: [
            {id: 'pharmacy-org', name: 'Test Pharmacy', type: 'pharmacy', lga: 'Enugu North'},
            {id: 'hospital-org', name: 'Test Hospital', type: 'hospital', lga: 'Enugu North'}
          ]};
        } else if (url.endsWith('/screenings') && method === 'POST') {
          payload = {patient_id: 'patient-test-id', screening_id: 'screening-test-id',
            result: 'positive', urgency: 'urgent', event: {event_hash: 'screening-hash'}};
        } else if (url.endsWith('/referrals') && method === 'POST') {
          payload = {referral_id: 'referral-test-id', urgency: 'urgent',
            eligibility: {decision: 'unknown', simulated: true}, notification: {status: 'simulated'}};
        }
        return new Response(JSON.stringify(payload), {
          status: 200, headers: {'Content-Type': 'application/json'}
        });
      };
    """

    with sync_playwright() as playwright:
        chromium_path = shutil.which("chromium") or shutil.which("chromium-browser")
        launch_options = {"headless": True, "args": ["--no-sandbox", "--disable-dev-shm-usage"]}
        if chromium_path:
            launch_options["executable_path"] = chromium_path
        browser = playwright.chromium.launch(**launch_options)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.set_content(f"{html}<style>{css}</style>")
        page.evaluate(mock_fetch)
        page.add_script_tag(content=motion_js)
        page.add_script_tag(content=js)
        page.locator('.oc-landing [data-auth="login"]').first.click()

        page.locator("#login-email").fill("admin@onecare.example")
        page.locator("#login-password").fill("not-used-by-contract-mock")
        page.locator("#login-form button[type=submit]").click()
        page.get_by_role("heading", name="Good to see you").wait_for()

        page.locator('[data-action="logout"]').click()
        page.locator('.oc-landing [data-auth="login"]').first.click()
        page.locator("#login-email").fill("pharmacy@onecare.example")
        page.locator("#login-password").fill("not-used-by-contract-mock")
        page.locator("#login-form button[type=submit]").click()
        page.get_by_role("heading", name="Welcome to your screening desk").wait_for()

        page.locator('.nav-btn[data-view="screening"]').click()
        page.locator("#patient-phone").fill("+2348098765432")
        page.locator("#patient-age").select_option("40-49")
        page.locator("#sbp").fill("168")
        page.locator("#dbp").fill("104")
        page.locator("#facility").select_option("hospital-org")
        page.locator('input[name="consent"]').check()
        page.locator("#screening-form button[type=submit]").click()
        page.get_by_text("Screening and referral recorded").wait_for()
        assert page.get_by_text("referral-test-id", exact=False).count() == 1

        calls = page.evaluate("window.__mockCalls")
        assert any(call["url"].endswith("/screenings") and call["method"] == "POST" for call in calls)
        assert any(call["url"].endswith("/referrals") and call["method"] == "POST" for call in calls)
        browser.close()


def test_confirmatory_assignment_and_late_redirect_forms_call_the_api():
    """New workflow screens must submit real authenticated API requests, not just render."""
    html = '<div id="app"></div><div id="toast-region" class="toast-region"></div>'
    css = (ROOT / "app/web/assets/css/app.css").read_text(encoding="utf-8") + (ROOT / "app/web/assets/css/heritage.css").read_text(encoding="utf-8")
    motion_js = (ROOT / "app/web/assets/js/heritage-motion.js").read_text(encoding="utf-8")
    js = (ROOT / "app/web/assets/js/app.js").read_text(encoding="utf-8")
    mock_fetch = r"""
      window.__calls = [];
      window.__user = null;
      window.__confirmed = false;
      window.__redirected = false;
      window.fetch = async (input, options = {}) => {
        const url = String(input);
        const method = (options.method || 'GET').toUpperCase();
        const body = options.body ? JSON.parse(options.body) : {};
        window.__calls.push({url, method, body});
        let payload = {};
        if (url.endsWith('/auth/login') && method === 'POST') {
          const role = body.email.startsWith('clinician@') ? 'clinician' : 'hospital';
          window.__user = {id: role + '-1', email: body.email, role,
            organisation_id: 'hospital-org', patient_id: null};
          payload = {access_token: 'ui-regression-token', token_type: 'bearer', expires_in: 3600, user: window.__user};
        } else if (url.endsWith('/auth/me')) {
          payload = window.__user;
        } else if (url.endsWith('/hospital/queue')) {
          if (window.__user.role === 'clinician') {
            payload = {queue: [{id: 'ref-confirm', patient_id: 'patient-12345678', facility_id: 'hospital-org',
              urgency: 'urgent', status: 'CLINICAL_ENCOUNTER_COMPLETED', sla_deadline: '2026-11-25T12:00:00Z',
              owner_user_id: 'clinician-1', owner_role: 'clinician', unassigned: false,
              sla_breached: false, escalated_at: null, details_redacted: false, systolic: 168, diastolic: 104,
              confirmatory_test_recorded: window.__confirmed}]};
          } else {
            const queue = [{id: 'ref-assign', patient_id: 'patient-assign', facility_id: 'hospital-org',
              urgency: 'routine', status: 'REFERRAL_CREATED', sla_deadline: '2026-11-25T12:00:00Z',
              owner_user_id: null, owner_role: null, unassigned: true, sla_breached: false, escalated_at: null,
              details_redacted: false, systolic: 150, diastolic: 95, confirmatory_test_recorded: false}];
            if (!window.__redirected) queue.push({id: 'ref-redirect', patient_id: 'patient-redirect', facility_id: 'hospital-org',
              urgency: 'urgent', status: 'REFERRAL_DECLINED', sla_deadline: '2026-11-25T12:00:00Z',
              owner_user_id: 'hospital-1', owner_role: 'hospital', unassigned: false, sla_breached: false,
              escalated_at: null, details_redacted: false, systolic: 165, diastolic: 101, confirmatory_test_recorded: false});
            payload = {queue};
          }
        } else if (url.endsWith('/organisations')) {
          payload = {organisations: [
            {id: 'hospital-org', name: 'Hospital A', type: 'hospital'},
            {id: 'alternate-org', name: 'Hospital B', type: 'hospital'}
          ]};
        } else if (url.endsWith('/hospital/attention')) {
          payload = {overdue: [], unassigned: []};
        } else if (url.endsWith('/hospital-org/staff')) {
          payload = {staff: [{id: 'clinician-1', email: 'clinician@onecare.test', role: 'clinician'}]};
        } else if (url.endsWith('/confirmatory-assessment') && method === 'POST') {
          window.__confirmed = true;
          payload = {ok: true};
        } else if (url.endsWith('/ref-assign/assign') && method === 'POST') {
          payload = {ok: true};
        } else if (url.endsWith('/ref-redirect/redirect') && method === 'POST') {
          window.__redirected = true;
          payload = {ok: true};
        }
        return new Response(JSON.stringify(payload), {status: 200, headers: {'Content-Type': 'application/json'}});
      };
    """

    with sync_playwright() as playwright:
        chromium_path = shutil.which("chromium") or shutil.which("chromium-browser")
        launch_options = {"headless": True, "args": ["--no-sandbox", "--disable-dev-shm-usage"]}
        if chromium_path:
            launch_options["executable_path"] = chromium_path
        browser = playwright.chromium.launch(**launch_options)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.set_content(f"{html}<style>{css}</style>")
        page.evaluate(mock_fetch)
        page.add_script_tag(content=motion_js)
        page.add_script_tag(content=js)
        page.locator('.oc-landing [data-auth="login"]').first.click()

        # Assigned clinician documents confirmatory assessment before disposition appears.
        page.locator("#login-email").fill("clinician@onecare.test")
        page.locator("#login-password").fill("test-password-not-used")
        page.locator("#login-form button[type=submit]").click()
        page.get_by_role("heading", name="Clinical review worklist").wait_for()
        page.locator('.nav-btn[data-view="queue"]').click()
        form = page.locator('form[data-form="confirmatory-assessment"]')
        form.locator('select[name="method"]').select_option("repeat_office")
        form.locator('input[name="systolic"]').fill("148")
        form.locator('input[name="diastolic"]').fill("94")
        form.locator('textarea[name="note"]').fill("Repeat office measurement recorded by assigned clinician.")
        form.locator('button[type=submit]').click()
        page.locator('form[data-form="return-disposition"]').wait_for()
        confirm_call = page.evaluate("window.__calls.find(x => x.url.endsWith('/confirmatory-assessment'))")
        assert confirm_call["method"] == "POST"
        assert confirm_call["body"]["systolic"] == 148
        assert confirm_call["body"]["diastolic"] == 94

        # Hospital operator can reassign an owner and redirect a declined referral.
        page.locator('[data-action="logout"]').click()
        page.locator('.oc-landing [data-auth="login"]').first.click()
        page.locator("#login-email").fill("hospital@onecare.test")
        page.locator("#login-password").fill("test-password-not-used")
        page.locator("#login-form button[type=submit]").click()
        page.get_by_role("heading", name="Referral coordination").wait_for()
        page.locator('.nav-btn[data-view="queue"]').click()
        assign_form = page.locator('form[data-form="assign-referral-owner"][data-id="ref-assign"]')
        assign_form.locator('select[name="owner_user_id"]').select_option("clinician-1")
        assign_form.locator('button[type=submit]').click()
        page.locator('form[data-form="redirect-referral"]').wait_for()
        redirect_form = page.locator('form[data-form="redirect-referral"]')
        redirect_form.locator('select[name="facility_id"]').select_option("alternate-org")
        redirect_form.locator('button[type=submit]').click()

        calls = page.evaluate("window.__calls")
        assign_call = next(call for call in calls if call["url"].endswith("/ref-assign/assign"))
        redirect_call = next(call for call in calls if call["url"].endswith("/ref-redirect/redirect"))
        assert assign_call["body"]["owner_user_id"] == "clinician-1"
        assert redirect_call["body"]["facility_id"] == "alternate-org"
        browser.close()


def test_original_visual_heritage_landing_and_six_stage_care_ring_render():
    html = '<div id="app"></div><div id="toast-region" class="toast-region"></div>'
    css = (ROOT / "app/web/assets/css/app.css").read_text(encoding="utf-8") + (ROOT / "app/web/assets/css/heritage.css").read_text(encoding="utf-8")
    motion_js = (ROOT / "app/web/assets/js/heritage-motion.js").read_text(encoding="utf-8")
    js = (ROOT / "app/web/assets/js/app.js").read_text(encoding="utf-8")
    with sync_playwright() as playwright:
        chromium_path = shutil.which("chromium") or shutil.which("chromium-browser")
        launch_options = {"headless": True, "args": ["--no-sandbox", "--disable-dev-shm-usage"]}
        if chromium_path:
            launch_options["executable_path"] = chromium_path
        browser = playwright.chromium.launch(**launch_options)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.set_content(f"{html}<style>{css}</style>")
        page.add_script_tag(content=motion_js)
        page.add_script_tag(content=js)
        page.get_by_role("heading", name="Every patient deserves a closed loop.").wait_for()
        demo_link = page.locator('.oc-landing a[href="/demo"]')
        assert demo_link.count() == 1
        assert "automatic demo" in demo_link.inner_text().lower()
        assert page.locator(".oc-loop-art .arc").count() == 6
        assert page.locator(".oc-stage").count() == 6
        assert page.locator("canvas[data-oc-particles]").count() == 1
        page.mouse.move(520, 430)
        assert page.locator(".oc-cursor-dot").count() == 1
        assert page.locator(".oc-cursor-ring").count() == 1
        page.locator('.oc-landing [data-auth="login"]').first.click()
        page.get_by_role("heading", name="Welcome back").wait_for()
        browser.close()


def test_motion_respects_reduced_motion_and_mobile_layout():
    """Do not force pointer effects or animated motion on mobile/reduced-motion users."""
    html = '<div id="app"></div><div id="toast-region" class="toast-region"></div>'
    css = (ROOT / "app/web/assets/css/app.css").read_text(encoding="utf-8") + (ROOT / "app/web/assets/css/heritage.css").read_text(encoding="utf-8")
    motion_js = (ROOT / "app/web/assets/js/heritage-motion.js").read_text(encoding="utf-8")
    js = (ROOT / "app/web/assets/js/app.js").read_text(encoding="utf-8")
    with sync_playwright() as playwright:
        chromium_path = shutil.which("chromium") or shutil.which("chromium-browser")
        launch_options = {"headless": True, "args": ["--no-sandbox", "--disable-dev-shm-usage"]}
        if chromium_path:
            launch_options["executable_path"] = chromium_path
        browser = playwright.chromium.launch(**launch_options)
        page = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        page.emulate_media(reduced_motion="reduce")
        page.set_content(html)
        page.add_style_tag(content=css)
        page.add_script_tag(content=motion_js)
        page.add_script_tag(content=js)
        page.get_by_role("heading", name="Every patient deserves a closed loop.").wait_for()
        page.wait_for_timeout(100)
        assert page.locator(".oc-loop-art .arc").count() == 6
        assert page.locator(".oc-cursor-dot").count() == 0
        assert page.locator(".oc-cursor-ring").count() == 0
        assert page.locator("canvas[data-oc-particles]").evaluate("el => getComputedStyle(el).display") == "none"
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
        browser.close()
