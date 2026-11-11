"""A step does what it says, on the element it names.

10 Nov 2026: a story asked for a list of filters in a side panel that the app
inventory had no key for. The plan did not skip its test cases; the code read
the item names of the main list for "the side panel lists ...", opened an
item's page by name for "I click the filter ... in the side panel", and
checked that the page had loaded for "the side panel is visible". Every gate
passed - each step called a real page-object method on a real inventory key -
and the coverage audit, which reads the Gherkin, judged one of the three test
cases fully checked. The scenarios tested something else under the story's
words.

The deterministic rules cannot see this: whether `item_names` is "the side
panel's filters" is a reading of meaning. So one model call, after the gate,
reads each step of the story's own step files beside the code that runs for
it (its definition, the page-object methods it calls, and the inventory
elements that code reads, with the inventory's notes) and names the steps
whose code acts on or checks a different element than the wording names.

Each page-object method's code is shown ONCE, after the steps, and each step
names the methods that run for it. 11 Nov 2026: eight steps of one story
repeated the same shared helpers (navigation, waits, locators) under every
step - 61,000 characters, 85% of it the same helpers - and the last step was
not read ("the prompt is full"). If the prompt is still too long, inherited
helpers are shown by signature and docstring only, before any step is left
unread.

A step named here has nothing in the inventory it CAN use honestly: its
scenarios are left out (validators.action_steps.leave_out_stand_ins) and its
test cases listed as not automated with the reason, so the story's other test
cases are still coded; a story left with nothing is refused, naming the
steps. The answer is advice-grade (a model's reading), so a failed call
changes nothing.

Generic: page objects are found by the project's naming rule (class
`StartPage` <-> fixture `start_page`); nothing here names an application.
"""
from __future__ import annotations

import ast
import logging
import re
import textwrap
from pathlib import Path

from pydantic import BaseModel, Field

from validators.action_steps import _find, _page_object_calls
from validators.opening_step import _class_sources, _snake

logger = logging.getLogger(__name__)

PREFIX = "Step fidelity error"
_SEL = re.compile(r"""\bsel\(\s*["']([A-Za-z0-9_]+)["']""")
_MAX_METHOD_CHARS = 2500
_MAX_PROMPT_CHARS = 60000


class StepFinding(BaseModel):
    id: str = Field(description="The step's id, e.g. S3")
    reason: str = Field(description="One sentence: what the step names, and what its code "
                                    "uses instead")


class StepFidelityAudit(BaseModel):
    stand_ins: list[StepFinding] = Field(default_factory=list)


def _source(text: str, node) -> str:
    return (ast.get_source_segment(text, node) or "")[:_MAX_METHOD_CHARS]


def _class_texts(generated_files, project_root: Path) -> dict:
    """{class name: source text of its file} - the batch first, as _class_sources."""
    out: dict = {}

    def add(text: str):
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name not in out:
                out[node.name] = text

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


def _methods_reached(classes: dict, texts: dict, cls_name: str, method: str,
                     seen: set, out: list, depth: int = 0) -> None:
    """Append (Class.method, source) for the method and the self.* methods it
    calls (two levels), skipping the page objects' shared helpers' internals."""
    hit = _find(classes, cls_name, method)
    if hit is None or (hit[0], method) in seen or depth > 2:
        return
    owner, func = hit
    seen.add((owner, method))
    out.append((f"{owner}.{method}", _source(texts.get(owner, ""), func)))
    for node in ast.walk(func):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "self"):
            _methods_reached(classes, texts, cls_name, node.func.attr, seen, out, depth + 1)


def _elements(inventory: dict, keys: set) -> list:
    """[(page.key, selector, note)] for every inventory element named `keys`."""
    rows = []
    for page, entry in sorted((inventory.get("pages") or {}).items()):
        if not isinstance(entry, dict):
            continue
        elements = entry.get("elements") or {}
        notes = entry.get("elements_notes") or {}
        for key in sorted(keys & set(elements)):
            value = elements[key]
            selector = value.get("selector") if isinstance(value, dict) else value
            rows.append((f"{page}.{key}", selector, notes.get(key, "")))
    return rows


def step_bindings(generated_files, inventory: dict, project_root=None,
                  skip=()) -> list:
    """[{id, path, keyword, phrase, code, methods, own}] - every step function
    of the batch's step files (not those in `skip`): `code` is its definition,
    the names of the page-object methods that run for it and the inventory
    elements that code reads; `methods` is [(Class.method, source)] and `own`
    the classes its page fixtures name (a method of another class - a base
    class - is an inherited helper)."""
    from validators.gherkin_analyzer import step_functions
    if project_root is None:
        from config.paths import PROJECT_ROOT
        project_root = PROJECT_ROOT
    classes = _class_sources(generated_files, Path(project_root))
    texts = _class_texts(generated_files, Path(project_root))
    page_fixtures = {_snake(name): name for name in classes}
    out = []
    for f in generated_files or []:
        path = getattr(f, "file_path", "") or ""
        if not (path.startswith("tests/step_defs/") and path.endswith(".py")) or path in skip:
            continue
        content = getattr(f, "content", "") or ""
        for kind, phrase, _ptype, func in step_functions(content) or []:
            params = {a.arg for a in func.args.args}
            fixtures = {p: page_fixtures[p] for p in params if p in page_fixtures}
            reached: list = []
            seen: set = set()
            for fixture, method in _page_object_calls(func, fixtures):
                _methods_reached(classes, texts, fixtures[fixture], method, seen, reached)
            code = _source(content, func)
            keys = set(_SEL.findall(code)) | {k for _n, src in reached for k in _SEL.findall(src)}
            parts = [f"Step definition:\n{code}"]
            if reached:
                parts.append("Page-object methods that run for it (code below): "
                             + ", ".join(name for name, _src in reached))
            rows = _elements(inventory, keys)
            if rows:
                parts.append("Inventory elements this code reads:\n" + "\n".join(
                    f"- {k}: {sel}" + (f" - note: {note}" if note else "") for k, sel, note in rows))
            out.append({"id": f"S{len(out) + 1}", "path": path, "keyword": kind,
                        "phrase": phrase, "code": "\n\n".join(parts), "methods": reached,
                        "own": set(fixtures.values())})
    return out


def _signature(src: str) -> str:
    """A method's `def` line(s) and docstring - its code left out."""
    lines = textwrap.dedent(src).splitlines()
    try:
        func = ast.parse(textwrap.dedent(src)).body[0]
        head = "\n".join(lines[:func.body[0].lineno - 1])
        doc = ast.get_docstring(func)
    except (SyntaxError, IndexError, AttributeError):
        # A long method's code is cut at _MAX_METHOD_CHARS: its `def` line(s) still lead.
        end = next((i for i, line in enumerate(lines) if line.rstrip().endswith(":")), 0)
        head, doc = "\n".join(lines[:end + 1]), None
    body = f'    """{doc}"""\n' if doc else ""
    return f"{head}\n{body}    ...  # inherited helper - code not shown"


def _prompt(steps: list, limit: int) -> tuple:
    """(user prompt, steps read): the steps, then each method's code once.
    Over `limit`, inherited helpers (methods of a class no step's fixture
    names) are cut to their signature; still over, the last steps are left
    unread."""
    def build(chosen, short):
        methods: dict = {}
        for s in chosen:
            for name, src in s["methods"]:
                methods.setdefault(name, src)
        own = set().union(*(s["own"] for s in chosen)) if chosen else set()
        head = [f"## {s['id']}: {s['keyword'].capitalize()} {s['phrase']}\n{s['code']}"
                for s in chosen]
        if methods:
            head.append("## Page-object methods (each shown once)\n\n" + "\n\n".join(
                f"### {name}\n" + (_signature(src) if short and name.split(".")[0] not in own
                                   else src) for name, src in methods.items()))
        return "\n\n".join(head)

    for n in range(len(steps), 0, -1):
        for short in (False, True):
            text = build(steps[:n], short)
            if len(text) <= limit:
                if short:
                    logger.info("Step fidelity: inherited helpers shown by signature only - "
                                "the prompt would be over %d characters.", limit)
                return text, n
    return build(steps[:1], True), 1


def audit(llm, generated_files, inventory: dict, prompt: str, project_root=None,
          skip=()) -> list:
    """`Step fidelity error` lines for the steps the model reads as stand-ins.
    [] when there is nothing to judge or the call fails (never a reason to stop)."""
    steps = step_bindings(generated_files, inventory, project_root, skip)
    if not steps:
        return []
    user_prompt, read = _prompt(steps, _MAX_PROMPT_CHARS)
    if read < len(steps):
        logger.warning("Step fidelity: %d step(s) not read - the prompt is full.",
                       len(steps) - read)
    try:
        result = llm.invoke_structured(system_prompt=prompt, user_prompt=user_prompt,
                                       output_schema=StepFidelityAudit)
    except Exception as e:                                         # noqa: BLE001
        logger.warning("Step fidelity audit not run (%s): %s", type(e).__name__, e)
        return []
    if not isinstance(result, StepFidelityAudit):
        logger.warning("Step fidelity audit not run: the answer was not an audit")
        return []
    by_id = {s["id"]: s for s in steps}
    errors = []
    for finding in result.stand_ins:
        s = by_id.get((finding.id or "").strip())
        reason = " ".join((finding.reason or "").split())
        if s is None or not reason:
            continue
        errors.append(f"{PREFIX} in '{s['path']}': the step `{s['keyword'].capitalize()} "
                      f"{s['phrase']}` - {reason.rstrip('.')}. Its code acts on or checks a "
                      "different element than the step names, so the scenario passes or "
                      "fails for something the story does not state. If the app inventory "
                      "has no key for the element, a person adds it.")
    return errors
