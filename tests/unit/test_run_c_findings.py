"""What the validation found after Run B (4 Nov 2026), one test per fix.

Scheduled runs the repository host never started are reported. Generic
names only.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from core import health_checks as hc

ROOT = Path(__file__).resolve().parents[2]
UTC = dt.timezone.utc


# ── scheduled runs the host never started ───────────────────────────────

@pytest.mark.parametrize("expr, start, end, n", [
    ("*/30 * * * *", dt.datetime(2026, 1, 5, 0, 0), dt.datetime(2026, 1, 5, 2, 0), 4),
    ("7,37 5-6 * * 1-5", dt.datetime(2026, 1, 5, 0, 0), dt.datetime(2026, 1, 6, 0, 0), 4),
    ("7,37 5-6 * * 1-5", dt.datetime(2026, 1, 3, 0, 0), dt.datetime(2026, 1, 5, 0, 0), 0),
    ("45 1 * * *", dt.datetime(2026, 1, 3, 0, 0), dt.datetime(2026, 1, 5, 0, 0), 2),
    ("0 0 1 * 0", dt.datetime(2026, 1, 1, 0, 0), dt.datetime(2026, 1, 12, 0, 0), 2),
    ("0 12 * * 7", dt.datetime(2026, 1, 3, 0, 0), dt.datetime(2026, 1, 5, 0, 0), 1),
])
def test_cron_fires_counts_the_minutes_a_line_names(expr, start, end, n):
    # 5 Jan 2026 is a Monday. "0 0 1 * 0" is the 1st OR a Sunday: the window
    # starts after 1 Jan 00:00, so Sunday 4 and Sunday 11 Jan count.
    assert hc.cron_fires(expr, start.replace(tzinfo=UTC), end.replace(tzinfo=UTC)) == n


@pytest.mark.parametrize("expr", ["", "* * * *", "60 * * * *", "0 0 * * MON", "*/0 * * * *"])
def test_a_line_that_cannot_be_read_counts_nothing(expr):
    now = dt.datetime(2026, 1, 5, tzinfo=UTC)
    assert hc.cron_fires(expr, now - dt.timedelta(hours=1), now) is None


def _tree(tmp_path, cron):
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "job.yml").write_text(f'on:\n  schedule:\n    - cron: "{cron}"\n  workflow_dispatch:\n')
    return tmp_path


class _Host:
    def __init__(self, runs):
        self.runs = runs

    def get_workflow_runs(self, name, branch, limit=20):
        return self.runs[:limit]


NOW = dt.datetime(2026, 1, 6, 12, 0, tzinfo=UTC)


def _run(hours_ago, event="schedule"):
    return {"event": event, "created_at": (NOW - dt.timedelta(hours=hours_ago)).isoformat()}


def test_a_schedule_that_never_started_is_reported(tmp_path):
    root = _tree(tmp_path, "0 * * * *")
    (f,) = hc.schedule_findings(_Host([_run(2, "workflow_dispatch"), _run(30)]), root, NOW, 24, 3)
    assert f.problem and f.alert_id == "workflow-not-starting:job.yml"
    assert "asked for 24 runs" in f.detail and "started none" in f.detail


def test_one_started_run_closes_it(tmp_path):
    root = _tree(tmp_path, "0 * * * *")
    (f,) = hc.schedule_findings(_Host([_run(5), _run(30)]), root, NOW, 24, 3)
    assert not f.problem and f.title.startswith("Scheduled runs of job.yml start again")


def test_a_schedule_asking_for_few_runs_is_not_judged_silent(tmp_path):
    root = _tree(tmp_path, "0 3 * * *")                # once a day: below the minimum of 3
    (f,) = hc.schedule_findings(_Host([_run(30)]), root, NOW, 24, 3)
    assert not f.problem


def test_runs_that_do_not_reach_the_window_start_give_no_finding(tmp_path):
    root = _tree(tmp_path, "0 * * * *")
    busy = [_run(h / 10, "push") for h in range(100)]   # 100 runs, all inside the last 10 h
    assert hc.schedule_findings(_Host(busy), root, NOW, 24, 3) == []


def test_an_unreadable_schedule_gives_no_finding(tmp_path):
    root = _tree(tmp_path, "0 0 * * MON")
    assert hc.schedule_findings(_Host([]), root, NOW, 24, 3) == []


def test_the_health_check_runs_it_with_the_shipped_settings():
    import yaml
    from core.ops_settings import DEFAULTS
    shipped = yaml.safe_load((ROOT / "config" / "config.yaml").read_text())["pipeline_health"]
    assert shipped["schedule_window_hours"] == DEFAULTS["pipeline_health"]["schedule_window_hours"]
    assert shipped["schedule_min_expected"] == DEFAULTS["pipeline_health"]["schedule_min_expected"]
    src = (ROOT / "scripts" / "pipeline_health_check.py").read_text(encoding="utf-8")
    assert "hc.schedule_findings(host, root, now," in src


# ── a planned list of like elements can be declared a family ────────────

def _inv():
    return {"pages": {"p": {"url": "/p", "elements": {"head": "h1"}}}}


def test_a_planned_family_is_declared_multi_match():
    from core.inventory_planned import add_planned_element, add_planned_page
    out, why = add_planned_element(_inv(), "p", "rows", "ul > li", family=True)
    assert not why and out["pages"]["p"]["multi_match"] == ["rows"]
    out, why = add_planned_element(_inv(), "p", "one", "#one")
    assert not why and "multi_match" not in out["pages"]["p"]
    out, why = add_planned_page(_inv(), "q", "/q", {"items": ".item", "title": "h2"},
                                ["Q"], families=["items"])
    assert not why and out["pages"]["q"]["multi_match"] == ["items"]
    _out, why = add_planned_page(_inv(), "q", "/q", {"title": "h2"}, ["Q"], families=["nope"])
    assert "--family names no element" in why


def test_a_declared_planned_family_with_several_matches_is_confirmed():
    from inventory_tools.introspect import diff_page
    d = diff_page("p", {"rows": "ul > li"}, {"ul > li": 27}, set(), [],
                  declared_family={"rows"}, declared_planned={"rows"})
    assert [x["element"] for x in d["planned_live"]] == ["rows"] and not d["ambiguous"]
    d = diff_page("p", {"rows": "ul > li"}, {"ul > li": 27}, set(), [],
                  declared_planned={"rows"})
    assert not d["planned_live"] and d["ambiguous"], "undeclared: ambiguous, never confirmed"


def test_the_script_takes_family():
    from scripts.plan_inventory import main
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert main(["page", "--page", "zz_demo", "--url", "/zz_demo", "--component", "Z",
                     "--element", "rows=ul > li", "--family", "rows", "--dry-run"]) == 0
    assert '"multi_match": [\n    "rows"' in buf.getvalue()


# ── a test case about the prompt is sent back ───────────────────────────

def _case(title, *expected):
    from core.schemas import TestCase, TestStep
    return TestCase(title=title, description="d", expected_outcome="done", steps=[
        TestStep(step_number=i, action=f"do {i}", expected_result=e)
        for i, e in enumerate(expected, 1)])


@pytest.mark.parametrize("title, expected", [
    ("[Negative] The list page and its search are not defined in the Application Under Test",
     "the page opens"),
    ("[Negative] Search", "the search box is not described in the application context"),
    ("[Negative] Search", "the filter is not present in the app notes"),
])
def test_a_test_case_about_the_prompt_is_refused(title, expected):
    from core.test_case_rules import test_case_problems
    problems = test_case_problems(_case(title, expected))
    assert problems and "tests what the prompt describes" in problems[0]


@pytest.mark.parametrize("expected", [
    "the search box is not present on the page",
    "the product is not available in the inventory",
    "no row for 'Item' is present",
])
def test_absence_on_the_application_is_not_about_the_prompt(expected):
    from core.test_case_rules import test_case_problems
    assert not any("tests what the prompt" in p
                   for p in test_case_problems(_case("[Negative] Gone", expected)))


def test_both_prompts_say_a_new_thing_is_new():
    for name in ("agent1_analyst.md", "agent1_impact_aware.md"):
        text = (ROOT / "prompts" / name).read_text(encoding="utf-8")
        assert "never write a test case stating that something is not defined" in text


# ── a red run still starts the agent again while stories wait ───────────

@pytest.mark.parametrize("name", ["agent1_analyst.yml", "agent2_coder.yml"])
def test_a_red_run_still_hands_off(name):
    import yaml
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"))
    (job,) = wf["jobs"].values()
    step = next(s for s in job["steps"] if "again while stories wait" in s.get("name", ""))
    assert step["if"].startswith("${{ !cancelled()")
    src = (ROOT / "core" / "handoff.py").read_text(encoding="utf-8")
    assert "the run took none of the stories that waited when it began" in src, \
        "the progress rule is what keeps a red run from looping"


# ── a story that needs a person is handed back, not taken every scan ────

def test_a_partial_set_is_handed_back_with_what_to_do():
    from agents.agent1_analyst import NEEDS_A_PERSON_WHY, STOPPED, hand_back

    class T:
        def __init__(self):
            self.removed, self.comments = [], []

        def remove_label(self, k, label):
            self.removed.append(label)

        def add_comment(self, k, body):
            self.comments.append(body)
    t = T()
    why = NEEDS_A_PERSON_WHY["partial_test_cases"].format(n=1)
    assert hand_back(t, "AB-1", why, {"selection": {"required_labels": ["go"]}}) == ["go"]
    (body,) = t.comments
    assert body.startswith(STOPPED) and "take a place another story waits for" in body
    assert "1 test case(s) are linked" in body and "Add `go` again to retry" in body
    src = (ROOT / "agents" / "agent1_analyst.py").read_text(encoding="utf-8")
    assert 'if result.get("status") in _NEEDS_A_PERSON and not args.dry_run:' in src


# ── the impact-aware draft has room to reason and answer ────────────────

def test_the_budget_grows_with_the_approved_cases():
    from agents.agent1_impact import BASE_OUTPUT_TOKENS, MAX_OUTPUT_TOKENS, output_budget
    assert output_budget(0) == BASE_OUTPUT_TOKENS
    assert output_budget(7) > 2 * BASE_OUTPUT_TOKENS > output_budget(1)
    assert output_budget(100) == MAX_OUTPUT_TOKENS
    src = (ROOT / "agents" / "agent1_analyst.py").read_text(encoding="utf-8")
    assert "max_output_tokens=output_budget(len(impacted))" in src


def test_an_empty_truncated_answer_is_named_as_reasoning():
    from core.llm_client import truncation_evidence
    lines = truncation_evidence("", {"output_token_details": {"reasoning": 12288}})
    assert "the answer never began" in lines[0] and "12,288 tokens" in lines[1]
    assert "not a loop" in truncation_evidence(None)[1]


# ── a re-analysis that finds nothing settles the open review ────────────

def test_an_empty_reanalysis_supersedes_the_open_review(tmp_path, monkeypatch):
    import agents.agent0_impact as a0
    from core import impact_review
    from tests.unit.test_agent0 import FakeModel, TITLE_12, _only_in, _settings
    fake, jira, root, g = _world(tmp_path, monkeypatch)
    s = _settings(shadow_mode=False)
    page, key = _only_in(g, "SBX-12", "SBX-11")
    first = a0.analyse_requirement(jira, "SBX-5", FakeModel([f"{page}:{key}"], must={TITLE_12}),
                                   _settings(), root)
    assert a0.publish(jira, "SBX-5", first, s)["action"] == "review-created"
    review = jira.get_subtasks("SBX-5")[0]
    again = a0.analyse_requirement(jira, "SBX-5", FakeModel([]), _settings(), root)
    again["ranked"], again["content_hash"] = [], "f" * 12
    out = a0.publish(jira, "SBX-5", again, s, force=True)
    assert out == {"story": "SBX-5", "action": "nothing-to-review", "review_superseded": review["key"]}
    labels = fake.issues["SBX-5"]["labels"]
    assert "ai-ready" in labels and "impact-proposed" not in labels
    text = jira.get_subtasks("SBX-5")[0]["description"]
    assert "Superseded" in text and impact_review.parse_rows(text) == {}


def _world(tmp_path, monkeypatch):
    import agents.agent0_impact as a0
    import config.paths as paths
    from core.impact_graph import build_impact_graph
    from tests.unit.test_agent0 import build_repo, jira_client_over, seed_jira
    fake = seed_jira()
    fake.add("Story", "A story", key="SBX-5", labels=["impact-check"], components=["Login"],
             description="When the password is wrong, the error message also links to reset.")
    jira = jira_client_over(fake, monkeypatch)
    root = build_repo(tmp_path / "repo")
    monkeypatch.setattr(paths, "FEATURES_DIR", root / "features")
    monkeypatch.setattr(paths, "PROJECT_ROOT", root)
    a0._GRAPHS.clear()
    return fake, jira, root, build_impact_graph(root)


# ── a proposal closed unmerged can be proposed again ────────────────────

class _Branches:
    def __init__(self, existing, open_heads, readable=True):
        self.existing, self.open_heads, self.readable = set(existing), list(open_heads), readable

    def branch_exists(self, b):
        return b in self.existing

    def list_open_prs(self, strict=False):
        if not self.readable:
            raise RuntimeError("down")
        return [{"head_ref": h} for h in self.open_heads]


@pytest.mark.parametrize("existing, open_heads, readable, expected", [
    ([], [], True, "cu/ab-1"),                                   # never proposed
    (["cu/ab-1"], ["cu/ab-1"], True, None),                      # still open
    (["cu/ab-1"], [], True, "cu/ab-1-2"),                        # closed: a new branch
    (["cu/ab-1", "cu/ab-1-2"], [], True, "cu/ab-1-3"),
    (["cu/ab-1", "cu/ab-1-2"], ["cu/ab-1-2"], True, None),       # the second one open
    (["cu/ab-1"], [], False, None),                              # cannot tell: as before
])
def test_a_closed_proposal_frees_a_new_branch(existing, open_heads, readable, expected):
    from core.context_update import free_branch
    assert free_branch(_Branches(existing, open_heads, readable), "cu/ab-1") == expected


# ── a start never cancels a run already waiting to start ────────────────

def test_a_run_waiting_to_start_is_not_replaced():
    from tests.unit.test_agents_start_the_next_agent import Host, Tracker, _start

    class Waiting(Host):
        def __init__(self, statuses):
            super().__init__()
            self.statuses = statuses

        def get_workflow_runs(self, workflow, branch, limit=20):
            return [{"status": s} for s in self.statuses]
    host = Waiting(["queued", "in_progress"])
    out = _start(Tracker({"ready": ["S-1"]}), host)
    assert not out["started"] and host.started == [] and not out.get("error")
    assert "already waiting to start" in out["why"]
    host = Waiting(["in_progress", "completed"])                 # the run asking is going
    assert _start(Tracker({"ready": ["S-1"]}), host)["started"]

    class Broken(Host):
        def get_workflow_runs(self, *a, **k):
            raise RuntimeError("down")
    assert _start(Tracker({"ready": ["S-1"]}), Broken())["started"], "cannot tell: as before"


@pytest.mark.parametrize("name", ["agent1_analyst.yml", "agent2_coder.yml"])
def test_a_one_story_run_starts_the_scan_without_the_progress_rule(name):
    import yaml
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"))
    (job,) = wf["jobs"].values()
    step = next(s for s in job["steps"] if "again while stories wait" in s.get("name", ""))
    assert step["env"]["STORY_KEY"] == "${{ github.event.inputs.story_key }}"
    assert 'if [ -n "$STORY_KEY" ]; then WAITED=""; fi' in step["run"]


# ── a yes/no predicate over a row is not a misnamed reader ──────────────

def _rows_page(body: str):
    from types import SimpleNamespace as NS
    return NS(file_path="pages/rows_page.py", content=(
        "from pages.base_page import BasePage\n\n\nclass RowsPage(BasePage):\n"
        '    INVENTORY_PAGE = "rows_demo"\n\n' + body))


@pytest.fixture
def rows_inventory(monkeypatch):
    import validators.method_resolution_validator as v
    monkeypatch.setattr(v, "_load_configured_inventory", lambda root: {"pages": {"rows_demo": {
        "elements": {"item_rows": "tr.item"}, "multi_match": ["item_rows"],
        "row_family": "item_rows"}}})
    return v


def test_a_predicate_reading_a_row_is_accepted(rows_inventory):
    body = ('    def has_item_with_cost(self, name: str, cost: str) -> bool:\n'
            '        text = self.get_text(self.sel("item_rows"))\n'
            '        return name in text and cost in text\n')
    assert rows_inventory.validate_readers_return_what_they_name([_rows_page(body)], ROOT) == []


def test_a_reader_returning_row_text_under_a_field_name_is_still_refused(rows_inventory):
    body = ('    def get_item_cost(self) -> str:\n'
            '        return self.get_text(self.sel("item_rows"))\n')
    (err,) = rows_inventory.validate_readers_return_what_they_name([_rows_page(body)], ROOT)
    assert err.startswith("Reader naming error") and "cost" in err


# ── a refused story is told which rule failed, not only a summary ───────

_GATES = ["validate_filename_consistency", "validate_feature_file_structure",
          "validate_extended_page_objects_keep_methods", "validate_step_definitions_complete",
          "validate_no_duplicate_step_definitions", "validate_imports_resolvable",
          "validate_method_resolution", "validate_page_object_selectors",
          "validate_no_unused_step_definitions", "validate_fixtures_exist"]


@pytest.mark.parametrize("gate", _GATES)
def test_every_gate_hands_its_errors_to_the_blocked_comment(gate, monkeypatch):
    """4 Nov 2026, SCRUM-292: the blocked comment carried one summary line
    ("the LLM likely used inconsistent method names") and lost the eight errors
    under it - among them that a reserved page object lacked the method."""
    import inspect
    import agents.agent2_coder as a2
    src = inspect.getsource(a2._validate_generated_files)
    for name in _GATES:
        assert name in src
        monkeypatch.setattr(a2, name, lambda *a, **k: [])
    monkeypatch.setattr(a2, gate, lambda *a, **k: [f"{gate} error in 'x.py'"])
    with pytest.raises(a2.GateFailure) as raised:
        a2._validate_generated_files([], "AB-1")
    assert raised.value.errors == [f"{gate} error in 'x.py'"]


def test_a_method_a_reserved_page_lacks_is_a_person_s_step():
    from core.blocked import blocked_comment
    err = ("Method resolution error in 'tests/step_defs/test_x.py': line 4 calls "
           "`menu.go_to_reports()`, but `MenuPage` does not define `go_to_reports`. "
           "`pages/menu_page.py` is a RESERVED file - Agent 2 must not modify it, so ...")
    text = blocked_comment("AB-1", "0" * 16, [err, "Method resolution error in 'y': other"])
    assert "`MenuPage.go_to_reports` (pages/menu_page.py)" in text
    assert "A person adds the method" in text and "cannot show" not in text
    plain = blocked_comment("AB-1", "0" * 16, ["Method resolution error in 'y': other"])
    assert "cannot show" in plain and "reserved page object" not in plain


def test_refused_files_are_printed_with_workflow_commands_off(capsys):
    from types import SimpleNamespace as NS
    from agents.agent2_coder import show_refused_files
    show_refused_files([NS(file_path="pages/x_page.py", content="::add-mask::boom\nclass X: pass")])
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "::group::Refused by the final gate: pages/x_page.py"
    token = out[1].split("::stop-commands::")[1]
    assert out[2:4] == ["::add-mask::boom", "class X: pass"]
    assert out[4] == f"::{token}::" and out[5] == "::endgroup::"


# ── a new page object may not borrow another page object's page ─────────

def _po(path, cls, page, body="    def open_it(self, base_url: str) -> None:\n        self.navigate(base_url)\n"):
    from types import SimpleNamespace as NS
    return NS(file_path=path, content=(f"from pages.base_page import BasePage\n\n\nclass {cls}(BasePage):\n"
                                       f'    INVENTORY_PAGE = "{page}"\n\n' + body))


@pytest.fixture
def menu_project(tmp_path):
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "menu_page.py").write_text(
        'from pages.base_page import BasePage\n\n\nclass MenuPage(BasePage):\n    INVENTORY_PAGE = "menu"\n')
    return tmp_path, {"pages": {"menu": {"elements": {"reports_link": "a.r"}}}}


def test_a_new_page_object_borrowing_a_page_it_does_not_use_is_refused(menu_project):
    """4 Nov 2026, SCRUM-292: the page was not in the inventory; the new page
    object set INVENTORY_PAGE to the navigation entry and navigated by a
    hard-coded path, so the missing page was never named."""
    from validators.method_resolution_validator import validate_page_object_selectors
    root, inv = menu_project
    (err,) = validate_page_object_selectors([_po("pages/reports_page.py", "ReportsPage", "menu")], root, inv)
    assert "MenuPage (pages/menu_page.py) implements, and resolves none of its elements" in err
    using = "    def open_reports(self) -> None:\n        self.click(self.sel(\"reports_link\"))\n"
    assert validate_page_object_selectors(
        [_po("pages/reports_page.py", "ReportsPage", "menu", using)], root, inv) == []
    assert validate_page_object_selectors(
        [_po("pages/menu_page.py", "MenuPage", "menu")], root, inv) == []    # its own file


def test_a_borrowed_page_is_reported_as_a_missing_page():
    from core.blocked import blocked_comment
    err = ("Selector inventory error in 'pages/reports_page.py': class ReportsPage sets "
           "INVENTORY_PAGE = 'menu', the page MenuPage (pages/menu_page.py) implements, and "
           "resolves none of its elements. A page object ...")
    text = blocked_comment("AB-1", "0" * 16, [err])
    assert "A new page object (ReportsPage) has no inventory page of its own" in text
    assert "plan_inventory page" in text and "cannot show" not in text


# ── a committed page object the steps need a method on joins the repair ─

def test_a_committed_page_object_missing_a_called_method_joins_the_batch(tmp_path, monkeypatch):
    """4 Nov 2026, SCRUM-293: the steps called HomePage.go_to_test_cases(); the
    plan had not named home_page.py, so only the step definitions were
    repaired, and the story was refused after every attempt."""
    import agents.agent2_coder as a2
    import validators.method_resolution_validator as v
    from core.schemas import CodePlan, GeneratedFile
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "front_page.py").write_text("class FrontPage: ...\n")
    (tmp_path / "pages" / "menu_page.py").write_text("class MenuPage: ...\n")
    monkeypatch.setattr(v, "_reserved_page_files", lambda: {"pages/menu_page.py"})
    steps = GeneratedFile(file_path="tests/step_defs/test_x.py", content="# steps")
    from core.schemas import FilePlan
    own = FilePlan(file_path="tests/step_defs/test_x.py", file_type="step_definitions",
                   purpose="steps")
    plan = CodePlan(feature_name="x", branch_name="auto/AB-1-x", pr_title="t", pr_body="b",
                    notes="", files_to_create=[own])
    err = ("Method resolution error in 'tests/step_defs/test_x.py': line {n} calls "
           "`front.{m}()`, but `FrontPage` does not define `{m}`. Did you mean ...")
    errors = [err.format(n=3, m="go_to_reports"), err.format(n=9, m="has_reports_link"),
              ("Method resolution error in 'tests/step_defs/test_x.py': line 5 calls "
               "`menu.open_reports()`, but `MenuPage` does not define `open_reports`. ...")]
    batch = [steps]
    feedback = a2._bring_in_page_objects(batch, plan, errors, root=tmp_path)
    assert [f.file_path for f in batch] == ["pages/front_page.py", "tests/step_defs/test_x.py"]
    assert batch[0].content == "class FrontPage: ...\n" and batch[0].is_new_file is False
    assert [fp.file_path for fp in plan.files_to_create] == ["pages/front_page.py",
                                                             "tests/step_defs/test_x.py"]
    (fb,) = feedback
    assert fb.startswith("Page object error in 'pages/front_page.py':")
    assert "`go_to_reports()`, `has_reports_link()`" in fb and "keep every existing method" in fb
    assert list(a2._group_validator_errors_by_file(feedback)) == ["pages/front_page.py"]
    # next attempt: still missing -> the feedback again, the file not added twice
    again = a2._bring_in_page_objects(batch, plan, errors[:1], root=tmp_path)
    assert len(again) == 1 and len(batch) == 2 and len(plan.files_to_create) == 2


def test_a_page_object_the_model_planned_is_not_given_extra_feedback(tmp_path, monkeypatch):
    import agents.agent2_coder as a2
    import validators.method_resolution_validator as v
    from core.schemas import CodePlan, GeneratedFile
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "front_page.py").write_text("class FrontPage: ...\n")
    monkeypatch.setattr(v, "_reserved_page_files", lambda: set())
    batch = [GeneratedFile(file_path="pages/front_page.py", content="planned", is_new_file=False,
                           purpose="the plan's own extension")]
    from core.schemas import FilePlan
    plan = CodePlan(feature_name="x", branch_name="b", pr_title="t", pr_body="b", notes="",
                    files_to_create=[FilePlan(file_path="pages/front_page.py",
                                              file_type="page_object", purpose="p")])
    err = ("Method resolution error in 'tests/step_defs/test_x.py': line 3 calls "
           "`front.go()`, but `FrontPage` does not define `go`.")
    assert a2._bring_in_page_objects(batch, plan, [err], root=tmp_path) == []
    assert len(batch) == 1


def test_the_repair_loop_extends_the_page_object_and_the_error_goes(tmp_path, monkeypatch):
    import agents.agent2_coder as a2
    import validators.method_resolution_validator as v
    from core.schemas import CodePlan, FilePlan, GeneratedFile
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "front_page.py").write_text("class FrontPage:\n    pass\n")
    monkeypatch.setattr(a2, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(v, "_reserved_page_files", lambda: set())
    err = ("Method resolution error in 'tests/step_defs/test_x.py': line 3 calls "
           "`front.go_to_reports()`, but `FrontPage` does not define `go_to_reports`.")

    def errors(files):
        page = next((f for f in files if f.file_path == "pages/front_page.py"), None)
        return [] if page and "def go_to_reports" in page.content else [err]
    monkeypatch.setattr(a2, "_collect_repairable_errors", errors)
    monkeypatch.setattr(a2, "_absence_claim_errors", lambda *a: [])
    repaired = []

    def generate(llm, fp, plan, *a, previous_attempt="", **k):
        repaired.append(fp.file_path)
        if fp.file_path == "pages/front_page.py":
            return previous_attempt + "\n    def go_to_reports(self):\n        pass\n"
        return previous_attempt
    monkeypatch.setattr(a2, "generate_file_content", generate)
    monkeypatch.setattr(a2, "_is_degraded_regeneration", lambda *a: False)
    steps = GeneratedFile(file_path="tests/step_defs/test_x.py", content="# steps")
    plan = CodePlan(feature_name="x", branch_name="b", pr_title="t", pr_body="b", notes="",
                    files_to_create=[FilePlan(file_path="tests/step_defs/test_x.py",
                                              file_type="step_definitions", purpose="s")])
    out = a2._attempt_step_coverage_repair([steps], None, plan, [], {}, "", None)
    assert repaired[0] == "pages/front_page.py", "the page object is repaired first"
    page = next(f for f in out if f.file_path == "pages/front_page.py")
    assert "def go_to_reports" in page.content and errors(out) == []
