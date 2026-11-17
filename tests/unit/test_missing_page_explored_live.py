"""PW1: a story refused for a page the inventory lacks - the page is found by a
link on the application, read live and proposed, instead of only refused.

core/page_explore.py (pure), scripts/explore_missing_pages.py (orchestration,
browser and model faked), scripts/resume_explored_story.py, the request
core/blocked.py records, and check_inventory_staleness --inventory. Generic
example data only: no application is named.
"""
import json
import sys
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from core import blocked
from core import inventory_update as iu
from core import page_explore as pe
from scripts import explore_missing_pages as em
from scripts import resume_explored_story as rs

BASE = "https://app.example"
INV = {"pages": {
    "home": {"url": "/", "elements": {"title": "h1"}},
    "orders": {"url": "/orders", "elements": {"orders_table": "#orders"}},
    "order_detail": {"url": "/orders/{order_id}", "url_sample": "/orders/1",
                     "elements": {"order_total": "#total"}},
}}
UNKNOWN_PAGE = ("Selector inventory error in pages/reports_page.py: class ReportsPage sets "
                "INVENTORY_PAGE = 'reports_list', which is not a page in the app inventory")


# ── what a refusal asks for ─────────────────────────────────────────────

def test_a_page_the_generated_code_named_is_requested():
    assert pe.requested([UNKNOWN_PAGE], INV) == {"pages": ["reports_list"], "reasons": [],
                                                  "known_pages": {}}


def test_a_plan_reason_naming_no_known_page_is_requested():
    why = "PRJ-7: needs the export button on the reports page, not in the app inventory"
    assert pe.requested([why], INV) == {"pages": [], "reasons": [why], "known_pages": {}}


def test_a_missing_element_on_a_known_page_is_asked_of_that_page():
    for why, page in (("PRJ-7: needs the print button on orders, not in the app inventory",
                       "orders"),
                      ("PRJ-7: needs the total on the order detail page, not in the app "
                       "inventory", "order_detail")):
        assert pe.requested([why], INV) == {"pages": [], "reasons": [],
                                            "known_pages": {page: [why]}}


def test_a_key_the_validator_found_on_no_page_is_asked_of_its_page():
    err = ("Selector inventory error in pages/orders_page.py: self.sel('print_button'), but "
           "'print_button' is not an element on inventory page 'orders', nor on any other page")
    assert pe.requested([err], INV) == {"pages": [], "reasons": [],
                                        "known_pages": {"orders": ["print_button"]}}
    typo = err.replace("print_button", "orders_tabel")              # a misspelling: repaired
    assert pe.requested([typo], INV) is None


def test_other_refusals_request_nothing():
    assert pe.requested(["Step fidelity error: the step clicks nothing"], INV) is None
    assert pe.requested([], INV) is None


def test_a_misspelt_known_page_is_not_requested():
    err = UNKNOWN_PAGE.replace("reports_list", "orderz")
    assert pe.requested([err], INV) is None


def test_requests_are_one_per_story(tmp_path):
    path = tmp_path / "r.json"
    pe.record_request("PRJ-1", {"pages": ["a"], "reasons": []}, path)
    pe.record_request("PRJ-2", {"pages": ["b"], "reasons": []}, path)
    pe.record_request("PRJ-1", {"pages": ["c"], "reasons": []}, path)
    got = {r["story"]: r["pages"] for r in pe.read_requests(path)}
    assert got == {"PRJ-1": ["c"], "PRJ-2": ["b"]}
    assert pe.read_requests(tmp_path / "missing.json") == []


class _Comments:
    def __init__(self):
        self.posted = []

    def get_comments(self, key):
        return []

    def add_comment(self, key, text):
        self.posted.append((key, text))


def test_a_refusal_records_a_request_only_where_the_workflow_asks(tmp_path, monkeypatch):
    path = tmp_path / "explore.json"
    monkeypatch.delenv("EXPLORE_REQUESTS_FILE", raising=False)
    monkeypatch.setattr("core.inventory_planned.load_inventory", lambda ctx: INV)
    blocked.post_blocked_once(_Comments(), "PRJ-1", "f" * 16, [UNKNOWN_PAGE])
    assert not path.exists()
    monkeypatch.setenv("EXPLORE_REQUESTS_FILE", str(path))
    blocked.post_blocked_once(_Comments(), "PRJ-1", "f" * 16, [UNKNOWN_PAGE])
    assert pe.read_requests(path) == [{"story": "PRJ-1", "pages": ["reports_list"],
                                       "reasons": [], "known_pages": {}}]


def test_a_refusal_for_anything_else_records_nothing(tmp_path, monkeypatch):
    path = tmp_path / "explore.json"
    monkeypatch.setenv("EXPLORE_REQUESTS_FILE", str(path))
    monkeypatch.setattr("core.inventory_planned.load_inventory", lambda ctx: INV)
    blocked.post_blocked_once(_Comments(), "PRJ-1", "f" * 16, ["Coverage gate failed"])
    assert not path.exists()


def test_exploring_switched_off_records_nothing(tmp_path, monkeypatch):
    path = tmp_path / "explore.json"
    monkeypatch.setenv("EXPLORE_REQUESTS_FILE", str(path))
    monkeypatch.setattr("core.inventory_planned.load_inventory", lambda ctx: INV)
    real = pe.settings()
    monkeypatch.setattr(pe, "settings", lambda: {**real, "explore_missing_pages": False})
    blocked.post_blocked_once(_Comments(), "PRJ-1", "f" * 16, [UNKNOWN_PAGE])
    assert not path.exists()


def test_the_blocked_comment_is_unchanged(monkeypatch):
    c = _Comments()
    monkeypatch.delenv("EXPLORE_REQUESTS_FILE", raising=False)
    assert blocked.post_blocked_once(c, "PRJ-1", "f" * 16, [UNKNOWN_PAGE])
    assert c.posted and "plan_inventory page" in c.posted[0][1]


# ── the links ───────────────────────────────────────────────────────────

FOUND = {
    "(root)": [{"href": "/reports_list", "text": "Reports"}, {"href": "/orders", "text": "Orders"},
               {"href": "/orders/7", "text": "Order 7"}, {"href": "#top", "text": "Top"},
               {"href": "https://other.example/x", "text": "Elsewhere"},
               {"href": "/logout", "text": "Sign out"}, {"href": "/img/a.png", "text": ""},
               {"href": "/help/", "text": "Help"}],
    "orders": [{"href": "/reports_list", "text": "All reports"},
               {"href": "/delete_account", "text": "Delete my account"}],
}


def test_candidates_are_the_pages_the_inventory_lacks():
    cands, never = pe.candidate_links(FOUND, INV, BASE, never=["logout", "delete"])
    assert [c["path"] for c in cands] == ["/reports_list", "/help"]
    assert cands[0] == {"path": "/reports_list", "texts": ["Reports", "All reports"],
                        "linked_from": ["(root)", "orders"]}
    assert never == ["/delete_account", "/logout"]


def test_candidates_are_capped():
    cands, _ = pe.candidate_links(FOUND, INV, BASE, limit=1)
    assert len(cands) == 1


def test_a_link_carrying_the_page_name_is_chosen_without_a_model():
    cands, _ = pe.candidate_links(FOUND, INV, BASE)
    assert pe.by_name(["reports_list"], cands) == "/reports_list"
    assert pe.by_name(["Reports-List"], cands) == "/reports_list"
    assert pe.by_name(["something_else"], cands) is None
    assert pe.by_name([], cands) is None
    two = cands + [{"path": "/a/reports_list", "texts": [], "linked_from": []}]
    assert pe.by_name(["reports_list"], two) is None          # ambiguous: the model decides


class _LLM:
    def __init__(self, answer):
        self.answer, self.prompts = answer, []

    def invoke_structured(self, system_prompt, user_prompt, output_schema):
        self.prompts.append(user_prompt)
        return output_schema(**self.answer)


def test_the_model_chooses_among_the_listed_links_only():
    cands, _ = pe.candidate_links(FOUND, INV, BASE)
    assert pe.choose_link(_LLM({"path": "/help", "why": "the steps open Help"}), "p", cands) \
        == ("/help", "the steps open Help")
    path, why = pe.choose_link(_LLM({"path": "/invented", "why": "x"}), "p", cands)
    assert path == "" and "not one of the links" in why
    assert pe.choose_link(_LLM({"path": "", "why": "none fits"}), "p", cands) == ("", "none fits")


def test_the_prompt_carries_the_story_the_refusal_and_the_links():
    cands, _ = pe.candidate_links(FOUND, INV, BASE)
    tpl = (pe.Path(__file__).resolve().parents[2] / "prompts" / "explore_page_link.md").read_text()
    text = pe.link_prompt(tpl, {"summary": "Export reports", "description": "As a user..."},
                          [{"key": "PRJ-9", "summary": "Open the reports list"}],
                          ["reports_list"], ["needs the reports page"], cands)
    for part in ("Export reports", "PRJ-9 Open the reports list", "reports_list",
                 "needs the reports page", "/reports_list", "'All reports'"):
        assert part in text
    assert "{" not in text.replace("{order_id}", "")


# ── the page ────────────────────────────────────────────────────────────

def test_the_page_takes_the_name_the_code_used_else_the_path():
    assert pe.page_name(["reports_list"], "/reports_list", INV) == "reports_list"
    assert pe.page_name([], "/help-centre", INV) == "help_centre"
    assert pe.page_name([], "/2024", INV) == "page_2024"
    assert pe.page_name(["orders"], "/orders-archive", INV) == "orders_2"


def test_with_page_adds_an_empty_page_or_says_why_not():
    out, why = pe.with_page(INV, "reports_list", "/reports_list", ["Reports"])
    assert why == "" and out["pages"]["reports_list"] == {
        "url": "/reports_list", "components": ["Reports"], "elements": {}}
    assert "reports_list" not in INV["pages"]                      # input untouched
    assert "already exists" in pe.with_page(INV, "orders", "/x")[1]
    assert "already page 'orders'" in pe.with_page(INV, "orders_list", "/orders/")[1]
    assert "starting with '/'" in pe.with_page(INV, "x", "x")[1]
    assert "snake_case" in pe.with_page(INV, "Bad-Name", "/x")[1]


def _drift(name, elements, unstable=(), families=()):
    return {"pages_checked": 1, "pages": {name: {"missing": [], "new_data_tests": []}},
            "new_elements": {name: elements},
            "new_element_declarations": {name: {"unstable": list(unstable),
                                                "multi_match": list(families),
                                                "conditional": [], "shared": {}}}}


def test_the_page_gets_the_elements_the_nightly_update_would_add():
    stub, _ = pe.with_page(INV, "reports_list", "/reports_list")
    drift = _drift("reports_list", {"reports_heading": "h2.title", "row_link": ".row a",
                                    "export_button": "#export", "fragile": "div > span"},
                   unstable=["fragile"], families=["row_link"])
    upd = iu.build_update(drift, stub, set(), max_additions_per_page=2, allow_removal=False)
    assert [r["element"] for r in upd.added] == ["export_button", "reports_heading"]
    assert [r["element"] for r in upd.fragile] == ["fragile"]
    assert [r["element"] for r in upd.over_cap] == ["row_link"]
    new = pe.proposed(INV, upd.inventory, "reports_list")
    assert set(new["pages"]) == set(INV["pages"]) | {"reports_list"}
    assert new["pages"]["reports_list"]["elements"] == {"export_button": "#export",
                                                        "reports_heading": "h2.title"}
    assert "multi_match" not in new["pages"]["reports_list"]     # no empty declaration
    assert {k: v for k, v in new["pages"].items() if k != "reports_list"} == INV["pages"]


def test_a_family_keeps_its_declaration():
    stub, _ = pe.with_page(INV, "reports_list", "/reports_list")
    upd = iu.build_update(_drift("reports_list", {"row_link": ".row a"}, families=["row_link"]),
                          stub, set(), allow_removal=False)
    page = pe.proposed(INV, upd.inventory, "reports_list")["pages"]["reports_list"]
    assert page["multi_match"] == ["row_link"]


def test_the_body_names_the_story_and_is_parsed_back():
    stub, _ = pe.with_page(INV, "reports_list", "/reports_list")
    upd = iu.build_update(_drift("reports_list", {"export_button": "#export"}), stub, set(),
                          allow_removal=False)
    body = pe.render_body("PRJ-7", "reports_list", "/reports_list", "the link's text", upd,
                          inventory_path="app_inventory/app.json", not_visited=["/logout"])
    assert pe.parse_body(body) == ("PRJ-7", "reports_list")
    assert "`export_button`" in body and "`/logout`" in body and "the link's text" in body
    assert pe.parse_body("a pull request without the line") is None


def test_settings_refuse_a_branch_prefix_with_an_issue_key(monkeypatch):
    monkeypatch.setattr("core.ops_settings.section",
                        lambda name: {"explore_branch_prefix": "explore/PRJ-1-",
                                      "heal_branch_prefix": "heal/"})
    with pytest.raises(ValueError, match="issue key"):
        pe.settings()


# ── the orchestration (browser, model, tracker and host faked) ─────────

class _Tracker:
    def __init__(self):
        self.comments = {}

    def get_story(self, key):
        return {"key": key, "summary": "Export reports", "description": "...",
                "components": ["Reports"]}

    def get_linked_test_cases(self, key):
        return [{"key": "PRJ-9", "summary": "Open the reports list"}]

    def get_comments(self, key):
        return self.comments.get(key, [])

    def add_comment(self, key, text):
        self.comments.setdefault(key, []).append(text)


class _Host:
    def __init__(self, open_prs=()):
        self.files, self.prs, self.branches, self._open = {}, [], set(), list(open_prs)

    def list_open_prs(self, prefix="", strict=False):
        return [{"number": n, "head_ref": f"{prefix}x", "url": f"u/{n}"} for n, _b in self._open]

    def get_pr_metadata(self, n):
        return {"body": dict(self._open)[n]}

    def branch_exists(self, b):
        return b in self.branches

    def create_branch(self, b, base):
        self.branches.add(b)

    def create_or_update_file(self, path, text, msg, branch):
        self.files[(branch, path)] = text

    def open_pull_request(self, title, body, branch, base):
        self.prs.append((title, body, branch))
        return f"https://host.example/pr/{len(self.prs)}"

    def delete_branch(self, b):
        self.branches.discard(b)


@pytest.fixture
def setup(monkeypatch, tmp_path):
    original = json.dumps(INV, indent=2) + "\n"
    ctx = SimpleNamespace(base_url=BASE, inventory_file="app_inventory/app.json")
    reads = []

    def fake_read(stub, name):
        reads.append((name, stub["pages"][name]["url"]))
        return _drift(name, {"export_button": "#export", "reports_heading": "h2"}), ""
    monkeypatch.setattr(em, "read_page", fake_read)

    def go(req, host=None, links=FOUND, llm=None, dry_run=False, open_prs=()):
        tracker = _Tracker()
        host = host or _Host()
        out = em.explore(req, tracker=tracker, host=host, inventory=INV, original=original,
                         ctx=ctx, s=pe.settings(), links=links, open_prs=list(open_prs),
                         dry_run=dry_run, llm_factory=lambda: llm)
        return out, tracker, host
    return go, reads


def test_a_page_named_by_the_code_is_proposed_without_a_model(setup):
    go, reads = setup
    out, tracker, host = go({"story": "PRJ-7", "pages": ["reports_list"], "reasons": []})
    assert out["status"] == "proposed" and reads == [("reports_list", "/reports_list")]
    (title, body, branch), = host.prs
    assert branch == "inventory-explore/reports-list" and "reports_list" in title
    written = json.loads(host.files[(branch, "app_inventory/app.json")])
    assert written["pages"]["reports_list"] == {
        "url": "/reports_list", "components": ["Reports"],
        "elements": {"export_button": "#export", "reports_heading": "h2"}}
    assert pe.parse_body(body) == ("PRJ-7", "reports_list")
    (comment,) = tracker.comments["PRJ-7"]
    assert comment.startswith(pe.MARKER) and "https://host.example/pr/1" in comment


def test_otherwise_one_model_call_chooses(setup, monkeypatch):
    go, reads = setup
    monkeypatch.setattr("core.usage_ledger.post_usage_to_story", lambda *a, **k: None)
    llm = _LLM({"path": "/help", "why": "the test cases open Help"})
    out, _t, host = go({"story": "PRJ-7", "pages": [], "reasons": ["needs a help page"]}, llm=llm)
    assert out["status"] == "proposed" and reads == [("help", "/help")]
    assert len(llm.prompts) == 1 and "needs a help page" in llm.prompts[0]
    assert "chosen among 2 link(s)" in host.prs[0][1]


def test_no_fitting_link_proposes_nothing_and_says_so(setup, monkeypatch):
    go, reads = setup
    monkeypatch.setattr("core.usage_ledger.post_usage_to_story", lambda *a, **k: None)
    out, tracker, host = go({"story": "PRJ-7", "pages": [], "reasons": ["x"]},
                            llm=_LLM({"path": "", "why": "none fits"}))
    assert out["status"] == "no_fit" and not host.prs and not reads
    assert "none fits" in tracker.comments["PRJ-7"][0]
    assert "plan_inventory page" in tracker.comments["PRJ-7"][0]


def test_no_link_at_all_proposes_nothing(setup):
    go, _ = setup
    out, tracker, host = go({"story": "PRJ-7", "pages": ["x"], "reasons": []}, links={})
    assert out["status"] == "no_link" and not host.prs and tracker.comments["PRJ-7"]


def test_an_open_proposal_is_never_doubled(setup):
    go, reads = setup
    out, tracker, host = go({"story": "PRJ-7", "pages": ["reports_list"], "reasons": []},
                            open_prs=[{"number": 4, "story": "PRJ-7", "page": "reports_list",
                                       "url": "u"}])
    assert out == {"story": "PRJ-7", "status": "open", "pr": 4}
    assert not host.prs and not reads and not tracker.comments


def test_a_page_that_cannot_be_read_is_not_proposed(setup, monkeypatch):
    go, _ = setup
    monkeypatch.setattr(em, "read_page", lambda stub, name: (None, "it did not load (HTTP 404)"))
    out, tracker, host = go({"story": "PRJ-7", "pages": ["reports_list"], "reasons": []})
    assert out["status"] == "not_read" and not host.prs
    assert "HTTP 404" in tracker.comments["PRJ-7"][0]


def test_a_page_with_no_durable_element_is_not_proposed(setup, monkeypatch):
    go, _ = setup
    monkeypatch.setattr(em, "read_page",
                        lambda stub, name: (_drift(name, {"f": "div > a"}, unstable=["f"]), ""))
    out, _t, host = go({"story": "PRJ-7", "pages": ["reports_list"], "reasons": []})
    assert out["status"] == "empty" and not host.prs


def test_a_dry_run_opens_and_posts_nothing(setup):
    go, _ = setup
    out, tracker, host = go({"story": "PRJ-7", "pages": ["reports_list"], "reasons": []},
                            dry_run=True)
    assert out["status"] == "dry_run" and not host.prs and not host.branches
    assert not tracker.comments


def test_no_requests_is_a_quiet_success(tmp_path, capsys):
    assert em.main(["--requests", str(tmp_path / "none.json")]) == 0
    assert "nothing to explore" in capsys.readouterr().out


# ── merging the proposal starts Agent 2 again ──────────────────────────

class _MergeHost:
    def __init__(self, body, story_pr=None, refuse=False):
        self.body, self.story_pr, self.refuse, self.started = body, story_pr, refuse, []

    def get_pr_metadata(self, n):
        return {"body": self.body}

    def find_open_pr_for_story(self, story):
        return self.story_pr

    def dispatch_workflow(self, wf, ref, inputs):
        if self.refuse:
            raise RuntimeError("403")
        self.started.append((wf, ref, inputs))


BODY = f"{pe.MARKER} story: PRJ-7 page: reports_list\n\n..."


def test_a_merged_proposal_starts_agent_2_on_its_story():
    tracker = _Tracker()
    host = _MergeHost(BODY)
    out = rs.resume(lambda: tracker, host, 12, "agent2_coder.yml")
    assert out == {"status": "started", "story": "PRJ-7"}
    assert host.started == [("agent2_coder.yml", "main", {"story_key": "PRJ-7"})]
    assert "started on this story again" in tracker.comments["PRJ-7"][0]


def test_any_other_merge_reads_one_pull_request_and_nothing_else():
    def no_tracker():
        raise AssertionError("the tracker is not needed")
    assert rs.resume(no_tracker, _MergeHost("a story pull request"), 3, "w.yml") == \
        {"status": "not_an_exploration"}


def test_a_story_with_an_open_pull_request_is_told_not_started():
    tracker = _Tracker()
    host = _MergeHost(BODY, story_pr={"number": 30})
    out = rs.resume(lambda: tracker, host, 12, "agent2_coder.yml")
    assert out["status"] == "story_pr_open" and not host.started
    assert "#30" in tracker.comments["PRJ-7"][0]


def test_a_refused_start_tells_the_story_to_run_agent_2_by_hand():
    tracker = _Tracker()
    out = rs.resume(lambda: tracker, _MergeHost(BODY, refuse=True), 12, "agent2_coder.yml")
    assert out["status"] == "error"
    assert "Run Agent 2 with this story's key" in tracker.comments["PRJ-7"][0]


# ── the nightly check reads an inventory it is given ───────────────────

def test_the_nightly_check_reads_the_inventory_it_is_given(tmp_path, monkeypatch):
    import scripts.check_inventory_staleness as chk
    committed = tmp_path / "committed.json"
    committed.write_text(json.dumps({"pages": {"home": {"url": "/", "elements": {"a": "#a"}}}}))
    given = tmp_path / "given.json"
    given.write_text(json.dumps({"pages": {
        "home": {"url": "/", "elements": {"a": "#a"}},
        "reports_list": {"url": "/reports_list", "elements": {}}}}))
    ctx = SimpleNamespace(name="Sample", base_url=BASE, inventory_path=lambda: committed,
                          inventory_file="committed.json")
    monkeypatch.setattr(chk.AppContext, "load", staticmethod(lambda: ctx))

    @contextmanager
    def fake_browser(headless=True):
        page = MagicMock()
        page.url = BASE + "/reports_list"
        yield page
    monkeypatch.setattr(chk, "browser_page", fake_browser)
    monkeypatch.setattr(chk, "resolve_selectors",
                        lambda page, url, sels, attrs, detail=None: ({}, set(), True))
    descriptors = [{"tag": "button", "attrs": {"id": "export"}, "text": "Export",
                    "renderedText": "Export", "label": "", "visible": True,
                    "thirdParty": False, "hasIconChild": False, "cssPath": ""}]
    monkeypatch.setattr(chk, "collect_uncovered",
                        lambda page, url, sels, attrs, **k: ("Reports", descriptors))
    out = tmp_path / "r.json"
    monkeypatch.setattr(sys, "argv", ["check", "--no-login", "--inventory", str(given),
                                      "--page", "reports_list", "--compare", "--json", str(out)])
    assert chk.main() == 0
    report = json.loads(out.read_text())
    assert list(report["pages"]) == ["reports_list"]
    assert report["new_elements"]["reports_list"]


def test_a_story_whose_proposal_was_closed_is_not_explored_again(setup):
    go, reads = setup
    req = {"story": "PRJ-7", "pages": ["reports_list"], "reasons": []}
    tracker, host = _Tracker(), _Host()
    out = em.explore(req, tracker=tracker, host=host, inventory=INV, original="{}",
                     ctx=SimpleNamespace(base_url=BASE, inventory_file="i.json"),
                     s=pe.settings(), links=FOUND, open_prs=[], dry_run=False,
                     llm_factory=lambda: None,
                     closed_prs=[{"number": 5, "story": "PRJ-7", "page": "reports_list"}])
    assert out == {"story": "PRJ-7", "status": "closed_before", "pr": 5}
    assert not host.prs and not reads


def test_closed_proposals_are_read_from_their_bodies():
    host = SimpleNamespace(list_closed_prs=lambda prefix, limit=100: [
        {"number": 5, "merged": False, "body": f"{pe.MARKER} story: PRJ-7 page: reports_list"},
        {"number": 6, "merged": True, "body": f"{pe.MARKER} story: PRJ-8 page: help"},
        {"number": 7, "merged": False, "body": "another pull request"}])
    assert em._closed_explore_prs(host, "inventory-explore/") == [
        {"number": 5, "story": "PRJ-7", "page": "reports_list"}]


def test_the_page_a_reason_names_is_read_from_its_on_phrase():
    far = ("PRJ-7: needs the API list on the API reference page reached from the home page, "
           "not in the app inventory")
    assert pe.requested([far], INV) == {"pages": [], "reasons": [far], "known_pages": {}}
    near = "PRJ-7: needs the export link on the orders page, not in the app inventory"
    assert pe.requested([near], INV)["known_pages"] == {"orders": [near]}
    vague = "PRJ-7: the orders export is not in the app inventory"
    assert pe.requested([vague], INV) is None          # no "on <page>": the cautious reading


# ── a page read for the first time: its headings and its template content ─

def test_headings_a_test_can_name_the_page_by():
    from inventory_tools import introspect as i
    assert i.heading_selector("  Reports  list ") == 'text="Reports list"'
    assert i.heading_selector('Say "hi"') is None and i.heading_selector("") is None
    assert i.heading_selector("x" * 81) is None
    texts = ["Reports list", "Filters", "Reports list", "2024 overview", "Menu"]
    counts = {'text="Reports list"': 1, 'text="Filters"': 2, 'text="2024 overview"': 1,
              'text="Menu"': 1}
    got = i.heading_elements(texts, counts, covered={'text="Menu"'}, taken={"x"})
    assert got == {"reports_list_heading": 'text="Reports list"',
                   "h_2024_overview_heading": 'text="2024 overview"'}
    assert i.heading_elements(["Reports list"], counts, set(), {"reports_list_heading"}) == {}


def test_list_items_another_pages_family_covers_are_this_pages_content():
    inv = {"pages": {
        "catalogue": {"url": "/catalogue", "elements": {"item_titles": ".list .title a",
                                                        "contact_email": "#email"},
                      "multi_match": ["item_titles"]},
        "menu": {"url": "/", "always": True, "elements": {"menu_links": "nav a"},
                 "multi_match": ["menu_links"]},
        "reports_list": {"url": "/reports_list", "elements": {}}}}
    drift = {"new_elements": {"reports_list": {"export_button": "#export"}},
             "new_element_declarations": {"reports_list": {"shared": {
                 "report_1_link": {"selector": "role=link[name='Report 1']",
                                   "covered_by": "catalogue.item_titles"},
                 "reach_email_field": {"selector": "#email",
                                         "covered_by": "catalogue.contact_email"},
                 "start_link": {"selector": "role=link[name='Home']",
                               "covered_by": "menu.menu_links"}}}}}
    out, rows = pe.template_content(drift, "reports_list", inv)
    assert out["new_elements"]["reports_list"] == {
        "export_button": "#export", "report_1_link": "role=link[name='Report 1']"}
    assert set(out["new_element_declarations"]["reports_list"]["shared"]) == {
        "reach_email_field", "start_link"}                 # a single key, and shared chrome
    assert rows == [{"element": "report_1_link", "selector": "role=link[name='Report 1']",
                     "covered_by": "catalogue.item_titles"}]
    assert "report_1_link" in drift["new_element_declarations"]["reports_list"]["shared"]
    assert pe.template_content({}, "reports_list", inv)[1] == []


def test_the_body_names_the_template_it_shares():
    stub, _ = pe.with_page(INV, "reports_list", "/reports_list")
    upd = iu.build_update(_drift("reports_list", {"r1": "role=link[name='R1']"}), stub, set(),
                          allow_removal=False)
    body = pe.render_body("PRJ-7", "reports_list", "/reports_list", "x", upd,
                          inventory_path="i", template=[{"element": "r1", "selector": "s",
                                                         "covered_by": "catalogue.item_titles"}])
    assert "**Same template as** `catalogue.item_titles`" in body


def test_the_check_reports_headings_only_when_asked(tmp_path, monkeypatch):
    import scripts.check_inventory_staleness as chk
    inv = tmp_path / "inv.json"
    inv.write_text(json.dumps({"pages": {"reports_list": {"url": "/reports_list",
                                                          "elements": {}}}}))
    ctx = SimpleNamespace(name="Sample", base_url=BASE, inventory_path=lambda: inv,
                          inventory_file="inv.json")
    monkeypatch.setattr(chk.AppContext, "load", staticmethod(lambda: ctx))

    @contextmanager
    def fake_browser(headless=True):
        page = MagicMock()
        page.url = BASE + "/reports_list"
        yield page
    monkeypatch.setattr(chk, "browser_page", fake_browser)
    monkeypatch.setattr(chk, "resolve_selectors",
                        lambda page, url, sels, attrs, detail=None: ({}, set(), True))
    monkeypatch.setattr(chk, "collect_uncovered", lambda page, url, sels, attrs, **k: ("R", []))
    monkeypatch.setattr(chk, "page_headings", lambda page: ["Reports list"])
    monkeypatch.setattr(chk, "count_on_page",
                        lambda page, sels, attrs=None: ({s: 1 for s in sels}, set()))
    out = tmp_path / "r.json"
    for flags, want in ((["--headings"], {"reports_list_heading": 'text="Reports list"'}),
                        ([], None)):
        monkeypatch.setattr(sys, "argv", ["check", "--no-login", "--compare", "--json",
                                          str(out), *flags])
        assert chk.main() == 0
        assert json.loads(out.read_text()).get("new_elements", {}).get("reports_list") == want


# ── the model words "not in the inventory" its own way (17 Nov 2026) ───

PARAPHRASE = ("PRJ-8: no scenario of its own in this pull request - the plan's notes: needs "
              "the reports heading and the list of report titles on the reports_list page, "
              "neither of which exists in the app inventory (no reports_list page object)")


def test_any_wording_that_denies_the_inventory_has_it_counts():
    for text in (PARAPHRASE, "needs the export button, not in the app inventory",
                 "the export button is missing from the inventory",
                 "the inventory has no export button", "no such element in the inventory"):
        assert blocked.says_not_in_inventory(text), text
    for text in ("the inventory was read", "Step fidelity error: the step clicks nothing",
                 "inventory key used: export_button"):
        assert not blocked.says_not_in_inventory(text), text


def test_a_paraphrased_refusal_is_requested_and_gets_the_inventory_advice(monkeypatch):
    assert pe.requested([PARAPHRASE], INV) == {"pages": [], "reasons": [PARAPHRASE],
                                                "known_pages": {}}
    text = blocked.blocked_comment("PRJ-8", "f" * 16, [PARAPHRASE])
    assert "plan_inventory element" in text and "plan_inventory page" in text


def test_a_page_name_the_refusal_writes_picks_the_link_without_a_model(setup):
    go, reads = setup
    out, _t, host = go({"story": "PRJ-8", "pages": [], "reasons": [PARAPHRASE]},
                       llm=_LLM({"path": "", "why": "never asked"}))
    assert out["status"] == "proposed" and reads == [("reports_list", "/reports_list")]
    assert "the refusal names `reports_list`" in host.prs[0][1]
    assert pe.names_in([PARAPHRASE]) == ["reports_list"]


def test_a_validators_own_wording_is_left_to_its_own_reading():
    assert not blocked.says_not_in_inventory(UNKNOWN_PAGE)
    assert not blocked.says_not_in_inventory(
        "self.sel('x'), but 'x' is not an element on inventory page 'orders', nor on any other page")


# ── the inventory's own shape: components, notes, additions to a known page ─

def test_components_are_named_as_the_other_pages_are():
    assert pe.components_for(["Reports", "Reports", " "], ["Reports list"], "x") == ["Reports"]
    assert pe.components_for([], ["  Reports  Centre "], "reports_list") == ["Reports Centre"]
    assert pe.components_for(None, ["reports"], "reports_list") == ["Reports"]
    assert pe.components_for([], ["", "123", "Help"], "reports_list") == ["Help"]
    assert pe.components_for([], [], "reports_list") == ["Reports List"]
    assert pe.components_for([], ["x" * 41], "help_centre") == ["Help Centre"]


def test_a_proposed_page_carries_the_notes_of_its_declarations():
    stub, _ = pe.with_page(INV, "reports_list", "/reports_list", ["Reports"])
    upd = iu.build_update(_drift("reports_list", {"row_link": ".row a", "save": "#save"},
                                 families=["row_link"]), stub, set(), allow_removal=False)
    page = pe.proposed(INV, upd.inventory, "reports_list")["pages"]["reports_list"]
    assert page["multi_match"] == ["row_link"] and page["multi_match_note"] == pe.MULTI_MATCH_NOTE
    assert "conditional" not in page and "conditional_note" not in page
    assert page["components"] == ["Reports"]


def test_elements_added_to_a_known_page_leave_the_rest_of_it_alone():
    inv = {"pages": {"orders": {"url": "/orders", "components": ["Orders"],
                                "elements": {"orders_table": "#orders", "old": "#gone"},
                                "elements_notes": {"orders_table": "the list"},
                                "conditional": ["orders_table"], "conditional_note": "mine"}}}
    drift = {"pages": {"orders": {"missing": [{"element": "old", "selector": "#gone"}]}},
             "new_elements": {"orders": {"old": "#old-new", "print_button": "#print",
                                         "detail_panel": "#panel"}},
             "new_element_declarations": {"orders": {"conditional": ["detail_panel"]}}}
    upd = iu.build_update(drift, inv, {"old", "orders_table"}, allow_removal=False)
    new = pe.with_added(inv, upd.inventory, "orders", upd.added)
    page = new["pages"]["orders"]
    assert page["elements"] == {"orders_table": "#orders", "old": "#gone",       # no replacement
                                "print_button": "#print", "detail_panel": "#panel"}
    assert page["conditional"] == ["orders_table", "detail_panel"]
    assert page["conditional_note"] == "mine" and page["elements_notes"] == {"orders_table":
                                                                              "the list"}
    assert page["components"] == ["Orders"] and inv["pages"]["orders"]["elements"]["old"] == "#gone"


def test_the_link_text_names_the_component_when_the_story_has_none(setup, monkeypatch):
    go, _ = setup
    monkeypatch.setattr(_Tracker, "get_story", lambda self, key: {"key": key, "summary": "s",
                                                                  "description": "",
                                                                  "components": []})
    out, _t, host = go({"story": "PRJ-7", "pages": ["reports_list"], "reasons": []})
    written = json.loads(next(iter(host.files.values())))
    assert written["pages"]["reports_list"]["components"] == ["Reports"]   # the link's words


def test_a_missing_element_of_a_known_page_is_proposed_on_that_page(monkeypatch):
    calls = []

    def fake_read(inv, name):
        calls.append((name, sorted(inv["pages"])))
        return ({"pages_checked": 1, "pages": {name: {"missing": []}},
                 "new_elements": {name: {"print_button": "#print", "orders_heading":
                                         'text="Your orders"', "fragile": "div > a"}},
                 "new_element_declarations": {name: {"unstable": ["fragile"]}}}, "")
    monkeypatch.setattr(em, "read_page", fake_read)
    tracker, host = _Tracker(), _Host()
    original = json.dumps(INV, indent=2) + "\n"
    req = {"story": "PRJ-9", "pages": [], "reasons": [],
           "known_pages": {"orders": ["needs the print button on orders"]}}
    out = em.explore(req, tracker=tracker, host=host, inventory=INV, original=original,
                     ctx=SimpleNamespace(base_url=BASE, inventory_file="i.json"),
                     s=pe.settings(), links={}, open_prs=[], dry_run=False,
                     llm_factory=lambda: (_ for _ in ()).throw(AssertionError("no model")))
    assert out["status"] == "proposed" and out["pages"] == ["orders"] and out["added"] == 2
    assert calls == [("orders", sorted(INV["pages"]))]          # read as it is, no page added
    (title, body, branch), = host.prs
    assert branch == "inventory-explore/orders-elements" and pe.parse_body(body) == ("PRJ-9",
                                                                                  "orders")
    written = json.loads(host.files[(branch, "i.json")])
    assert written["pages"]["orders"]["elements"] == {"orders_table": "#orders",
                                                      "print_button": "#print",
                                                      "orders_heading": 'text="Your orders"'}
    assert {k: v for k, v in written["pages"].items() if k != "orders"} == {
        k: v for k, v in INV["pages"].items() if k != "orders"}
    assert "needs the print button on orders" in body
    assert tracker.comments["PRJ-9"][0].startswith(pe.MARKER)


def test_an_element_an_open_pull_request_already_adds_is_not_proposed_again(monkeypatch):
    monkeypatch.setattr(em, "read_page", lambda inv, name: (
        {"pages_checked": 1, "pages": {name: {"missing": []}},
         "new_elements": {name: {"print_button": "#print"}}}, ""))
    monkeypatch.setattr(em, "_claimed", lambda host, path, inv, s: {
        ("orders", "#print"): "orders.print_button (u/7)"})
    tracker, host = _Tracker(), _Host()
    out = em.explore({"story": "PRJ-9", "pages": [], "reasons": [],
                      "known_pages": {"orders": ["print_button"]}},
                     tracker=tracker, host=host, inventory=INV, original="{}",
                     ctx=SimpleNamespace(base_url=BASE, inventory_file="i.json"),
                     s=pe.settings(), links={}, open_prs=[], dry_run=False,
                     llm_factory=lambda: None)
    assert out["status"] == "empty" and not host.prs
    assert "plan_inventory element" in tracker.comments["PRJ-9"][0]


def test_additions_in_open_pull_requests_are_read_per_page_and_selector():
    theirs = json.loads(json.dumps(INV))
    theirs["pages"]["orders"]["elements"]["print_button"] = "#print"
    theirs["pages"]["brand_new"] = {"url": "/n", "elements": {"x": "#x"}}
    host = SimpleNamespace(
        list_open_prs=lambda prefix, strict=False: [{"number": 7, "head_ref": "p/1",
                                                     "url": "u/7"}],
        get_file_content=lambda path, branch: json.dumps(theirs))
    assert iu.additions_in_open_prs(host, "p/", "i.json", INV) == {
        ("orders", "#print"): "orders.print_button (u/7)"}


def test_headings_in_the_pages_chrome_or_already_covered_are_left_out():
    from inventory_tools.browser import _headings_js
    from inventory_tools.introspect import COVER_ATTR, SHARED_ATTR
    js = _headings_js()
    for part in (COVER_ATTR, SHARED_ATTR, "header, footer, nav", "textContent"):
        assert part in js
