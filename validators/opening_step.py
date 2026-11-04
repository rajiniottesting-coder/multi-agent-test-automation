"""A scenario opens a page before it acts on one.

Every test starts on the browser's empty page. 4 Nov 2026: a generated
Background clicked a top-menu link as its first move - the approved test case
said "navigate to the home page, then click the link", and the "navigate" was
lost. Both scenarios waited 30 seconds for a link that could never appear,
found a whole Agent 4 run and a review round later. Every other check passed:
the method existed, the selector was right.

The rule, read from the files: the FIRST step a scenario runs (its
Background's first step, else its own) must make, as its first page-object
call, a call to a method that opens a page - one whose body calls
`self.navigate(...)` (or `self.page.goto(...)`), directly or through another
method of its class. Only what can be read is judged: a first step with no
page-object call (a fixture does the work), a fixture whose class cannot be
found, a step that cannot be matched, or a scenario that opens on a Then
(no setup at all) is left alone - the rule never guesses.

Generic: page objects are found by the project's naming rule (class
`StartPage` <-> fixture `start_page`); nothing here names an
application.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

_PREFIX = "Opening step error"
_STEP = re.compile(r"^\s*(Given|When|Then|And|But)\s+(.+?)\s*$")
_BLOCK = re.compile(r"^\s*(Background|Scenario Outline|Scenario Template|Scenario|Example)\s*:\s*(.*)$")
_NAVIGATE = {"navigate", "goto"}
# The first step that sets up or acts. A scenario that opens on a check (Then)
# has no setup at all - a different defect, not judged here.
_SETS_UP = {"given", "when"}


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _first_steps(feature: str) -> list:
    """[(scenario title, keyword, phrase)] - the first step each scenario runs."""
    background, out, block, title, steps = None, [], None, "", []

    def close():
        if block == "background":
            return
        if block and (background or steps):
            out.append((title, *(background or steps[0])))

    for line in feature.splitlines():
        m = _BLOCK.match(line)
        if m:
            close()
            block = "background" if m.group(1) == "Background" else "scenario"
            title, steps = m.group(2).strip(), []
            continue
        s = _STEP.match(line)
        if s and block:
            kw = s.group(1).lower()
            if block == "background" and background is None:
                background = (kw, s.group(2))
            elif block == "scenario" and not steps:
                steps.append((kw, s.group(2)))
    close()
    return out


def _class_sources(generated_files, project_root: Path) -> dict:
    """{class name: ClassDef} for every page object, the batch first."""
    out: dict = {}

    def add(source: str):
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name not in out:
                out[node.name] = node

    for f in generated_files or []:
        path = getattr(f, "file_path", "") or ""
        if path.startswith("pages/") and path.endswith(".py"):
            add(getattr(f, "content", "") or "")
    pages = Path(project_root) / "pages"
    if pages.is_dir():
        for py in sorted(pages.glob("*.py")):
            try:
                add(py.read_text(encoding="utf-8"))
            except OSError:
                continue
    return out


def _opens_a_page(cls: ast.ClassDef, method: str, seen=None) -> bool | None:
    """True / False, or None when the method is not on the class (unknown)."""
    seen = seen or set()
    funcs = {n.name: n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    func = funcs.get(method)
    if func is None:
        return None
    seen.add(method)
    for node in ast.walk(func):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        target, name = node.func.value, node.func.attr
        if name in _NAVIGATE and (
                (isinstance(target, ast.Name) and target.id == "self")
                or (isinstance(target, ast.Attribute) and target.attr == "page")):
            return True
        if (isinstance(target, ast.Name) and target.id == "self" and name in funcs
                and name not in seen and _opens_a_page(cls, name, seen)):
            return True
    return False


def _first_page_object_call(func, fixtures: dict):
    """(fixture, method) of the first call on a page-object parameter, or None."""
    calls = []
    for node in ast.walk(func):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id in fixtures):
            calls.append((node.lineno, node.col_offset, node.func.value.id, node.func.attr))
    if not calls:
        return None
    _l, _c, fixture, method = min(calls, key=lambda c: (c[0], c[1]))
    return fixture, method


def validate_scenarios_open_a_page_first(generated_files, project_root=None) -> list:
    from validators.gherkin_analyzer import _phrase_matches, step_functions
    if project_root is None:
        from config.paths import PROJECT_ROOT
        project_root = PROJECT_ROOT
    by_path = {getattr(f, "file_path", ""): getattr(f, "content", "") or ""
               for f in generated_files or []}
    classes = _class_sources(generated_files, Path(project_root))
    page_fixtures = {_snake(name): name for name in classes}
    errors = []
    for path, feature in by_path.items():
        if not (path.startswith("features/") and path.endswith(".feature")):
            continue
        sd_path = f"tests/step_defs/test_{path[len('features/'):-len('.feature')]}.py"
        steps = step_functions(by_path.get(sd_path, "")) or []
        reported = set()
        for title, keyword, phrase in _first_steps(feature):
            func = next((f for kind, p, t, f in steps
                         if kind == keyword and _phrase_matches(phrase, p, t)), None)
            if keyword not in _SETS_UP or func is None or (keyword, phrase) in reported:
                continue
            params = {a.arg for a in func.args.args}
            fixtures = {p: page_fixtures[p] for p in params if p in page_fixtures}
            first = _first_page_object_call(func, fixtures)
            if first is None:
                continue
            fixture, method = first
            if _opens_a_page(classes[fixtures[fixture]], method) is not False:
                continue
            reported.add((keyword, phrase))
            errors.append(
                f"{_PREFIX} in '{sd_path}': the first step of scenario '{title}' - "
                f"`{keyword.capitalize()} {phrase}` - acts before any page is opened: its "
                f"first page-object call is {fixture}.{method}(), which does not navigate. "
                "Every test starts on the browser's empty page. Open a page first - call a "
                "page-object method that calls navigate() (the page the test case starts "
                "on) - then act.")
    return errors
