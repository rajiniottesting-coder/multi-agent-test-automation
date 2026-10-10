"""Impact graph: which scenarios reach which page elements (Agent 0, step B2).

WHY THIS EXISTS
---------------
Agent 0 answers "which existing tests does this change touch?". Its first
layer follows the code: a scenario runs steps, a step runs a step-definition
function, that function calls page-object methods, and those methods use
inventory elements, which belong to pages and Components. This module builds
that chain once for the whole repository and answers the question in both
directions.

ONE WAY OF READING THE CODE
---------------------------
The generation gate already parses all of these files. This module does not
re-implement any of it; it calls the gate's own parsers, so Agent 0 and the
gate can never disagree about what a step matches or what a method touches:

    feature blocks, markers   agents.agent2_coder.parse_feature_file
    steps, And/But            validators.gherkin_analyzer._extract_feature_steps
    step decorators           validators.gherkin_analyzer._extract_decorator_phrases
    step matching             validators.gherkin_analyzer._phrase_matches
                              (the same backends pytest-bdd uses at runtime)
    page fixtures             validators.gherkin_analyzer._page_fixture_names_from_source
                              + validators.method_resolution_validator._parse_fixtures
    calls on fixtures         validators.method_resolution_validator._extract_method_calls_on_fixtures
    selector keys             validators.method_resolution_validator._sel_keys_in

RULES THE GRAPH FOLLOWS (each mirrors the runtime)
--------------------------------------------------
- Steps are module-scoped in pytest-bdd: a scenario in features/X.feature sees
  the steps in tests/step_defs/test_X.py and in conftest.py, nothing else.
- Background steps run before every scenario of their file.
- A step matches only decorators of its own kind (And/But resolved first).
- A method call resolves along the page class's inheritance chain, so a
  helper defined on BasePage is found when called on LoginPage.
- `self.sel("key")` resolves against the INVENTORY_PAGE of the class the
  method is CALLED ON, not the class that defines it. A key that exists on
  two pages therefore links to the right one.
- `self.<helper>()` inside a page method is followed, with the same receiver.
- Methods are split by where they are DEFINED. A method on a class with an
  inventory page (LoginPage.login_as) is the scenario's own page API and is in
  `ScenarioNode.methods`. A method inherited from a shared base with no
  inventory page of its own (BasePage.click, BasePage.sel) is infrastructure
  every page uses; it is in `ScenarioNode.shared_methods`, so a change to the
  base still finds every scenario without drowning the page-level signal.

Nothing is dropped silently. A step with no definition, a call to a method
that does not exist, or a key missing from the inventory is recorded in
`ImpactGraph.gaps`. Agent 0 must treat an unresolved link as "unknown", never
as "not impacted".

Pure static analysis: nothing is imported from pages/ or tests/, so building
the graph needs no browser and no credentials.
"""
from __future__ import annotations

import ast
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

Element = tuple[str, str]          # (inventory page, element key)
MethodRef = tuple[str, str]        # (class the method is called on, method name)


# ─────────────────────────────────────────────────────────────
# Nodes
# ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Gap:
    """Something the graph could not resolve. `kind` is one of:
    no_step_definition, unknown_method, unknown_element, unknown_page_class,
    no_inventory_page, unparseable_file."""
    kind: str
    where: str
    detail: str


@dataclass(frozen=True)
class StepDefinition:
    file: str                        # project-relative path
    function: str
    kind: str                        # given / when / then
    phrase: str
    parser_type: str                 # string / parse / cfparse / re
    calls: frozenset                 # frozenset[MethodRef]


@dataclass(frozen=True)
class PageMethod:
    cls: str
    name: str
    file: str
    keys: frozenset                  # literal keys passed to self.sel(...)
    self_calls: frozenset            # names of self.<method>() calls


@dataclass(frozen=True)
class ScenarioNode:
    file: str                        # project-relative feature path
    title: str
    jira_key: Optional[str]
    steps: tuple                     # ((kind, phrase), ...) background first
    step_definitions: tuple          # (StepDefinition, ...) in step order
    methods: frozenset               # frozenset[MethodRef]: page-level API, helpers included
    shared_methods: frozenset        # frozenset[MethodRef]: inherited from a shared base
    elements: frozenset              # frozenset[Element]
    pages: frozenset
    components: frozenset

    @property
    def ref(self) -> str:
        """Stable identity: the test case key when marked, else file::title."""
        return self.jira_key or f"{self.file}::{self.title}"


@dataclass
class ImpactGraph:
    scenarios: list = field(default_factory=list)          # [ScenarioNode]
    step_definitions: list = field(default_factory=list)   # [StepDefinition]
    page_methods: dict = field(default_factory=dict)       # {(cls, name): PageMethod}
    class_pages: dict = field(default_factory=dict)        # {cls: inventory page}
    inventory_elements: frozenset = frozenset()            # frozenset[Element]
    page_components: dict = field(default_factory=dict)    # {page: frozenset[str]}
    gaps: list = field(default_factory=list)               # [Gap]

    # ── reverse lookups: change -> scenarios ──────────────────
    def scenarios_using_element(self, page: str, key: str) -> list:
        return [s for s in self.scenarios if (page, key) in s.elements]

    def scenarios_using_key(self, key: str) -> list:
        """Every scenario using `key` on ANY page (an inventory key change
        whose page is not known yet)."""
        return [s for s in self.scenarios if any(k == key for _p, k in s.elements)]

    def scenarios_calling(self, cls: str, method: str) -> list:
        """Scenarios that call `method`, on `cls` or on any class inheriting
        it - page-level and shared methods alike, so a change to a BasePage
        method finds every scenario that reaches it."""
        receivers = {c for c in self._bases if cls in self._mro(c)} | {cls}
        return [s for s in self.scenarios
                if any(m == method and c in receivers
                       for c, m in s.methods | s.shared_methods)]

    def scenarios_on_page(self, page: str) -> list:
        return [s for s in self.scenarios if page in s.pages]

    def scenarios_in_component(self, component: str) -> list:
        return [s for s in self.scenarios if component in s.components]

    def scenario_for_key(self, jira_key: str) -> Optional[ScenarioNode]:
        return next((s for s in self.scenarios if s.jira_key == jira_key), None)

    # ── summary ───────────────────────────────────────────────
    def stats(self) -> dict:
        return {
            "scenarios": len(self.scenarios),
            "marked_scenarios": sum(1 for s in self.scenarios if s.jira_key),
            "step_definitions": len(self.step_definitions),
            "page_methods": len(self.page_methods),
            "inventory_elements": len(self.inventory_elements),
            "inventory_keys": len({k for _p, k in self.inventory_elements}),
            "links": sum(len(s.methods) + len(s.elements) for s in self.scenarios),
            "gaps": len(self.gaps),
        }

    def to_dict(self) -> dict:
        """JSON-ready view, for reports and the design diagrams."""
        return {
            "stats": self.stats(),
            "scenarios": [{
                "ref": s.ref, "file": s.file, "title": s.title, "jira_key": s.jira_key,
                "methods": sorted(f"{c}.{m}" for c, m in s.methods),
                "shared_methods": sorted(f"{c}.{m}" for c, m in s.shared_methods),
                "elements": sorted(f"{p}:{k}" for p, k in s.elements),
                "pages": sorted(s.pages), "components": sorted(s.components),
            } for s in self.scenarios],
            "gaps": [g.__dict__ for g in self.gaps],
        }

    # internal: inheritance chain of a page class, by name
    _bases: dict = field(default_factory=dict, repr=False)  # {cls: [base names]}

    def _mro(self, cls: str) -> list:
        order, todo = [], [cls]
        while todo:
            c = todo.pop(0)
            if c in order:
                continue
            order.append(c)
            todo.extend(self._bases.get(c, []))
        return order


# ─────────────────────────────────────────────────────────────
# Building
# ─────────────────────────────────────────────────────────────

_STEP_DECORATORS = {"given", "when", "then"}


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _load_inventory(root: Path, inventory_file: Optional[str]) -> dict:
    if inventory_file is None:
        import yaml
        cfg = yaml.safe_load((root / "config" / "config.yaml").read_text(encoding="utf-8")) or {}
        inventory_file = (cfg.get("app_under_test") or {}).get("inventory_file")
    if not inventory_file:
        return {}
    path = root / inventory_file
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("pages", {}) or {}


def _class_attr(cls_node: ast.ClassDef, name: str) -> Optional[str]:
    for node in cls_node.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == name for t in node.targets):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return node.value.value
    return None


def _self_calls(func: ast.AST) -> set:
    return {n.func.attr for n in ast.walk(func)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and isinstance(n.func.value, ast.Name) and n.func.value.id in ("self", "cls")}


def _read_pages(root: Path, graph: ImpactGraph, inventory: dict) -> dict:
    """Parse pages/*.py. Returns {cls: {method name: PageMethod}} (own methods)."""
    from validators.method_resolution_validator import _sel_keys_in

    by_class: dict = {}
    pages_dir = root / "pages"
    declared_pages: dict = {}
    for path in sorted(pages_dir.glob("*.py")) if pages_dir.is_dir() else []:
        if path.name.startswith("_"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, OSError, UnicodeDecodeError) as e:
            graph.gaps.append(Gap("unparseable_file", _rel(path, root), str(e)))
            continue
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            graph._bases[node.name] = [getattr(b, "id", getattr(b, "attr", ""))
                                       for b in node.bases]
            page = _class_attr(node, "INVENTORY_PAGE")
            if page:
                declared_pages[node.name] = page
            own = {}
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    own[item.name] = PageMethod(
                        cls=node.name, name=item.name, file=_rel(path, root),
                        keys=frozenset(_sel_keys_in(item)),
                        self_calls=frozenset(_self_calls(item)),
                    )
                    graph.page_methods[(node.name, item.name)] = own[item.name]
            by_class[node.name] = own

    # INVENTORY_PAGE is what self.sel() reads at runtime, inherited like any
    # class attribute. The inventory's page_object_class is the fallback.
    inv_by_class = {p.get("page_object_class"): name for name, p in inventory.items()
                    if p.get("page_object_class")}
    for cls in by_class:
        page = next((declared_pages[c] for c in graph._mro(cls) if c in declared_pages),
                    None) or inv_by_class.get(cls)
        if page:
            graph.class_pages[cls] = page
    return by_class


def _resolve_method(graph: ImpactGraph, by_class: dict, cls: str, name: str):
    for c in graph._mro(cls):
        method = by_class.get(c, {}).get(name)
        if method is not None:
            return method
    return None


def _page_fixtures(root: Path, by_class: dict) -> dict:
    """{fixture name: page class} as conftest registers them (snake_case of
    every BasePage subclass), the gate's rule."""
    from validators.gherkin_analyzer import _page_fixture_names_from_source
    fixtures: dict = {}
    pages_dir = root / "pages"
    for path in sorted(pages_dir.glob("*.py")) if pages_dir.is_dir() else []:
        if path.name.startswith("_"):
            continue
        try:
            names = _page_fixture_names_from_source(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        for cls in by_class:
            if _snake(cls) in names:
                fixtures[_snake(cls)] = cls
    return fixtures


def _read_step_module(path: Path, root: Path, fixtures: dict,
                      graph: ImpactGraph) -> list:
    """Step definitions in one module, each with the page methods it calls."""
    from validators.gherkin_analyzer import _extract_decorator_phrases
    from validators.method_resolution_validator import (
        _extract_method_calls_on_fixtures, _parse_fixtures)

    rel = _rel(path, root)
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (SyntaxError, OSError, UnicodeDecodeError) as e:
        graph.gaps.append(Gap("unparseable_file", rel, str(e)))
        return []

    local = dict(fixtures)
    local.update(_parse_fixtures(source))          # @pytest.fixture -> SomePage(...)
    out = []
    for fn in tree.body:
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        fn_src = ast.get_source_segment(source, fn) or ""
        calls = frozenset(
            (local[var], method)
            for var, method, _line in _extract_method_calls_on_fixtures(fn_src, set(local))
        )
        for dec in fn.decorator_list:
            dec_src = ast.get_source_segment(source, dec) or ""
            for kind, phrase, parser_type in _extract_decorator_phrases("@" + dec_src):
                if kind in _STEP_DECORATORS:
                    out.append(StepDefinition(rel, fn.name, kind, phrase,
                                              parser_type, calls))
    return out


def _scenarios_in_feature(path: Path, root: Path, graph: ImpactGraph) -> list:
    """[(title, jira_key, [(kind, phrase)])] with Background steps prepended."""
    from agents.agent2_coder import parse_feature_file
    from validators.gherkin_analyzer import _extract_feature_steps

    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        graph.gaps.append(Gap("unparseable_file", _rel(path, root), str(e)))
        return []
    _header, blocks = parse_feature_file(content)
    background: list = []
    out = []
    for block in blocks:
        if block.kind == "background":
            background = _extract_feature_steps(block.text())
        elif block.kind == "scenario":
            title = next((l.strip().split(":", 1)[1].strip() for l in block.lines
                          if l.strip().startswith(("Scenario:", "Scenario Outline:"))), "")
            out.append((title, block.jira_key, background + _extract_feature_steps(block.text())))
    return out


def build_impact_graph(project_root: Path | str,
                       inventory_file: Optional[str] = None) -> ImpactGraph:
    """Build the graph for the repository at `project_root`.

    `inventory_file` (project-relative) overrides the one named in
    config.yaml - for tests and for other applications' repositories.
    """
    from validators.gherkin_analyzer import _phrase_matches

    root = Path(project_root)
    graph = ImpactGraph()
    inventory = _load_inventory(root, inventory_file)
    graph.inventory_elements = frozenset(
        (page, key) for page, spec in inventory.items() for key in spec.get("elements", {}))
    graph.page_components = {page: frozenset(spec.get("components", []) or [])
                             for page, spec in inventory.items()}

    by_class = _read_pages(root, graph, inventory)
    fixtures = _page_fixtures(root, by_class)

    steps_dir = root / "tests" / "step_defs"
    modules = {p.name: _read_step_module(p, root, fixtures, graph)
               for p in sorted(steps_dir.glob("*.py"))
               if p.name.startswith("test_") or p.name == "conftest.py"} \
        if steps_dir.is_dir() else {}
    graph.step_definitions = [d for defs in modules.values() for d in defs]
    global_steps = modules.get("conftest.py", [])

    features_dir = root / "features"
    for feature in sorted(features_dir.glob("*.feature")) if features_dir.is_dir() else []:
        rel = _rel(feature, root)
        # pytest-bdd steps are module-scoped: features/X.feature runs with
        # tests/step_defs/test_X.py plus conftest.py.
        visible = modules.get(f"test_{feature.stem}.py", []) + global_steps
        for title, jira_key, steps in _scenarios_in_feature(feature, root, graph):
            where = f"{rel}::{title}"
            used: list = []
            for kind, phrase in steps:
                match = [d for d in visible if d.kind == kind
                         and _phrase_matches(phrase, d.phrase, d.parser_type)]
                if not match:
                    graph.gaps.append(Gap("no_step_definition", where, f"{kind} {phrase}"))
                used.extend(d for d in match if d not in used)

            methods, shared, elements = _walk_methods(
                graph, by_class, {c for d in used for c in d.calls}, where)
            pages = frozenset(p for p, _k in elements)
            components = frozenset(c for p in pages for c in graph.page_components.get(p, ()))
            graph.scenarios.append(ScenarioNode(
                file=rel, title=title, jira_key=jira_key, steps=tuple(steps),
                step_definitions=tuple(used), methods=frozenset(methods),
                shared_methods=frozenset(shared),
                elements=frozenset(elements), pages=pages, components=components,
            ))
    logger.info("Impact graph: %s", graph.stats())
    return graph


def _walk_methods(graph: ImpactGraph, by_class: dict, start: Iterable[MethodRef],
                  where: str) -> tuple[set, set, set]:
    """Follow calls through page methods (inheritance + self.<helper>()).

    Returns (page-level methods, shared methods, elements)."""
    methods: set = set()
    shared: set = set()
    elements: set = set()
    seen: set = set()
    frontier = list(start)
    while frontier:
        cls, name = frontier.pop()
        if (cls, name) in seen:
            continue
        seen.add((cls, name))
        if cls not in by_class:
            methods.add((cls, name))
            graph.gaps.append(Gap("unknown_page_class", where, cls))
            continue
        method = _resolve_method(graph, by_class, cls, name)
        if method is None:
            methods.add((cls, name))
            graph.gaps.append(Gap("unknown_method", where, f"{cls}.{name}"))
            continue
        # Defined on a class with its own inventory page -> page API;
        # defined on a shared base (no inventory page) -> infrastructure.
        (methods if method.cls in graph.class_pages else shared).add((cls, name))
        if method.keys:
            page = graph.class_pages.get(cls)
            if page is None:
                graph.gaps.append(Gap("no_inventory_page", where, cls))
            for key in method.keys:
                if page is None:
                    continue
                if (page, key) not in graph.inventory_elements:
                    graph.gaps.append(Gap("unknown_element", where, f"{page}:{key}"))
                elements.add((page, key))
        for helper in method.self_calls:
            if _resolve_method(graph, by_class, cls, helper) is not None:
                frontier.append((cls, helper))
    return methods, shared, elements


if __name__ == "__main__":                       # python -m core.impact_graph [root]
    import sys
    g = build_impact_graph(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parents[1])
    print(json.dumps(g.to_dict(), indent=1))
