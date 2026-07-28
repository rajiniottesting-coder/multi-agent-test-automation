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
        though `LoginPage` is a reserved file with only `open`, `login_as`,
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

    This lets us resolve `LoginPage` -> `pages.login_page` even when the
    import line is `from pages.login_page import LoginPage`.

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
            return LoginPage(page)

    We look for that exact shape: a fixture-decorated function that
    returns a single instantiation of a class. Other fixture shapes
    are skipped (we'd rather miss than guess wrong).

    Returns:
        Dict mapping fixture variable name -> class name it instantiates.
        E.g., {"login_page": "LoginPage", "inventory_page": "InventoryPage"}.
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
        # `login_page` -> `LoginPage`. Only applies to step function args
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