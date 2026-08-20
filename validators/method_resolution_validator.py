"""
Method resolution validator (Hotfix v5).

PURPOSE:
    For every step-definition file in the generated batch, verify that every
    method call on a page-object variable (like `inventory_page.click_logout()`)
    actually corresponds to a method defined on that page object class.

THE FAILURE MODES THIS CATCHES:

    (A) Cross-file naming inconsistency within the same generation batch.
        The LLM names a method `click_logout()` in `inventory_page.py` but
        calls it as `click_logout_link()` in `test_logout.py`. Both files
        are generated 10–20 seconds apart and the LLM "forgets" what it
        named things between calls. Result: AttributeError at test time.

    (B) Hallucinated methods on RESERVED page objects.
        The LLM calls `login_page.are_login_form_fields_visible()` even
        though `SomePage` is a reserved file with only `open`, `login_as`,
        and `get_error_message`. Reserved files can't be modified, so the
        method must exist already — but it doesn't.

    (C) Method calls on subclassed page objects that miss inherited methods.
        Methods defined on `BasePage` (like `is_visible`, `navigate`) are
        legitimately inherited; this validator must accept them, not flag
        them as missing.

DESIGN PRINCIPLES (app-agnostic, reusable across projects):

    1. NO HARDCODED PROJECT KNOWLEDGE.
       Class-name-to-fixture mapping is inferred from `@pytest.fixture`
       definitions in the same file. Method definitions come from AST
       parsing of the imported page object source. Inheritance is
       resolved by following the import chain.

    2. STATIC ANALYSIS ONLY.
       Uses Python's `ast` module — no code execution. Safe on any input.

    3. HANDLES THE THREE CONTEXTS:
       - In-batch generated file (e.g., the inventory_page.py being
         generated alongside test_logout.py)
       - Reserved/extendable file already on disk
       - Inherited from a base class (BasePage)

    4. CLEAR, REPAIR-FRIENDLY ERRORS.
       Errors use the same `<type> error in '<path>':` format as the
       coverage and import validators so the existing repair loop can
       group them by file and pass targeted feedback to the LLM.

    5. CONSERVATIVE — FALSE POSITIVES > FALSE NEGATIVES OK.
       If the validator can't statically determine whether a call is
       valid (e.g., the variable's class can't be inferred), it stays
       silent. We'd rather miss a real bug than flag a false one and
       waste a repair attempt.

USAGE:
    from validators.method_resolution_validator import validate_method_resolution
    errors = validate_method_resolution(generated_files, project_root)
    # errors is a list[str]; empty means all method calls resolve

SCOPE LIMITS (intentional):
    - Only validates step_definitions files. Other file types are
      skipped entirely.
    - Only validates calls of the form `<var>.<method>(...)` where
      `<var>` is a function parameter (a fixture). Direct `Class.method()`
      calls are not validated.
    - Does NOT validate method SIGNATURES (argument count or types).
      Catching name mismatches is sufficient to prevent the AttributeError
      class of bugs we've seen in production.
"""
from __future__ import annotations

import ast
import ast as _ast
import logging
import re
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)


# Public attributes on Playwright's Page class that are commonly used in
# step defs (e.g., `inventory_page.page.url`, `login_page.page.click(...)`).
# We don't validate calls on `.page` — Playwright's API is stable and
# documented externally. Listing them here would be brittle.
#
# Instead, we look for the `.page` attribute access pattern and skip the
# call entirely. See `_is_playwright_page_call`.


def _parse_class_methods(source: str, class_name: str) -> set[str]:
    """Extract all method names defined on a class from Python source.

    Returns:
        Set of method names. Empty if the class isn't found or source
        can't be parsed. Includes inherited methods only if they're
        explicitly redefined — true inheritance is resolved separately.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()

    methods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.add(item.name)
            # Don't break — handle the (unusual) case of duplicate class
            # names by collecting from all of them. AST will have caught
            # syntax issues already.
    return methods


def _parse_class_bases(source: str, class_name: str) -> list[str]:
    """Extract base class names for a class, in MRO-ish order.

    Returns:
        List of base class names. Only simple names are returned;
        complex bases like `module.Class` keep just the rightmost
        identifier. Empty if class not found.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            bases: list[str] = []
            for base in node.bases:
                if isinstance(base, ast.Name):
                    bases.append(base.id)
                elif isinstance(base, ast.Attribute):
                    # e.g., `pages.base_page.BasePage` -> `BasePage`
                    bases.append(base.attr)
            return bases
    return []


def _parse_imports_for_classes(source: str) -> dict[str, str]:
    """Parse `from X import Y` statements and return a {class_name: module}
    mapping for all imported names that look like class names (CapWords).

    This lets us resolve `SomePage` -> `pages.some_page` even when the
    import line is `from pages.some_page import SomePage`.

    Returns:
        Dict mapping imported name -> dotted module path it came from.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}

    mapping: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                imported_as = alias.asname or alias.name
                # Heuristic: class names are CapWords. Skip lowercase
                # imports (functions, modules).
                if imported_as and imported_as[0].isupper():
                    mapping[imported_as] = module
    return mapping


def _parse_fixtures(source: str) -> dict[str, str]:
    """Find `@pytest.fixture` definitions and return a {fixture_name: returned_class}
    mapping.

    For step def files, the typical pattern is:
        @pytest.fixture
        def login_page(page):
            return SomePage(page)

    We look for that exact shape: a fixture-decorated function that
    returns a single instantiation of a class. Other fixture shapes
    are skipped (we'd rather miss than guess wrong).

    Returns:
        Dict mapping fixture variable name -> class name it instantiates.
        E.g., {"some_page": "SomePage", "other_page": "OtherPage"}.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}

    fixtures: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue

        # Check for @pytest.fixture or @fixture decorator
        is_fixture = False
        for dec in node.decorator_list:
            if isinstance(dec, ast.Name) and dec.id == "fixture":
                is_fixture = True
            elif isinstance(dec, ast.Attribute) and dec.attr == "fixture":
                is_fixture = True
            elif isinstance(dec, ast.Call):
                # @pytest.fixture(scope="session") form
                if isinstance(dec.func, ast.Attribute) and dec.func.attr == "fixture":
                    is_fixture = True
                elif isinstance(dec.func, ast.Name) and dec.func.id == "fixture":
                    is_fixture = True

        if not is_fixture:
            continue

        # Look for a return statement instantiating a class
        for child in ast.walk(node):
            if isinstance(child, ast.Return) and isinstance(child.value, ast.Call):
                func = child.value.func
                if isinstance(func, ast.Name) and func.id and func.id[0].isupper():
                    fixtures[node.name] = func.id
                    break

    return fixtures


def _is_playwright_page_call(call_node: ast.Call) -> bool:
    """Detect calls of the form `<page_obj>.page.<anything>(...)`.

    These are direct Playwright Page API calls. We skip validation for
    them because Playwright's API is external and stable.

    Returns:
        True if the call is on a `.page.` chain (e.g., `lp.page.click()`).
    """
    func = call_node.func
    if not isinstance(func, ast.Attribute):
        return False
    # func.value is the thing being called .method on
    inner = func.value
    if isinstance(inner, ast.Attribute) and inner.attr == "page":
        return True
    return False


def _extract_method_calls_on_fixtures(
    source: str, fixture_names: set[str]
) -> list[tuple[str, str, int]]:
    """Find every `<fixture>.<method>(...)` call in the source.

    Args:
        source: Python source code to analyze.
        fixture_names: Set of variable names known to be page-object
            fixtures (from `_parse_fixtures` + step function args).

    Returns:
        List of (fixture_name, method_name, line_number) tuples.
        Calls that aren't on known fixtures are skipped.
        Calls on `.page.` (Playwright API) are skipped.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    calls: list[tuple[str, str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _is_playwright_page_call(node):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        # We want `<Name>.method(...)` where <Name> is a known fixture
        if not isinstance(func.value, ast.Name):
            continue
        var_name = func.value.id
        if var_name not in fixture_names:
            continue
        method_name = func.attr
        line = getattr(node, "lineno", 0)
        calls.append((var_name, method_name, line))
    return calls


def _collect_step_def_function_args(source: str) -> set[str]:
    """Find all parameter names used by step-definition functions
    (i.e., functions decorated with @given/@when/@then).

    These parameters are also fixture references — pytest-bdd injects
    fixtures by name. This catches calls like `inventory_page.foo()`
    where `inventory_page` is a step function parameter, not a local
    @pytest.fixture in this file.

    Returns:
        Set of parameter names that appear in step-decorated functions.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()

    params: set[str] = set()
    step_decorators = {"given", "when", "then"}

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue

        is_step = False
        for dec in node.decorator_list:
            # @given("..."), @when(...), @then(...)
            if isinstance(dec, ast.Call):
                f = dec.func
                if isinstance(f, ast.Name) and f.id in step_decorators:
                    is_step = True
                    break
                # @parsers.parse(...) wrapped — look one level deeper
                if isinstance(f, ast.Attribute) and f.attr in step_decorators:
                    is_step = True
                    break
            elif isinstance(dec, ast.Name) and dec.id in step_decorators:
                is_step = True
                break

        if is_step:
            for arg in node.args.args:
                params.add(arg.arg)

    return params


def _resolve_class_methods_with_inheritance(
    class_name: str,
    class_sources: dict[str, str],
    project_root: Path,
    visited: set[str] | None = None,
) -> set[str]:
    """Walk the inheritance chain of a class and collect all method names.

    Args:
        class_name: Class to start from.
        class_sources: Map of {class_name: source_text} for in-batch
            generated files. Lets us resolve classes that haven't been
            written to disk yet.
        project_root: Used to read base classes from disk if not in batch.
        visited: Internal — tracks visited classes to avoid infinite loops.

    Returns:
        Set of all method names available on instances of this class.
    """
    if visited is None:
        visited = set()
    if class_name in visited:
        return set()
    visited.add(class_name)

    methods: set[str] = set()

    # Try in-batch source first
    source = class_sources.get(class_name)
    if source is None:
        # Try to find the class on disk by checking common locations
        source = _find_class_source_on_disk(class_name, project_root)

    if source is None:
        return methods

    methods.update(_parse_class_methods(source, class_name))

    # Recurse into base classes
    for base_name in _parse_class_bases(source, class_name):
        if base_name == "object":
            continue
        methods.update(
            _resolve_class_methods_with_inheritance(
                base_name, class_sources, project_root, visited
            )
        )

    return methods


def _find_class_source_on_disk(class_name: str, project_root: Path) -> str | None:
    """Search the `pages/` directory for a class definition.

    Returns:
        File source as string if class is found, else None.
        Conservative: only searches `pages/` to avoid scanning the world.
    """
    pages_dir = project_root / "pages"
    if not pages_dir.exists():
        return None

    for py_file in pages_dir.glob("*.py"):
        if py_file.name.startswith("_"):
            continue
        try:
            source = py_file.read_text(encoding="utf-8")
        except OSError:
            continue
        # Quick check before parsing
        if f"class {class_name}" not in source:
            continue
        # Confirm via AST
        try:
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == class_name:
                    return source
        except SyntaxError:
            continue
    return None


def _build_class_source_map(
    generated_files: Iterable, project_root: Path
) -> dict[str, str]:
    """Build a {class_name: source_code} map covering both:
      - Page object files in this generation batch
      - Existing page object files on disk (for reserved/inherited classes)

    In-batch sources take precedence — if `inventory_page.py` is being
    extended in this batch, the new content wins over what's on disk.

    Returns:
        Dict mapping class name -> source code where it's defined.
    """
    sources: dict[str, str] = {}

    # Add in-batch generated page objects (highest priority)
    for f in generated_files:
        path = getattr(f, "file_path", "")
        content = getattr(f, "content", "")
        if not path.endswith(".py"):
            continue
        if not content:
            continue
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                sources[node.name] = content

    # Fill in classes only on disk (lower priority — don't overwrite batch)
    pages_dir = project_root / "pages"
    if pages_dir.exists():
        for py_file in pages_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            try:
                source = py_file.read_text(encoding="utf-8")
                tree = ast.parse(source)
            except (OSError, SyntaxError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name not in sources:
                    sources[node.name] = source

    return sources


def validate_method_resolution(
    generated_files: list, project_root: Path
) -> list[str]:
    """Verify that every page-object method called in step def files
    actually exists on the corresponding page object class.

    Args:
        generated_files: List of GeneratedFile objects (must have
            `file_path` and `content` attributes).
        project_root: Path to the repo root, used to read existing
            page objects on disk for inheritance resolution.

    Returns:
        List of error strings. Empty means all method calls resolve.
        Each error is in the format:
            "Method resolution error in '<step_def_path>': <details>"
        which the existing repair loop knows how to parse and target.
    """
    errors: list[str] = []

    # First pass: build the universe of known classes and their sources
    class_sources = _build_class_source_map(generated_files, project_root)

    # Second pass: validate each step-def file
    for f in generated_files:
        path = getattr(f, "file_path", "")
        content = getattr(f, "content", "")
        if not path.startswith("tests/step_defs/") or not path.endswith(".py"):
            continue
        if not content:
            continue

        # Determine which fixture-named variables in this file refer to
        # which page object classes.
        imported_classes = _parse_imports_for_classes(content)
        local_fixtures = _parse_fixtures(content)
        step_func_args = _collect_step_def_function_args(content)

        # Combined fixture name set: locally defined fixtures + step
        # function args (which are also fixture references at runtime).
        fixture_names = set(local_fixtures.keys()) | step_func_args

        # Map fixture variable -> class name
        # Priority: explicit local fixture > naming-convention inference
        fixture_to_class: dict[str, str] = dict(local_fixtures)

        # Naming-convention fallback: `inventory_page` -> `InventoryPage`,
        # `login_page` -> `SomePage`. Only applies to step function args
        # that aren't already mapped via a local fixture.
        for name in step_func_args:
            if name in fixture_to_class:
                continue
            cap_class = "".join(part.capitalize() for part in name.split("_"))
            if cap_class in imported_classes or cap_class in class_sources:
                fixture_to_class[name] = cap_class

        # Find every method call on a fixture variable
        calls = _extract_method_calls_on_fixtures(content, fixture_names)

        # Validate each call
        for var_name, method_name, line_no in calls:
            class_name = fixture_to_class.get(var_name)
            if class_name is None:
                # Can't resolve which class this fixture refers to.
                # Stay silent — we don't want false positives.
                continue

            available_methods = _resolve_class_methods_with_inheritance(
                class_name, class_sources, project_root
            )
            if not available_methods:
                # We couldn't read the class at all — don't flag, the
                # import validator probably already caught this.
                continue

            if method_name not in available_methods:
                # Build a helpful error with suggestions
                similar = _find_similar_methods(method_name, available_methods)
                methods_list = ", ".join(sorted(available_methods))
                err = (
                    f"Method resolution error in '{path}': "
                    f"line {line_no} calls `{var_name}.{method_name}()`, "
                    f"but `{class_name}` does not define `{method_name}`. "
                )
                if similar:
                    err += f"Did you mean one of: {', '.join(similar)}? "
                err += f"Available methods on `{class_name}`: [{methods_list}]."
                errors.append(err)

    return errors


def _find_similar_methods(target: str, available: set[str]) -> list[str]:
    """Find method names similar to `target` from `available`.

    Uses a simple substring + token-overlap heuristic. Returns up to
    3 candidates, most similar first.
    """
    target_tokens = set(re.split(r"_", target.lower()))
    target_tokens.discard("")

    scored: list[tuple[int, str]] = []
    for name in available:
        if name.startswith("_"):
            continue  # private methods not useful suggestions
        name_tokens = set(re.split(r"_", name.lower()))
        name_tokens.discard("")
        overlap = len(target_tokens & name_tokens)
        # Bonus if one is a substring of the other
        if target.lower() in name.lower() or name.lower() in target.lower():
            overlap += 2
        if overlap > 0:
            scored.append((overlap, name))

    scored.sort(key=lambda x: (-x[0], x[1]))
    return [name for _, name in scored[:3]]

# ═════════════════════════════════════════════════════════════════════════
# Page-object selector validator
#
# WHY THIS EXISTS (SCRUM-104, 31 Jul 2026):
#     `tests/unit/test_page_object_selectors.py` enforces the rule this whole
#     design rests on — a page object resolves selectors through
#     `self.sel("<key>")` against the app inventory, never from a literal
#     string. That rule was enforced ONLY by that unit test, which runs in
#     Agent 4, i.e. AFTER generation, AFTER the PR is open and AFTER the LLM
#     tokens are spent. Agent 2's own gate had eight validators and none of
#     them looked at page objects' selectors, so it happily shipped a page
#     object carrying four raw CSS literals and the red check landed on the
#     story PR.
#
#     This closes that loop: the same rule, checked statically at generation
#     time, feeding the repair loop so the model can self-correct before a
#     branch is ever created.
#
# THE TWO ESCAPE ROUTES IT CLOSES:
#     When the inventory lacks an element the story needs, a model has exactly
#     two ways to proceed anyway, and both produce code that cannot pass:
#       (A) invent a literal selector       -> caught by the literal scan
#       (B) invent an inventory key         -> caught by the key check
#     The intended third route — request the element via the plan's `notes`
#     field — is the only one this validator leaves open, which is the point.
#
# APP-AGNOSTIC: the rule is about SHAPE (a literal that looks like a selector)
# and about REFERENTIAL INTEGRITY (a key that must exist in whatever inventory
# is configured). No application, page or element name appears here.
# ═════════════════════════════════════════════════════════════════════════

# A selector-looking literal: bare CSS, or one of Playwright's engine prefixes.
# Deliberately the SAME shape as tests/unit/test_page_object_selectors.py — the
# two must agree, or generation passes and the unit gate still fails.
_SELECTOR_LITERAL_RE = re.compile(
    r'=\s*"(?:'
    r'\s*[.#\[]'                                    # .class  #id  [attr=…]
    r'|(?:role|text|label|alt|title|placeholder)='   # playwright engines
    r')[^"]*"'
)

_ERROR_PREFIX = "Selector inventory error"

# How many inventory keys to name when reporting an unknown one. Enough to be
# actionable, few enough that the repair prompt does not drown in them.
_MAX_KEYS_LISTED = 25

# BasePage helpers that are SAFE against a selector matching many elements,
# because they read or count the whole match set instead of asserting on one.
# Everything else is treated as strict: Playwright raises "strict mode
# violation: locator(...) resolved to N elements" the moment a locator that
# matches 2+ nodes is clicked, filled, waited on or asserted against.
#
# A WHITELIST, deliberately - not a blacklist. A helper added to BasePage
# tomorrow is strict until someone proves otherwise, which fails safe. The
# table helpers are here because a row-family locator is exactly what they are
# built to take.
# Helpers that READ a whole family. These are what the error message offers
# when someone wants the set rather than one member.
_FAMILY_READERS = frozenset({
    "get_all_texts", "get_count", "exists", "get_nth_text",
    "get_row_count", "get_column_values", "find_row_index_by_text",
    "get_cell_text",
})

# Helpers BUILT to take a family selector and resolve it to one element
# internally. Passing a family key to these is not a mistake, it is the
# documented signature - select_autocomplete_suggestion exists precisely so a
# page object never has to disambiguate an async suggestion list by hand.
# Without this set the validator rejected the very helper it tells people to
# use, and the repair loop then rewrote correct code (SCRUM-103, 31 Jul 2026).
_FAMILY_CONSUMERS = frozenset({
    "select_autocomplete_suggestion",
    # Address ONE member of a family by position. This is the sanctioned
    # alternative to building `">> nth=" + index` in a page object, and the
    # index is expected to come from find_row_index_by_text() - so the element
    # is identified by what it SAYS before it is reached by where it sits.
    "click_nth",
    "get_nth_attribute",
    # Scope to the row containing a text, then act inside it. This is the
    # PREFERRED way to touch one member of a family - it needs no index, so two
    # families never have to agree on cardinality or order.
    "click_in_row",
    "row_containing",
})

_PLURAL_SAFE_METHODS = _FAMILY_READERS | _FAMILY_CONSUMERS


def _is_page_object_path(file_path: str) -> bool:
    """True for `pages/<something>_page.py`, excluding the base class.

    Normalises separators first: a plan produced on Windows carries
    backslashes, and `pages\\admin_users_page.py` must match too.
    """
    norm = (file_path or "").replace("\\", "/").lstrip("./")
    if not norm.startswith("pages/"):
        return False
    name = norm.rsplit("/", 1)[-1]
    return name.endswith("_page.py") and name != "base_page.py"


def _load_configured_inventory(project_root: Path) -> dict | None:
    """The app inventory the framework is currently pointed at, or None.

    Returns None rather than raising on ANY problem (no config, no
    `inventory_file`, missing or malformed JSON). A validator must never be
    the reason a run dies: when the inventory cannot be read, the literal
    scan still runs and only the key check is skipped.
    """
    try:
        import json
        import yaml
        config_yaml = project_root / "config" / "config.yaml"
        cfg = yaml.safe_load(config_yaml.read_text(encoding="utf-8")) or {}
        rel = (cfg.get("app_under_test") or {}).get("inventory_file")
        if not rel:
            return None
        path = project_root / rel
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception as exc:                       # noqa: BLE001 - see docstring
        logger.warning("Selector validator: inventory unreadable (%s).", exc)
        return None


def _class_inventory_page(class_node: ast.ClassDef) -> str | None:
    """The class-level `INVENTORY_PAGE = "..."` value, or None if not set."""
    for node in class_node.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "INVENTORY_PAGE":
                if isinstance(node.value, ast.Constant) and isinstance(
                        node.value.value, str):
                    return node.value.value
    return None


def _sel_keys_used(class_node: ast.ClassDef) -> list[str]:
    """Constant keys passed to `self.sel(...)` / `cls.sel(...)` in the class.

    Only literal strings are collected. A computed key (an f-string, a
    variable, a dict lookup) is unknowable statically and is left alone
    rather than guessed at — a false accusation would send the repair loop
    chasing correct code.
    """
    keys: list[str] = []
    for node in ast.walk(class_node):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "sel":
            continue
        if not isinstance(func.value, ast.Name) or func.value.id not in {"self", "cls"}:
            continue
        if node.args and isinstance(node.args[0], ast.Constant) and isinstance(
                node.args[0].value, str):
            keys.append(node.args[0].value)
    return keys


def _strict_uses_of_sel(class_node: ast.ClassDef) -> list[tuple[str, str, int]]:
    """(sel_key, calling_method, lineno) for every self.sel() used STRICTLY.

    A "strict use" is `self.<method>(... self.sel("<key>") ...)` where <method>
    is not in _PLURAL_SAFE_METHODS. The outer call is what decides: the same
    key is fine in get_all_texts() and fatal in click().

    Only literal keys inside a call are reported. A key stashed in a variable
    first, or built with an f-string, is not traced - a static guess there
    would produce false accusations, and a false accusation sends the repair
    loop rewriting correct code.
    """
    found: list[tuple[str, str, int]] = []
    for outer in ast.walk(class_node):
        if not isinstance(outer, ast.Call):
            continue
        func = outer.func
        if not isinstance(func, ast.Attribute):
            continue
        method = func.attr
        if method == "sel":                     # the sel() call itself
            continue
        for arg in list(outer.args) + [kw.value for kw in outer.keywords]:
            for inner in ast.walk(arg):
                if (isinstance(inner, ast.Call)
                        and isinstance(inner.func, ast.Attribute)
                        and inner.func.attr == "sel"
                        and isinstance(inner.func.value, ast.Name)
                        and inner.func.value.id in {"self", "cls"}
                        and inner.args
                        and isinstance(inner.args[0], ast.Constant)
                        and isinstance(inner.args[0].value, str)):
                    if method not in _PLURAL_SAFE_METHODS:
                        found.append((inner.args[0].value, method,
                                      getattr(outer, "lineno", 0)))
    return found


def validate_page_object_selectors(
    generated_files: Iterable,
    project_root: Path,
    inventory: dict | None = None,
) -> list[str]:
    """Every generated page object must resolve selectors through the inventory.

    Checks three things, in the order a reader would:

      1. no selector literal appears anywhere in the file
      2. every page-object class declares `INVENTORY_PAGE`, and that page
         exists in the inventory
      3. every literal key passed to `self.sel(...)` exists on that page

    Returns a list of human-readable errors; empty means the batch is clean.
    Never raises: a file that does not parse is skipped (the syntax error is
    reported by the tooling that owns it), and an unreadable inventory
    downgrades to the literal scan alone.

    `inventory` is injectable so tests can supply a synthetic app; production
    callers leave it None and the configured one is loaded.
    """
    errors: list[str] = []

    page_objects = [
        f for f in (generated_files or [])
        if _is_page_object_path(getattr(f, "file_path", ""))
    ]
    if not page_objects:
        return errors

    if inventory is None:
        inventory = _load_configured_inventory(project_root)
    pages = (inventory or {}).get("pages")
    pages = pages if isinstance(pages, dict) else None

    for gen_file in page_objects:
        path = gen_file.file_path
        source = getattr(gen_file, "content", "") or ""

        # ── 1. literal selectors ──────────────────────────────────────
        for lineno, line in enumerate(source.splitlines(), 1):
            stripped = line.strip()
            # Same skip list as the unit test: comments and docstring/prose
            # lines legitimately SHOW a selector while teaching the rule.
            if stripped.startswith(("#", '"', "'", "*")):
                continue
            if _SELECTOR_LITERAL_RE.search(line):
                errors.append(
                    f"{_ERROR_PREFIX} in '{path}' line {lineno}: literal "
                    f"selector `{stripped[:70]}`. Page objects must call "
                    f'self.sel("<key>") and the element must be added to the '
                    f"app inventory. If the element is not in the inventory, "
                    f"request it in the plan's `notes` instead of inventing a "
                    f"selector."
                )

        # ── 1b. locator SYNTAX assembled in code ──────────────────────
        syntax_lines: set[int] = set()
        # A page object may resolve a key and it may pass that key around, but
        # it must never build Playwright locator syntax itself. `f"{self.sel(
        # 'rows')} >> nth={i}"` reads as inventory-driven and is not: it welds
        # a raw locator fragment onto a resolved value, in the one place the
        # literal-selector scan above cannot see, because the literal is a
        # format-string tail rather than a quoted selector.
        #
        # It shipped on main and reached a pull request. Agent 3 flagged it -
        # correctly - but Agent 3 only advises. This makes it blocking.
        # Lines that sit INSIDE a string constant are prose, not code. The
        # prefix test used elsewhere only catches a line that STARTS with a
        # quote, so the middle of a multi-line docstring slips through - and
        # documenting an anti-pattern by showing it is exactly the house style
        # base_page.py uses and Agent 2 copies. Ask the AST instead of guessing.
        doc_lines: set[int] = set()
        try:
            for node in _ast.walk(_ast.parse(source)):
                # A DOCSTRING is a bare string statement - an Expr whose value
                # is a plain string. Matching every string Constant instead
                # would swallow the f-string parts of the very expression this
                # rule exists to catch, because `f"...>> nth={i}"` is built
                # from Constant pieces too.
                if (isinstance(node, _ast.Expr)
                        and isinstance(node.value, _ast.Constant)
                        and isinstance(node.value.value, str)):
                    doc_lines.update(
                        range(node.lineno, (node.end_lineno or node.lineno) + 1))
        except SyntaxError:
            # Unparseable: fall back to scanning every line. A half-written
            # file is the repair loop's problem, and over-reporting here is
            # safer than letting a real violation through.
            pass

        for lineno, line in enumerate(source.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("#", '"', "'", "*")) or lineno in doc_lines:
                continue
            if ">> nth=" in line or ">>nth=" in line:
                syntax_lines.add(lineno)
                errors.append(
                    f"{_ERROR_PREFIX} in '{path}' line {lineno}: locator "
                    f"syntax built in code `{stripped[:70]}`. Use "
                    f"self.click_nth(self.sel(\"<key>\"), index) - the "
                    f"index-pinning belongs in BasePage, not assembled from a "
                    f"string here. To find the index by what the row SAYS, "
                    f"use self.find_row_index_by_text(...) first."
                )

        # ── 2 & 3. inventory wiring ───────────────────────────────────
        try:
            tree = ast.parse(source)
        except SyntaxError:
            # Unparseable file: the literal scan above still applied. Leave the
            # syntax error itself to be reported once, by its owner.
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            sel_keys = _sel_keys_used(node)
            inv_page = _class_inventory_page(node)

            # A class that never calls sel() and declares no INVENTORY_PAGE is
            # not a page object (a helper, an enum, a mixin) — skip it.
            if inv_page is None and not sel_keys:
                continue

            if inv_page is None:
                errors.append(
                    f"{_ERROR_PREFIX} in '{path}': class {node.name} calls "
                    f"self.sel(...) but declares no INVENTORY_PAGE. Set it to "
                    f"the key of the page it implements in the app inventory."
                )
                continue

            if pages is None:
                # No usable inventory in this environment. Reporting every key
                # as unknown would be noise, not signal.
                continue

            if inv_page not in pages:
                errors.append(
                    f"{_ERROR_PREFIX} in '{path}': class {node.name} sets "
                    f"INVENTORY_PAGE = '{inv_page}', which is not a page in "
                    f"the app inventory. Available pages: "
                    f"{', '.join(sorted(pages)[:_MAX_KEYS_LISTED])}."
                )
                continue

            page_entry = pages.get(inv_page) or {}
            elements = page_entry.get("elements")
            elements = elements if isinstance(elements, dict) else {}

            # ── multi-match enforcement ──────────────────────────────
            # `multi_match` lists the keys whose selector matches a FAMILY of
            # elements (dropdown options, table rows, per-row icons, repeated
            # field errors). Absent or malformed = unclassified page, and this
            # check is a no-op, so an old inventory keeps working unchanged.
            family = page_entry.get("multi_match")
            family = set(family) if isinstance(family, (list, tuple, set)) else set()
            # Families the app POPULATES ASYNCHRONOUSLY. Index 0 can be a
            # transient row that is not a real choice - a loading row, or a
            # 'nothing selected' default - so an index pin is not
            # merely awkward here, it silently selects nothing. Never offer
            # one as the remedy for these; by-text is the only correct answer.
            async_family = page_entry.get("async_family")
            async_family = (set(async_family)
                            if isinstance(async_family, (list, tuple, set))
                            else set())
            if family:
                for key, method, lineno in _strict_uses_of_sel(node):
                    if key not in family:
                        continue
                    # The remedy must only ever name actions the MODEL can
                    # take. Telling it to "add a key to the inventory" was a
                    # trap: rule 15 forbids inventing keys, the model cannot
                    # edit the inventory, so it wrote self.sel('<key>_first')
                    # for a key that does not exist and the run died on the
                    # very next check. Offer the pinned key only when one
                    # really exists; otherwise point at the by-text helper or
                    # at `notes`, which is the one escape hatch it is allowed.
                    first_key = f"{key}_first"
                    if key in async_family:
                        remedy = (
                            f"select the ONE element you want BY ITS TEXT - "
                            f"select_custom_option(trigger, '<text>') for a "
                            f"dropdown or autocomplete, click_role('option', "
                            f"'<text>') otherwise. '{key}' is populated "
                            f"asynchronously, so an index pin such as "
                            f"'>> nth=0' or a '{first_key}' key is NEVER "
                            f"correct here: index 0 may be a loading "
                            f"placeholder, and waiting for it to appear "
                            f"succeeds while selecting nothing"
                        )
                    elif first_key in elements:
                        remedy = (f"use self.sel('{first_key}'), which is the "
                                  f"same selector already pinned to one element")
                    else:
                        remedy = (
                            f"address the ONE element you want by its text or "
                            f"accessible name - select_custom_option(trigger, "
                            f"text) for a dropdown or autocomplete, "
                            f"click_role(role, name) for anything else. Do NOT "
                            f"write self.sel('{first_key}') or any other key "
                            f"that is not in the list above: inventing a key is "
                            f"rejected the same way a literal selector is. If "
                            f"no legal path exists, drop the behaviour and say "
                            f"so in `notes`"
                        )
                    if lineno in syntax_lines:
                        # This line was already reported for building locator
                        # syntax, and the remedy given there - click_nth - is
                        # also the correct answer to this complaint. Reporting
                        # both would be one defect described twice, which is
                        # what trains a reader to skim the gate output.
                        continue
                    errors.append(
                        f"{_ERROR_PREFIX} in '{path}' line {lineno}: "
                        f"{node.name}.{method}() is called with "
                        f"self.sel('{key}'), but '{key}' is listed under "
                        f"multi_match on inventory page '{inv_page}' - its "
                        f"selector matches SEVERAL elements. Playwright is "
                        f"strict, so this raises 'strict mode violation: "
                        f"locator(...) resolved to N elements' at runtime. "
                        f"Either {remedy}, or, if you meant the whole set, "
                        f"To act on ONE member, scope to the row that contains "
                        f"its text: click_in_row(<row family>, text, <control>). "
                        f"Or, if you meant the whole set, read it with one of: "
                        f"{', '.join(sorted(_FAMILY_READERS))}."
                    )

            for key in sel_keys:
                if key in elements:
                    continue
                available = ", ".join(sorted(elements)[:_MAX_KEYS_LISTED]) or "(none)"

                # Is the key real, but on ANOTHER page?
                #
                # This branch used to say "do not invent the key" to every
                # miss. A run was abandoned over a key that existed - a
                # navigation link, correctly named, sitting on the shared nav
                # page. Nothing had been invented; the model had reached across
                # page objects, which is a different mistake with a different
                # fix, and the message described neither.
                #
                # It also told the model to request the element "in the plan's
                # `notes`", which the repair loop cannot do: repair regenerates
                # a FILE, not the plan. The one instruction offered after a
                # rejection was impossible to carry out.
                elsewhere = sorted(
                    other for other, entry in (pages or {}).items()
                    if other != inv_page
                    and isinstance(entry, dict)
                    and key in (entry.get("elements") or {})
                )
                if elsewhere:
                    owners = ", ".join(f"'{o}'" for o in elsewhere)
                    errors.append(
                        f"{_ERROR_PREFIX} in '{path}': class {node.name} calls "
                        f"self.sel('{key}'), which belongs to inventory page "
                        f"{owners}, not to '{inv_page}'. A page object may only "
                        f"use keys from its OWN page - self.sel() resolves "
                        f"against INVENTORY_PAGE = '{inv_page}' and would raise "
                        f"at runtime. Drive that element through the page object "
                        f"for {owners} instead, from the step definition that "
                        f"owns the flow. Keys on this page: {available}."
                    )
                    continue

                errors.append(
                    f"{_ERROR_PREFIX} in '{path}': class {node.name} calls "
                    f"self.sel('{key}'), but '{key}' is not an element on "
                    f"inventory page '{inv_page}', nor on any other page in the "
                    f"inventory. Use one of the keys on this page: {available}. "
                    f"If the element genuinely does not exist yet, drop the "
                    f"behaviour and say so in `notes` - do not invent a key, and "
                    f"do not write a literal selector instead."
                )

    return errors

# ─────────────────────────────────────────────────────────────────────────
# Redundant page-object methods
#
# Two stories touching the same page object both branch from `main`, so
# neither can see the other's work. Story A adds `filter_by_brand()`, story B
# adds `filter_products_by_brand()`, and if the additions land far enough apart
# git merges both cleanly. Nothing fails: the page object simply grows two
# methods that do the same thing, and the duplication rots quietly.
#
# `validate_method_resolution` cannot catch this — it checks that a called
# method EXISTS, not that two methods are the same idea twice.
# ─────────────────────────────────────────────────────────────────────────

# Filler words only. `get` and `set` are deliberately NOT here: they are the
# difference between an accessor and a mutator, and treating them as noise made
# set_quantity and get_quantity look like one method twice.
_STOPWORDS = frozenset({
    "the", "a", "an", "to", "for", "by", "of", "on", "in", "with", "and",
    "then", "page",
})


def _semantic_tokens(method_name: str) -> frozenset:
    """Meaning-bearing words in a method name, order- and filler-independent.

    `filter_by_brand` and `filter_products_by_brand` differ by one noun that
    the class already implies, so both reduce to {filter, brand} once the
    stopwords and the page's own noun are removed.
    """
    parts = [p for p in method_name.strip("_").split("_") if p]
    return frozenset(p for p in parts if p not in _STOPWORDS)


def find_redundant_methods(source: str, page_noun: str = "") -> list[tuple[str, str]]:
    """Pairs of public methods in one class whose names mean the same thing.

    `page_noun` is the page's own subject ("products", "cart"), dropped from
    every name because a method on ProductsPage saying "products" adds nothing.

    Returns [] when the source will not parse: a half-written file is the
    repair loop's problem, not this check's.
    """
    # A file may arrive with content=None when an upstream fetch failed. That
    # is not a syntax error, so SyntaxError alone does not cover it - and a
    # gate that raises on a failed fetch would take down a story for a reason
    # unrelated to the code it was checking.
    if not isinstance(source, str) or not source.strip():
        return []
    try:
        tree = _ast.parse(source)
    except (SyntaxError, ValueError):
        return []

    noun = {page_noun.lower().rstrip("s"), page_noun.lower()} if page_noun else set()
    pairs: list[tuple[str, str]] = []

    for node in _ast.walk(tree):
        if not isinstance(node, _ast.ClassDef):
            continue
        methods = [n.name for n in node.body
                   if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef))
                   and not n.name.startswith("_")]
        seen: dict[frozenset, str] = {}
        for name in methods:
            # The page's own noun is dropped: a method on ProductsPage saying
            # "products" adds nothing, so filter_by_brand and
            # filter_products_by_brand are one behaviour under two names.
            #
            # This is strict on purpose, and it makes a BLUNT method name a
            # liability: `open()` and `open_product()` both reduce to {open}
            # and read as duplicates. That is the right pressure - a page
            # object method should say what it opens. Name them
            # `open_listing()` and `open_product()` and the ambiguity is gone
            # for a reader as well as for this check.
            key = _semantic_tokens(name) - noun
            if not key:
                continue
            if key in seen:
                pairs.append((seen[key], name))
            else:
                seen[key] = name
    return pairs


def validate_readiness_probe(generated_files: list, project_root=None,
                             inventory: dict | None = None) -> list:
    """A page that declares `readiness` must probe THAT element in is_loaded().

    A readiness probe has to hold in every state the page can be in. A heading
    that a search replaces is true in one state and false in another, so a
    probe built on it reports "not loaded" for a page that loaded perfectly
    well - three tests failed that way on a listing whose heading changes after
    a search.

    The generator could not have got this right on its own. Both headings were
    in the inventory; the state-dependent one was declared `conditional`, which
    correctly means "do not expect this on page load", so the model reasonably
    chose the other. Nothing said which element survives every state, because
    nothing could: only someone who has seen the page in each state knows.
    `readiness` is that answer, and this makes it binding.
    """
    errors: list = []
    if inventory is None:
        inventory = _load_configured_inventory(Path(project_root or '.'))
    if not inventory:
        return errors

    for f in generated_files or []:
        path = (getattr(f, "file_path", "") or "").replace("\\", "/")
        if not _is_page_object_path(path):
            continue
        source = getattr(f, "content", "") or ""
        if not isinstance(source, str):
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            inv_page = _class_inventory_page(node)
            entry = (inventory.get("pages") or {}).get(inv_page) or {}
            expected = entry.get("readiness")
            if not expected:
                continue

            probe = next((n for n in node.body
                          if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                          and n.name == "is_loaded"), None)
            if probe is None:
                continue

            used = {
                c.args[0].value
                for c in ast.walk(probe)
                if isinstance(c, ast.Call)
                and isinstance(c.func, ast.Attribute) and c.func.attr == "sel"
                and c.args and isinstance(c.args[0], ast.Constant)
                and isinstance(c.args[0].value, str)
            }
            if expected not in used:
                errors.append(
                    f"{_ERROR_PREFIX} in '{path}': {node.name}.is_loaded() "
                    f"probes {sorted(used) or 'nothing'}, but inventory page "
                    f"'{inv_page}' declares readiness = '{expected}'. A probe "
                    f"has to hold in EVERY state the page can be in; the "
                    f"declared element is the one that does. Use "
                    f"self.is_showing(self.sel(\"{expected}\"))."
                )
    return errors


def validate_no_duplicate_page_object_methods(
    generated_files: list, page_inventory: str = "") -> list[str]:
    """Fail when one page object gains two methods meaning the same thing.

    Runs at the generation gate, which is where a human is already looking at
    the diff — far cheaper than discovering it months later in a page object
    nobody can safely refactor.
    """
    errors: list[str] = []
    for f in generated_files or []:
        path = getattr(f, "file_path", "") or ""
        if not path.endswith("_page.py") or path.endswith("base_page.py"):
            continue
        noun = path.rsplit("/", 1)[-1].replace("_page.py", "")
        for first, second in find_redundant_methods(getattr(f, "content", ""), noun):
            errors.append(
                f"{path}: '{first}' and '{second}' mean the same thing. Two "
                f"stories editing this page object cannot see each other's "
                f"branches, so both may add their own name for one behaviour. "
                f"Keep whichever name the existing step definitions already "
                f"call and delete the other."
            )
    return errors