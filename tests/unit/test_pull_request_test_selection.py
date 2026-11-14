"""Which tests a pull request runs (backlog item X1): a pull request runs the scenarios its change can affect plus
the smoke set; anything read by every test runs the whole suite.

Generic names only.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from core import test_selection as ts

ON = {**ts.DEFAULTS, "enabled": True}


def _node(file, title, steps=(), methods=()):
    return SimpleNamespace(file=file, title=title,
                           step_definitions=tuple(SimpleNamespace(file=f) for f in steps),
                           methods=frozenset(methods), shared_methods=frozenset())


class Graph:
    """The two lookups the selection reads from Agent 0's impact graph."""

    def __init__(self, scenarios, page_methods, bases=None):
        self.scenarios, self.page_methods, self.bases = scenarios, page_methods, bases or {}

    def _mro(self, cls):
        return [cls] + self.bases.get(cls, [])


GRAPH = Graph(
    [_node("features/cart.feature", "Add an item", ["tests/step_defs/test_cart.py"],
           [("ShelfPage", "add")]),
     _node("features/cart.feature", "Remove an item", ["tests/step_defs/test_cart.py"],
           [("ShelfPage", "remove")]),
     _node("features/login.feature", "Log in", ["tests/step_defs/test_login.py"],
           [("LoginPage", "log_in"), ("LoginPage", "banner")])],
    {("ShelfPage", "add"): SimpleNamespace(file="pages/shelf_page.py"),
     ("ShelfPage", "remove"): SimpleNamespace(file="pages/shelf_page.py"),
     ("LoginPage", "log_in"): SimpleNamespace(file="pages/login_page.py"),
     ("SitePage", "banner"): SimpleNamespace(file="pages/site_page.py")},
    bases={"LoginPage": ["SitePage"]})


def _sel(*changed, labels=(), s=ON):
    return ts.select(list(changed), Path("."), s, labels=labels, graph=GRAPH)


def test_a_feature_file_runs_its_own_scenarios():
    out = _sel("features/cart.feature")
    assert out["mode"] == "selected" and out["smoke_tag"] == "smoke"
    assert out["scenarios"] == [["features/cart.feature", "Add an item"],
                                ["features/cart.feature", "Remove an item"]]


def test_a_step_module_runs_the_scenarios_using_it():
    assert _sel("tests/step_defs/test_login.py")["scenarios"] == [["features/login.feature",
                                                                  "Log in"]]


def test_a_page_object_runs_the_scenarios_calling_its_methods_inherited_too():
    assert _sel("pages/site_page.py")["scenarios"] == [["features/login.feature", "Log in"]]
    assert len(_sel("pages/shelf_page.py", "docs/notes.md")["scenarios"]) == 2


@pytest.mark.parametrize("path", ["app_inventory/app.json", "config/config.yaml",
                                  "pages/base_page.py", "tests/conftest.py",
                                  "tests/step_defs/conftest.py", "core/defects.py",
                                  "requirements.txt", ".github/workflows/agent4_runner.yml"])
def test_what_every_test_reads_runs_the_whole_suite(path):
    out = _sel("features/cart.feature", path)
    assert out["mode"] == "full" and path in out["why"]


def test_the_label_off_switch_no_list_and_no_trace_run_everything():
    assert _sel("features/cart.feature", labels=["full-suite"])["mode"] == "full"
    assert _sel("features/cart.feature", s={**ON, "enabled": False})["mode"] == "full"
    assert ts.select([], Path("."), ON, graph=GRAPH)["mode"] == "full"
    assert _sel("features/gone.feature")["mode"] == "full", "nothing traced: never an empty run"


def test_an_error_runs_the_whole_suite():
    class Broken:
        scenarios = property(lambda self: (_ for _ in ()).throw(RuntimeError("x")))
    out = ts.select(["features/cart.feature"], Path("."), ON, graph=Broken())
    assert out["mode"] == "full" and "RuntimeError" in out["why"]


def test_the_choice_round_trips_and_keeps_the_smoke_set(tmp_path):
    choice = _sel("features/cart.feature")
    path = ts.write(choice, tmp_path / "r" / ts.FILE)
    loaded = ts.load(path)
    assert ts.keeps(loaded, "features/cart.feature", "Add an item", set())
    assert not ts.keeps(loaded, "features/login.feature", "Log in", set())
    assert ts.keeps(loaded, "features/login.feature", "Log in", {"smoke"})
    assert ts.load(ts.write(ts.full("x"), tmp_path / "f.json")) is None, "full: all run"
    assert ts.load(tmp_path / "missing.json") is None


def test_pytest_deselects_what_the_selection_leaves_out(tmp_path, monkeypatch):
    from tests import conftest as root_conftest
    root = tmp_path
    path = ts.write(_sel("features/cart.feature"), root / "reports" / ts.FILE)
    monkeypatch.setenv(ts.ENV, str(path))

    def item(feature, title, tags=()):
        scen = SimpleNamespace(name=title, feature=SimpleNamespace(
            filename=str(root / "features" / feature)))
        return SimpleNamespace(obj=SimpleNamespace(__scenario__=scen),
                               iter_markers=lambda: [SimpleNamespace(name=t) for t in tags])
    items = [item("cart.feature", "Add an item"), item("login.feature", "Log in"),
             item("login.feature", "Smoke", ["smoke"]), SimpleNamespace(obj=object())]
    dropped = []
    config = SimpleNamespace(rootpath=root, hook=SimpleNamespace(
        pytest_deselected=lambda items: dropped.extend(items)))
    root_conftest.pytest_collection_modifyitems(config, items)
    assert [getattr(getattr(i.obj, "__scenario__", None), "name", None) for i in items] == \
        ["Add an item", "Smoke", None]
    assert len(dropped) == 1
    monkeypatch.delenv(ts.ENV)
    again = list(items)
    root_conftest.pytest_collection_modifyitems(config, again)
    assert again == items, "without the variable every test runs"


def test_agent3_reads_a_selected_green_run_scenario_by_scenario():
    from tests.unit.test_review_scenario_evidence import _issue, _report, apply
    from agents.agent3_reviewer import RunnerEvidence
    ran = {"borrowabookfromitscataloguecard": ["passed"]}
    not_run = _report(_issue("Return a book from the loan page"))
    assert apply(not_run, RunnerEvidence("success", ran, selected=True)).overall_verdict \
        == "request_changes", "a scenario the selection left out tells nothing"
    passed = _report(_issue("Borrow a book from its catalogue card"))
    assert apply(passed, RunnerEvidence("success", ran, selected=True)).overall_verdict \
        != "request_changes"
    assert apply(not_run, RunnerEvidence("success", ran)).overall_verdict != "request_changes", \
        "the whole suite green refutes it, as before"


def test_the_workflow_chooses_on_pull_requests_only_and_fails_open():
    wf = (Path(__file__).resolve().parents[2] / ".github" / "workflows"
          / "agent4_runner.yml").read_text()
    step = wf[wf.index("- name: Choose the tests for this pull request"):]
    step = step[:step.index("- name: Cache Playwright browsers")]
    assert "github.event_name == 'pull_request'" in step and "continue-on-error: true" in step
    assert "repos/$REPO/issues/$PR_NUMBER/labels" in step, "labels read live, for a re-run"
    assert wf.count("AGENT4_SELECTION: ${{ steps.select.outputs.file }}") == 2


def test_the_project_turns_it_on_with_its_smoke_tag():
    s = ts.settings()
    assert s["enabled"] is True and s["smoke_tag"] == "smoke" and s["full_label"]
