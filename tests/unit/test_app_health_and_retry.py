"""The application health check, the retry it gates, and defects only after a rerun.

30 Oct 2026, the nightly run on main: 17 of 17 tests failed - the forms, lists and
fields the tests looked for never appeared, on
four pages that were SERVED (no HTTP error, no timeout) without their content.
The next night all 17 passed with no change. Nothing told "the application was
not itself" from "17 tests are broken": more than ten failures switched the
retry off, and the triage raised ten defects from the first run alone, plus
one alert for the other seven.

Now (agent4_runner.yml): after a run with failures Agent 4 checks the
application directly (core/app_probe.py, scripts/app_probe.py), waiting for it
to come back. Not up - every failure is an outage (not judged, never a defect)
and the alert says what was served instead. Up - every failed test is run
again, and only a test that fails again can become a defect
(defects.only_after_retry); a failure that was not run again is listed in one
health alert. Generic names only.
"""
import http.server
import json
import os
import socketserver
import threading
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape

import pytest
import yaml

from core import app_probe
from core import junit_marks as jm
from scripts import finalise_junit as fj
from scripts import triage_failures as tf
from tests.unit.test_defects_after_rerun import _alerts, _bugs, _run, world  # noqa: F401

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = {"pages": {
    "home": {"url": "/", "elements": {"logo": "#logo", "box": "input#box"}},
    "login": {"url": "/login", "elements": {"email": "#email"}},
    "item": {"url": "/item/{id}", "elements": {"name": "h1"}},
}}


# ── which checks: from config, against the inventory ────────────────────────

def test_the_configured_pages_and_elements_are_resolved_from_the_inventory():
    plan = app_probe.checks({"health_check": [{"page": "home", "elements": ["logo", "box"]},
                                              {"page": "login", "elements": ["email"]}]},
                            INVENTORY)
    assert [(c.page, c.url, c.elements) for c in plan] == [
        ("home", "/", {"logo": "#logo", "box": "input#box"}),
        ("login", "/login", {"email": "#email"})]


def test_nothing_configured_checks_the_base_url_only():
    (only,) = app_probe.checks({}, INVENTORY)
    assert (only.url, only.elements) == ("/", {})


@pytest.mark.parametrize("entry, says", [
    ({"page": "nowhere", "elements": []}, "not in the app inventory"),
    ({"page": "home", "elements": ["logo", "ghost"]}, "no element(s) ghost"),
    ({"page": "item", "elements": ["name"]}, "needs a value"),
    ({"elements": ["logo"]}, "has no `page`"),
])
def test_a_wrong_setting_is_refused_never_checked_less(entry, says):
    with pytest.raises(ValueError, match=r"(?s).*" + says.replace("(", r"\(").replace(")", r"\)")):
        app_probe.checks({"health_check": [entry]}, INVENTORY)


def test_the_shipped_setting_matches_the_shipped_inventory():
    plan = app_probe.checks()
    assert plan and all(c.elements for c in plan), \
        "this application's check looks for content, not only a status"
    app = yaml.safe_load((ROOT / "config" / "config.yaml").read_text())["app_under_test"]
    inv = json.loads((ROOT / app["inventory_file"]).read_text())
    for c in plan:
        page = inv["pages"][c.page]
        for key in c.elements:
            assert key not in (page.get("conditional") or []), f"{c.page}.{key} is conditional"


# ── the wait loop ───────────────────────────────────────────────────────────

class _Clock:
    def __init__(self):
        self.t = 0.0
        self.sleeps = []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


def test_a_short_outage_is_waited_out(monkeypatch):
    answers = iter([{"available": False, "problem": "home was served without logo",
                     "checked": [], "served": {}},
                    {"available": True, "problem": None, "checked": ["home: logo"],
                     "served": None}])
    monkeypatch.setattr(app_probe, "probe_once", lambda *a: next(answers))
    clock = _Clock()
    out = app_probe.probe(lambda: object(), "https://a.example", [], 1000, 600, 60,
                          sleep=clock.sleep, clock=clock)
    assert out["available"] and out["attempts"] == 2 and clock.sleeps == [60]
    assert "after 2 checks" in app_probe.summary(out)


def test_an_application_that_stays_down_is_reported_after_the_wait(monkeypatch):
    monkeypatch.setattr(app_probe, "probe_once", lambda *a: {
        "available": False, "problem": "login was served without email", "checked": [],
        "served": {"url": "https://a.example/login", "title": "Maintenance",
                   "text": "Back soon"}})
    clock = _Clock()
    out = app_probe.probe(lambda: object(), "https://a.example", [], 1000, 300, 60,
                          sleep=clock.sleep, clock=clock)
    assert not out["available"] and out["attempts"] == 6 and sum(clock.sleeps) == 300, \
        "a check every 60 s, the last one at the end of the wait"
    text = app_probe.summary(out)
    assert "NOT up after 6 check(s)" in text and "'Maintenance'" in text and "Back soon" in text


def test_a_page_that_cannot_open_is_a_finding_not_a_crash():
    def boom():
        raise RuntimeError("browser gone")
    out = app_probe.probe(boom, "https://a.example", [], 1000, 0, 60)
    assert out["available"] is False and "could not open a page" in out["problem"]


# ── in a real browser ───────────────────────────────────────────────────────

class _Site(http.server.BaseHTTPRequestHandler):
    mode = "up"

    def log_message(self, *a):
        pass

    def do_GET(self):
        if type(self).mode == "error":
            self.send_response(503)
            self.end_headers()
            return
        if type(self).mode == "up":
            body = ('<img id="logo" alt="logo"><input id="box">' if self.path == "/"
                    else '<input id="email">')
        else:                                    # served, but not the application
            body = "<title>Maintenance</title><p>We will be back soon.</p>"
        data = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture(scope="module")
def site():
    class S(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True
    srv = S(("127.0.0.1", 0), _Site)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


@pytest.fixture(scope="module")
def browser():
    sync = pytest.importorskip("playwright.sync_api")
    pw = sync.sync_playwright().start()
    try:
        exe = os.environ.get("CHROMIUM_EXECUTABLE")
        b = pw.chromium.launch(**({"executable_path": exe} if exe else {}))
    except Exception as exc:                                       # noqa: BLE001
        pw.stop()
        pytest.skip(f"no browser to launch here: {type(exc).__name__}")
    yield b
    b.close()
    pw.stop()


def _browser_probe(browser, site, monkeypatch, mode):
    from pages.base_page import BasePage
    monkeypatch.setattr(BasePage, "_navigation_retry_delays_ms", classmethod(lambda c: ()))
    _Site.mode = mode
    plan = app_probe.checks({"health_check": [{"page": "home", "elements": ["logo", "box"]},
                                              {"page": "login", "elements": ["email"]}]},
                            INVENTORY)
    context = browser.new_context()
    page = context.new_page()
    page.set_default_timeout(3000)
    try:
        return app_probe.probe_once(page, site, plan, 1500)
    finally:
        context.close()


def test_in_a_browser_an_application_serving_itself_is_up(browser, site, monkeypatch):
    out = _browser_probe(browser, site, monkeypatch, "up")
    assert out["available"] and out["checked"] == ["home: logo, box", "login: email"]


def test_in_a_browser_a_page_served_without_its_content_is_not_up(browser, site, monkeypatch):
    out = _browser_probe(browser, site, monkeypatch, "elsewhere")
    assert out["available"] is False
    assert "home" in out["problem"] and "without logo, box" in out["problem"]
    assert out["served"]["title"] == "Maintenance" and "back soon" in out["served"]["text"]


def test_in_a_browser_a_server_error_is_not_up(browser, site, monkeypatch):
    out = _browser_probe(browser, site, monkeypatch, "error")
    # Chromium refuses an error status with no body outright
    # (net::ERR_HTTP_RESPONSE_CODE_FAILURE) instead of returning the 503.
    assert out["available"] is False and "did not load" in out["problem"]


# ── the run's report: an application not up makes every failure an outage ──

LOGIN_TIMEOUT = ("playwright._impl._errors.TimeoutError: Locator.fill: Timeout 30000ms exceeded."
                 "\nCall log:\nwaiting for locator(\"[data-test='user-email']\")")
DOWN = {"available": False, "attempts": 9, "problem": "login (x) was served without email",
        "summary": "The application is NOT up after 9 check(s): login was served without email."}


def _junit(*cases):
    body = []
    for name, outcome, msg, props in cases:
        p = "".join(f'<property name="{k}" value="{v}"/>' for k, v in (props or {}).items())
        m = escape(msg, {'"': "&quot;"})
        fail = f'<failure message="{m}">{m}</failure>' if outcome == "failed" else ""
        body.append(f'<testcase classname="tests.step_defs.test_x" name="{name}">'
                    + (f"<properties>{p}</properties>" if p else "") + fail + "</testcase>")
    return ET.fromstring(f"<testsuites><testsuite>{''.join(body)}</testsuite></testsuites>")


def test_an_application_not_up_makes_every_failure_an_outage_with_the_reason():
    root = _junit(("test_a", "failed", "TimeoutError: x", None),
                  ("test_b", "failed", "AssertionError: No row", None),
                  ("test_c", "passed", "", None))
    out = fj.finalise(root, None, DOWN)
    assert out["app_down"] == ["tests.step_defs.test_x::test_a", "tests.step_defs.test_x::test_b"]
    case = jm.cases(root)[0]
    assert jm.is_outage(case) and "NOT up after 9" in jm.props(case)["outage_reason"]
    assert not jm.is_outage(jm.cases(root)[2])


@pytest.mark.parametrize("probe", [None, {"available": True}, {"available": "unknown"}, "junk"])
def test_an_application_found_up_or_not_checked_marks_nothing(probe):
    root = _junit(("test_a", "failed", "TimeoutError: x", None))
    assert fj.finalise(root, None, probe)["app_down"] == []
    assert not jm.is_outage(jm.cases(root)[0])


def test_an_outage_already_named_by_its_text_is_counted_once():
    nav = ("AssertionError: Navigation to https://a.example/ returned HTTP 503 (x) after 3 "
           "attempts. The page did not load")
    root = _junit(("test_a", "failed", nav, None), ("test_b", "failed", "TimeoutError: y", None))
    out = fj.finalise(root, None, DOWN)
    assert out["outage"] == ["tests.step_defs.test_x::test_a", "tests.step_defs.test_x::test_b"]


def test_the_cli_reads_the_check(tmp_path, capsys):
    junit = tmp_path / "junit.xml"
    ET.ElementTree(_junit(("test_a", "failed", "TimeoutError: x", None))).write(junit)
    (tmp_path / "app_probe.json").write_text(json.dumps(DOWN))
    assert fj.main([str(junit), "--app-probe", str(tmp_path / "app_probe.json")]) == 0
    assert "the application was not up" in capsys.readouterr().out
    code, reason = fj.verdict(junit, "1")
    assert code == 1 and "1 not judged (application unavailable)" in reason, \
        "nothing was tested, so the check is not green either"


# ── the night of 30 October, replayed ───────────────────────────────────────

def test_the_night_of_30_october_raises_no_defect_and_says_what_was_served(world, tmp_path):
    """17 of 17 failed on pages served without their content."""
    fake, *_ = world
    root = _junit(*[(f"test_{i}", "failed", LOGIN_TIMEOUT, None) for i in range(17)])
    fj.finalise(root, None, DOWN)
    out = _run(world, tmp_path, root, probe=DOWN)
    assert out["raised"] == [] and out["capped"] == [] and out["not_retried"] == []
    assert len(out["outages"]) == 17 and _bugs(fake) == []
    (alert,) = _alerts(fake)
    assert alert.startswith(f"[health:open] {tf.OUTAGE}")
    assert "The application health check found: The application is NOT up" in alert


# ── the workflow ────────────────────────────────────────────────────────────

def _steps():
    wf = yaml.safe_load((ROOT / ".github/workflows/agent4_runner.yml").read_text(encoding="utf-8"))
    return wf["jobs"]["test"]["steps"]


def _named(steps, fragment):
    return next(s for s in steps if fragment in (s.get("name") or ""))


def test_the_check_runs_after_the_first_run_and_gates_the_retry():
    steps = _steps()
    names = [s.get("name") or "" for s in steps]
    order = ["Keep only the final attempt", "Check the application is up",
             "Retry failed tests once", "Mark what the run learned"]
    idx = [next(i for i, n in enumerate(names) if frag in n) for frag in order]
    assert idx == sorted(idx)
    probe = _named(steps, "Check the application is up")
    assert probe["id"] == "probe" and probe.get("continue-on-error") is True
    assert "steps.e2e.outputs.exit_code == '1'" in probe["if"]
    assert "scripts.app_probe" in probe["run"] and "reports/app_probe.json" in probe["run"]
    assert "secrets." not in str(probe), "public pages only: the check holds no credential"
    retry = _named(steps, "Retry failed tests once")
    assert "steps.probe.outputs.available != 'false'" in retry["if"], \
        "an unknown check retries as before; only a check that found it down skips"
    assert int(retry["env"]["MAX_RETRIED_TESTS"]) >= 50, "every failure is run again"
    assert "--app-probe reports/app_probe.json" in _named(steps, "Mark what the run learned")["run"]


def test_the_script_says_unknown_and_never_fails_on_a_wrong_setting(tmp_path, monkeypatch, capsys):
    import scripts.app_probe as sp
    monkeypatch.setattr(app_probe, "checks", lambda *a, **k: (_ for _ in ()).throw(
        ValueError("health_check page 'x' is not in the app inventory")))
    out_file = tmp_path / "gh_out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    report = tmp_path / "app_probe.json"
    assert sp.main(["--report", str(report)]) == 0
    assert out_file.read_text() == "available=unknown\n"
    data = json.loads(report.read_text())
    assert data["available"] == "unknown" and "not usable" in data["problem"]
    assert "::warning::" in capsys.readouterr().out


# ── F50: one base URL for the tests, the agents and the application check ──

def _resolver():
    import importlib.util
    spec = importlib.util.spec_from_file_location("_e2e_conftest", ROOT / "tests" / "conftest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.resolve_base_url


@pytest.mark.parametrize("env, cfg, expected", [
    (None, {"app_under_test": {"base_url": "https://new.example"},
            "base_url": "https://old.example"}, "https://new.example"),
    (None, {"base_url": "https://old.example"}, "https://old.example"),
    ("https://staging.example", {"app_under_test": {"base_url": "https://new.example"}},
     "https://staging.example"),
])
def test_the_tests_run_against_the_application_the_agents_and_the_check_use(
        monkeypatch, env, cfg, expected):
    """9 Nov 2026: the tests read a top-level base_url while the agents and the
    application check read app_under_test.base_url - a project setting only the
    documented one ran its tests against the previous application."""
    if env:
        monkeypatch.setenv("BASE_URL", env)
    else:
        monkeypatch.delenv("BASE_URL", raising=False)
    assert _resolver()(cfg) == expected


def test_the_shipped_config_has_one_base_url():
    config = yaml.safe_load((ROOT / "config" / "config.yaml").read_text())
    assert "base_url" not in config, "a second base URL can silently disagree"
    assert config["app_under_test"]["base_url"]
