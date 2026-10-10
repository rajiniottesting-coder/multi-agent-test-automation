"""Onboarding kit (design E2): readiness checks on a synthetic application.

The synthetic app lives in a temporary directory and is NOT this repository:
it has no config/ directory, its inventory sits at a custom path, and its names
are generic. It uses the conventional layout the layer 1 builder reads
(features/, tests/step_defs/, pages/) - that layout is the one thing the
builder requires, and REQUIRED_LAYOUT reports it when absent.

Covers: the builder registry, the adapter and Protocol checks, layout,
inventory, graph and marker checks, and the CLI exit codes.
"""
import json
import textwrap
from pathlib import Path

import pytest

from core import impact_graph, onboarding
from core.impact_graph import build_impact_graph
from integrations import repo_host, tracker
from integrations.repo_host import RepoHost
from integrations.tracker import Tracker
from scripts import onboarding_check


def _w(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")


@pytest.fixture
def synthetic_app(tmp_path):
    """A small application outside the repository layout, with no config/."""
    _w(tmp_path, "qa/inventory.json", json.dumps({"pages": {
        "widgets": {"components": ["Widgets"], "elements": {"save_button": {}}},
        "reports": {"elements": {"export": {}}},            # no Components: a WARN
    }}))
    _w(tmp_path, "pages/base_page.py", '''
        class BasePage:
            INVENTORY_PAGE = None
            def sel(self, key): return key
            def click(self, locator): self.page.click(locator)
    ''')
    _w(tmp_path, "pages/widget_page.py", '''
        from pages.base_page import BasePage
        class WidgetPage(BasePage):
            INVENTORY_PAGE = "widgets"
            def save(self):
                self.click(self.sel("save_button"))
    ''')
    _w(tmp_path, "features/orders.feature", '''
        Feature: Orders

          # JIRA: ORD-1 (hash: aaaaaaaa)
          Scenario: Save a widget
            Given a widget page is open
            When I save the widget

          Scenario: Open a widget
            Given a widget page is open
    ''')
    _w(tmp_path, "tests/step_defs/test_orders.py", '''
        from pytest_bdd import given, when, scenarios, parsers
        scenarios("../../features/orders.feature")
        @given("a widget page is open")
        def open_widget(widget_page):
            pass
        @when("I save the widget")
        def save(widget_page):
            widget_page.save()
    ''')
    return tmp_path


def _by_name(checks, name):
    return next(c for c in checks if c.name == name)


# ─────────────────────────────────────────────────────────────
# Graph builder registry
# ─────────────────────────────────────────────────────────────

def test_this_suite_language_is_registered_with_the_existing_builder():
    assert impact_graph.graph_builder_for("python-pytest-bdd") is build_impact_graph


def test_language_lookup_is_case_and_space_insensitive():
    assert impact_graph.graph_builder_for("  Python-PyTest-BDD ") is build_impact_graph


def test_unknown_language_has_no_builder():
    assert impact_graph.graph_builder_for("cobol-mainframe") is None


def test_a_registered_builder_is_used_for_its_language(monkeypatch, synthetic_app):
    calls = []

    def builder(root, inventory_file=None):
        calls.append((root, inventory_file))
        return impact_graph.ImpactGraph()

    monkeypatch.setitem(impact_graph._GRAPH_BUILDERS, "java-selenium", builder)
    checks, _ = onboarding.graph_checks(synthetic_app, "java-selenium", "qa/inventory.json")
    assert calls == [(synthetic_app, "qa/inventory.json")]
    assert _by_name(checks, "graph builder").status == onboarding.OK


# ─────────────────────────────────────────────────────────────
# Adapters: registration, Protocol completeness, construction
# ─────────────────────────────────────────────────────────────

def _complete_stub(proto):
    """An object that supplies every operation the Protocol declares."""
    return type("Stub", (), {n: (lambda self, *a, **k: None)
                             for n in onboarding.protocol_members(proto)})()


def test_protocol_members_are_the_declared_operations():
    members = onboarding.protocol_members(Tracker)
    assert {"project_key"} <= members          # a property the Protocol declares
    assert not any(m.startswith("_") for m in members)


def test_a_complete_adapter_passes():
    stub = _complete_stub(Tracker)
    check = onboarding.adapter_check("tracker", "stub", Tracker, ["stub"], lambda n, fresh: stub)
    assert check.status == onboarding.OK


def test_an_incomplete_adapter_fails_and_names_what_is_missing():
    partial = type("Partial", (), {"branch_exists": lambda self, *a: None})()
    check = onboarding.adapter_check("repo host", "partial", RepoHost,
                                     ["partial"], lambda n, fresh: partial)
    assert check.status == onboarding.FAIL
    missing = onboarding.missing_members(RepoHost, partial)
    assert "create_branch" in missing           # a real gap is named
    assert "branch_exists" not in missing       # a provided operation is not
    assert "lacks" in check.detail


def test_an_unregistered_adapter_fails_and_lists_what_is_registered():
    check = onboarding.adapter_check("tracker", "nope", Tracker, ["jira"],
                                     lambda n, fresh: None)
    assert check.status == onboarding.FAIL
    assert "jira" in check.detail


def test_an_adapter_that_cannot_be_constructed_warns_instead_of_failing():
    def no_credentials(name, fresh):
        raise RuntimeError("no token in the environment")

    check = onboarding.adapter_check("tracker", "jira", Tracker, ["jira"], no_credentials)
    assert check.status == onboarding.WARN
    assert "RuntimeError" in check.detail


# ─────────────────────────────────────────────────────────────
# Layout, inventory, graph, markers on the synthetic app
# ─────────────────────────────────────────────────────────────

def test_the_synthetic_app_needs_no_config_when_its_inventory_is_named(synthetic_app):
    assert not (synthetic_app / "config").exists()
    checks = onboarding.run_checks(synthetic_app, inventory_file="qa/inventory.json")
    assert _by_name(checks, "inventory").status == onboarding.OK


def test_layout_is_ok_for_the_conventional_directories(synthetic_app):
    layout = onboarding.layout_checks(synthetic_app)
    assert {c.status for c in layout} == {onboarding.OK}


def test_a_missing_directory_is_a_warn_naming_the_directory(synthetic_app):
    (synthetic_app / "pages" / "widget_page.py").unlink()
    (synthetic_app / "pages" / "base_page.py").unlink()
    (synthetic_app / "pages").rmdir()
    checks = onboarding.layout_checks(synthetic_app)
    warn = [c for c in checks if c.status == onboarding.WARN]
    assert [c.name for c in warn] == ["layout: pages/"]


def test_pages_without_components_are_a_warn(synthetic_app):
    checks = onboarding.run_checks(synthetic_app, inventory_file="qa/inventory.json")
    comp = _by_name(checks, "inventory: components")
    assert comp.status == onboarding.WARN and "reports" in comp.detail


def test_a_missing_inventory_is_a_fail(synthetic_app):
    checks = onboarding.run_checks(synthetic_app, inventory_file="qa/missing.json")
    assert _by_name(checks, "inventory").status == onboarding.FAIL


def test_the_graph_finds_the_scenario_and_its_element_link(synthetic_app):
    checks, graph = onboarding.graph_checks(synthetic_app, "python-pytest-bdd", "qa/inventory.json")
    assert _by_name(checks, "graph builder").status == onboarding.OK
    titles = {s.title for s in graph.scenarios}
    assert {"Save a widget", "Open a widget"} <= titles
    save = next(s for s in graph.scenarios if s.title == "Save a widget")
    assert ("widgets", "save_button") in save.elements


def test_unmarked_scenarios_are_a_warn_that_points_to_the_backfill(synthetic_app):
    _, graph = onboarding.graph_checks(synthetic_app, "python-pytest-bdd", "qa/inventory.json")
    markers = onboarding.marker_checks(graph)
    assert len(markers) == 1 and markers[0].status == onboarding.WARN
    assert "1 of 2" in markers[0].detail
    assert "backfill_markers.py" in markers[0].action


def test_fully_marked_scenarios_are_ok(tmp_path):
    _w(tmp_path, "features/one.feature", '''
        Feature: One

          # JIRA: ONE-1 (hash: aaaaaaaa)
          Scenario: Only one
            Given nothing
    ''')
    _w(tmp_path, "tests/step_defs/test_one.py", "from pytest_bdd import given\n")
    _w(tmp_path, "pages/x.py", "class X:\n    pass\n")
    _, graph = onboarding.graph_checks(tmp_path, "python-pytest-bdd", "qa/none.json")
    assert onboarding.marker_checks(graph)[0].status == onboarding.OK


def test_gaps_are_reported_as_unknown_not_as_not_impacted(synthetic_app):
    _w(synthetic_app, "features/extra.feature", '''
        Feature: Extra

          Scenario: Uses a step nobody defines
            When something no step defines happens
    ''')
    checks, _ = onboarding.graph_checks(synthetic_app, "python-pytest-bdd", "qa/inventory.json")
    gaps = _by_name(checks, "graph: gaps")
    assert gaps.status == onboarding.WARN
    assert "unknown, never as not impacted" in gaps.detail


def test_an_unknown_language_fails_and_says_what_is_registered(synthetic_app):
    checks, graph = onboarding.graph_checks(synthetic_app, "cobol-mainframe", "qa/inventory.json")
    assert graph is None
    assert checks[0].status == onboarding.FAIL
    assert "python-pytest-bdd" in checks[0].detail


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────

def _stub_adapters(monkeypatch):
    """Keep the CLI tests offline: both adapters register and construct as stubs."""
    monkeypatch.setitem(tracker._ADAPTERS, "stub", lambda: _complete_stub(Tracker))
    monkeypatch.setitem(repo_host._ADAPTERS, "stub", lambda: _complete_stub(RepoHost))


def test_cli_exits_zero_when_there_are_only_warnings(synthetic_app, monkeypatch, capsys):
    _stub_adapters(monkeypatch)
    code = onboarding_check.main(["--root", str(synthetic_app), "--inventory", "qa/inventory.json",
                                  "--tracker", "stub", "--repo-host", "stub"])
    out = capsys.readouterr().out
    assert code == 0
    assert "WARN" in out and "backfill_markers.py" in out


def test_cli_strict_fails_on_warnings(synthetic_app, monkeypatch):
    _stub_adapters(monkeypatch)
    assert onboarding_check.main(["--root", str(synthetic_app), "--inventory", "qa/inventory.json",
                                  "--tracker", "stub", "--repo-host", "stub", "--strict"]) == 1


def test_cli_exits_one_on_a_fail(synthetic_app, monkeypatch):
    _stub_adapters(monkeypatch)
    assert onboarding_check.main(["--root", str(synthetic_app), "--inventory", "qa/inventory.json",
                                  "--tracker", "stub", "--repo-host", "stub",
                                  "--language", "cobol-mainframe"]) == 1


def test_cli_fails_on_an_unregistered_tracker(synthetic_app, monkeypatch):
    _stub_adapters(monkeypatch)
    assert onboarding_check.main(["--root", str(synthetic_app), "--inventory", "qa/inventory.json",
                                  "--tracker", "xray", "--repo-host", "stub"]) == 1


def test_cli_never_writes_into_the_application(synthetic_app, monkeypatch):
    _stub_adapters(monkeypatch)
    before = sorted(p.relative_to(synthetic_app) for p in synthetic_app.rglob("*"))
    onboarding_check.main(["--root", str(synthetic_app), "--inventory", "qa/inventory.json",
                           "--tracker", "stub", "--repo-host", "stub"])
    after = sorted(p.relative_to(synthetic_app) for p in synthetic_app.rglob("*"))
    assert before == after


def test_no_config_and_no_inventory_flag_is_a_readable_fail(tmp_path):
    _w(tmp_path, "features/a.feature", "Feature: A\n  Scenario: S\n    Given x\n")
    checks, graph = onboarding.graph_checks(tmp_path, "python-pytest-bdd", None)
    assert graph is None
    assert checks[0].status == onboarding.FAIL
    assert "--inventory" in checks[0].detail
