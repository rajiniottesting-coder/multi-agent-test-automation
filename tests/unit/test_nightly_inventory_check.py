"""The one nightly inventory check (X10): check_inventory_staleness reads the
application the way the tests use it, so the Inventory Health workflow can run
it alone and hand its report to Agent 0.

The browser is faked: no network, no Chromium. The inventory is a small
generic one written to a temporary path, so the tests name no application.
"""
import json
import sys
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import scripts.check_inventory_staleness as chk
from inventory_tools import browser, introspect

BASE = "https://x.test"

INV = {"pages": {
    "menu": {"url": "/", "always": True, "elements": {"menu_home": "#m-home",
                                                      "menu_list": "#m-list",
                                                      "menu_out": "#m-out"}},
    "overlay": {"url": "(overlay)", "always": True, "elements": {"banner": "#banner"}},
    "signin": {"url": "/account/login", "elements": {"user": "#user", "pass": "#pass"}},
    "home": {"url": "/", "elements": {"hero": "#hero", "title": "h1"}},
    "list": {"url": "/list", "elements": {"rows": ".row", "count": "#count"}},
}}


@pytest.fixture
def crawl(tmp_path, monkeypatch):
    state = {"counts": {}, "later": {}, "visits": [], "logins": [], "logged_in": True,
             "ids": {}, "advice": []}

    def run(*flags, inventory=INV, creds=("u", "p")):
        path = tmp_path / "inv.json"
        path.write_text(json.dumps(inventory))
        monkeypatch.setattr(chk.AppContext, "load", staticmethod(lambda: SimpleNamespace(
            name="X", base_url=BASE, inventory_path=lambda: path)))
        page = MagicMock()

        @contextmanager
        def fake_browser(headless=True):
            yield page

        def resolve(pg, url, sels, attrs):
            path_ = url.replace(BASE, "")
            state["visits"].append(path_)
            page.url = url
            return ({s: state["counts"].get(s, 1) for s in sels},
                    set(state["ids"].get(path_, ())), True)

        def count_again(pg, sels, attrs):
            return {s: state["later"].get(s, state["counts"].get(s, 1)) for s in sels}, set()

        def login(pg, url, *a):
            state["logins"].append((url.replace(BASE, ""), list(state["visits"])))
            return state["logged_in"]

        monkeypatch.setattr(chk, "browser_page", fake_browser)
        monkeypatch.setattr(chk, "resolve_selectors", resolve)
        monkeypatch.setattr(chk, "count_on_page", count_again)
        monkeypatch.setattr(chk, "do_login", login)
        monkeypatch.setattr(chk, "ambiguity_advice", lambda pg, sel: state["advice"].append(sel)
                            or {"described": ["<li.a> shown \"One\""], "exact_fix": None})
        monkeypatch.setattr(chk, "exact_fix", lambda pg, sel: None)
        monkeypatch.setattr(chk, "RENDER_WAIT_MS", 1000)
        out = tmp_path / "r.json"
        if out.exists():
            out.unlink()
        argv = ["chk", "--json", str(out), *flags]
        if creds:
            argv += ["--username", creds[0], "--password", creds[1]]
        else:
            argv += ["--username", "", "--password", ""]
        monkeypatch.setattr(sys, "argv", argv)
        code = chk.main()
        return code, (json.loads(out.read_text()) if out.exists() else None)
    return state, run


# ── signed in, at the inventory's login page ───────────────────────────

def test_it_signs_in_at_the_login_page_the_inventory_records(crawl):
    state, run = crawl
    code, report = run()
    assert code == 0
    assert [u for u, _ in state["logins"]] == ["/account/login"], "not the root"


def test_the_login_page_is_read_signed_out_before_signing_in(crawl):
    state, run = crawl
    _, report = run()
    (_, before), = state["logins"]
    assert before == ["/account/login"]
    assert report["pages"]["signin"]["state"] == "signed out"
    assert state["visits"].count("/account/login") == 1


def test_a_failed_login_stops_with_exit_2_and_writes_no_report(crawl, capsys):
    state, run = crawl
    state["logged_in"] = False
    code, report = run()
    assert code == 2 and report is None
    assert "LOGIN FAILED at /account/login" in capsys.readouterr().out
    assert state["visits"] == ["/account/login"], "no page read after the failed login"


def test_without_credentials_it_goes_on_signed_out(crawl):
    state, run = crawl
    state["logged_in"] = False
    code, report = run(creds=None)
    assert code == 0 and report is not None


def test_no_login_reads_every_page_without_signing_in(crawl):
    state, run = crawl
    code, report = run("--no-login")
    assert state["logins"] == [] and "signin" in report["pages"]
    assert "state" not in report["pages"]["signin"]


# ── every page, the shared menu included ───────────────────────────────

def test_an_always_page_with_an_address_is_read_and_never_compared(crawl, monkeypatch):
    state, run = crawl
    compared = []
    monkeypatch.setattr(chk, "collect_uncovered",
                        lambda pg, url, sels, attrs, **k: compared.append(url) or ("T", []))
    state["counts"] = {"#m-out": 0}
    state["ids"] = {"/": {"hero-id"}}
    code, report = run("--compare")
    menu = report["pages"]["menu"]
    assert menu["missing"] == [{"element": "menu_out", "selector": "#m-out"}]
    assert menu["new_data_tests"] == [], "the page's own test-ids are not the menu's"
    assert "overlay" not in report["pages"], "an overlay with no address is not visited"
    assert BASE + "/" in compared and compared.count(BASE + "/") == 1, "home only"


# ── a page that did not render ─────────────────────────────────────────

def test_a_page_that_renders_late_is_read_again_not_reported_stale(crawl):
    state, run = crawl
    state["counts"] = {".row": 0, "#count": 0}
    state["later"] = {".row": 3, "#count": 1}
    code, report = run("--fail-on-drift")
    assert report["pages"]["list"]["missing"] == []
    assert report["pages_not_rendered"] == [] and code == 1      # .row x3 is ambiguous


def test_a_page_that_never_renders_is_listed_apart_and_never_stale(crawl, capsys):
    state, run = crawl
    state["counts"] = {".row": 0, "#count": 0}
    code, report = run("--fail-on-breakage")
    assert report["pages_not_rendered"] == ["list"]
    assert "list" not in report["pages"], "nothing on it is drift"
    assert report["has_drift"] is False and report["breaking"] is True and code == 1
    assert "[list] NOT RENDERED" in capsys.readouterr().out


def test_keys_not_expected_now_do_not_decide_rendering():
    sels = {"a": "#a", "b": "#b", "c": "#c", "d": "#d"}
    live = {"#a": 1, "#b": 0, "#c": 0, "#d": 1}
    assert introspect.rendered(sels, live) is True
    assert introspect.rendered(sels, {"#a": 1}) is False, "one shell element proves nothing"
    assert introspect.rendered(sels, {"#a": 1}, declared_conditional={"b", "c", "d"}) is True
    assert introspect.rendered(sels, {}, declared_removed={"a", "b"},
                               declared_planned={"c"}, declared_conditional={"d"}) is True
    assert introspect.rendered({"one": "#x"}, {"#x": 1}) is True
    assert introspect.rendered({}, {}) is True


# ── invalid and ambiguous selectors ────────────────────────────────────

def test_an_invalid_selector_is_reported_invalid_never_stale(crawl, capsys):
    state, run = crawl
    state["counts"] = {"h1": browser.INVALID}
    code, report = run("--fail-on-breakage")
    home = report["pages"]["home"]
    assert home["invalid"] == [{"element": "title", "selector": "h1"}]
    assert home["missing"] == [], "a stale key is proposed for removal; this one needs fixing"
    assert report["invalid_selectors"] == 1 and report["breaking"] and code == 1
    assert "INVALID title: h1" in capsys.readouterr().out


def test_an_ambiguous_selector_says_what_it_matched(crawl, capsys):
    state, run = crawl
    state["counts"] = {"#hero": 2}
    run()
    assert state["advice"] == ["#hero"]
    out = capsys.readouterr().out
    assert "AMBIG   hero: #hero -> 2 matches" in out and '1. <li.a> shown "One"' in out
    assert "... and 1 more" in out


# ── what fails the run ─────────────────────────────────────────────────

def test_a_new_test_id_alone_is_drift_but_breaks_nothing(crawl):
    state, run = crawl
    state["ids"] = {"/list": {"brand-new"}}
    code, report = run("--fail-on-breakage")
    assert report["has_drift"] is True and report["breaking"] is False and code == 0
    code, _ = run("--fail-on-drift")
    assert code == 1


def test_page_reads_only_that_page(crawl):
    state, run = crawl
    code, report = run("--page", "list")
    assert set(report["pages"]) == {"list"} and report["only_page"] == "list"
    assert state["visits"] == ["/list"], "the login page is not read either"


def test_an_unknown_page_stops_with_exit_3(crawl, capsys):
    _state, run = crawl
    code, report = run("--page", "nope")
    assert code == 3 and report is None
    assert "Available: home, list, menu, overlay, signin" in capsys.readouterr().out


# ── the browser helpers both tools share ───────────────────────────────

def test_count_on_page_counts_a_rejected_selector_invalid(monkeypatch):
    def fake_count(page, sel):
        if sel == "bad[":
            raise ValueError("not a selector")
        return 2
    monkeypatch.setattr(browser, "_count_selector", fake_count)
    page = MagicMock()
    page.evaluate.return_value = ["a"]
    page.frames = []
    counts, ids = browser.count_on_page(page, ["ok", "bad["])
    assert counts == {"ok": 2, "bad[": browser.INVALID} and ids == {"a"}


def test_exact_fix_only_when_the_exact_form_matches_one(monkeypatch):
    found = {'text="Save"': 1, 'text="Go"': 2}
    monkeypatch.setattr(browser, "locate", lambda page, sel: SimpleNamespace(
        count=lambda: found.get(sel, 0)))
    assert browser.exact_fix(None, "text=Save") == 'text="Save"'
    assert browser.exact_fix(None, "text=Go") is None
    assert browser.exact_fix(None, "#save") is None


def test_verify_locators_uses_the_shared_helpers():
    """One copy of each: the person's tool and the nightly check cannot drift apart."""
    import scripts.verify_locators as vl
    assert vl.exact_text_form is browser.exact_text_form
    assert vl.signed_out_pages is browser.signed_out_pages
    assert vl._describe_matches is browser.describe_locator
    assert vl._DESCRIBE_JS is browser.DESCRIBE_JS


# ── one rule set: the nightly check reads a key as verify_locators does ─

@pytest.mark.parametrize("declared", ["", "multi_match", "conditional", "removed", "planned"])
@pytest.mark.parametrize("count", [browser.INVALID, 0, 1, 3])
def test_both_tools_judge_a_reading_alike(monkeypatch, capsys, declared, count):
    """verify_locators (a person's visual check) and the nightly check classify
    each reading with their own code; this pins them to one rule set."""
    import scripts.verify_locators as vl
    sels = {"k": "#k", "a": "#a", "b": "#b"}
    counts = {"#k": count, "#a": 1, "#b": 1}

    def resolve_one(page, sel):
        if counts[sel] == browser.INVALID:
            raise ValueError("invalid")
        return SimpleNamespace(count=lambda: counts[sel])
    monkeypatch.setattr(vl, "_resolve_one", resolve_one)
    monkeypatch.setattr(vl, "_wait_for_render", lambda *a, **k: True)
    monkeypatch.setattr(vl, "_highlight", lambda *a, **k: False)
    monkeypatch.setattr(vl, "_describe_matches", lambda *a, **k: [])
    monkeypatch.setattr(vl, "_count", lambda *a, **k: 0)
    entry = {"url": "/p", "elements": dict(sels)}
    if declared:
        entry[declared] = ["k"]
    _ok, bad = vl._verify_page(MagicMock(), BASE, "p", entry, 0, False)

    diff = introspect.diff_page(
        "p", sels, counts, set(),
        declared_family=set(entry.get("multi_match") or []),
        declared_conditional=set(entry.get("conditional") or []),
        declared_removed=set(entry.get("removed") or []),
        declared_planned=set(entry.get("planned") or []))
    nightly_bad = bool(diff["missing"] or diff["ambiguous"] or diff["reappeared"]
                       or count == browser.INVALID)
    assert bool(bad) == nightly_bad


# ── the Inventory Health workflow runs it and hands the report on ──────

def _health_steps():
    import yaml
    from config.paths import PROJECT_ROOT
    wf = yaml.safe_load((PROJECT_ROOT / ".github" / "workflows" / "inventory_health.yml")
                        .read_text(encoding="utf-8"))
    return wf, wf["jobs"]["verify"]["steps"]


def test_inventory_health_runs_the_one_check_and_hands_its_report_to_agent0():
    wf, steps = _health_steps()
    assert wf["permissions"] == {"contents": "read", "actions": "write"}
    by = {s.get("id") or s.get("name"): s for s in steps}
    names = list(by)
    for sid in ("verify", "retry"):
        run = by[sid]["run"]
        assert "check_inventory_staleness --compare --fail-on-breakage" in run
        assert "--json reports/drift.json" in run and "verify_locators" not in run
        assert by[sid]["env"]["PAGE_KEY"] == "${{ github.event.inputs.page }}"
        assert "${{" not in run, "the page key reaches the shell through env only"
    drop = by["Keep the report only when the application was up"]
    keep = by["Keep the drift report for Agent 0"]
    hand = by["Hand the report to Agent 0"]
    assert names.index("retry") < names.index(drop["name"]) < names.index(keep["name"]) \
        < names.index(hand["name"]) < names.index("Report")
    assert "d.get('available') is False" in drop["run"] and "rm -f reports/drift.json" in drop["run"]
    assert keep["if"] == hand["if"] == "always() && !github.event.inputs.page", \
        "a one-page report does not describe the inventory"
    assert keep["with"] == {"name": "inventory-drift-report", "path": "reports/drift.json",
                            "retention-days": 7, "if-no-files-found": "ignore"}
    assert hand["env"] == {"GH_TOKEN": "${{ github.token }}"}
    assert "impact_settings()['enabled']" in hand["run"]
    assert "gh workflow run agent0_impact.yml" in hand["run"]
    assert '-f mode=drift -f drift_report_run="${{ github.run_id }}"' in hand["run"]


def test_the_summary_quotes_the_first_problem_of_the_check():
    from scripts.inventory_health_report import _first_problem
    assert _first_problem("  [home] x\n    INVALID title: h1 -> rejected\n") \
        == "INVALID title: h1 -> rejected"
    assert _first_problem("  [list] NOT RENDERED - none of its keys\n").startswith("[list] NOT")
    assert _first_problem("  LOGIN FAILED at /login (still on the form)\n    STALE a: b\n") \
        .startswith("LOGIN FAILED")
