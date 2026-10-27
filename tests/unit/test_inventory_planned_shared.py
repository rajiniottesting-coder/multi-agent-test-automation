"""P1-4: planned inventory entries (F-12, L19), new pages (L25) and elements a
shared section repeats on every page (G14).

  * planned  - a person adds an element (or a whole page) from the design before
    deployment. Agent 2 may use it, and its PR says so; every checker reads its
    absence as "not live yet"; the nightly update never removes it and confirms
    it once the crawl finds it. A planned page is not touched until one of its
    planned keys is live - then its other live elements are added too (L25).
  * shared   - seen on PR #228: the nightly update added a footer field, already
    in the inventory as one page's key, to four other pages under a new name.
    The crawl now marks other pages' selectors with their owner; such an element
    is listed with that key and never added again.
  * unlisted - links to same-origin pages no inventory url matches are listed.

Generic pages and selectors only; no application names.
"""
import json
import sys
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from core import inventory_planned as planned_mod
from core import inventory_update as iu
from core.impact_analysis import drift_seeds
from core.schemas import GeneratedFile
from inventory_tools import introspect

SELS = {"save": "#save", "coupon": "[data-test='coupon']", "help": "#help"}


# ── introspect.diff_page / summarize_drift ───────────────────────────────

def _diff(counts, **declared):
    return introspect.diff_page("p", dict(SELS), counts, set(), **declared)


def test_a_planned_element_not_live_is_not_drift():
    d = _diff({"#save": 1, "[data-test='coupon']": 0, "#help": 1}, declared_planned={"coupon"})
    assert d["missing"] == [] and d["planned_live"] == []
    assert d["planned_waiting"] == [{"element": "coupon", "selector": "[data-test='coupon']"}]
    report = introspect.summarize_drift({"p": d}, [])
    assert report["has_drift"] is False and report["planned_waiting"] == 1
    assert drift_seeds(report).elements == set(), "Agent 0 seeds nothing for it"


@pytest.mark.parametrize("count, family, live, ambiguous", [
    (1, set(), True, False),
    (3, {"coupon"}, True, False),          # a declared family may match several
    (3, set(), False, True),               # several, undeclared: ambiguity, not live
])
def test_a_planned_element_found_is_live(count, family, live, ambiguous):
    d = _diff({"#save": 1, "[data-test='coupon']": count, "#help": 1},
              declared_planned={"coupon"}, declared_family=family)
    assert bool(d["planned_live"]) is live
    assert bool(d["ambiguous"]) is ambiguous
    assert d["missing"] == []


def test_without_the_declaration_a_missing_element_is_still_stale():
    d = _diff({"#save": 1, "[data-test='coupon']": 0, "#help": 1})
    assert d["missing"][0]["element"] == "coupon" and d["planned_waiting"] == []


# ── introspect: shared elements and unlisted pages ───────────────────────

def _desc(tag, attrs, text, visible=True):
    return {"tag": tag, "attrs": attrs, "text": text, "renderedText": text, "label": "",
            "visible": visible, "thirdParty": False, "hasIconChild": False, "cssPath": ""}


def test_an_element_another_page_covers_is_shared_not_new():
    descriptors = [
        _desc("input", {"placeholder": "Your email", introspect.SHARED_ATTR: "home.footer_email"}, ""),
        _desc("button", {"id": "pay"}, "Pay"),
        _desc("button", {"id": "save", introspect.COVER_ATTR: ""}, "Save"),
    ]
    found = introspect.uncovered_entry("https://x.test/p", "P", descriptors,
                                       base_url="https://x.test")
    assert list(found["elements"]) == ["pay_button"], "only the truly new element"
    (name, row), = found["shared"].items()
    assert row["covered_by"] == "home.footer_email"
    assert introspect.SHARED_ATTR not in row["selector"], "the mark never reaches a selector"
    shared = introspect.shared_descriptors(descriptors)
    assert len(shared) == 1 and introspect.SHARED_ATTR not in shared[0]["attrs"]


def test_unlisted_paths_are_grouped_and_known_ones_skipped():
    inventory = {"pages": {"home": {"url": "/"}, "list": {"url": "/items"},
                           "item": {"url": "/item/{id}"},
                           "menu": {"url": "/overlay", "always": True}}}
    hrefs = {"home": ["/items", "/item/7", "/about", "/brand/a", "/brand/b",
                      "https://other.test/x", "/logo.png", "#top", "mailto:a@b.c",
                      "javascript:void(0)", "/overlay"],
             "list": ["/brand/a", "about"]}
    rows = introspect.unlisted_paths(hrefs, inventory, "https://x.test")
    assert rows == [
        {"group": "/brand", "count": 2, "example": "/brand/a", "linked_from": ["home", "list"]},
        {"group": "/about", "count": 1, "example": "/about", "linked_from": ["home", "list"]},
        {"group": "/overlay", "count": 1, "example": "/overlay", "linked_from": ["home"]},
    ]
    assert len(introspect.unlisted_paths(hrefs, inventory, "https://x.test", limit=1)) == 1


# ── the browser marks other pages' selectors with their owner ────────────

def test_collect_uncovered_marks_shared_selectors_after_its_own(monkeypatch):
    from inventory_tools import browser
    calls = []
    monkeypatch.setattr(browser, "_goto_spa_tolerant", lambda page, url: None)
    monkeypatch.setattr(browser, "_mark_selector",
                        lambda page, sel, attr="", value="": calls.append((sel, attr, value)))
    monkeypatch.setattr(browser, "_snapshot_descriptors", lambda page, attrs: [])
    page = MagicMock()
    page.title.return_value = "T"
    browser.collect_uncovered(page, "u", ["#own"], shared={"#footer": "home.footer_email"})
    assert calls == [("#own", "", ""), ("#footer", introspect.SHARED_ATTR, "home.footer_email")]


def test_mark_selector_keeps_the_first_owner(monkeypatch):
    from inventory_tools import browser
    matches = MagicMock()
    monkeypatch.setattr(browser, "_resolve_one", lambda page, sel: matches)
    browser._mark_selector(MagicMock(), "#x", introspect.SHARED_ATTR, "a.k")
    script, args = matches.evaluate_all.call_args.args
    assert "hasAttribute" in script and args == [introspect.SHARED_ATTR, "a.k"]
    browser._mark_selector(MagicMock(), "#x")
    assert introspect.COVER_ATTR in matches.evaluate_all.call_args.args[0]


# ── check_inventory_staleness: what it passes and reports ────────────────

@pytest.fixture
def crawl(tmp_path, monkeypatch):
    from scripts import check_inventory_staleness as chk
    state = {"collect": [], "counts": {}, "reachable": {}, "landed": {}}

    def run(inventory, *flags):
        path = tmp_path / "inv.json"
        path.write_text(json.dumps(inventory))
        monkeypatch.setattr(chk.AppContext, "load", staticmethod(lambda: SimpleNamespace(
            name="X", base_url="https://x.test", inventory_path=lambda: path)))
        page = MagicMock()

        @contextmanager
        def browser(headless=True):
            yield page

        def resolve(pg, url, sels, attrs):
            path_ = url.replace("https://x.test", "")
            page.url = "https://x.test" + state["landed"].get(path_, path_)
            return ({s: state["counts"].get(s, 1) for s in sels}, set(),
                    state["reachable"].get(path_, True))

        def collect(pg, url, sels, attrs, shared=None):
            state["collect"].append((url.replace("https://x.test", ""), list(sels), dict(shared or {})))
            return "T", [_desc("a", {"href": "/news/1"}, "News"), _desc("a", {"href": "/news/2"}, "More")]
        monkeypatch.setattr(chk, "browser_page", browser)
        monkeypatch.setattr(chk, "resolve_selectors", resolve)
        monkeypatch.setattr(chk, "collect_uncovered", collect)
        out = tmp_path / "r.json"
        monkeypatch.setattr(sys, "argv", ["chk", "--no-login", "--json", str(out), *flags])
        code = chk.main()
        return code, json.loads(out.read_text())
    return chk, state, run


INV = {"pages": {
    "home": {"url": "/", "elements": {"footer_email": "#fe", "hero": "#hero", "old": "#old",
                                      "soon": "#soon"},
             "removed": ["old"], "planned": ["soon"]},
    "list": {"url": "/list", "elements": {"rows": ".row", "footer_email_copy": "#fe"}},
    "menu": {"url": "(overlay)", "always": True, "elements": {"nav": "nav a"}},
}}


def test_other_pages_live_keys_are_passed_as_shared(crawl):
    chk, state, run = crawl
    run(INV, "--compare")
    shared = {url: sh for url, _sels, sh in state["collect"]}
    assert shared["/list"] == {"#hero": "home.hero"}, (
        "not its own selectors, not the always page, not a removed or planned key")
    assert shared["/"] == {".row": "list.rows"}


def test_a_planned_key_and_a_planned_page_not_live_are_not_drift(crawl):
    chk, state, run = crawl
    inv = json.loads(json.dumps(INV))
    inv["pages"]["wish"] = {"url": "/wish", "planned_page": True, "planned": ["heading"],
                            "elements": {"heading": "h1.wish"}}
    state["counts"] = {"#soon": 0, "#old": 0}
    state["reachable"] = {"/wish": False}
    code, report = run(inv, "--compare", "--fail-on-drift")
    assert report["unreachable_pages"] == [] and report["planned_pages_waiting"] == ["wish"]
    assert report["pages"]["home"]["planned_waiting"][0]["element"] == "soon"
    assert report["has_drift"] is False and code == 0


def test_a_planned_page_that_redirects_is_waiting_too(crawl):
    chk, state, run = crawl
    inv = json.loads(json.dumps(INV))
    inv["pages"]["wish"] = {"url": "/wish", "planned_page": True, "planned": ["heading"],
                            "elements": {"heading": "h1.wish"}}
    state["landed"] = {"/wish": "/"}
    _code, report = run(inv)
    assert report["planned_pages_waiting"] == ["wish"] and "wish" not in report["pages"]


def test_compare_reports_unlisted_pages(crawl):
    chk, state, run = crawl
    _code, report = run(INV, "--compare")
    assert report["unlisted_paths"][0]["group"] == "/news"
    assert report["unlisted_paths"][0]["count"] == 2


# ── the nightly inventory update ─────────────────────────────────────────

def _inv(**page):
    base = {"url": "/p", "elements": dict(SELS), "planned": ["coupon"]}
    base.update(page)
    return {"pages": {"p": base}}


def _drift(live=(), waiting=(), missing=(), new=None, declared=None, **extra):
    return {"pages_checked": 1,
            "pages": {"p": {"missing": list(missing), "ambiguous": [], "new_data_tests": [],
                            "reappeared": [], "planned_live": list(live),
                            "planned_waiting": list(waiting)}},
            "new_elements": {"p": new or {}},
            "new_element_declarations": {"p": declared or {}}, **extra}


LIVE = {"element": "coupon", "selector": "[data-test='coupon']", "matches": 1}
WAIT = {"element": "coupon", "selector": "[data-test='coupon']"}


def test_a_planned_key_found_live_is_confirmed():
    upd = iu.build_update(_drift(live=[LIVE]), _inv(), {"save"})
    assert upd.changed and "planned" not in upd.inventory["pages"]["p"]
    assert upd.inventory["pages"]["p"]["elements"]["coupon"] == "[data-test='coupon']"
    assert upd.confirmed == [{"page": "p", "element": "coupon",
                              "selector": "[data-test='coupon']", "page_confirmed": False}]
    assert "Planned elements now live - confirmed (1)" in iu.render_body(upd, "inv.json", "d")


def test_a_planned_key_still_waiting_is_never_removed():
    """Even reported missing by an old report, with removal on and no code naming it."""
    upd = iu.build_update(_drift(waiting=[WAIT], missing=[{"element": "coupon",
                                                            "selector": "x"}]),
                          _inv(), set(), allow_removal=True)
    assert "coupon" in upd.inventory["pages"]["p"]["elements"]
    assert upd.removed == [] and upd.inventory["pages"]["p"]["planned"] == ["coupon"]
    assert "**Planned, not live yet**" in iu.render_body(upd, "inv.json", "d")
    assert not upd.changed


def test_a_planned_page_not_live_is_never_touched():
    inv = _inv(planned_page=True)
    drift = _drift(waiting=[WAIT], missing=[{"element": "save", "selector": "#save"},
                                            {"element": "help", "selector": "#help"}],
                   new={"error_text": "text=Not found"})
    upd = iu.build_update(drift, inv, set())
    assert upd.inventory == inv and not upd.changed
    assert upd.planned_pages_waiting == ["p"] and upd.added == upd.removed == []
    assert "pages `p`" in iu.render_body(upd, "inv.json", "d")


def test_a_planned_page_found_live_is_confirmed_and_crawled_like_any_page():
    """L25: its first live planned key confirms the page, and its other live
    elements are added the same night."""
    upd = iu.build_update(_drift(live=[LIVE], new={"pay_button": "#pay"}),
                          _inv(planned_page=True), set())
    page = upd.inventory["pages"]["p"]
    assert "planned_page" not in page and "planned" not in page
    assert page["elements"]["pay_button"] == "#pay"
    assert upd.confirmed[0]["page_confirmed"] is True and upd.pages_confirmed == ["p"]
    assert "page confirmed live" in iu.render_body(upd, "inv.json", "d")


def test_a_planned_page_with_nothing_planned_is_refused_loudly():
    upd = iu.build_update(_drift(), _inv(planned_page=True, planned=[]), set())
    assert upd.refused[0]["element"] == "(page)" and "nothing can confirm" in upd.refused[0]["refused"]
    assert not upd.changed


def test_waiting_pages_from_the_crawl_are_listed():
    upd = iu.build_update(_drift(planned_pages_waiting=["q"]), _inv(), set())
    assert upd.planned_pages_waiting == ["q"]


def test_a_shared_element_is_listed_not_added():
    shared = {"footer_email_input": {"selector": "input[placeholder='Your email']",
                                     "covered_by": "home.footer_email"}}
    upd = iu.build_update(_drift(declared={"shared": shared}), _inv(), set())
    assert upd.added == [] and "footer_email_input" not in upd.inventory["pages"]["p"]["elements"]
    assert upd.shared == [{"page": "p", "element": "footer_email_input",
                           "selector": "input[placeholder='Your email']",
                           "covered_by": "home.footer_email"}]
    body = iu.render_body(upd, "inv.json", "d")
    assert "Not added - already covered on another page (1)" in body and "`home.footer_email`" in body


def test_unlisted_pages_are_listed_in_the_body():
    rows = [{"group": "/news", "count": 2, "example": "/news/1", "linked_from": ["p"]},
            {"group": "/about", "count": 1, "example": "/about", "linked_from": ["p"]}]
    upd = iu.build_update(_drift(unlisted_paths=rows), _inv(), set())
    body = iu.render_body(upd, "inv.json", "d")
    assert "`/news` (2 paths, e.g. `/news/1`)" in body and "| `/about` | p |" in body
    assert not upd.changed, "a listing alone opens no pull request"


def test_a_removed_key_leaves_the_planned_list_too():
    page = {"elements": {"a": "#a"}, "planned": ["a"]}
    iu._drop_key(page, "a")
    assert page["planned"] == []


# ── adding planned entries ───────────────────────────────────────────────

BASE_INV = {"pages": {"p": {"url": "/p", "elements": {"save": "#save"}}}}


def test_add_a_planned_element():
    out, why = planned_mod.add_planned_element(BASE_INV, "p", "coupon", "[data-test='coupon']")
    assert why == "" and out["pages"]["p"]["planned"] == ["coupon"]
    assert "planned" not in BASE_INV["pages"]["p"], "the input is not modified"
    for args, reason in [(("q", "x", "#x"), "page is not in the inventory"),
                         (("p", "Bad", "#x"), "snake_case"),
                         (("p", "save", "#y"), "already exists"),
                         (("p", "other", "#save"), "already used")]:
        same, why = planned_mod.add_planned_element(BASE_INV, *args)
        assert reason in why and same is BASE_INV


def test_add_a_planned_page():
    out, why = planned_mod.add_planned_page(BASE_INV, "wish", "/wish",
                                            {"heading": "h1.wish", "add": "#add"}, ["Wish"])
    assert why == ""
    assert out["pages"]["wish"] == {"url": "/wish", "components": ["Wish"], "planned_page": True,
                                    "elements": {"heading": "h1.wish", "add": "#add"},
                                    "planned": ["heading", "add"]}
    for args, reason in [(("Wish", "/w", {"a": "#a"}), "snake_case"),
                         (("p", "/w", {"a": "#a"}), "already exists"),
                         (("w", "w", {"a": "#a"}), "starting with '/'"),
                         (("w", "/p/", {"a": "#a"}), "already page 'p'"),
                         (("w", "/w", {}), "at least one element"),
                         (("w", "/w", {"Bad": "#a"}), "Bad: ")]:
        same, why = planned_mod.add_planned_page(BASE_INV, *args)
        assert reason in why and same is BASE_INV, args


def _po(page, *keys):
    body = "\n".join(f"        self.click(self.sel('{k}'))" for k in keys)
    return GeneratedFile(file_path=f"pages/{page}_page.py", is_new_file=True, purpose="p",
                         content=f"class P(BasePage):\n    INVENTORY_PAGE = \"{page}\"\n"
                                 f"    def go(self):\n{body}\n")


def test_the_planned_keys_a_page_object_uses():
    inv = {"pages": {"p": {"elements": dict(SELS), "planned": ["coupon"]},
                     "q": {"elements": {"coupon": "#c"}}}}
    files = [_po("p", "save", "coupon"), _po("q", "coupon"),
             GeneratedFile(file_path="features/x.feature", content="sel('coupon')",
                           is_new_file=True, purpose="f"),
             GeneratedFile(file_path="pages/broken.py", is_new_file=True, purpose="b",
                           content="INVENTORY_PAGE = 'p'\nself.sel(\"coupon\")\ndef (:")]
    assert planned_mod.planned_keys_used(files, inv) == ["p.coupon"]
    assert planned_mod.planned_keys_used(files[1:3], inv) == []
    section = planned_mod.pr_section(["p.coupon"])
    assert "Uses planned elements - not deployed yet" in section and "`p.coupon`" in section
    assert planned_mod.pr_section([]) == ""


@pytest.mark.parametrize("trailing", [True, False])
def test_the_plan_cli_keeps_the_files_format(tmp_path, monkeypatch, trailing):
    from scripts import plan_inventory as cli
    path = tmp_path / "inv.json"
    original = json.dumps(BASE_INV, indent=2) + ("\n" if trailing else "")
    path.write_text(original)
    monkeypatch.setattr(cli.AppContext, "load", staticmethod(lambda: SimpleNamespace(
        inventory_path=lambda: path, inventory_file="inv.json")))
    assert cli.main(["element", "--page", "p", "--key", "coupon", "--selector", "#c",
                     "--dry-run"]) == 0
    assert path.read_text() == original, "--dry-run writes nothing"
    assert cli.main(["element", "--page", "p", "--key", "coupon", "--selector", "#c"]) == 0
    text = path.read_text()
    assert text.endswith("\n") is trailing and json.loads(text)["pages"]["p"]["planned"] == ["coupon"]
    assert cli.main(["element", "--page", "p", "--key", "coupon", "--selector", "#d"]) == 1
    assert cli.main(["page", "--page", "wish", "--url", "/wish", "--component", "Wish",
                     "--element", "heading=h1.wish"]) == 0
    assert json.loads(path.read_text())["pages"]["wish"]["planned_page"] is True
    with pytest.raises(SystemExit):
        cli.main(["page", "--page", "w2", "--url", "/w2", "--element", "no-selector"])


# ── verify_locators, promote_draft, onboarding ───────────────────────────

@pytest.mark.parametrize("count, status, ok", [(0, "PLAN", (3, 0)), (1, "LIVE", (3, 0))])
def test_verify_locators_reads_a_planned_element(monkeypatch, capsys, count, status, ok):
    from scripts import verify_locators as vl
    counts = {"#save": 1, "[data-test='coupon']": count, "#help": 1}
    monkeypatch.setattr(vl, "_resolve_one", lambda page, sel: SimpleNamespace(
        count=lambda: counts[sel]))
    monkeypatch.setattr(vl, "_wait_for_render", lambda page, sels, *a, **k: True)
    entry = {"url": "/p", "planned": ["coupon"], "elements": dict(SELS)}
    assert vl._verify_page(MagicMock(), "https://x.test", "p", entry, 0, False) == ok
    assert status in capsys.readouterr().out


def test_verify_locators_reads_a_planned_page_not_live(monkeypatch, capsys):
    from scripts import verify_locators as vl
    monkeypatch.setattr(vl, "_wait_for_render", lambda page, sels, *a, **k: False)
    entry = {"url": "/w", "planned_page": True, "planned": ["h"], "elements": {"h": "h1"}}
    assert vl._verify_page(MagicMock(), "https://x.test", "w", entry, 0, False) == (0, 0)
    assert "PLANNED PAGE - not live yet" in capsys.readouterr().out
    page = MagicMock()
    page.goto.side_effect = RuntimeError("404")
    assert vl._verify_page(page, "https://x.test", "w", entry, 0, False) == (0, 0)
    assert "PLANNED PAGE" in capsys.readouterr().out


def test_promote_draft_prunes_a_planned_entry_whose_element_is_gone():
    from scripts.promote_draft import prune
    inv = {"pages": {"p": {"elements": {"save": "#save"}, "planned": ["coupon"]}}}
    prune(inv)
    assert "planned" not in inv["pages"]["p"]


def test_onboarding_warns_on_planned_entries_nothing_can_confirm():
    from core.onboarding import OK, WARN, inventory_checks
    ok = inventory_checks({"p": {"components": ["C"], "elements": {"a": "#a"}, "planned": ["a"]}},
                          "inv.json")
    assert [c.status for c in ok if c.name == "inventory: planned"] == [OK]
    warn = inventory_checks({"p": {"components": ["C"], "elements": {}, "planned": ["a"]},
                             "w": {"components": ["C"], "planned_page": True}}, "inv.json")
    check, = [c for c in warn if c.name == "inventory: planned"]
    assert check.status == WARN and "p.a" in check.detail and "w" in check.detail
    assert not [c for c in inventory_checks({"p": {"components": ["C"]}}, "i")
                if c.name == "inventory: planned"], "silent when nothing is planned"


# ── Agent 2's pull request names the planned keys its code uses ──────────

def test_agent2_pr_names_planned_keys_its_page_object_uses(tmp_path, monkeypatch):
    from unittest.mock import patch
    import agents.agent2_coder as a2
    import config.paths as paths
    from core.schemas import CodePlan, FilePlan
    from tests.sandbox.fake_jira import FakeRepoHost, jira_client_over
    from tests.sandbox.seed import build_repo, repo_files, seed_jira

    fake = seed_jira()
    fake.add("Story", "Apply a coupon", key="SBX-70", labels=["ai-processed", "human-approved"])
    fake.add("Test Case", "[Positive] Apply a coupon at checkout", key="SBX-71", description="d")
    fake.link("Relates", "SBX-71", "SBX-70")
    jira = jira_client_over(fake, monkeypatch)
    root = build_repo(tmp_path / "repo")
    monkeypatch.setattr(paths, "FEATURES_DIR", root / "features")
    monkeypatch.setattr(a2, "FEATURES_DIR", root / "features")
    monkeypatch.setattr(planned_mod, "load_inventory", lambda ctx: {
        "pages": {"checkout": {"elements": {"coupon": "[data-test='coupon']"},
                               "planned": ["coupon"]}}})
    gh = FakeRepoHost(repo_files(root))
    plan = CodePlan(feature_name="coupon", branch_name="auto/SBX-70-coupon", pr_title="Coupon",
                    pr_body="Body", notes="", files_to_create=[
                        FilePlan(file_path="features/coupon.feature", file_type="feature", purpose="f"),
                        FilePlan(file_path="pages/checkout_page.py", file_type="page_object",
                                 purpose="p")])

    def gen(llm, file_plan, *a, **k):
        if file_plan.file_path.endswith(".feature"):
            return ("Feature: Coupon\n\n  Scenario: Apply a coupon at checkout\n"
                    "    Given I am on the checkout page\n")
        return ("class CheckoutPage(BasePage):\n    INVENTORY_PAGE = \"checkout\"\n"
                "    def apply_coupon(self):\n        self.click(self.sel(\"coupon\"))\n")

    with patch.object(a2, "get_tracker", return_value=jira), \
         patch.object(a2, "get_repo_host", return_value=gh), patch.object(a2, "LLMClient"), \
         patch.object(a2, "build_plan", return_value=plan), \
         patch.object(a2, "generate_file_content", side_effect=gen), \
         patch.object(a2, "_attempt_step_coverage_repair", side_effect=lambda g, *a, **k: g), \
         patch.object(a2, "_validate_generated_files"):
        result = a2.run("SBX-70")
    assert result["uses_planned"] == ["checkout.coupon"]
    assert "Uses planned elements - not deployed yet" in gh.prs[0]["body"]
    assert "`checkout.coupon`" in gh.prs[0]["body"]


def test_a_held_page_confirms_nothing():
    """Most selectors stale: the page did not render as itself - nothing on it
    is edited, a planned key found there included."""
    stale = [{"element": "save", "selector": "#save"}, {"element": "help", "selector": "#help"}]
    inv = _inv()
    upd = iu.build_update(_drift(live=[LIVE], missing=stale), inv, set())
    assert upd.held_pages and upd.confirmed == [] and upd.inventory == inv


# ── a new element on EVERY page is a shared section: listed, not added ───
# Found by the real-browser run of P1-4: a menu link no key covered yet was
# added once per page, the same night - PR #228's duplication for an element
# not in the inventory at all.

def _pages_drift(new_by_page, extra_pages=(), **kw):
    names = list(new_by_page) + list(extra_pages)
    return {"pages_checked": len(names),
            "pages": {n: {"missing": [], "ambiguous": [], "new_data_tests": [], "reappeared": []}
                      for n in names},
            "new_elements": new_by_page, "new_element_declarations": {}, **kw}


def _pages_inv(*names, **extra):
    inv = {"pages": {n: {"url": f"/{n}", "elements": {"x": f"#{n}-x"}} for n in names}}
    for n, fields in extra.items():
        inv["pages"][n].update(fields)
    return inv


MENU = {"menu_link": "role=link[name='Menu']"}


def test_a_new_element_on_every_measured_page_is_listed_once_not_added():
    drift = _pages_drift({"a": {**MENU, "own_a": "#oa"}, "b": dict(MENU), "c": dict(MENU)})
    upd = iu.build_update(drift, _pages_inv("a", "b", "c"), set())
    assert [(r["page"], r["element"]) for r in upd.added] == [("a", "own_a")]
    assert upd.layout == [{"element": "menu_link", "selector": "role=link[name='Menu']",
                           "pages": ["a", "b", "c"]}]
    body = iu.render_body(upd, "inv.json", "d")
    assert "Not added - new on every page: a shared section (1)" in body and "a, b, c" in body


def test_an_element_on_some_pages_only_is_page_specific_and_added():
    drift = _pages_drift({"a": dict(MENU), "b": dict(MENU)}, extra_pages=["c"])
    upd = iu.build_update(drift, _pages_inv("a", "b", "c"), set())
    assert {(r["page"], r["element"]) for r in upd.added} == {("a", "menu_link"), ("b", "menu_link")}
    assert upd.layout == []


@pytest.mark.parametrize("minimum, layout", [(3, False), (2, True)])
def test_below_the_minimum_page_count_nothing_is_called_layout(minimum, layout):
    drift = _pages_drift({"a": dict(MENU), "b": dict(MENU)})
    upd = iu.build_update(drift, _pages_inv("a", "b"), set(), layout_min_pages=minimum)
    assert bool(upd.layout) is layout and bool(upd.added) is not layout


def test_a_planned_page_not_live_does_not_count_as_measured():
    drift = _pages_drift({"a": dict(MENU), "b": dict(MENU), "c": dict(MENU)}, extra_pages=["w"])
    inv = _pages_inv("a", "b", "c", "w", w={"planned_page": True, "planned": ["x"]})
    upd = iu.build_update(drift, inv, set())
    assert upd.layout and upd.layout[0]["pages"] == ["a", "b", "c"] and upd.added == []


def test_the_minimum_is_configured_and_passed():
    import yaml
    from core.impact_settings import DEFAULTS
    cfg = yaml.safe_load(open("config/config.yaml", encoding="utf-8"))
    shipped = cfg["agents"]["agent0_impact"]["inventory_update"]
    assert shipped["layout_min_pages"] == DEFAULTS["inventory_update"]["layout_min_pages"] == 3
    src = open("scripts/propose_inventory_update.py", encoding="utf-8").read()
    assert 'layout_min_pages=int(cfg["layout_min_pages"])' in src
