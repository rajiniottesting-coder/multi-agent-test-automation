"""A claim that something is NOT there must survive into the code, and mean it.

WHAT WENT WRONG (validation story: "remove a field")
    A story removed a field from a page. No test case said the field was gone,
    so no scenario checked it, and every test passed against an application
    that still had the field. Agent 1 now has to verify each acceptance
    criterion (core.acceptance_coverage). This module makes sure the absence
    step it writes is not lost or emptied on the way to the browser:

    1. Claims carried (absence_claims_missing). A test case whose expected result
       says something is not shown, not present, no longer offered, gone or
       hidden must have a scenario with a Then step that says so. A scenario that
       quietly drops it passes whether or not the thing was removed.
    2. Steps that assert what they say (validate_absence_steps_assert_absence).
       A Then step worded "... should not ...", "no ... should be shown" must
       assert absence in its body: a negated predicate, an absence predicate
       (is_<thing>_absent, has_no_<things>), a `present=False` wait, `not in`,
       `== 0`. A body that only checks the page loaded passes either way.
    3. Absence proven on a loaded page (validate_absence_predicates_prove_their_page).
       A permanent element of a page - one the inventory does not list as
       conditional - is "absent" before the page has rendered and on every other
       page. An absence predicate for one must prove its page first
       (`return self.is_loaded() and self.is_gone(...)`), or a removal check
       passes on a blank screen.

Generic on purpose: the vocabulary is plain English about tests, and the only
application-specific input is the inventory's own `conditional` lists, so
nothing here names an application. Quoted text is message CONTENT, not the
claim's wording, and is ignored when deciding what a sentence claims.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

# ─────────────────────────────────────────────────────────────
# What a sentence claims
# ─────────────────────────────────────────────────────────────
_QUOTED = re.compile(r"(?<![A-Za-z])(['\"‘’“”])(?:(?!\1).){1,200}?\1(?![A-Za-z])"
                     r"|<[^<>]{1,80}>|\{[^{}]{1,80}\}")

_ON_SCREEN = (r"shown|show|displayed|display|visible|present|offered|offer(?:s|ing)?|available"
              r"|listed|rendered|there|included|appear(?:s|ed|ing)?|exists?|selectable"
              r"|editable|enabled")

# "Something is not on the screen": the claim a removal, a rename (the old
# wording), a hidden or disabled feature and a deleted item all reduce to.
_ABSENCE = re.compile(rf"""
      (?:\b(?:no\s+longer|not|never)\b|n't\b)[^.;\n]{{0,30}}?\b(?:{_ON_SCREEN})\b
    | \b(?:absent|gone|removed|hidden|disappear(?:s|ed)?|unavailable|non-?existent|missing)\b
    | \bno\s+(?:[\w'\-]+\s+){{0,4}}?(?:is|are)\s+(?:shown|displayed|present|visible|offered
          |available|listed|rendered|there)\b
    | \bno\s+(?:[\w'\-]+\s+){{0,3}}?(?:field|option|control|button|link|input|menu|tab|section
          |column|element|icon|entry|row|widget|label|text|message|dialog|pop-?up|modal)s?\b
""", re.IGNORECASE | re.VERBOSE)

# Wider: also "it cannot be reached" - a removed page or address.
_EXCLUSION = re.compile(r"""
      (?:\b(?:no\s+longer|not|never)\b|n't\b)[^.;\n]{0,30}?\b(?:found|reachable|accessible
          |opened|open|opens|loaded|navigat\w*|seen|see)\b
    | \bnot[\s-]+found\b | \b404\b | \bredirect\w*\s+(?:to|away)\b
""", re.IGNORECASE | re.VERBOSE)

_REFUSAL = re.compile(r"""
    \b(?:denied|forbidden|blocked|rejected|refused|prevented|unauthori[sz]ed|error|cannot|can't
       |unable|disabled|not\s+(?:allowed|permitted|authori[sz]ed|accepted|saved|submitted))\b
""", re.IGNORECASE | re.VERBOSE)


def _unquoted(text: str) -> str:
    """The sentence without quoted message content or <placeholders>."""
    return _QUOTED.sub(" ", text or "")


def states_absence(text: str) -> bool:
    """True when the sentence claims something is NOT on the screen."""
    return bool(_ABSENCE.search(_unquoted(text)))


def states_exclusion(text: str) -> bool:
    """states_absence, or something cannot be reached (not found, redirected away)."""
    plain = _unquoted(text)
    return bool(_ABSENCE.search(plain) or _EXCLUSION.search(plain))


def states_refusal(text: str) -> bool:
    """True when the sentence claims an action is refused, rejected or blocked."""
    return bool(_REFUSAL.search(_unquoted(text)))


# A Gherkin step that SAYS something is absent: the negation governs the step's
# own verb ("should not", "no ... should be shown"), not a quoted message or an
# adjective ("the password is not correct" is a presence claim about a message).
_NEGATED_STEP = re.compile(rf"""
      \b(?:should|must|does|do|will|would|can|could)\s+(?:not|no\s+longer|never)\b
    | \b(?:shouldn't|mustn't|doesn't|don't|won't|can't|cannot)\b
    | \b(?:is|are|was|were|be|remains?)\s+(?:not|no\s+longer|never)\s+(?:{_ON_SCREEN}|in|on|part)\b
    | \b(?:isn't|aren't|wasn't|weren't)\s+(?:{_ON_SCREEN}|in|on)\b
    | ^\s*(?:no|none\s+of|nothing)\b
    | \bno\s+longer\b
    | \b(?:is|are|be|remains?)\s+(?:absent|gone|hidden)\b
    | \bdisappears?\b
""", re.IGNORECASE | re.VERBOSE)


def negated_step(text: str) -> bool:
    """True when a Gherkin step's own wording asserts absence or refusal."""
    return bool(_NEGATED_STEP.search(_unquoted(text)))


def _short(text: str, limit: int = 110) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit - 3] + "..."


# ─────────────────────────────────────────────────────────────
# 1. Claims carried from the approved test case into its scenario
# ─────────────────────────────────────────────────────────────
_EXPECTED = re.compile(r"^\s*(?:[-*#]+\s*)?[_*]*expected[_*]*\s*:[_*]*\s*(.+)$", re.IGNORECASE)
_STEP_LINE = re.compile(r"^\s*(Given|When|Then|And|But|\*)\s+(.+)$")


def expected_results(description: str) -> list[str]:
    """Every step's expected result in a rendered test case description.

    Reads the tracker's rendering (`_Expected:_ ...`, wiki markup or markdown)
    line by line; [] for a description in any other shape.
    """
    out = []
    for line in (description or "").splitlines():
        m = _EXPECTED.match(line)
        if m:
            out.append(m.group(1).strip())
    return out


def absence_claims(description: str) -> list[str]:
    """The expected results of a test case that claim something is not there."""
    return [e for e in expected_results(description) if states_absence(e)]


def assertion_steps(scenario_text: str) -> list[str]:
    """The Then/And/But steps of one scenario (an And after a When is a When)."""
    out, mode = [], None
    for line in (scenario_text or "").splitlines():
        m = _STEP_LINE.match(line)
        if not m:
            continue
        keyword, text = m.groups()
        if keyword in ("Given", "When", "Then"):
            mode = keyword
        if mode == "Then":
            out.append(text.strip())
    return out


def absence_claims_missing(test_cases: list, scenarios: dict) -> list[str]:
    """Errors for scenarios that drop an absence claim their test case makes.

    test_cases: [{"key", "summary", "description"}]. scenarios: {key: (feature
    path, scenario text)} for the scenarios found in this batch; a test case
    with no scenario here is not judged (it is not in this batch).
    """
    errors = []
    for tc in test_cases or []:
        key = tc.get("key")
        if not key or key not in scenarios:
            continue
        claims = absence_claims(tc.get("description", ""))
        if not claims:
            continue
        path, text = scenarios[key]
        if any(negated_step(s) for s in assertion_steps(text)):
            continue
        errors.append(
            f"Absence claim error in '{path}': the scenario for {key} "
            f"('{_short(tc.get('summary', ''), 70)}') drops what its approved test case "
            f"asserts - \"{_short(claims[0])}\". Nothing in the scenario checks that it is "
            f"NOT there, so it passes whether or not the change happened. Add a Then (or "
            f"And) step that says so in the test case's words - for example \"Then <the "
            f"thing> should not be shown on <the page>\" - and give it a step definition "
            f"that asserts absence through an is_<thing>_absent() predicate.")
    return errors


# ─────────────────────────────────────────────────────────────
# 2. A step worded as absence asserts absence
# ─────────────────────────────────────────────────────────────
_ABSENCE_NAME = re.compile(r"absent|gone|hidden|(?:^|_)not(?:_|$)|(?:^|_)no(?:_|$)|missing"
                           r"|disappear|without|disabled|denied|refused|rejected|blocked"
                           r"|forbidden|error|cleared|empty|removed"
                           r"|(?:^|_)un(?:listed|shown|displayed|available|offered)", re.IGNORECASE)
_ABSENCE_WAITS = frozenset({"is_gone", "wait_hidden"})


def _call_name(call: ast.Call) -> str:
    f = call.func
    return getattr(f, "attr", None) or getattr(f, "id", None) or ""


def _is_false(node) -> bool:
    return isinstance(node, ast.Constant) and node.value is False


def _is_zero(node) -> bool:
    return isinstance(node, ast.Constant) and node.value == 0 and node.value is not False


def answers_absence(func: ast.AST, page_methods: dict | None = None) -> bool:
    """True when the function body asserts or waits for something to be absent.

    page_methods ({fixture name: {method name: ast}}) lets a call on a page
    object count when the METHOD answers absence - `wait_until_unlisted()`
    built on `wait_for_row(..., present=False)` - whatever its name says.
    """
    params = {a.arg for a in getattr(getattr(func, "args", None), "args", [])}
    for node in ast.walk(func):
        if isinstance(node, ast.Assert):
            t = node.test
            if isinstance(t, ast.UnaryOp) and isinstance(t.op, ast.Not):
                return True
            if isinstance(t, ast.Compare):
                for op, right in zip(t.ops, t.comparators):
                    if isinstance(op, (ast.NotIn, ast.IsNot)):
                        return True
                    if isinstance(op, (ast.Is, ast.Eq)) and (_is_false(right) or _is_zero(right)
                                                             or (isinstance(right, ast.Constant)
                                                                 and right.value is None)):
                        return True
        if isinstance(node, ast.Call):
            name = _call_name(node)
            if name in _ABSENCE_WAITS or _ABSENCE_NAME.search(name):
                return True
            owner = getattr(node.func, "value", None)
            if (page_methods and isinstance(owner, ast.Name) and owner.id in params
                    and owner.id in page_methods):
                method = page_methods[owner.id].get(name)
                if method is not None and _absence_answer_in(method):
                    return True
            if any(_is_false(a) for a in node.args) or \
                    any(_is_false(k.value) for k in node.keywords):
                return True
    return False


def _step_texts(func: ast.AST) -> list[tuple[str, str]]:
    """[(keyword, phrase)] this function is bound to."""
    out = []
    for dec in getattr(func, "decorator_list", []):
        if not isinstance(dec, ast.Call):
            continue
        name = getattr(dec.func, "id", None) or getattr(dec.func, "attr", None)
        if name not in {"given", "when", "then"}:
            continue
        for node in ast.walk(dec):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                out.append((name, node.value))
                break
    return out


def _page_methods(generated_files, project_root) -> dict:
    """{fixture name: {method name: ast}} for the page objects - this batch
    first, then the committed ones."""
    from validators.method_resolution_validator import _page_classes
    out: dict = {}
    for fixture, (cls, _path) in _page_classes(generated_files, Path(project_root or ".")).items():
        out[fixture] = {n.name: n for n in cls.body
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return out


def validate_absence_steps_assert_absence(generated_files: list,
                                          project_root=None) -> list[str]:
    """Fail a Then step worded as absence whose body never asserts absence."""
    errors: list[str] = []
    page_methods = None
    for f in generated_files or []:
        path = (getattr(f, "file_path", "") or "").replace("\\", "/")
        if not (path.startswith("tests/") and path.endswith(".py")):
            continue
        try:
            tree = ast.parse(getattr(f, "content", "") or "")
        except SyntaxError:
            continue
        for func in ast.walk(tree):
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            phrases = [p for kw, p in _step_texts(func) if kw == "then" and negated_step(p)]
            if not phrases or answers_absence(func):
                continue
            if page_methods is None:
                page_methods = _page_methods(generated_files, project_root)
            if answers_absence(func, page_methods):
                continue
            errors.append(
                f"Absence step error in '{path}' line {func.lineno}: the step "
                f"\"{_short(phrases[0], 90)}\" says something is NOT there, but "
                f"{func.name}() asserts nothing that answers absence, so it passes whether or "
                f"not the thing is there. Assert it is gone: `assert <page>.is_<thing>_absent()` "
                f"(a page-object predicate built on self.is_gone()), `assert not <page>.has_"
                f"<thing>()` for a conditional element, a `present=False` wait, or `not in` / "
                f"`== 0` on what the page lists.")
    return errors


# ─────────────────────────────────────────────────────────────
# 3. Absence of a permanent element is proven on a loaded page
# ─────────────────────────────────────────────────────────────
_PAGE_PROOFS = frozenset({"is_loaded", "require_own_page", "confirm_arrival", "is_showing",
                          "wait_visible", "wait_for_text"})


def _sel_keys(func: ast.AST) -> set:
    keys = set()
    for node in ast.walk(func):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "sel" and node.args
                and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
            keys.add(node.args[0].value)
    return keys


def _self_call(node: ast.AST) -> str | None:
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "self"):
        return node.func.attr
    return None


def _absence_answer_in(func: ast.AST) -> bool:
    """Does the method answer "is it absent?" - is_gone/wait_hidden, a negated
    glance, a zero count, or a present=False wait?"""
    for node in ast.walk(func):
        name = _self_call(node)
        if name in _ABSENCE_WAITS:
            return True
        if name and any(k.arg == "present" and _is_false(k.value) for k in node.keywords):
            return True
        if (isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not)
                and _self_call(node.operand) in {"is_visible", "exists"}):
            return True
        if (isinstance(node, ast.Compare) and _self_call(node.left) in {"get_count", "get_row_count"}
                and any(isinstance(op, ast.Eq) for op in node.ops)
                and any(_is_zero(c) for c in node.comparators)):
            return True
    return False


def _proves_page(func: ast.AST) -> bool:
    return any(_self_call(n) in _PAGE_PROOFS for n in ast.walk(func))


def _inventory_pages(project_root: Path) -> dict:
    """{page_object_class: {"conditional": set, "page": name}} from the configured
    inventory; {} when it cannot be read (a validator never kills a run)."""
    from validators.method_resolution_validator import _load_configured_inventory
    out: dict = {}
    for name, spec in ((_load_configured_inventory(project_root) or {}).get("pages") or {}).items():
        if isinstance(spec, dict) and spec.get("page_object_class"):
            out[spec["page_object_class"]] = {
                "conditional": set(spec.get("conditional") or []), "page": name}
    return out


def _disk_methods(project_root: Path, path: str) -> dict:
    """{(class, method): ast.dump} of the committed version of a page object."""
    out: dict = {}
    try:
        tree = ast.parse((project_root / path).read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return out
    for cls in tree.body:
        if isinstance(cls, ast.ClassDef):
            for node in cls.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out[(cls.name, node.name)] = ast.dump(node)
    return out


def validate_absence_predicates_prove_their_page(generated_files: list,
                                                 project_root=None) -> list[str]:
    """Fail a NEW or CHANGED absence predicate on a permanent element that does
    not prove its page is there first. Committed methods are left alone."""
    root = Path(project_root or ".")
    pages = _inventory_pages(root)
    errors: list[str] = []
    for f in generated_files or []:
        path = (getattr(f, "file_path", "") or "").replace("\\", "/")
        if not (path.startswith("pages/") and path.endswith(".py")) or path.endswith("base_page.py"):
            continue
        try:
            tree = ast.parse(getattr(f, "content", "") or "")
        except SyntaxError:
            continue
        committed = _disk_methods(root, path)
        for cls in tree.body:
            if not isinstance(cls, ast.ClassDef):
                continue
            methods = [n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            if not any(m.name == "is_loaded" for m in methods):
                continue                                 # no page-load proof to require
            conditional = (pages.get(cls.name) or {}).get("conditional", set())
            for m in methods:
                if m.name == "is_loaded" or m.name.startswith("_"):
                    continue
                if committed.get((cls.name, m.name)) == ast.dump(m):
                    continue                             # unchanged committed code
                if not _absence_answer_in(m) or _proves_page(m):
                    continue
                permanent = sorted(_sel_keys(m) - conditional)
                if not permanent:
                    continue
                key = permanent[0]
                errors.append(
                    f"Absence proof error in '{path}' line {m.lineno}: {cls.name}.{m.name}() "
                    f"answers that '{key}' is absent, but '{key}' is a permanent element of this "
                    f"page (the inventory does not list it as conditional). It is just as absent "
                    f"before the page has rendered, or on any other page, so the check passes "
                    f"whether or not it was removed. Prove the page first: `return "
                    f"self.is_loaded() and self.is_gone(self.sel(\"{key}\"))`.")
    return errors
