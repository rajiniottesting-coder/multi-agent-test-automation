"""A step that says it clicks, clicks.

10 Nov 2026: a story asked that an on-page control return the visitor to the
top of the page. The inventory had no key for the control, so the generated
step `When I click the <control>` called a page-object method that scrolled
the window by script - the OUTCOME the control produces - and clicked
nothing. Every check passed; the scenario would stay green with the control
missing or broken. A test that simulates what a control does is a test of
the browser, not of the application.

The rule, read from the files: a Given/When step whose wording says the user
clicks, presses or taps something must, in its step definition, make a
page-object call that clicks - a method whose body calls a clicking action
(`click`, `dblclick`, `tap`, `check`, ...), directly or through another
method of its class or of the page objects' base class. Only what can be
read is judged: a step whose definition makes no page-object call, a method
that cannot be found, or a step that cannot be matched is left alone.

When the element the step names is not in the inventory, the honest answer
is to leave the test case out (the plan's Skipped reason) so a person adds the
element - never to simulate the outcome.

Generic: page objects are found by the project's naming rule (class
`StartPage` <-> fixture `start_page`); nothing here names an application.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from validators.opening_step import _class_sources, _snake

_PREFIX = "Action step error"
_STEP = re.compile(r"^\s*(Given|When|Then|And|But)\s+(.+?)\s*$")
_BLOCK = re.compile(r"^\s*(Background|Scenario Outline|Scenario Template|Scenario|Example)\s*:")
# The wording that claims a click. A verb on its own, so "the clickable
# title" or "a pressed state" in a check is not one.
_CLAIMS_A_CLICK = re.compile(r"\b(?:click|clicks|clicking|press|presses|pressing|tap|taps|"
                             r"tapping|double-click|double-clicks)\b", re.I)
# Locator / page actions that are a click on an element.
_CLICKING = {"click", "dblclick", "tap", "check", "uncheck", "set_checked",
             "select_option", "press", "dispatch_event"}
_ACTS = {"given", "when"}


def _action_steps(feature: str) -> list:
    """[(keyword, phrase)] of every Given/When step (And/But take the keyword
    before them) whose wording claims a click."""
    out, last = [], None
    for line in feature.splitlines():
        if _BLOCK.match(line):
            last = None
            continue
        m = _STEP.match(line)
        if not m:
            continue
        kw = m.group(1).lower()
        if kw in ("and", "but"):
            kw = last
        else:
            last = kw
        if kw in _ACTS and _CLAIMS_A_CLICK.search(m.group(2)):
            out.append((kw, m.group(2)))
    return out


def _methods(cls: ast.ClassDef) -> dict:
    return {n.name: n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _bases(cls: ast.ClassDef) -> list:
    return [b.id for b in cls.bases if isinstance(b, ast.Name)]


def _find(classes: dict, cls_name: str, method: str, seen_cls=None):
    """(class, method node) along the class and its known bases, or None."""
    seen_cls = seen_cls or set()
    cls = classes.get(cls_name)
    if cls is None or cls_name in seen_cls:
        return None
    seen_cls.add(cls_name)
    func = _methods(cls).get(method)
    if func is not None:
        return cls_name, func
    for base in _bases(cls):
        hit = _find(classes, base, method, seen_cls)
        if hit:
            return hit
    return None


def _clicks(classes: dict, cls_name: str, method: str, seen=None) -> bool | None:
    """True / False, or None when the method cannot be found."""
    seen = seen if seen is not None else set()
    hit = _find(classes, cls_name, method)
    if hit is None:
        return None
    owner, func = hit
    if (owner, method) in seen:
        return False
    seen.add((owner, method))
    unknown = False
    for node in ast.walk(func):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        name, target = node.func.attr, node.func.value
        if name in _CLICKING:
            return True
        if isinstance(target, ast.Name) and target.id == "self":
            got = _clicks(classes, cls_name, name, seen)
            if got:
                return True
            if got is None and not name.startswith("_"):
                unknown = True
    return None if unknown else False


def _page_object_calls(func, fixtures: dict) -> list:
    """[(fixture, method)] of every call on a page-object parameter, in order."""
    calls = []
    for node in ast.walk(func):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id in fixtures):
            calls.append((node.lineno, node.col_offset, node.func.value.id, node.func.attr))
    return [(f, m) for _l, _c, f, m in sorted(calls)]


def validate_click_steps_click(generated_files, project_root=None) -> list:
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
        for keyword, phrase in _action_steps(feature):
            if (keyword, phrase) in reported:
                continue
            func = next((f for kind, p, t, f in steps
                         if kind == keyword and _phrase_matches(phrase, p, t)), None)
            if func is None:
                continue
            params = {a.arg for a in func.args.args}
            fixtures = {p: page_fixtures[p] for p in params if p in page_fixtures}
            calls = _page_object_calls(func, fixtures)
            if not calls:
                continue
            verdicts = [_clicks(classes, fixtures[f], m) for f, m in calls]
            if any(v is not False for v in verdicts):
                continue
            reported.add((keyword, phrase))
            named = ", ".join(f"{f}.{m}()" for f, m in calls)
            errors.append(
                f"{_PREFIX} in '{sd_path}': the step `{keyword.capitalize()} {phrase}` says "
                f"the user clicks, but its definition clicks nothing: {named} makes no click "
                "(directly or through the methods it calls). A step that performs what a "
                "control would do passes even when the control is missing or broken. Click "
                "the element the step names (self.click(self.sel('<key>')) in the page "
                "object). If the app inventory has no key for that element, do not simulate "
                "it: leave that test case out with the reason (the element is missing) so a "
                "person adds it.")
    return errors
