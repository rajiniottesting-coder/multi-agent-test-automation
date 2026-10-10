"""
Unit tests for core/impact_graph.py (Agent 0 design, step B2).

A small synthetic repository exercises every rule the graph follows; one
test builds the graph for this repository itself.
"""
import json
import textwrap
from pathlib import Path

import pytest

from core.impact_graph import build_impact_graph

ROOT = Path(__file__).resolve().parents[2]


def _w(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")


@pytest.fixture
def repo(tmp_path):
    _w(tmp_path, "inv.json", json.dumps({"pages": {
        "shop":   {"components": ["Shop"], "elements": {"buy": {}, "modal": {}, "price": {}}},
        "detail": {"components": ["Shop", "Detail"], "elements": {"modal": {}, "title": {}}},
        "nav":    {"components": ["Navigation"], "elements": {"logout": {}}},
    }}))
    _w(tmp_path, "pages/base_page.py", '''
        class BasePage:
            INVENTORY_PAGE = None
            def sel(self, key): return key
            def click(self, locator): self.page.click(locator)
            def heading_shown(self): return self.sel("title")
    ''')
    _w(tmp_path, "pages/shop_page.py", '''
        from pages.base_page import BasePage
        class ShopPage(BasePage):
            INVENTORY_PAGE = "shop"
            def buy(self):
                self.click(self.sel("buy"))
                self._confirm()
            def _confirm(self):
                return self.sel("modal")
            def price(self):
                return self.sel("price")
            def ghost_key(self):
                return self.sel("not_in_inventory")
    ''')
    _w(tmp_path, "pages/detail_page.py", '''
        from pages.base_page import BasePage
        class DetailPage(BasePage):
            INVENTORY_PAGE = "detail"
            def confirm(self):
                return self.sel("modal")
    ''')
    _w(tmp_path, "pages/nav_page.py", '''
        from pages.base_page import BasePage
        class NavPage(BasePage):
            INVENTORY_PAGE = "nav"
            def logout(self):
                self.click(self.sel("logout"))
    ''')
    _w(tmp_path, "features/shop.feature", '''
        Feature: Shop

          Background:
            Given I am on the shop

          # JIRA: AB-1 (hash: aaaaaaaa)
          Scenario: Buy a thing
            When I buy it
            And I check the price
            Then I log out

          Scenario Outline: Detail
            When I confirm on detail for "<item>"
            Then nothing defined here

            Examples:
              | item |
              | x    |
    ''')
    _w(tmp_path, "features/other.feature", '''
        Feature: Other

          Scenario: Uses a step only shop defines
            When I buy it
    ''')
    _w(tmp_path, "tests/step_defs/conftest.py", '''
        from pytest_bdd import then
        @then("I log out")
        def log_out(nav_page):
            nav_page.logout()
    ''')
    _w(tmp_path, "tests/step_defs/test_shop.py", '''
        from pytest_bdd import given, when, then, parsers
        @given("I am on the shop")
        def on_shop(shop_page):
            pass
        @when("I buy it")
        def buy(shop_page):
            shop_page.buy()
        @when("I check the price")
        def check_price(shop_page):
            shop_page.price()
        @then("I check the price")
        def then_price(shop_page):
            shop_page.ghost_key()
        @when(parsers.re(r'I confirm on detail for "(?P<item>[^"]*)"'))
        def confirm(detail_page, item):
            detail_page.confirm()
            detail_page.heading_shown()
            detail_page.page.reload()
            detail_page.no_such_method()
    ''')
    _w(tmp_path, "tests/step_defs/test_other.py", '''
        from pytest_bdd import when
    ''')
    return tmp_path


@pytest.fixture
def graph(repo):
    return build_impact_graph(repo, inventory_file="inv.json")


def _s(graph, title):
    return next(s for s in graph.scenarios if s.title == title)


def _m(refs):
    return sorted(f"{c}.{m}" for c, m in refs)


class TestScenarios:
    def test_marker_and_background(self, graph):
        s = _s(graph, "Buy a thing")
        assert s.jira_key == "AB-1" and s.ref == "AB-1"
        assert s.steps[0] == ("given", "I am on the shop")
        assert s.file == "features/shop.feature"

    def test_unmarked_scenario_ref_is_file_and_title(self, graph):
        assert _s(graph, "Detail").ref == "features/shop.feature::Detail"

    def test_and_resolves_to_the_previous_keyword(self, graph):
        s = _s(graph, "Buy a thing")
        # "And I check the price" follows When -> the @when, not the @then
        assert "ShopPage.price" in _m(s.methods)
        assert "ShopPage.ghost_key" not in _m(s.methods)

    def test_steps_are_module_scoped(self, graph):
        s = _s(graph, "Uses a step only shop defines")
        assert s.methods == frozenset() and s.step_definitions == ()
        assert any(g.kind == "no_step_definition" and "I buy it" in g.detail
                   and "other.feature" in g.where for g in graph.gaps)

    def test_conftest_steps_are_visible_to_every_feature(self, graph):
        assert "NavPage.logout" in _m(_s(graph, "Buy a thing").methods)


class TestMethodsAndElements:
    def test_self_helpers_are_followed(self, graph):
        s = _s(graph, "Buy a thing")
        assert "ShopPage._confirm" in _m(s.methods)
        assert ("shop", "modal") in s.elements

    def test_inherited_method_resolves_and_is_shared(self, graph):
        s = _s(graph, "Buy a thing")
        assert "ShopPage.click" in _m(s.shared_methods)
        assert "ShopPage.click" not in _m(s.methods)

    def test_inherited_sel_uses_the_receivers_page(self, graph):
        # heading_shown is defined on BasePage, called on DetailPage
        assert ("detail", "title") in _s(graph, "Detail").elements

    def test_a_key_on_two_pages_links_only_to_the_receivers_page(self, graph):
        assert ("shop", "modal") in _s(graph, "Buy a thing").elements
        assert ("detail", "modal") not in _s(graph, "Buy a thing").elements
        assert ("detail", "modal") in _s(graph, "Detail").elements
        assert ("shop", "modal") not in _s(graph, "Detail").elements

    def test_pages_and_components(self, graph):
        s = _s(graph, "Buy a thing")
        assert s.pages == {"shop", "nav"}
        assert s.components == {"Shop", "Navigation"}

    def test_playwright_calls_are_not_page_methods(self, graph):
        assert not any(m == "reload" or m == "page" for _c, m in
                       _s(graph, "Detail").methods | _s(graph, "Detail").shared_methods)


class TestGaps:
    def test_missing_step_definition(self, graph):
        assert any(g.kind == "no_step_definition" and "nothing defined here" in g.detail
                   for g in graph.gaps)

    def test_unknown_method(self, graph):
        assert any(g.kind == "unknown_method" and g.detail == "DetailPage.no_such_method"
                   for g in graph.gaps)

    def test_unknown_element_is_reported_not_dropped(self, repo):
        _w(repo, "tests/step_defs/test_shop.py",
           (repo / "tests/step_defs/test_shop.py").read_text()
           + '\n@when("I poke a ghost")\ndef ghost(shop_page):\n    shop_page.ghost_key()\n')
        _w(repo, "features/shop.feature",
           (repo / "features/shop.feature").read_text()
           + "\n  Scenario: Ghost\n    When I poke a ghost\n")
        g = build_impact_graph(repo, inventory_file="inv.json")
        assert any(x.kind == "unknown_element" and x.detail == "shop:not_in_inventory"
                   for x in g.gaps)

    def test_unparseable_page_file(self, repo):
        _w(repo, "pages/broken_page.py", "class Broken(:\n")
        g = build_impact_graph(repo, inventory_file="inv.json")
        assert any(x.kind == "unparseable_file" and "broken_page.py" in x.where for x in g.gaps)


class TestReverseLookups:
    def test_by_element(self, graph):
        assert [s.title for s in graph.scenarios_using_element("shop", "modal")] == ["Buy a thing"]

    def test_by_key_on_any_page(self, graph):
        assert {s.title for s in graph.scenarios_using_key("modal")} == {"Buy a thing", "Detail"}

    def test_by_method_including_subclass_receivers(self, graph):
        assert [s.title for s in graph.scenarios_calling("ShopPage", "buy")] == ["Buy a thing"]
        # a change to BasePage.click reaches every scenario that clicks
        assert {s.title for s in graph.scenarios_calling("BasePage", "click")} == {"Buy a thing"}

    def test_by_page_and_component(self, graph):
        assert {s.title for s in graph.scenarios_on_page("detail")} == {"Detail"}
        assert {s.title for s in graph.scenarios_in_component("Shop")} == {"Buy a thing", "Detail"}

    def test_by_test_case_key(self, graph):
        assert graph.scenario_for_key("AB-1").title == "Buy a thing"
        assert graph.scenario_for_key("AB-99") is None


class TestStatsAndExport:
    def test_stats(self, graph):
        st = graph.stats()
        assert st["scenarios"] == 3 and st["marked_scenarios"] == 1
        assert st["step_definitions"] == 6
        assert st["inventory_elements"] == 6 and st["inventory_keys"] == 5
        assert st["page_methods"] == 3 + 4 + 1 + 1

    def test_to_dict_is_json_serialisable(self, graph):
        json.dumps(graph.to_dict())

    def test_missing_directories_give_an_empty_graph(self, tmp_path):
        g = build_impact_graph(tmp_path, inventory_file="none.json")
        assert g.scenarios == [] and g.gaps == []


def test_this_repository_builds_without_unparseable_files():
    """The real repository: every feature, step module and page object parses,
    and every scenario is found."""
    g = build_impact_graph(ROOT)
    assert not [x for x in g.gaps if x.kind == "unparseable_file"]
    import re
    n_scenarios = sum(len(re.findall(r"^\s*Scenario(?: Outline)?:", f.read_text(encoding="utf-8"), re.M))
                      for f in (ROOT / "features").glob("*.feature"))
    assert len(g.scenarios) == n_scenarios
    assert all(s.elements for s in g.scenarios), "a scenario reaches no element"


def test_the_graph_uses_the_gates_step_matcher(repo, monkeypatch):
    """Agent 0 and the gate must read the code the same way: the graph calls
    the gate's own matcher, so changing the gate changes the graph."""
    import validators.gherkin_analyzer as ga
    monkeypatch.setattr(ga, "_phrase_matches", lambda *a, **k: False)
    g = build_impact_graph(repo, inventory_file="inv.json")
    assert all(not s.step_definitions for s in g.scenarios)
