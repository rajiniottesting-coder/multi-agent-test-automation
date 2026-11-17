"""PW2: a test failing on main because a selector changed - the element is found
live with its new selector, proposed in one pull request, and no defect is
raised for it while the fix is in review.

core/selector_heal.py (pure), scripts/heal_selectors.py (orchestration: the
live reading, the model, the host and the tracker faked), the triage's
`healed` input, and the nightly inventory update leaving a key in an open heal
pull request alone. Generic example data only: no application is named.
"""
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

import pytest

from core import inventory_update as iu
from core import selector_heal as sh
from scripts import heal_selectors as hs

NEVER = 'TimeoutError: Locator.click: Timeout 30000ms exceeded.\nCall log:\n  - waiting for locator("#save-btn")'
HIDDEN = 'unexpected value "hidden" - PRESENT in the DOM but HIDDEN'
KINDS = ["element never appeared - probably the wrong page", "element never appeared",
         "readiness probe returned False"]


def _case(name, msg=NEVER, retried=True, outage=False, outcome="failed", module="test_orders"):
    props = []
    if retried:
        props.append('<property name="retried" value="1"/>')
    if outage:
        props.append('<property name="outage" value="1"/>')
    body = "" if outcome == "passed" else f'<failure message="x"><![CDATA[{msg}]]></failure>'
    return (f'<testcase classname="tests.step_defs.{module}" name="{name}">'
            f'<properties>{"".join(props)}</properties>{body}</testcase>')


def _root(*cases):
    return ET.fromstring(f"<testsuites><testsuite>{''.join(cases)}</testsuite></testsuites>")


# ── which failures ──────────────────────────────────────────────────────

def test_only_failures_a_changed_selector_can_explain_are_checked():
    root = _root(_case("test_save"), _case("test_hidden", msg=HIDDEN),
                 _case("test_once", retried=False), _case("test_down", outage=True),
                 _case("test_ok", outcome="passed"))
    got = sh.healable(root, KINDS)
    assert [(t, label) for t, label, _x in got] == [
        ("tests.step_defs.test_orders::test_save",
         "element never appeared - probably the wrong page")]
    assert [t for t, *_ in sh.healable(root, KINDS, only_after_retry=False)] == [
        "tests.step_defs.test_orders::test_save", "tests.step_defs.test_orders::test_once"]


# ── which keys ──────────────────────────────────────────────────────────

def _graph():
    s1 = SimpleNamespace(file="features/orders.feature", title="Save an order",
                         steps=(("when", "I save the order"),),
                         elements=frozenset({("orders", "save_button"), ("menu", "start_link")}))
    s2 = SimpleNamespace(file="features/orders.feature", title="List orders",
                         steps=(), elements=frozenset({("orders", "orders_table")}))
    return SimpleNamespace(scenarios=[s1, s2], selectors={
        ("orders", "save_button"): "#save-btn", ("menu", "start_link"): "a.home",
        ("orders", "orders_table"): "#orders"})


T1 = "tests.step_defs.test_orders::test_save_an_order"
T2 = "tests.step_defs.test_orders::test_list_orders[row 1]"


def test_each_failing_test_reaches_its_scenarios_keys():
    got = sh.keys_by_test(_graph(), [T1, T2, "tests.step_defs.test_x::test_unknown"])
    assert got[T1] == {("orders", "save_button"), ("menu", "start_link")}
    assert got[T2] == {("orders", "orders_table")}
    assert got["tests.step_defs.test_x::test_unknown"] == set()


def test_a_quoted_selector_narrows_the_keys_to_read():
    keys = {("orders", "save_button"), ("menu", "start_link")}
    sel = _graph().selectors
    assert sh.narrow(keys, NEVER, sel) == {("orders", "save_button")}
    assert sh.narrow(keys, "Timeout waiting for get_by_role('button')", sel) == keys
    quoted = {("p", "k"): "[data-qa=\"x\"]"}
    assert sh.narrow(set(quoted), 'waiting for locator("[data-qa=\\"x\\"]")', quoted) == set(quoted)


def test_the_page_most_failing_tests_reach_is_read_first():
    reached = {"a": {("orders", "x"), ("menu", "y")}, "b": {("orders", "z")}, "c": {("cart", "q")}}
    assert sh.pages_to_check(reached, 2) == ["orders", "cart"]
    assert sh.pages_to_check(reached, 5) == ["orders", "cart", "menu"]


# ── the reading of one page ─────────────────────────────────────────────

REPORT = {"pages": {"orders": {"missing": [{"element": "save_button", "selector": "#save-btn"}]}},
          "new_elements": {"orders": {"save_button": "#save", "save_order_button": "#save-order",
                                      "row_links": ".row a", "fragile": "div > span"}},
          "new_element_declarations": {"orders": {"unstable": ["fragile"],
                                                  "multi_match": ["row_links"]}}}


def test_stale_keys_and_durable_candidates_are_read_from_the_report():
    assert sh.stale_keys(REPORT, "orders") == {"save_button": "#save-btn"}
    cands, families = sh.candidates(REPORT, "orders")
    assert set(cands) == {"save_button", "save_order_button", "row_links"}
    assert families == {"row_links"}
    assert sh.stale_keys(REPORT, "cart") == {} and sh.candidates(REPORT, "cart") == ({}, set())


def test_a_family_key_heals_only_to_a_family_and_the_reverse():
    entry = {"multi_match": ["rows"]}
    assert sh.fits("rows", entry, "row_links", {"row_links"}) == ""
    assert "list of elements" in sh.fits("rows", entry, "save", {"row_links"})
    assert "names one element" in sh.fits("save", entry, "row_links", {"row_links"})
    assert sh.fits("save", entry, "save_order_button", {"row_links"}) == ""


class _LLM:
    def __init__(self, answer):
        self.answer, self.prompts = answer, []

    def invoke_structured(self, system_prompt, user_prompt, output_schema):
        self.prompts.append(user_prompt)
        return output_schema(**self.answer)


def test_the_model_chooses_among_the_live_elements_only():
    cands = {"save_order_button": "#save-order"}
    assert sh.choose(_LLM({"element": "save_order_button", "why": "same Save button"}), "p",
                     cands) == ("save_order_button", "same Save button")
    name, why = sh.choose(_LLM({"element": "invented", "why": "x"}), "p", cands)
    assert name == "" and "not one of the live elements" in why


def test_the_prompt_carries_the_key_its_note_the_steps_and_the_candidates():
    tpl = (Path(__file__).resolve().parents[2] / "prompts" / "heal_selector.md").read_text()
    text = sh.heal_prompt(tpl, "orders", "/orders", "save_button", "#save-btn", "the Save button",
                          [("when", "I save the order")], {"save_order_button": "#save-order"})
    for part in ("`orders` (/orders)", "`save_button`", "`#save-btn`", "the Save button",
                 "- when I save the order", "- save_order_button: #save-order"):
        assert part in text
    assert "{" not in text


# ── the change ──────────────────────────────────────────────────────────

INV = {"pages": {"orders": {"url": "/orders", "elements": {
    "save_button": "#save-btn", "cancel_button": "#cancel"}}}}


def test_apply_replaces_the_selector_and_refuses_a_duplicate():
    heals = [{"page": "orders", "key": "save_button", "old": "#save-btn", "new": "#save"},
             {"page": "orders", "key": "cancel_button", "old": "#cancel", "new": "#save"},
             {"page": "orders", "key": "gone_key", "old": "#g", "new": "#h"}]
    new, refused = sh.apply(INV, heals)
    assert new["pages"]["orders"]["elements"] == {"save_button": "#save",
                                                  "cancel_button": "#cancel"}
    assert [(r["key"], r["why"]) for r in refused] == [
        ("cancel_button", "another key of the page already uses that selector"),
        ("gone_key", "the key is not on the page any more")]
    assert INV["pages"]["orders"]["elements"]["save_button"] == "#save-btn"   # input untouched


def test_a_test_is_healed_only_when_every_stale_key_it_reaches_is_fixed():
    reached = {"a": {("orders", "save_button")},
               "b": {("orders", "save_button"), ("orders", "total")},
               "c": {("orders", "cancel_button")},
               "d": {("cart", "x")}}
    stale = {("orders", "save_button"), ("orders", "total")}
    healed, not_healed = sh.healed_tests(reached, stale, {("orders", "save_button"): "pr"},
                                         checked={"orders"})
    assert healed == {"a": ["orders.save_button"]}
    assert "orders.total" in not_healed["b"]
    assert "matches on the live page" in not_healed["c"]
    assert "not read live" in not_healed["d"]


def test_the_body_lists_each_key_and_is_read_back():
    heals = [{"page": "orders", "key": "save_button", "old": "#save-btn", "new": "#save",
              "how": "the live element has the key's name"}]
    body = sh.render_body(heals, {"t1": ["orders.save_button"]}, inventory_path="inv.json",
                          run_url="https://ci.example/1")
    assert sh.pending_keys(body) == {("orders", "save_button")}
    assert "`#save`" in body and "`t1`" in body and "https://ci.example/1" in body
    assert sh.pending_keys("no marker") == set()


def test_the_report_round_trips(tmp_path):
    path = tmp_path / "heal.json"
    sh.write_report(path, {"t1": ["orders.save_button"]}, {"t2": "why"}, {"t1": "u/1"})
    assert sh.read_report(path) == {"t1": {"keys": ["orders.save_button"], "pr": "u/1"}}
    assert sh.read_report(tmp_path / "none.json") == {}


# ── the orchestration ───────────────────────────────────────────────────

class _Host:
    def __init__(self, open_prs=None):
        self.prs, self.files, self.branches = [], {}, set()
        self.open = open_prs or {}           # {(prefix, branch): inventory text}

    def list_open_prs(self, prefix="", strict=False):
        return [{"number": i, "head_ref": b, "url": f"https://host.example/pr/{i}"}
                for i, ((p, b), _t) in enumerate(self.open.items(), 1) if p == prefix]

    def get_file_content(self, path, branch):
        for (p, b), text in self.open.items():
            if b == branch:
                return text
        raise FileNotFoundError(branch)

    def branch_exists(self, b):
        return b in self.branches

    def create_branch(self, b, base):
        self.branches.add(b)

    def create_or_update_file(self, path, text, msg, branch):
        self.files[(branch, path)] = text

    def open_pull_request(self, title, body, branch, base):
        self.prs.append((title, body, branch))
        return f"https://host.example/pr/new{len(self.prs)}"

    def delete_branch(self, b):
        self.branches.discard(b)


@pytest.fixture
def world(tmp_path, monkeypatch):
    inv_path = tmp_path / "inv.json"
    inv = {"pages": {"orders": {"url": "/orders", "elements": {
        "save_button": "#save-btn", "orders_table": "#orders"},
        "elements_notes": {"save_button": "the Save button"}},
        "menu": {"url": "/", "always": True, "elements": {"start_link": "a.home"}}}}
    inv_path.write_text(json.dumps(inv, indent=2) + "\n")
    ctx = SimpleNamespace(inventory_path=lambda: inv_path, inventory_file="inv.json")
    monkeypatch.setattr(hs.AppContext, "load", staticmethod(lambda: ctx))
    monkeypatch.setattr("core.impact_graph.build_impact_graph", lambda root: _graph())
    reads = []

    def read(page):
        reads.append(page)
        return REPORT if page == "orders" else {"pages": {page: {"missing": []}}}
    s = {"heal_failure_kinds": KINDS, "heal_branch_prefix": "inventory-heal/",
         "heal_max_pages": 5}

    def go(*cases, host=None, llm=None, dry_run=False):
        host = host if host is not None else _Host()
        out = hs.heal(_root(*cases), s=s, run_url="https://ci.example/9",
                      dry_run=dry_run, host=host, tracker=None,
                      llm_factory=(lambda: llm) if llm else None, read=read)
        return out, host
    return go, reads, inv


def test_a_key_whose_live_element_has_its_name_is_healed_without_a_model(world):
    go, reads, _inv = world
    out, host = go(_case("test_save_an_order"))
    assert reads == ["orders"]                               # narrowed by the quoted selector
    assert [(h["key"], h["new"]) for h in out["heals"]] == [("save_button", "#save")]
    assert out["healed"] == {T1: ["orders.save_button"]}
    (title, body, branch), = host.prs
    assert branch.startswith("inventory-heal/") and sh.pending_keys(body) == {("orders",
                                                                              "save_button")}
    written = json.loads(host.files[(branch, "inv.json")])
    assert written["pages"]["orders"]["elements"]["save_button"] == "#save"
    assert written["pages"]["orders"]["elements_notes"] == {"save_button": "the Save button"}
    assert out["prs"][T1] == "https://host.example/pr/new1"


def _heal(report, llm=None, host=None):
    s = {"heal_failure_kinds": KINDS, "heal_branch_prefix": "inventory-heal/",
         "heal_max_pages": 5}
    host = host if host is not None else _Host()
    out = hs.heal(_root(_case("test_save_an_order")), s=s, run_url="r",
                  dry_run=False, host=host, tracker=None,
                  llm_factory=(lambda: llm) if llm else None, read=lambda page: report)
    return out, host


def test_otherwise_one_model_call_chooses(world):
    report = json.loads(json.dumps(REPORT))
    del report["new_elements"]["orders"]["save_button"]
    llm = _LLM({"element": "save_order_button", "why": "the same Save control"})
    out, host = _heal(report, llm)
    assert [(h["key"], h["new"]) for h in out["heals"]] == [("save_button", "#save-order")]
    assert "one model call" in out["heals"][0]["how"] and len(llm.prompts) == 1
    assert "the Save button" in llm.prompts[0] and "I save the order" in llm.prompts[0]
    assert host.prs and out["healed"] == {T1: ["orders.save_button"]}


def test_a_model_that_finds_none_leaves_the_failure_to_the_triage(world):
    report = json.loads(json.dumps(REPORT))
    del report["new_elements"]["orders"]["save_button"]
    out, host = _heal(report, _LLM({"element": "", "why": "none is the Save button"}))
    assert out["healed"] == {} and not host.prs
    assert "no live element found for orders.save_button" in out["not_healed"][T1]


def test_no_live_element_leaves_the_failure_to_the_triage(world):
    empty = {"pages": REPORT["pages"], "new_elements": {"orders": {}}}
    out, host = _heal(empty, _LLM({"element": "x", "why": "never asked"}))
    assert out["healed"] == {} and not host.prs
    assert "no live element found for orders.save_button" in out["not_healed"][T1]


def test_a_key_an_open_pull_request_changes_is_left_to_it(world):
    go, reads, inv = world
    theirs = json.loads(json.dumps(inv))
    theirs["pages"]["orders"]["elements"]["save_button"] = "#save"
    host = _Host({("inventory-heal/", "inventory-heal/2026-11-16"): json.dumps(theirs)})
    out, host = go(_case("test_save_an_order"), host=host)
    assert not host.prs and out["heals"] == []
    assert out["healed"] == {T1: ["orders.save_button"]}
    assert out["prs"][T1] == "https://host.example/pr/1"


def test_a_test_whose_keys_all_match_is_not_healed(world):
    go, _reads, _inv = world
    out, host = go(_case("test_list_orders[row 1]", msg="TimeoutError: waiting for locator('#x')"))
    assert out["healed"] == {} and not host.prs
    assert "matches on the live page" in out["not_healed"][T2]


def test_a_dry_run_opens_nothing_and_heals_no_test(world):
    go, _reads, _inv = world
    out, host = go(_case("test_save_an_order"), dry_run=True)
    assert out["healed"] == {} and not host.prs and out["heals"]


def test_nothing_failing_reads_nothing(world):
    go, reads, _inv = world
    out, host = go(_case("test_ok", outcome="passed"))
    assert out["healed"] == {} and reads == [] and not host.prs


def test_plan_says_whether_a_browser_is_needed(tmp_path, monkeypatch):
    out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    (tmp_path / "junit.xml").write_text(
        f"<testsuites><testsuite>{_case('test_save')}</testsuite></testsuites>")
    assert hs.main(["--reports-dir", str(tmp_path), "--plan"]) == 0
    assert out.read_text().strip() == "needed=true"
    out.write_text("")
    (tmp_path / "junit.xml").write_text(
        f"<testsuites><testsuite>{_case('test_h', msg=HIDDEN)}</testsuite></testsuites>")
    assert hs.main(["--reports-dir", str(tmp_path), "--plan"]) == 0
    assert out.read_text().strip() == "needed=false"


def test_no_report_needs_nothing(tmp_path, monkeypatch):
    out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    assert hs.main(["--reports-dir", str(tmp_path / "none"), "--plan"]) == 0
    assert out.read_text().strip() == "needed=false"


# ── the triage raises no defect for a healed test ───────────────────────

def test_the_triage_raises_no_defect_for_a_healed_test(monkeypatch, tmp_path):
    from tests.unit.test_defect_triage import BUG, _bugs, _case as tcase, _junit
    from core import defects
    from core import pipeline_health as ph
    from scripts import triage_failures as tf
    from tests.sandbox.fake_jira import FakeJira, jira_client_over
    ph.reset_cache()
    fake = FakeJira()
    fake.add("Story", "Orders", key="SBX-1")
    jira = jira_client_over(fake, monkeypatch)
    real = defects.section("defects")
    monkeypatch.setattr(defects, "settings", lambda: {**real, "max_new_per_run": 10})
    features = tmp_path / "features"
    features.mkdir()
    never = "TimeoutError: Locator.click: Timeout 30000ms exceeded"
    junit = _junit(tmp_path, tcase("test_a", "failed", msg=never),
                   tcase("test_b", "failed", msg=never))
    healed = {"tests.step_defs.test_cart::test_a": {"keys": ["orders.save_button"],
                                                     "pr": "https://host.example/pr/5"}}
    out = tf.run(jira, junit, "https://ci.example/1", features, healed=healed)
    assert out["healed"] == ["tests.step_defs.test_cart::test_a (https://host.example/pr/5)"]
    assert len(out["raised"]) == 1 and len(_bugs(fake)) == 1
    assert "test_b" in next(iter(_bugs(fake).values()))["summary"]
    assert BUG
    ph.reset_cache()


def test_triage_reads_the_heal_report_from_the_reports_dir(tmp_path, monkeypatch):
    from scripts import triage_failures as tf
    sh.write_report(tmp_path / sh.HEAL_FILE, {"t": ["p.k"]}, {}, {"t": "u"})
    seen = {}
    monkeypatch.setattr("integrations.tracker.get_tracker", lambda: object())
    monkeypatch.setattr(tf, "run", lambda *a, **k: seen.update(k) or {"report": True})
    assert tf.main(["--reports-dir", str(tmp_path)]) == 0
    assert seen["healed"] == {"t": {"keys": ["p.k"], "pr": "u"}}


# ── the nightly update leaves a key in an open heal pull request alone ─

def test_the_nightly_update_keeps_a_key_an_open_heal_proposes():
    drift = {"pages": {"orders": {"missing": [{"element": "save_button",
                                               "selector": "#save-btn"}]}},
             "new_elements": {"orders": {"save_button": "#save"}}}
    upd = iu.build_update(drift, INV, set(),
                          pending={("orders", "save_button"): "https://host.example/pr/5"})
    assert not upd.replaced and not upd.removed and not upd.added
    assert upd.kept_missing == [{"page": "orders", "element": "save_button",
                                 "selector": "#save-btn",
                                 "why": "a selector-heal pull request proposes its new "
                                        "selector (https://host.example/pr/5)"}]
    plain = iu.build_update(drift, INV, set())
    assert [r["element"] for r in plain.replaced] == ["save_button"]       # unchanged without


def test_changed_keys_are_read_from_a_branch():
    theirs = json.loads(json.dumps(INV))
    theirs["pages"]["orders"]["elements"]["save_button"] = "#save"
    theirs["pages"]["orders"]["elements"]["new_key"] = "#n"
    host = _Host({("p/", "p/x"): json.dumps(theirs)})
    assert iu.changed_keys_on_branch(host, "inv.json", "p/x", INV) == {
        ("orders", "save_button"): "#save"}
    assert iu.keys_in_open_prs(host, "p/", "inv.json", INV) == {
        ("orders", "save_button"): "https://host.example/pr/1"}
    assert iu.changed_keys_on_branch(host, "inv.json", "nope", INV) == {}


def test_a_heal_a_person_closed_is_never_proposed_again(world):
    go, _reads, _inv = world
    body = sh.render_body([{"page": "orders", "key": "save_button", "old": "#save-btn",
                            "new": "#save", "how": "x"}], {}, inventory_path="i", run_url="r")
    assert sh.proposed_changes(body) == {("orders", "save_button", "#save")}
    host = _Host()
    host.list_closed_prs = lambda prefix, limit=100: [{"number": 3, "merged": False,
                                                       "body": body}]
    out, host = go(_case("test_save_an_order"), host=host)
    assert out["heals"] == [] and not host.prs and out["healed"] == {}
    merged = _Host()
    merged.list_closed_prs = lambda prefix, limit=100: [{"number": 3, "merged": True,
                                                         "body": body}]
    out, merged = go(_case("test_save_an_order"), host=merged)
    assert [h["new"] for h in out["heals"]] == ["#save"]          # a merged one says nothing


def test_the_nightly_update_does_not_add_the_element_a_heal_gives_its_key():
    drift = {"pages": {"orders": {"missing": [{"element": "save_button",
                                               "selector": "#save-btn"}]}},
             "new_elements": {"orders": {"submit_button": "#save", "print_button": "#print"}}}
    upd = iu.build_update(
        drift, INV, set(), pending={("orders", "save_button"): "u/5"},
        claimed={("orders", "#save"): "orders.save_button (u/5)"})
    assert [r["element"] for r in upd.added] == ["print_button"]
    assert upd.refused == [{"page": "orders", "element": "submit_button", "selector": "#save",
                            "refused": "a selector-heal pull request gives this element to "
                                       "orders.save_button (u/5)"}]
    assert [r["element"] for r in iu.build_update(drift, INV, set()).added] == \
        ["print_button", "submit_button"]                       # unchanged without a claim


def test_claims_carry_the_selector_each_open_pull_request_gives():
    theirs = json.loads(json.dumps(INV))
    theirs["pages"]["orders"]["elements"]["save_button"] = "#save"
    host = _Host({("p/", "p/x"): json.dumps(theirs)})
    assert iu.claims_in_open_prs(host, "p/", "inv.json", INV) == {
        ("orders", "save_button"): {"url": "https://host.example/pr/1", "selector": "#save"}}
