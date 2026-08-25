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
from typing import Iterable, Optional

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


def _resolve_class_signatures(class_name: str, class_sources: dict,
                              project_root: Path,
                              visited: set = None) -> dict:
    """{method name: (required positional count, accepts extra)} for a class.

    The companion to _resolve_class_methods_with_inheritance, which answers
    "does this method exist" and stops there. Existence is half the question:
    a call with the wrong number of arguments raises TypeError at run time
    just as surely as a call to a method that is not there, and the gate
    passed one straight through to Agent 4.

    `self` is excluded. A parameter with a default is not required. A method
    taking *args or **kwargs accepts anything, so it is never flagged.
    """
    visited = visited if visited is not None else set()
    if class_name in visited:
        return {}
    visited.add(class_name)

    source = class_sources.get(class_name)
    if source is None:
        for folder in ("pages", "tests/step_defs"):
            for path in sorted((Path(project_root) / folder).glob("*.py")):
                try:
                    text = path.read_text(encoding="utf-8")
                except OSError:
                    continue
                if f"class {class_name}" in text:
                    source = text
                    break
            if source:
                break
    if not source:
        return {}

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}

    signatures: dict = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue

        # Bases first, so an override on this class wins.
        for base in node.bases:
            base_name = getattr(base, "id", None) or getattr(base, "attr", None)
            if base_name and base_name != "object":
                signatures.update(_resolve_class_signatures(
                    base_name, class_sources, project_root, visited))

        for item in node.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            args = item.args
            positional = [a.arg for a in (args.posonlyargs + args.args)
                          if a.arg != "self"]
            defaulted = len(args.defaults)
            required = max(0, len(positional) - defaulted)
            flexible = bool(args.vararg or args.kwarg)
            signatures[item.name] = (required, len(positional), flexible)
    return signatures


def _call_arity(content: str, fixture_names: set) -> dict:
    """{(var, method, line): (positional args, keyword arg names)} for each call."""
    found: dict = {}
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return found

    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in fixture_names):
            continue
        # A splat means the count is not knowable here; say nothing.
        if any(isinstance(a, ast.Starred) for a in node.args):
            continue
        if any(k.arg is None for k in node.keywords):
            continue
        found[(node.func.value.id, node.func.attr, node.lineno)] = (
            len(node.args), {k.arg for k in node.keywords})
    return found


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


def _page_file_for_class(class_name: str) -> str:
    """`NavPage` -> `pages/nav_page.py`. The project's fixed convention."""
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", class_name).lower()
    return f"pages/{snake}.py"


def _reserved_page_files() -> set:
    """Page-object files Agent 2 is forbidden to modify.

    Read once, defensively: a validator must not fail because config is
    unreadable in a unit test.
    """
    try:
        from core.app_context import AppContext
        return {p.replace("\\", "/")
                for p in AppContext.load().reserved_paths_normalized()}
    except Exception:                                          # noqa: BLE001
        return set()


# Polarity pairs. A missing method that is an existing one with the polarity
# flipped is a MISSING CAPABILITY, not a misspelling - and suggesting the
# existing one sends a model to the method that asserts the contrary state.
_POLARITY = [
    ("_in", "_out"), ("_on", "_off"), ("logged_in", "logged_out"),
    ("enabled", "disabled"), ("shown", "hidden"), ("visible", "hidden"),
    ("present", "absent"), ("empty", "filled"), ("open", "closed"),
    ("valid", "invalid"), ("success", "failure"),
]


def _opposite_of(missing: str, known) -> str | None:
    """An existing method that is `missing` with its polarity flipped."""
    known = set(known or ())
    for a, b in _POLARITY:
        for x, y in ((a, b), (b, a)):
            if missing.endswith(x) or f"{x}_" in missing or missing.endswith(x + "()"):
                candidate = missing.replace(x, y)
                if candidate != missing and candidate in known:
                    return candidate
    return None


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
        arities = _call_arity(content, fixture_names)

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
                # A missing name that is the OPPOSITE of an existing one is a
                # different problem from a typo, and the "did you mean"
                # suggestion actively misleads: it offers the method that
                # asserts the contrary state. A model told "you meant
                # wait_until_logged_in" cannot use it to prove a logout, so it
                # invents another name, and the repair loop oscillates between
                # two spellings of a capability the page object simply does
                # not have. That happened for three attempts before the
                # no-progress guard stopped it.
                counterpart = _opposite_of(method_name, available_methods)

                err = (
                    f"Method resolution error in '{path}': "
                    f"line {line_no} calls `{var_name}.{method_name}()`, "
                    f"but `{class_name}` does not define `{method_name}`. "
                )
                # A method missing from a RESERVED page object is not
                # something the repair loop can ever fix: Agent 2 is forbidden
                # to edit that file, so no rewording of the CALL can help, and
                # four attempts are spent discovering that. Say it once, in the
                # first error, so a human reads the real instruction instead of
                # a convergence warning.
                owner = _page_file_for_class(class_name)
                if owner in _reserved_page_files():
                    err += (
                        f"`{owner}` is a RESERVED file - Agent 2 must not "
                        f"modify it, so this cannot be fixed by regenerating: "
                        f"no name for the call exists, because the capability "
                        f"is not there. A human has to add `{method_name}` to "
                        f"`{class_name}`, or the story has to be written "
                        f"against a capability the page already has. Do not "
                        f"keep renaming the call. "
                    )
                elif counterpart:
                    err += (
                        f"`{class_name}` defines `{counterpart}`, which is the "
                        f"OPPOSITE state - do not substitute it, it asserts the "
                        f"contrary of what this step needs. The page object has "
                        f"no method for this state at all. Add one (the waiting "
                        f"form of whatever positively PROVES the state, not the "
                        f"absence of its opposite), or if the state cannot be "
                        f"observed on this page, say so on the Jira issue "
                        f"rather than renaming the call. "
                    )
                elif similar:
                    err += f"Did you mean one of: {', '.join(similar)}? "
                err += f"Available methods on `{class_name}`: [{methods_list}]."
                errors.append(err)
                continue

            # The method EXISTS. Does the call actually fit it?
            #
            # A call with the wrong number of arguments raises TypeError at
            # run time just as surely as a call to a method that is not there
            # - and this check stopped at the name, so `open_listing()` on a
            # method declaring `open_listing(self, base_url)` passed the gate,
            # passed review's structural checks, and failed two scenarios in
            # Agent 4 with a TypeError before a single browser action ran.
            #
            # Silent wherever the answer is not knowable: a splat argument, a
            # method taking *args or **kwargs, or a class we could not read.
            signature = _resolve_class_signatures(
                class_name, class_sources, project_root).get(method_name)
            arity = arities.get((var_name, method_name, line_no))
            if not signature or arity is None:
                continue

            required, accepted, flexible = signature
            if flexible:
                continue
            given_positional, given_keywords = arity
            supplied = given_positional + len(given_keywords)

            if supplied < required or given_positional > accepted:
                errors.append(
                    f"Call signature error in '{path}': line {line_no} calls "
                    f"`{var_name}.{method_name}()` with {supplied} argument"
                    f"{'' if supplied == 1 else 's'}, but `{class_name}."
                    f"{method_name}` requires {required}"
                    f"{f' and accepts up to {accepted}' if accepted != required else ''}. "
                    f"Python raises TypeError before the method body runs, so "
                    f"the test fails without touching the browser and the "
                    f"traceback points at the step definition rather than at "
                    f"anything the application did. Pass what the signature "
                    f"asks for - a step definition can request the fixture it "
                    f"needs, `base_url` included - or change the signature if "
                    f"the argument is not really needed."
                )

    errors.extend(_methods_removed_by_regeneration(generated_files, project_root))

    return errors



def _methods_removed_by_regeneration(generated_files: list,
                                     project_root: Path) -> list:
    """Public methods a regenerated page object DROPS, and who still calls them.

    Agent 2 emits a whole file, not a patch. When the file already exists, the
    replacement is free to lose methods the story did not happen to need - and
    the batch's own step definitions will not miss them, because they were
    written against the same replacement.

    What misses them is everything ALREADY on main. A story regenerated the
    shared navigation page object, kept two of its own methods and dropped
    eight, three of which the reference login suite calls. Every check in the
    batch passed: the generated step definitions resolved perfectly against
    the generated page object. The reference suite then failed at run time
    with AttributeError, and the committed-tree unit test caught it only after
    the branch existed.

    This closes that gap at the generation gate, where it can still be
    repaired. It reads the CURRENT file from disk, the generated replacement,
    and every committed step definition - the callers that were never in the
    batch to speak for themselves.

    Returns error strings in the standard format, so the repair loop routes
    them to the page object that dropped the method.
    """
    errors: list = []
    try:
        root = Path(project_root)
        step_def_dir = root / "tests" / "step_defs"
        committed: dict = {}
        if step_def_dir.is_dir():
            for path in sorted(step_def_dir.glob("*.py")):
                if path.name in ("__init__.py", "conftest.py"):
                    continue
                committed[f"tests/step_defs/{path.name}"] = path.read_text(
                    encoding="utf-8")
    except Exception:                                     # noqa: BLE001
        return errors

    batch_paths = {getattr(f, "file_path", "") for f in generated_files or []}

    # Methods the inventory declares as starting-state remedies. These are
    # protected even with no caller - see the branch below.
    try:
        _, declared_calls = _starting_state_rules(project_root)
    except Exception:                                     # noqa: BLE001
        declared_calls = set()

    for gen in generated_files or []:
        path = getattr(gen, "file_path", "") or ""
        if not (path.startswith("pages/") and path.endswith(".py")):
            continue
        if path.endswith("base_page.py"):
            continue

        on_disk = Path(project_root) / path
        if not on_disk.is_file():
            continue                                      # a new page object

        try:
            before = ast.parse(on_disk.read_text(encoding="utf-8"))
            after = ast.parse(getattr(gen, "content", "") or "")
        except (SyntaxError, OSError):
            continue

        def public_methods(tree):
            out: dict = {}
            for cls in tree.body:
                if not isinstance(cls, ast.ClassDef):
                    continue
                out[cls.name] = {
                    n.name for n in cls.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and not n.name.startswith("_")
                }
            return out

        old_methods = public_methods(before)
        new_methods = public_methods(after)

        for class_name, old_set in old_methods.items():
            removed = old_set - new_methods.get(class_name, set())
            if not removed:
                continue

            fixture = _camel_to_snake(class_name)
            for method in sorted(removed):
                callers = []
                for step_path, source in committed.items():
                    if step_path in batch_paths:
                        continue          # regenerated too; it speaks for itself
                    if re.search(rf"\b{re.escape(fixture)}\.{re.escape(method)}\s*\(",
                                 source):
                        callers.append(step_path)
                if not callers:
                    # A METHOD WITH NO CALLER YET CAN STILL BE LOAD-BEARING.
                    #
                    # "Nothing calls it, so dropping it is safe" holds for an
                    # ordinary helper. It does not hold for a method the
                    # INVENTORY names under `_starting_state.establishing_
                    # calls`: that method exists so a scenario can own its
                    # starting state, and the first scenario to need it has
                    # not been written yet. By definition it has no caller on
                    # the day it is committed.
                    #
                    # Without this branch the asset is deleted by the next
                    # regeneration of its own page object, silently, and every
                    # persistent-state remedy goes back to naming a call that
                    # does not exist - the failure this pair of checks was
                    # built to end.
                    if method not in declared_calls:
                        continue
                    errors.append(
                        f"Method resolution error in '{path}': the regenerated "
                        f"`{class_name}` no longer defines `{method}()`. "
                        f"Nothing calls it YET, which is exactly why it must "
                        f"survive: the inventory names it under "
                        f"`_starting_state.establishing_calls` as the way a "
                        f"scenario owns its starting state, so the first "
                        f"scenario to need it has not been written. Deleting "
                        f"it leaves every persistent-state error naming a "
                        f"method that does not exist. Keep it and add your "
                        f"methods beside it."
                    )
                    continue
                errors.append(
                    f"Method resolution error in '{path}': the regenerated "
                    f"`{class_name}` no longer defines `{method}()`, but "
                    f"{', '.join(callers)} still calls it. Agent 2 emits a "
                    f"whole file, so a replacement silently drops what this "
                    f"story did not need - and the callers already on main are "
                    f"not in this batch to notice. Keep every public method the "
                    f"current file defines and add yours beside them; removing "
                    f"one is only safe when nothing else calls it."
                )
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
#
# Deliberately the SAME shape as tests/unit/test_page_object_selectors.py. The
# comment said that before this pattern did: the generation-time version
# required an ASSIGNMENT (`= "..."`), so a literal handed straight to a call
# slipped past it.
#
#     row = self.row_containing(self.sel("rows"), name)
#     return row.locator(".row-quantity").inner_text()
#                        ^^^^^^^^^^^^^^^^ no `=` in front, so never seen
#
# The gate passed it, the page object shipped, and the committed-tree scan -
# whose pattern had no such requirement - failed the build afterwards. The two
# checks disagreeing is the precise failure the original comment warned about.
#
# Matching a quoted literal ANYWHERE is safe here because the shape is
# specific: an inventory key never starts with . # [ or a Playwright engine
# prefix, and comment / docstring lines are skipped before this runs.
_SELECTOR_LITERAL_RE = re.compile(
    r"""["'](?:"""
    r"""\s*[.#\[]"""                                   # .class  #id  [attr=…]
    r"""|(?:role|text|label|alt|title|placeholder)="""   # playwright engines
    r""")[^"']*["']"""
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
def _family_sets_from_base_page() -> tuple:
    """(readers, consumers) as pages/base_page.py declares them.

    Read by AST rather than imported: importing BasePage would pull Playwright
    into every validator run, and a validator must not need a browser library
    to read a list of names.

    The lists live beside the helpers because keeping a second copy here failed
    twice - a family-aware helper added to BasePage and recommended in the
    prompt, with this file never told, so the gate rejected the prompt's own
    advice. The fallback below is the same content, used only if base_page.py
    cannot be read at all; a validator must never be the reason a run dies.
    """
    fallback = (
        frozenset({"exists", "find_row_index_by_text", "get_all_texts",
                   "get_cell_text", "get_column_values", "get_count",
                   "get_nth_text", "get_row_count", "wait_for_count"}),
        frozenset({"click_in_row", "click_nth", "get_nth_attribute",
                   "row_containing", "select_autocomplete_suggestion",
                   "wait_for_row"}),
    )
    try:
        here = Path(__file__).resolve().parents[1] / "pages" / "base_page.py"
        tree = ast.parse(here.read_text(encoding="utf-8"))
        found = {}
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            for name in names:
                if name not in ("FAMILY_READERS", "FAMILY_CONSUMERS"):
                    continue
                call = node.value
                if (isinstance(call, ast.Call) and call.args
                        and isinstance(call.args[0], ast.Set)):
                    found[name] = frozenset(
                        e.value for e in call.args[0].elts
                        if isinstance(e, ast.Constant))
        if "FAMILY_READERS" in found and "FAMILY_CONSUMERS" in found:
            return found["FAMILY_READERS"], found["FAMILY_CONSUMERS"]
    except Exception:                                     # noqa: BLE001
        logger.debug("family sets: falling back to the built-in copy")
    return fallback


_FAMILY_READERS, _FAMILY_CONSUMERS = _family_sets_from_base_page()

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
    every name because a method on ListingPage saying "products" adds nothing.

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

    # Strip the page's own noun in its EXACT form only. Stripping the singular
    # as well removed the very word that distinguishes a CONTAINER from an
    # ITEM: on a plural-named page, `open_<plural>_page` opens the listing and
    # `open_<singular>` opens one record, and both collapsed to {open}. The
    # plural is a redundant restatement of the class name; the singular names
    # the thing being acted on, and is meaning-bearing.
    noun = {page_noun.lower()} if page_noun else set()
    pairs: list[tuple[str, str]] = []

    for node in _ast.walk(tree):
        if not isinstance(node, _ast.ClassDef):
            continue
        methods = [n.name for n in node.body
                   if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef))
                   and not n.name.startswith("_")]
        seen: dict[frozenset, str] = {}
        for name in methods:
            # The page's own noun is dropped: a method on ListingPage saying
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
                # `... error in '<path>':` is the shape the repair loop's
                # grouper reads. This message did not use it, so a duplicate
                # was never routed to a file and never got a targeted repair
                # attempt - it went straight to the final gate and killed the
                # story with no explanation of what to change.
                f"Duplicate method error in '{path}': "
                f"'{first}' and '{second}' read as the same thing "
                f"once the page's own noun is dropped. Two stories editing "
                f"this page object cannot see each other's branches, so both "
                f"may add their own name for one behaviour.\n"
                f"  If they ARE one behaviour: keep whichever name the "
                f"existing step definitions already call and delete the "
                f"other.\n"
                f"  If they are genuinely different - '{first}' being a bare "
                f"verb that does not say what it acts on is the usual cause - "
                f"RENAME the vaguer one so it does. Do not delete either: "
                f"deleting a method the tests call breaks them, and this "
                f"message used to advise exactly that."
            )
    return errors


# ─────────────────────────────────────────────────────────────────────────
# A predicate that backs an assertion must WAIT
#
# A scenario removed an item, then asserted the collection was empty. It was
# not - yet. The predicate was built on is_visible(), which reads the DOM once
# and returns. No retry, and - this is the part that cost the day - no log
# line either, so the run produced a bare `assert False` and no evidence
# whatsoever about which condition failed or why.
#
# The reviewer had already flagged the same pattern elsewhere in the same pull
# request, correctly, as a race against a state change. Advice alone does not
# hold: this is statically checkable, so it is checked.
#
# The rule is narrow on purpose. is_visible() and get_count() are the right
# tools for BRANCHING - "is the banner up, and if so dismiss it" - where
# waiting for something that is legitimately absent would cost a full timeout
# every time. What they are not is the basis of a method whose name promises a
# yes/no answer a test will assert on.
# ─────────────────────────────────────────────────────────────────────────

# Probes that read the page ONCE. Each maps to the waiting helper that asks
# the same question properly.
#
# `exists` was missing, and it is `count() > 0` - exactly as racy as
# get_count(). A predicate returning it was waved through by the check that
# had just rejected the identical predicate written with get_count, which is
# how a page object ended up shipping the same defect under a different name.
_NON_WAITING_PROBES = {
    "is_visible": "is_showing",
    "get_count": "wait_for_count(<family>, <n>) for an exact number, or "
                 "wait_for_any(<family>) for \"are there any\"",
    "exists": "wait_for_any",
}
_PREDICATE_PREFIXES = ("is_", "has_", "was_", "can_", "does_", "did_")


def _sel_keys_in(func: ast.AST) -> set:
    """Every literal key passed to self.sel(...) inside one function."""
    keys: set = set()
    for node in ast.walk(func):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "sel"
                and node.args
                and isinstance(node.args[0], ast.Constant)):
            keys.add(node.args[0].value)
    return keys


def _returns_non_waiting_probe(func: ast.AST) -> Optional[str]:
    """The non-waiting helper this function RETURNS, if it returns one.

    Only `return`ed calls count. A predicate that calls is_visible() partway
    through and then waits properly is doing something more interesting than
    this check can judge, and guessing at it would produce the kind of false
    positive that gets a validator switched off.
    """
    for node in ast.walk(func):
        if not isinstance(node, ast.Return) or node.value is None:
            continue
        for inner in ast.walk(node.value):
            if not isinstance(inner, ast.Call):
                continue
            attr = inner.func
            if (isinstance(attr, ast.Attribute)
                    and isinstance(attr.value, ast.Name)
                    and attr.value.id == "self"
                    and attr.attr in _NON_WAITING_PROBES):
                return attr.attr
    return None


def _conditional_keys(project_root) -> set:
    """Selector keys the inventory declares as CONDITIONAL, on any page.

    A conditional element is one that is legitimately absent in some states -
    a sign-out link while signed out. Waiting for it costs a full timeout
    every time the answer is "no", which is exactly when a predicate is most
    useful. `is_visible()` is the right tool there.
    """
    keys: set = set()
    try:
        inventory = _load_configured_inventory(Path(project_root)) or {}
        for entry in (inventory.get("pages") or {}).values():
            if isinstance(entry, dict):
                keys.update(entry.get("conditional") or [])
    except Exception:                                     # noqa: BLE001
        pass
    return keys


def _has_waiting_sibling(cls: ast.ClassDef, name: str) -> bool:
    """True if the class offers a waiting form of the same question.

    `is_signed_in()` beside `wait_until_signed_in()` is a deliberate PAIR, not
    an oversight: one answers now, one waits. Rejecting the fast half of a
    documented pair is how this validator sent a repair loop round four times
    renaming a method it should have left alone.
    """
    stem = re.sub(r"^(is|has|was|can|does|did)_", "", name)
    for node in cls.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name == name or not node.name.startswith("wait"):
            continue
        if stem and stem in node.name:
            return True
    return False


def validate_predicates_wait(generated_files: list, project_root=None) -> list[str]:
    """Fail a page-object predicate whose answer is read from a single glance.

    Applies to page objects only, and only to methods named like a question -
    `is_*`, `has_*`, `was_*` and friends - that RETURN the result of a
    non-waiting probe.

    Two exemptions, both learned the hard way. A predicate probing an element
    the inventory declares CONDITIONAL is right to glance: waiting for
    something legitimately absent burns the full timeout on every negative
    answer. And a predicate with a waiting sibling on the same class is half
    of a deliberate pair - `is_signed_in()` and `wait_until_signed_in()` - so
    rejecting it asks for the pair to be destroyed.
    """
    conditional = _conditional_keys(project_root or Path("."))
    errors: list[str] = []
    for f in generated_files or []:
        path = getattr(f, "file_path", "") or ""
        if not path.startswith("pages/") or not path.endswith(".py"):
            continue
        if path.endswith("base_page.py"):
            continue                       # the helpers themselves live here
        try:
            tree = ast.parse(getattr(f, "content", "") or "")
        except SyntaxError:
            continue                       # a syntax error is reported elsewhere

        for cls in tree.body:
            if not isinstance(cls, ast.ClassDef):
                continue
            for node in cls.body:
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if not node.name.startswith(_PREDICATE_PREFIXES):
                    continue
                probe = _returns_non_waiting_probe(node)
                if not probe:
                    continue
                if _has_waiting_sibling(cls, node.name):
                    continue
                if conditional & _sel_keys_in(node):
                    continue
                errors.append(
                    f"Waiting predicate error in '{path}' line {node.lineno}: "
                    f"{cls.name}.{node.name}() returns self.{probe}(...), which reads the page ONCE and "
                    f"logs nothing. A step definition asserting on this races "
                    f"any state change that has not finished - most often the "
                    f"action immediately before it - and when it loses, the "
                    f"failure is a bare `assert False` with no evidence at "
                    f"all. Use self.{_NON_WAITING_PROBES[probe]}(...), which "
                    f"retries until the timeout and logs the reason it gave "
                    f"up. Keep self.{probe}() for BRANCHING on optional state, "
                    f"where waiting for something legitimately absent would "
                    f"cost a full timeout - not for a method whose name "
                    f"promises an answer a test will assert on."
                )
    return errors


# ─────────────────────────────────────────────────────────────────────────
# A step definition must not resolve selectors
#
# `nav_page.sel("some_key")` in a step definition puts a selector key in the
# step layer. It works, which is why it keeps appearing - and it quietly
# undoes the reason page objects exist. The key is now in two places, the
# inventory can be re-crawled without the step noticing, and the step reads
# as plumbing rather than as the behaviour it is supposed to describe.
#
# The reviewer catches this most times and describes it well. Most times is
# not a gate.
# ─────────────────────────────────────────────────────────────────────────

def validate_no_selectors_in_step_defs(generated_files: list) -> list[str]:
    """Fail a step-definition file that calls .sel() on anything."""
    errors: list[str] = []
    for f in generated_files or []:
        path = getattr(f, "file_path", "") or ""
        if not path.startswith("tests/step_defs/") or not path.endswith(".py"):
            continue
        try:
            tree = ast.parse(getattr(f, "content", "") or "")
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            attr = node.func
            if not (isinstance(attr, ast.Attribute) and attr.attr == "sel"):
                continue
            owner = getattr(attr.value, "id", None) or "<a page object>"
            key = ""
            if node.args and isinstance(node.args[0], ast.Constant):
                key = f"'{node.args[0].value}'"
            errors.append(
                f"Selector boundary error in '{path}' line {node.lineno}: "
                f"this step definition calls "
                f"{owner}.sel({key}). Selector keys belong inside the page "
                f"object; a step definition should read as the behaviour it "
                f"describes and call a named method. Add the query to the page "
                f"object - a method that does the probe internally - and call "
                f"that from the step. Putting the key here means the inventory "
                f"can be re-crawled without this file noticing."
            )
    return errors


# ─────────────────────────────────────────────────────────────────────────
# An absolute assertion on state the application KEEPS
#
# The failure this exists for, from the trace: one add-to-cart click in the
# whole run, one product added, and the collection read half a second later
# held two - the second left behind by a previous run against the same shared
# account.
#
# No wait fixes that. wait_for_count() would have retried for thirty seconds
# and found the same leftover. The scenario asserted an ABSOLUTE number
# against state it did not create and does not own.
#
# This was guidance in the context modules for months and was regenerated away
# every time, because a model reading "assert relatively" and a test case
# saying "the cart should contain exactly one product" will write what the
# test case says. Guidance loses that argument; a gate does not.
#
# The rule fires only where the inventory DECLARES the state persistent, so an
# application without shared per-user state is untouched, and an application
# that has it says so in the one place app knowledge belongs.
# ─────────────────────────────────────────────────────────────────────────

# Verbs that DO something, so a question-shaped name cannot look like a
# remedy. `is_empty` matched a bare "empty" here and marked the file as owning
# its state - the assertion under test was read as its own mitigation, and the
# check passed the exact code it was written to stop.
_STATE_OWNING_CALLS = re.compile(
    r"(clear|reset|remove_all|delete_all|purge|empty_the|make_empty)", re.I)
# A scenario owns its starting state only if it DOES something about it.
#
# This was a substring scan over the whole file, `register` included. A step
# named `@given("a newly registered account")` contains the word, so the check
# read the scenario's description of itself as proof of what it does - and the
# step behind that name called a helper whose own docstring says "This does
# NOT create the account", then signed in as the shared role. The scenario
# claimed a fresh account, used a shared one, and asserted the collection was
# empty. It passed on a run where the leftovers happened to be gone.
#
# Same shape as the earlier `is_empty` bug in this file: the check read its own
# subject as its own mitigation. Names are claims; calls are evidence.
# The framework-provided fixture is the one thing that is app-agnostic: it
# yields an identity nothing has used before. Everything else is declared.
_DEFAULT_FRESH_FIXTURES = ("unique_username",)


def _resolvable_establishing_calls(establishing_calls, generated_files,
                                   project_root) -> set:
    """Of the calls the inventory advertises, the ones that actually EXIST.

    `_starting_state.establishing_calls` is a declaration of intent. Nothing
    checked that a page object anywhere defines the method, and for one whole
    run nothing did: the inventory advertised two clearing calls, the app
    context told the generator to use them, the remedy in every error
    message named them, and no page object in the batch or on disk defined
    either. The model was told to call something that was not there.

    That is the failure this module already has a name for - unsatisfiable
    guidance gets approximated - applied to the remedy itself. So the remedy
    only offers what resolves. If nothing does, the caller falls back to the
    relative assertion, which is always available.
    """
    if not establishing_calls:
        return set()

    defined: set = set()
    for f in generated_files or []:
        path = (getattr(f, "file_path", "") or "").replace("\\", "/")
        if path.startswith("pages/") and path.endswith(".py"):
            try:
                tree = ast.parse(getattr(f, "content", "") or "")
            except SyntaxError:
                continue
            defined |= {n.name for n in ast.walk(tree)
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

    pages_dir = Path(project_root or ".") / "pages"
    if pages_dir.is_dir():
        for path in pages_dir.glob("*.py"):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, OSError, UnicodeDecodeError):
                continue
            defined |= {n.name for n in ast.walk(tree)
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

    return {c for c in establishing_calls if c in defined}


def _available_remedies(fresh_fixtures, establishing_calls,
                        feature_in_batch: bool = False,
                        declared_calls=None) -> str:
    """The ways to own a clean start that THIS application can express.

    The remedy sentence used to be hardcoded, and it led with "register a
    fresh account". In an application whose inventory holds no password field
    and no account-details form, that is not a thing the generator can do. It
    approximated: it invented a password, never submitted it, and the login
    failed at run time - a whole story lost to an instruction that could not
    be carried out.

    "Unsatisfiable guidance gets approximated" is already a reading rule here.
    This is the same rule applied to the error MESSAGE, which is guidance too,
    and is read at the moment the model is most willing to do something odd.

    So the options are assembled from the declaration. An application that
    declares no way to establish a clean start is told to assert relatively,
    which it can always do.
    """
    options = []
    if fresh_fixtures:
        options.append(
            f"register a fresh identity using the "
            f"{', '.join(sorted(fresh_fixtures))} fixture"
        )
    if establishing_calls:
        options.append(
            f"clear the state in a Given step, via "
            f"{' or '.join(sorted(establishing_calls))}() - and place that "
            f"step AFTER the one that signs in. The application keeps this "
            f"state against the signed-in user, so clearing it while signed "
            f"out clears a different user's, and the clearing step navigates "
            f"away from wherever the scenario was, which is a second way to "
            f"break the sign-in that follows"
        )
    if not options:
        # WHY there is nothing to offer changes what the reader should do,
        # so the two cases are not collapsed. Saying "the inventory declares
        # nothing" when it declares two calls that simply do not exist sends
        # whoever reads this log looking in the wrong file.
        unresolved = sorted(set(declared_calls or ()) - set(establishing_calls or ()))
        if unresolved:
            return (
                f"This application DECLARES a way to establish a clean start "
                f"({', '.join(unresolved)}) but no page object defines it, so "
                f"it cannot be called. Until one does, the assertion must be "
                f"RELATIVE - that what this scenario added is present, or is "
                f"gone - which holds whatever the state started as. That is a "
                f"change to this file alone. Do NOT call "
                f"{unresolved[0]}(): it does not exist."
            )
        return (
            "This application declares no way to establish a clean start "
            "(`_starting_state` in the inventory is empty), so the assertion "
            "must be RELATIVE - that what this scenario added is present, or "
            "is gone - which holds whatever the state started as. That is a "
            "change to this file alone."
        )
    # ORDER MATTERS, and it is not the order of preference.
    #
    # The repair loop regenerates ONE file. Owning the starting state needs
    # three: a Given line in the .feature, a clearing method on the page
    # object, and the step definition that joins them. A model repairing the
    # step-def file alone cannot do any of that - it can only rewrite the
    # assertion in front of it.
    #
    # The message used to lead with owning the state. A story spent four
    # repair attempts and 3,170 characters of feedback trying to follow it,
    # produced the same four errors each time, and was abandoned. The one
    # thing it could have done was listed second and described as the
    # fallback.
    #
    # So the achievable remedy comes first, and the other is labelled with the
    # files it needs, which is the fact that decides whether it is available.
    if feature_in_batch:
        # THE FEATURE FILE IS BEING REPAIRED IN THIS SAME ATTEMPT.
        #
        # The text below used to be sent unconditionally, and it opened
        # "IF YOU ARE EDITING ONLY THE STEP-DEFINITION FILE - which is the
        # case during a repair". That stopped being true once the feature
        # file could be routed to: both files are now repaired in one pass,
        # the feature first, and the step-def prompt is given the rewritten
        # scenario.
        #
        # So the two messages of that same attempt contradicted each other.
        # The feature was told "add a Given that clears the state first"; the
        # step definition was told, in the same breath, that owning the state
        # "is not something a single-file repair can deliver" and that it
        # should assert relatively instead. It obeyed the message in front of
        # it, never bound the Given the feature had just grown, and the next
        # attempt regenerated the feature back to where it started. Three
        # attempts of that, then the story failed.
        #
        # When the scenario can change, the three-file fix IS available and
        # this is where the model is told so.
        return (
            "The feature file for this scenario is being repaired in THIS "
            "SAME attempt, so the three-file fix IS available to you now: "
            "the scenario may gain a Given that clears the state, and this "
            "file binds it. If the scenario has one - or gains one - "
            "implement it ("
            + "; or ".join(options)
            + ") and then the absolute assertion below it is honest, because "
            "the scenario put the state there itself.\n"
            "If the scenario does NOT clear the state, make this assertion "
            "RELATIVE instead: assert that what this scenario added is "
            "present, or is gone, which holds whatever the state started as. "
            "Do not invent a way to own the state that the inventory cannot "
            "express: a registration flow the inventory does not describe "
            "cannot be written, and half of one fails at run time."
        )

    return (
        "IF YOU ARE EDITING ONLY THE STEP-DEFINITION FILE - which is the case "
        "here, because the feature file is not part of this batch - the fix "
        "available to you is to make the assertion "
        "RELATIVE: assert that what this scenario added is present, or is "
        "gone, which holds whatever the state started as. That needs no other "
        "file.\n"
        "The alternative is for the scenario to OWN its starting state ("
        + "; or ".join(options)
        + "), but that spans THREE files - a Given line in the .feature, a "
        "clearing method on the page object, and the step definition binding "
        "them - so it is not something a single-file repair can deliver. "
        "Do not invent a way to own the state that the inventory "
        "cannot express: a registration flow the inventory does not describe "
        "cannot be written, and half of one fails at run time."
    )


def _shared_account_names(project_root) -> frozenset:
    """Account keys the inventory declares under `test_users`.

    These are SHARED. Signing in as one inherits whatever every previous run
    left behind, which is the entire reason the persistent-state rule exists.
    """
    try:
        inventory = _load_configured_inventory(Path(project_root)) or {}
        return frozenset((inventory.get("test_users") or {}).keys())
    except Exception:                                     # noqa: BLE001
        return frozenset()


def _starting_state_rules(project_root) -> tuple:
    """(fresh-identity fixtures, calls that establish a clean start).

    Read from the inventory's `_starting_state` block, because WHICH call
    genuinely gives a scenario a clean slate is a property of the application.

    The first version guessed from method names - anything matching
    register|signup|create_account counted. That is exactly the mistake this
    check exists to catch: a step named "a newly registered account" called
    begin_signup(), whose own docstring says "This does NOT create the
    account", and the check passed it. Then the name-based pattern passed it a
    second time, for the same reason in a different place.

    Names are claims. A declaration is a claim somebody made deliberately,
    in the file where app knowledge belongs, next to the pages it describes.
    """
    fixtures = set(_DEFAULT_FRESH_FIXTURES)
    calls: set = set()
    try:
        inventory = _load_configured_inventory(Path(project_root)) or {}
        block = inventory.get("_starting_state") or {}
        # An EXPLICIT list replaces the default, including an explicit empty
        # one. The default used to be unioned in unconditionally, so an
        # application saying "there is no way to register here" was overruled
        # and told to register anyway - which is how a story spent its repair
        # budget writing half a registration flow that failed at run time.
        #
        # Absent key -> the framework fixture applies, which is the sensible
        # default for an application that has not thought about this yet.
        # Present key -> the application has thought about it; believe it.
        if "fresh_identity_fixtures" in block:
            fixtures = set(block.get("fresh_identity_fixtures") or [])
        calls.update(block.get("establishing_calls") or [])
    except Exception:                                     # noqa: BLE001
        pass
    return frozenset(fixtures), frozenset(calls)


def _camel_to_snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _persistent_pages(project_root) -> set:
    """Inventory pages that declare they hold state surviving the run."""
    try:
        inventory = _load_configured_inventory(Path(project_root))
    except Exception:                                     # noqa: BLE001
        return set()
    pages = (inventory or {}).get("pages") or {}
    return {
        name for name, entry in pages.items()
        if isinstance(entry, dict) and entry.get("persistent_state")
    }


def _fixtures_for_pages(generated_files: list, project_root, pages: set) -> dict:
    """{fixture_name: inventory_page} for page objects bound to `pages`.

    Three sources, most authoritative last: the inventory's own
    `page_object_class`, then page objects on disk, then the ones being
    generated now.

    The inventory has to be one of them. A step definition can be regenerated
    while its page object is not - `ai-update` does exactly that - and a check
    that only reads generated files would then find no mapping and pass a
    scenario it should have stopped. Silence from a missing lookup is the
    failure mode this whole file exists to avoid.
    """
    fixtures: dict = {}
    try:
        inventory = _load_configured_inventory(Path(project_root)) or {}
        for page in pages:
            entry = (inventory.get("pages") or {}).get(page) or {}
            cls = entry.get("page_object_class")
            fixtures[_camel_to_snake(cls) if cls else f"{page}_page"] = page
    except Exception:                                     # noqa: BLE001
        pass

    sources: dict = {}
    try:
        for path in sorted(Path(project_root).glob("pages/*_page.py")):
            if path.name == "base_page.py":
                continue
            sources[f"pages/{path.name}"] = path.read_text(encoding="utf-8")
    except Exception:                                     # noqa: BLE001
        pass
    for f in generated_files or []:
        path = getattr(f, "file_path", "") or ""
        if path.startswith("pages/") and path.endswith(".py"):
            sources[path] = getattr(f, "content", "") or ""

    for path, source in sources.items():
        if path.endswith("base_page.py"):
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for cls in tree.body:
            if not isinstance(cls, ast.ClassDef):
                continue
            for node in cls.body:
                if not isinstance(node, ast.Assign):
                    continue
                targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
                if "INVENTORY_PAGE" not in targets:
                    continue
                if isinstance(node.value, ast.Constant) and node.value.value in pages:
                    fixtures[_camel_to_snake(cls.name)] = node.value.value
    return fixtures


def _names_derived_from(func: ast.AST, fixtures: dict) -> set:
    """Fixture names, plus locals assigned from one of them.

    Generated step definitions rarely assert on the fixture inline. They read
    it into a local first:

        names = collection_page.item_names()
        assert len(names) == count

    A check that only looked at the assert expression saw `len(names) == count`
    and no fixture at all - which is how the first version of this validator
    passed the exact code it was written to stop.
    """
    derived = {name for name in fixtures}
    changed = True
    while changed:                       # a local assigned from another local
        changed = False
        for node in ast.walk(func):
            if not isinstance(node, ast.Assign):
                continue
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if not targets or all(t in derived for t in targets):
                continue
            for inner in ast.walk(node.value):
                if isinstance(inner, ast.Name) and inner.id in derived:
                    derived.update(targets)
                    changed = True
                    break
    return derived


# Gherkin wording that CLAIMS an exact state. A step definition implementing
# one of these has no choice: the phrase is the requirement, and a relative
# assertion would not satisfy the sentence it is bound to.
_ABSOLUTE_STEP_TEXT = re.compile(
    r"\b(exactly|only|precisely)\b|\bshould be empty\b|\bis empty\b|\bno \w+ (?:left|remain)",
    re.I)


def _enclosing_step_text(func: ast.AST) -> str:
    """The Gherkin phrase this step definition is bound to, from its decorator.

    De-duplicated. A step bound under more than one keyword - `@when` and
    `@then` carrying the same phrase, which is legitimate - produced the
    phrase twice, and the error message then truncated the doubled string
    mid-word at its 90-character cap. The model reading that feedback was
    shown a sentence that appears in no feature file.
    """
    parts: list = []
    for dec in getattr(func, "decorator_list", []):
        for node in ast.walk(dec):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                parts.append(node.value)
    return " ".join(dict.fromkeys(parts))


def _feature_in_batch(step_source: str, generated_files: list) -> Optional[str]:
    """The .feature file this step-def module drives, if it is in this batch.

    Returns the batch path so an error can be reported against it - the repair
    loop routes on the path in the message, so resolving this is what makes
    the feature file the thing that gets regenerated. When it resolves to
    None every such error falls back to the step-definition file, and a
    scenario that only the feature file can fix is never fixed.

    IT HAD NEVER RESOLVED. The first version matched
    `scenarios("<something>")` with a regex requiring a quote straight after
    the bracket. But the generation prompt and the reference step definition
    both mandate a different call:

        scenarios(str(feature_path("<the feature stem>")))

    - a helper, not a literal path, so the quote is three tokens away and the
    string is a bare snake_case name with no directory and no extension. The
    regex matched nothing on every file the framework actually produces, and
    the feature file was never once blamed in a real run. Two separate fixes
    were built on top of this and inherited its silence; both looked correct
    in isolation because their tests used a literal-path call the prompt does
    not allow.

    So the shape is no longer guessed. Every string constant inside the
    `scenarios(...)` call is a candidate, whatever wraps it, and each is
    compared by STEM so a bare name, a name with `.feature`, and a full
    relative path all resolve alike. test_feature_resolution_matches_the_real_convention
    reads the committed reference step definition and requires this to
    resolve it, so the two cannot drift apart again.
    """
    try:
        tree = ast.parse(step_source or "")
    except SyntaxError:
        return None

    candidates: list = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if name not in {"scenarios", "scenario"}:
            continue
        # Any string anywhere inside the call - `feature_path("x")`,
        # `str(...)`, an f-string prefix, a plain literal.
        for sub in ast.walk(node):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                candidates.append(sub.value)
    if not candidates:
        return None

    def stem(value: str) -> str:
        base = value.replace("\\", "/").rsplit("/", 1)[-1]
        return base[:-len(".feature")] if base.endswith(".feature") else base

    wanted = {stem(c) for c in candidates if c.strip()}
    for f in generated_files or []:
        path = getattr(f, "file_path", "") or ""
        if path.endswith(".feature") and stem(path) in wanted:
            return path
    return None


def _absolute_assertion_helpers(generated_files: list, project_root) -> set:
    """Page-object methods whose whole job is an ABSOLUTE assertion.

    The check below reads `assert` statements. A step definition can make the
    same claim without one:

        @then(parsers.parse("the list should contain exactly {count:d} rows"))
        def assert_row_count(some_page, count):
            some_page.wait_for_row_count(count)      # no `assert` anywhere

    The assertion moved into the page object, which is good style and made it
    invisible to a check that looks for the keyword. A run shipped an absolute
    count on persistent state that way, and the reviewer caught what the gate
    had been written to catch.

    A method counts as one of these when its body waits for or compares an
    exact number - `wait_for_count`, or an equality against `get_count`. That
    is behaviour, not a name: `wait_for_row_count` and `expect_two` are both
    caught, and a method merely called `check_something` is not.
    """
    sources: dict = {}
    try:
        for path in sorted(Path(project_root).glob("pages/*.py")):
            if path.name == "base_page.py":
                continue
            sources[path.name] = path.read_text(encoding="utf-8")
    except Exception:                                     # noqa: BLE001
        pass
    for f in generated_files or []:
        fp = getattr(f, "file_path", "") or ""
        if fp.startswith("pages/") and fp.endswith(".py") and not fp.endswith("base_page.py"):
            sources[fp.rsplit("/", 1)[-1]] = getattr(f, "content", "") or ""

    helpers: set = set()
    for source in sources.values():
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for cls in tree.body:
            if not isinstance(cls, ast.ClassDef):
                continue
            for node in cls.body:
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for inner in ast.walk(node):
                    if (isinstance(inner, ast.Call)
                            and isinstance(inner.func, ast.Attribute)
                            and inner.func.attr == "wait_for_count"):
                        helpers.add(node.name)
                    elif (isinstance(inner, ast.Compare)
                          and any(isinstance(op, ast.Eq) for op in inner.ops)
                          and "get_count" in ast.dump(inner)):
                        helpers.add(node.name)
    return helpers


def _absolute_assertion_target(test: ast.AST, derived: set, fixtures: dict):
    """The persistent fixture this assertion makes an ABSOLUTE claim about.

    Absolute means a fixed shape of the whole collection - a cardinality, an
    equality against a full list, or emptiness:

        assert len(names) == count        assert x.count() == 2
        assert names == expected          assert x.is_empty()

    Relative claims are what the guidance asks for and are left alone:

        assert product in names           assert product not in names

    The comparison value is deliberately NOT required to be a literal. The
    failing scenario compared against `count`, a parameter parsed out of the
    Gherkin step - which is an absolute claim written the ordinary way.
    """
    def touches(node) -> bool:
        return any(isinstance(n, ast.Name) and n.id in derived
                   for n in ast.walk(node))

    if isinstance(test, ast.Compare):
        if not any(isinstance(op, (ast.Eq, ast.NotEq)) for op in test.ops):
            return None
        if not (touches(test.left) or any(touches(c) for c in test.comparators)):
            return None
    elif isinstance(test, ast.Call):
        func = test.func
        if not (isinstance(func, ast.Attribute)
                and re.search(r"(^|_)empty$", func.attr)
                and touches(test)):
            return None
    else:
        return None

    for node in ast.walk(test):
        if isinstance(node, ast.Name) and node.id in fixtures:
            return node.id
    return next(iter(fixtures), None)


def validate_persistent_state_assertions(
        generated_files: list, project_root=None) -> list[str]:
    """Fail an absolute assertion on state the inventory says the app keeps."""
    project_root = project_root or Path(".")
    pages = _persistent_pages(project_root)
    if not pages:
        return []
    fixtures = _fixtures_for_pages(generated_files, project_root, pages)
    if not fixtures:
        return []
    fresh_fixtures, establishing_calls = _starting_state_rules(project_root)
    # Only advertise remedies that exist. See _resolvable_establishing_calls:
    # a run spent every attempt being told to call a clearing method that no
    # page object defined.
    usable_calls = _resolvable_establishing_calls(
        establishing_calls, generated_files, project_root)
    assertion_helpers = _absolute_assertion_helpers(generated_files, project_root)
    shared_accounts = _shared_account_names(project_root)

    errors: list[str] = []
    for f in generated_files or []:
        path = getattr(f, "file_path", "") or ""
        if not path.startswith("tests/step_defs/") or not path.endswith(".py"):
            continue
        source = getattr(f, "content", "") or ""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue

        # Does this file establish its own starting state anywhere?
        #
        # Two ways, both evidence rather than assertion: a step REQUESTS a
        # fresh-identity fixture, or a call is MADE whose name says it creates
        # an account. A word appearing in a Gherkin step name proves nothing -
        # that is the scenario describing its intent, and intent is exactly
        # what this check exists to verify.
        requested = {a.arg for fn in ast.walk(tree)
                     if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
                     for a in fn.args.args}
        owns_state = bool(requested & fresh_fixtures)

        # A fresh identity that is then ABANDONED owns nothing.
        #
        # Third version of this check, third version of one mistake. It
        # believed a word in a step name, then a promising method name, and
        # now a fixture merely being REQUESTED. Each moved closer to behaviour
        # and stopped one step short.
        #
        # A file that asks for a fresh identity and then authenticates with an
        # account the inventory declares SHARED has contradicted itself: the
        # new identity is created and discarded, the session belongs to the
        # shared account, and every absolute assertion afterwards is a coin
        # toss on what the last run left. Both halves are declared - the
        # fixtures under `_starting_state`, the shared accounts under
        # `test_users` - so this needs no guessing.
        if owns_state and shared_accounts:
            used_shared = sorted({
                node.value for node in ast.walk(tree)
                if isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value in shared_accounts
            })
            if used_shared:
                owns_state = False
                contradiction = (
                    f" This file asks for a fresh identity "
                    f"({', '.join(sorted(requested & fresh_fixtures))}) and "
                    f"then signs in as {', '.join(repr(u) for u in used_shared)}, "
                    f"which the inventory declares under `test_users` as a "
                    f"SHARED account. The new identity is created and "
                    f"discarded; the session belongs to the shared account, so "
                    f"the assertion runs against whatever the last run left."
                )
            else:
                contradiction = ""
        else:
            contradiction = ""
        if not owns_state:
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr in establishing_calls):
                    owns_state = True
                    break
        if not owns_state:
            # Only a call made for its EFFECT counts - its own statement, not
            # something buried inside the assertion being judged.
            for node in ast.walk(tree):
                if not isinstance(node, ast.Expr):
                    continue
                if not isinstance(node.value, ast.Call):
                    continue
                func = node.value.func
                if (isinstance(func, ast.Attribute)
                        and not func.attr.startswith(("is_", "has_"))
                        and _STATE_OWNING_CALLS.search(func.attr)):
                    owns_state = True
                    break
        if owns_state:
            continue

        for func in ast.walk(tree):
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            args = {a.arg for a in func.args.args}
            if not (args & set(fixtures)):
                continue                 # this step does not touch such a page
            derived = _names_derived_from(func, {
                k: v for k, v in fixtures.items() if k in args})
            live = {k: v for k, v in fixtures.items() if k in args}
            for node in ast.walk(func):
                fixture = None
                if isinstance(node, ast.Assert):
                    fixture = _absolute_assertion_target(node.test, derived, live)
                elif (isinstance(node, ast.Expr)
                      and isinstance(node.value, ast.Call)
                      and isinstance(node.value.func, ast.Attribute)
                      and node.value.func.attr in assertion_helpers):
                    # An absolute claim delegated to the page object. No
                    # `assert` keyword, same assertion.
                    owner = node.value.func.value
                    if isinstance(owner, ast.Name) and owner.id in live:
                        fixture = owner.id
                if not fixture:
                    continue
                # WHICH FILE has to change?
                #
                # If the Gherkin phrase itself claims an exact state - "exactly
                # 2 rows", "should be empty" - the step definition is not free
                # to assert relatively. The repair prompt injects the feature
                # file as AUTHORITATIVE, so the model must implement the
                # sentence it was given, and the sentence is the problem.
                #
                # Reporting against the step-def file asked a model to fix a
                # file that could not be fixed. It spent four attempts and
                # 3,170 characters on it and was abandoned - not because the
                # advice was wrong, but because it was addressed to the wrong
                # file. The repair loop routes on the path in this message, so
                # naming the feature file is what lets the scenario text be
                # rewritten, after which the step definition follows.
                # ROUTE TO BOTH FILES, NOT ONE.
                #
                # The first version reported only the step-def file and a
                # story burned four attempts on a file that could not be
                # fixed. The remedy was to detect an absolute-sounding step
                # phrase and report the FEATURE instead - which worked for
                # the phrases the pattern knew and deadlocked identically on
                # the ones it did not. `<the collection> should be empty`
                # routed; `I should see an empty <collection>`, `<the
                # collection> should contain no entries` and `no entries
                # should remain` did not, and the next story to phrase it a
                # different way failed exactly as the incident before it.
                #
                # A phrase list cannot be completed - proven twice now - so it
                # is no longer load-bearing. When the feature is in the batch,
                # BOTH files are reported: the scenario may be the thing
                # demanding an exact state, or the step definition may have
                # over-asserted on a relative phrase, and each message goes to
                # the file that can answer it. The repair loop regenerates the
                # feature first and writes it back before repairing the step
                # definition, so the step-def prompt sees the rewritten
                # scenario within the same attempt.
                #
                # The pattern survives only to say WHICH is more likely.
                # Nothing routes on it, so a phrase it misses costs a hint,
                # not a story.
                step_text = _enclosing_step_text(func)
                feature_path = _feature_in_batch(source, generated_files)
                reads_absolute = bool(_ABSOLUTE_STEP_TEXT.search(step_text))

                if feature_path:
                    likely = (
                        "This phrase reads as an EXACT claim, so the scenario "
                        "is the likely culprit. "
                        if reads_absolute else
                        "This phrase does not obviously demand an exact state, "
                        "so the step definition may simply have over-asserted. "
                        "If this scenario is already true whatever the state "
                        "started as, leave it unchanged - the step-definition "
                        "error reported separately covers that case. "
                    )
                    errors.append(
                        f"Persistent state error in '{feature_path}': the step "
                        f"`{step_text.strip()[:90]}` claims an EXACT state on "
                        f"a page the inventory declares persistent_state - the "
                        f"application keeps it against the signed-in user, so "
                        f"it survives logout and survives the run, and a "
                        f"previous run's leftovers are counted too. The step "
                        f"DEFINITION cannot fix this: it must implement the "
                        f"phrase it is given. Rewrite the SCENARIO so it asks "
                        f"for something true whatever the state started as - "
                        f"that the item this scenario added is present, or is "
                        f"gone - or add a Given to this feature that clears "
                        f"the state first. " + likely
                    )
                    # NO `continue`. The step-definition error is emitted too,
                    # so whichever of the two files is actually wrong has been
                    # told. Stopping here is what made the routing a guess
                    # that had to be right first time.

                errors.append(
                    f"Persistent state error in '{path}' line {node.lineno}: "
                    f"this asserts an ABSOLUTE state on {fixture}, whose inventory page '{fixtures[fixture]}' is "
                    f"declared persistent_state - the application keeps it against "
                    f"the signed-in user, so it survives logout and survives the "
                    f"run. A previous run's leftovers are counted too, and no wait "
                    f"removes them. "
                    + _available_remedies(fresh_fixtures, usable_calls,
                                          feature_in_batch=bool(feature_path),
                                          declared_calls=establishing_calls)
                    + contradiction
                )
    return errors


# ─────────────────────────────────────────────────────────────────────────
# A page-object method must say what it acts on
#
# The reference page object defined `open(base_url)`. Agent 2 copied the
# convention onto a listing page, added `open_product()` for the detail page,
# and the duplicate-method check rejected the pair: strip the page's own noun
# from `open_product` and what is left is `open`.
#
# The two are not one behaviour - one opens the listing, one opens a single
# record - so the framework had taught a name and then punished it, and the
# remedy it printed ("delete the other") would have broken the tests.
#
# No syntactic rule can separate that pair from a real duplicate after the
# fact: `filter_by_brand` / `filter_products_by_brand` has the identical
# shape and IS one behaviour. So the check moves earlier. A bare verb collides
# with every `verb_object` name that will ever be added beside it, and it is
# unreadable on its own - `open()` on a listing page opens what? Requiring the
# object at the point the method is written costs nothing and removes the
# collision before there is anything to collide with.
# ─────────────────────────────────────────────────────────────────────────

# Framework-mandated names, which the base class or a validator requires
# verbatim and which no page object is free to rename.
_MANDATED_METHOD_NAMES = frozenset({
    "is_loaded", "page_url", "confirm_arrival", "sel",
})

# Verbs that take no object. "logout what?" is not a question, and a rule that
# demanded `logout_session()` would be renaming working code to satisfy a
# check. The first draft of this validator flagged NavPage.logout() and was
# wrong to - the list exists because being right about `open()` does not make
# a rule right about every bare verb.
_INTRANSITIVE_ACTIONS = frozenset({
    "logout", "refresh", "reload", "submit", "back", "close", "dismiss",
    "cancel", "confirm", "continue", "proceed", "accept", "decline",
})


# ─────────────────────────────────────────────────────────────────────────
# A step definition must verify the quantity its own sentence names
#
# WHAT SHIPPED
#   Two stories reached review with step definitions whose Gherkin promised
#   a count and whose bodies checked something else:
#
#       @then(parsers.parse("the list should contain exactly {count:d} rows"))
#       def assert_count(some_page):            # `count` never accepted
#           some_page.wait_for_row("First Item", present=True)
#
#   The phrase says exactly N. The body waits for one hard-coded name and
#   never counts anything, so it passes for N=1, N=2 and N=99 alike - and in
#   a Scenario Outline it passes every row. The reviewer caught both, which
#   is the expensive way to find something a parser can see.
#
# WHY IT APPEARED NOW, AND WHY THIS CLOSES THE LOOP
#   The persistent-state check forbids an absolute assertion on a page the
#   application keeps state for, and tells a single-file repair to assert
#   RELATIVELY. That is correct advice for the BODY and says nothing about
#   the sentence. So the cheapest way to satisfy it is to weaken the body and
#   leave the phrase promising a count nobody checks - which is what the
#   model did, twice.
#
#   With this check the shortcut is closed. On a persistent page the body may
#   not assert the count and this rule says the phrase may not claim one, so
#   the only way out is to change the SENTENCE - which is what the feature
#   error has been asking for all along. On an ordinary page both are legal
#   and the body simply has to do what it says.
#
#   That is why routing follows persistence rather than being reported
#   against the step definition every time: telling a model to assert a count
#   the other validator rejects is the deadlock this pair exists to avoid.

# A phrase that promises a QUANTITY. Deliberately narrower than
# _ABSOLUTE_STEP_TEXT, which also matches "exactly the item I added" - a
# perfectly good relative phrase where "exactly" modifies a thing, not a
# number. Only a number, a placeholder or an emptiness word counts.
_CLAIMS_A_QUANTITY = re.compile(
    r"\b(?:exactly|only|precisely)\s+"
    r"(?:\{[^}]*\}|\d+|one|two|three|four|five|no)\b"
    r"|\b(?:should\s+be|is|are|remains?)\s+empty\b"
    r"|\bno\s+\w+\s+(?:left|remain\w*)\b",
    re.I,
)

# Calls whose whole job is to verify a quantity. A body containing one of
# these has done what the sentence promised.
_COUNTS_SOMETHING = re.compile(r"count|(^|_)empty$|^len$", re.I)


def _step_texts(func: ast.AST) -> list:
    """Every Gherkin phrase this function is bound to."""
    out = []
    for dec in getattr(func, "decorator_list", []):
        for node in ast.walk(dec):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                out.append(node.value)
    return out


def _step_keywords(func: ast.AST) -> set:
    """The pytest-bdd keywords binding this function: given / when / then."""
    out: set = set()
    for dec in getattr(func, "decorator_list", []):
        node = dec.func if isinstance(dec, ast.Call) else dec
        name = getattr(node, "id", None) or getattr(node, "attr", None)
        if name in {"given", "when", "then"}:
            out.add(name)
    return out


def _captured_params(func: ast.AST) -> set:
    """Placeholder names in the step phrase, typed `{n:d}` or bare `{n}`."""
    names = set()
    for text in _step_texts(func):
        for m in re.finditer(r"\{(\w+)(?::\w+)?\}", text):
            names.add(m.group(1))
    return names


def _body_verifies_a_quantity(func: ast.AST) -> bool:
    """True when the body compares or waits on a number, or reads emptiness."""
    for node in ast.walk(func):
        if isinstance(node, ast.Compare) and any(
                isinstance(op, (ast.Eq, ast.NotEq, ast.Lt, ast.LtE,
                                ast.Gt, ast.GtE)) for op in node.ops):
            return True
        if isinstance(node, ast.Call):
            name = None
            if isinstance(node.func, ast.Attribute):
                name = node.func.attr
            elif isinstance(node.func, ast.Name):
                name = node.func.id
            if name and _COUNTS_SOMETHING.search(name):
                return True
    return False


def validate_step_claims_are_verified(
        generated_files: list, project_root=None) -> list[str]:
    """Fail a step whose sentence promises a quantity its body never checks."""
    project_root = project_root or Path(".")
    persistent = _persistent_pages(project_root)
    fixtures = _fixtures_for_pages(generated_files, project_root, persistent) \
        if persistent else {}

    errors: list[str] = []
    for f in generated_files or []:
        path = getattr(f, "file_path", "") or ""
        if not path.startswith("tests/step_defs/") or not path.endswith(".py"):
            continue
        source = getattr(f, "content", "") or ""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        feature_path = _feature_in_batch(source, generated_files)

        for func in ast.walk(tree):
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            texts = _step_texts(func)
            if not texts:
                continue
            phrase = " ".join(texts)
            accepted = {a.arg for a in func.args.args}
            # Does this step drive a page whose state the application keeps?
            # If so the body is not ALLOWED to assert the count, so the
            # sentence is the only thing that can change.
            touches_persistent = bool(accepted & set(fixtures))

            # (1) A captured placeholder the body never receives.
            #
            # Not a binding error - pytest-bdd injects only what the function
            # asks for and ignores the rest, so this runs green. That is the
            # problem: the step is parameterised and behaves identically for
            # every value, so a Scenario Outline passes every row.
            unused = sorted(_captured_params(func) - accepted)

            # (2) A sentence promising a quantity, and a body that never
            #     compares, counts or reads emptiness.
            #
            # ONLY FOR AN ASSERTION STEP. A `@then` claims something is true
            # and must check it. A `@given` does the opposite: it MAKES the
            # sentence true. "Given the cart is empty" bound to a clearing
            # call is not an unverified claim, it is the arrangement - and it
            # is exactly the fix the persistent-state error asks for.
            #
            # Not distinguishing them meant this check rejected the one exit
            # the framework had spent four other checks pointing at. A story
            # reached the gate with a correct clearing Given and one error:
            # this one, on that Given. `@when` is the same - an action, not a
            # claim.
            claims = ("then" in _step_keywords(func)
                      and bool(_CLAIMS_A_QUANTITY.search(phrase)))
            unverified = claims and not _body_verifies_a_quantity(func)

            if not unused and not unverified:
                continue

            what = []
            if unused:
                what.append(
                    f"captures {', '.join(repr(u) for u in unused)} which the "
                    f"function never accepts, so the step behaves identically "
                    f"for every value and a Scenario Outline passes every row"
                )
            if unverified:
                what.append(
                    "promises a quantity that the body never compares, counts "
                    "or reads emptiness for, so it passes whatever the real "
                    "number is"
                )
            said = " and ".join(what)
            short = phrase.strip()[:90]

            if touches_persistent and feature_path:
                errors.append(
                    f"Step claim error in '{feature_path}': the step "
                    f"`{short}` {said}. This step drives a page the inventory "
                    f"declares persistent_state, so the body is NOT permitted "
                    f"to assert the count either - the persistent-state check "
                    f"rejects exactly that. The sentence is the only thing "
                    f"that can change: reword the scenario to ask for "
                    f"something true whatever the state started as (that what "
                    f"this scenario added is present, or is gone), or add a "
                    f"Given that clears the state first and then assert the "
                    f"count honestly."
                )
                continue

            errors.append(
                f"Step claim error in '{path}' line {func.lineno}: the step "
                f"`{short}` {said}. A step definition must verify what its "
                f"own sentence says. Accept the captured parameter and "
                f"compare against it, or assert the count through the page "
                f"object - and if the step is not meant to check a quantity, "
                f"the SENTENCE is what has to change, not the body."
            )
    return errors


# ─────────────────────────────────────────────────────────────────────────
# A persistent page object must carry the clearing call by NAME
#
# Owning a starting state is a three-file decision and the page object is one
# of the three. It is also the ONLY one a repair cannot reach: the repair loop
# regenerates the feature and the step definitions, never the page object. So
# a page object that reaches the gate without the clearing method has closed
# the door on the absolute assertion for the rest of the run - the scenario
# either weakens to a relative check or the story fails.
#
# Leaving that to guidance did not work, for a reason that was nobody's fault
# to read: the required NAME lives under `_starting_state.establishing_calls`,
# and every top-level `_` key is stripped before the inventory reaches the
# model. It was asked for a method it had never been shown the name of, then
# corrected against that name. The prompt now renders the contract explicitly
# (_build_starting_state_block); this makes it enforced rather than requested.
#
# Deliberately narrow: it fires only for a page the inventory itself marks
# `persistent_state`, only when the inventory declares a call, and only for a
# page object being generated in this batch. An application declaring nothing
# is untouched.
# ─────────────────────────────────────────────────────────────────────────


def validate_persistent_pages_can_be_cleared(
        generated_files: list, project_root=None) -> list[str]:
    """Fail a generated page object for a persistent page that cannot clear."""
    project_root = project_root or Path(".")
    try:
        _, establishing = _starting_state_rules(project_root)
        inventory = _load_configured_inventory(Path(project_root)) or {}
    except Exception:                                     # noqa: BLE001
        return []
    if not establishing:
        return []

    # {PageObjectClass: inventory page name} for persistent pages only.
    owners = {
        (page.get("page_object_class") or ""): name
        for name, page in (inventory.get("pages") or {}).items()
        if isinstance(page, dict) and page.get("persistent_state")
        and page.get("page_object_class")
    }
    if not owners:
        return []

    required = sorted(establishing)[0]
    errors: list[str] = []
    for f in generated_files or []:
        path = (getattr(f, "file_path", "") or "").replace("\\", "/")
        if not (path.startswith("pages/") and path.endswith(".py")):
            continue
        if path.endswith("base_page.py"):
            continue
        try:
            tree = ast.parse(getattr(f, "content", "") or "")
        except SyntaxError:
            continue

        for cls in ast.walk(tree):
            if not isinstance(cls, ast.ClassDef) or cls.name not in owners:
                continue
            defined = {
                n.name for n in cls.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            if defined & set(establishing):
                continue
            errors.append(
                f"Starting state error in '{path}': `{cls.name}` is the page "
                f"object for inventory page '{owners[cls.name]}', which is "
                f"declared persistent_state, but it defines none of the "
                f"clearing calls the inventory names "
                f"({', '.join(sorted(establishing))}). Add `{required}()`, "
                f"with that exact name - it removes every entry so a scenario "
                f"can OWN its starting state in a Given and then assert an "
                f"absolute count honestly. Write it even if this story does "
                f"not call it: a repair regenerates the feature and the step "
                f"definitions but NEVER the page object, so this is the only "
                f"moment it can be added, and every persistent-state message "
                f"tells the reader to call it."
            )
    return errors


# ─────────────────────────────────────────────────────────────────────────
# A reader must return what its NAME promises, not the container
#
# WHAT SHIPPED
#     def get_<a field>_for(self, record):
#         return self.row_containing(self.sel("<row family>"), record).inner_text()
#
#     assert actual == quantity        # quantity is "2"
#
#   `actual` is the whole row - name, category, price, quantity and total
#   concatenated - so the equality can never hold on any data, in any run.
#   Two scenarios failed in CI with the expected value plainly visible INSIDE
#   the value they were compared against.
#
# WHY THE MODEL WROTE IT
#   The story needed a quantity and the inventory declares no element for
#   one. `row_containing()` returns a whole row and its docstring says it is
#   "for reading rather than clicking", so reading the row was the only move
#   on offer. The method was then NAMED for the field it was supposed to
#   isolate, and everything downstream trusted the name.
#
#   This is the first defect this framework ever caught, in a new place: a
#   value asserted against something that cannot equal it. There the family
#   held names and the assertion wanted a price. Here the family holds rows
#   and the assertion wants a cell.
#
# THE FIX IS NAMED IN THE MESSAGE
#   BasePage already has get_cell_text() and get_column_values() for exactly
#   this - a cell inside a row, addressed by index or by a cell selector. If
#   neither can be used because the inventory describes no cell, then the
#   value is not readable on that page and the honest move is to say so
#   rather than to name a method after it.
#
# Deliberately narrow. It fires only when a method reads ROW-LEVEL text - a
# selector key the inventory itself lists under `multi_match` - and is named
# after something that key does not contain.
# ─────────────────────────────────────────────────────────────────────────

# Words that describe the ROW itself. A method named with one of these is
# honest about returning the whole thing.
_ROW_LEVEL_WORDS = frozenset({
    "row", "rows", "text", "texts", "line", "lines", "raw", "content",
    "contents", "entry", "entries", "record", "records", "all", "each",
})

# Leading verbs a reader conventionally starts with, stripped before the
# promised noun is read off the name.
_READER_VERBS = frozenset({
    "get", "read", "fetch", "find", "value", "values", "for", "of", "the",
    "by", "from", "in", "at", "with", "current", "displayed", "shown",
})

# How row text gets read. Playwright's own accessor and the sanctioned
# BasePage readers that return text.
_TEXT_READERS = frozenset({
    "inner_text", "text_content", "get_text", "get_all_texts", "get_nth_text",
})


# Helpers that scope their second selector INSIDE a row, one row at a time.
#
#     cell = rows.nth(i).locator(cell_locator).nth(cell_index)
#
# So the cell selector is evaluated with a single row as its root. An
# absolute one - anything anchored on an id or a class that sits ABOVE the
# row - matches nothing there, and the failure arrives thirty seconds later
# as `Locator.inner_text: Timeout exceeded`, naming a locator that reads
# perfectly well in isolation.
_ROW_SCOPED_HELPERS = {"get_column_values", "get_cell_text"}


# Ways a page object can establish that it is on its own page before acting.
_PAGE_PRECONDITIONS = {"require_own_page", "confirm_arrival", "navigate", "open"}


def validate_fills_confirm_their_page(generated_files: list,
                                      project_root=None) -> list[str]:
    """Fail a page-object method that fills a field without reaching its page.

    Filling a field that is not on screen does not fail fast. Playwright waits
    the full timeout and then reports the LOCATOR as having timed out, which
    reads like a broken selector when the selector is fine and the page is
    wrong. Thirty seconds spent, and the reader sent to the one place the
    fault is not.

    It has cost two stories. The first was a sign-in method, fixed by adding a
    private guard to that one class - which taught the next generated page
    object nothing, so a search method did it again. The guard belongs on
    BasePage and the requirement belongs here, or the same failure arrives
    once per page object that fills anything.

    FILLING specifically, and only when it is the FIRST action. A method that
    clicks its way somewhere and then fills has already established where it
    is; a method that fills as its opening move is asserting a page it has not
    checked. Clicks are excluded on purpose: a click from the wrong page fails
    in a second with a clear message, and requiring a precondition on every
    click would make the rule wrong more often than right.
    """
    errors: list[str] = []
    for gen in generated_files or []:
        path = getattr(gen, "file_path", "") or ""
        if not (path.startswith("pages/") and path.endswith(".py")):
            continue
        if path.endswith("base_page.py"):
            continue
        try:
            tree = ast.parse(getattr(gen, "content", "") or "")
        except SyntaxError:
            continue

        for cls in tree.body:
            if not isinstance(cls, ast.ClassDef):
                continue
            for node in cls.body:
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if node.name.startswith("_"):
                    continue

                first = _first_page_action(node)
                if first != "fill":
                    continue
                if _calls_any(node, _PAGE_PRECONDITIONS):
                    continue

                errors.append(
                    f"Unconfirmed page error in '{path}' line {node.lineno}: "
                    f"`{node.name}()` fills a field as its first action "
                    f"without establishing that the browser is on this page. "
                    f"If it is not, Playwright waits the FULL timeout and then "
                    f"reports the locator as having timed out - which reads as "
                    f"a broken selector when the selector is fine and the page "
                    f"is wrong. Call `self.require_own_page()` first: it costs "
                    f"a string comparison when already there, and navigates "
                    f"when not."
                )
    return errors


def _first_page_action(func: ast.AST):
    """The name of the first self.<action>() this function performs, or None.

    In source order, which is execution order for the straight-line opening of
    a method - and the opening is the question: what does this method do
    before it has established anything?
    """
    for node in ast.walk(func):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "self"
                and node.func.attr not in ("sel", "page_url")):
            return node.func.attr
    return None


def _calls_any(func: ast.AST, names: set) -> bool:
    for node in ast.walk(func):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in names):
            return True
    return False


def validate_row_index_is_not_a_cell_index(generated_files: list,
                                           project_root=None) -> list[str]:
    """Fail a row index passed where a CELL index belongs.

    `get_column_values(row_family, cell_selector, cell_index)` selects a cell
    WITHIN each row and returns one value PER ROW. The two indices count
    different things, and a page object used one for both:

        values = self.get_column_values(rows, quantities, index)
        return values[index]

    For the FIRST row that is accidentally correct - `nth(0)` is the only
    cell, and `values[0]` is the only row. For any other row the cell lookup
    finds nothing, every entry comes back empty, and the method returns "".

    So it passes on the first row and silently returns the wrong answer on
    the rest. A test asserting on it fails with a comparison against an empty
    string, pointing at the assertion rather than at the reader that produced
    it - and only when the data happens to put the item somewhere other than
    first, which is why it survives a demo and breaks later.

    Detected by the one shape that cannot be anything else: the SAME name
    passed as the cell index and used to subscript the result.
    """
    errors: list[str] = []
    for gen in generated_files or []:
        path = getattr(gen, "file_path", "") or ""
        if not (path.startswith("pages/") and path.endswith(".py")):
            continue
        if path.endswith("base_page.py"):
            continue
        try:
            tree = ast.parse(getattr(gen, "content", "") or "")
        except SyntaxError:
            continue

        for func in ast.walk(tree):
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            # {variable holding the result: the name used as its cell index}
            cell_index_of: dict = {}
            for node in ast.walk(func):
                if not (isinstance(node, ast.Assign)
                        and len(node.targets) == 1
                        and isinstance(node.targets[0], ast.Name)
                        and isinstance(node.value, ast.Call)
                        and isinstance(node.value.func, ast.Attribute)
                        and node.value.func.attr == "get_column_values"
                        and len(node.value.args) >= 3
                        and isinstance(node.value.args[2], ast.Name)):
                    continue
                cell_index_of[node.targets[0].id] = node.value.args[2].id

            for node in ast.walk(func):
                if not (isinstance(node, ast.Subscript)
                        and isinstance(node.value, ast.Name)
                        and isinstance(node.slice, ast.Name)):
                    continue
                used = cell_index_of.get(node.value.id)
                if used is None or used != node.slice.id:
                    continue

                errors.append(
                    f"Row index used as a cell index in '{path}' line "
                    f"{node.lineno}: `{used}` is passed to "
                    f"`get_column_values()` as the CELL index and then used to "
                    f"subscript its result as a ROW index. Those count "
                    f"different things - the third argument picks a cell "
                    f"WITHIN each row, and the result holds one value PER ROW. "
                    f"It is accidentally correct for the first row and returns "
                    f"an empty string for every other, silently. Pass the cell "
                    f"position the column actually occupies (0 where the "
                    f"family already names one cell per row) and keep "
                    f"`{used}` for the subscript: "
                    f"`get_column_values(<rows>, <cells>, 0)[{used}]`."
                )
    return errors


# Methods that are on `str` and not on `list`, and vice versa. Calling one on
# the wrong kind raises AttributeError the moment the line runs.
_STR_ONLY_METHODS = frozenset({
    "strip", "lstrip", "rstrip", "lower", "upper", "title", "capitalize",
    "split", "rsplit", "splitlines", "replace", "startswith", "endswith",
    "format", "encode", "casefold", "zfill", "removeprefix", "removesuffix",
    "isdigit", "isnumeric", "isalpha", "isspace",
})
_LIST_ONLY_METHODS = frozenset({"append", "extend", "sort", "reverse"})


def _base_page_return_kinds(project_root) -> dict:
    """{helper name: 'list' | 'str'} read from BasePage's own annotations.

    The signatures are already extracted for the generation prompt, so the
    model is TOLD `get_column_values(...) -> List[str]`. Reading the same
    annotations here means the gate and the prompt agree by construction,
    with nothing to keep in step.
    """
    kinds: dict = {}
    try:
        source = (Path(project_root) / "pages" / "base_page.py").read_text(
            encoding="utf-8")
        tree = ast.parse(source)
    except Exception:                                     # noqa: BLE001
        return kinds

    for cls in tree.body:
        if not isinstance(cls, ast.ClassDef):
            continue
        for node in cls.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.returns is None:
                continue
            try:
                annotation = ast.unparse(node.returns)
            except Exception:                             # noqa: BLE001
                continue
            if annotation.startswith(("List[", "list[")):
                kinds[node.name] = "list"
            elif annotation == "str":
                kinds[node.name] = "str"
    return kinds


def validate_helper_return_types_are_respected(generated_files: list,
                                               project_root=None) -> list[str]:
    """Fail a string method called on a helper that returns a list.

        text = self.get_column_values(rows, cells, 0)   # -> List[str]
        return int(text.strip())                        # AttributeError

    The annotation is not a hint: `.strip()` does not exist on a list, and
    the line raises the moment it runs. A page object shipped exactly this
    and the runner failed with `'list' object has no attribute 'strip'` -
    after a successful login, a search and an add-to-cart, so the failure
    arrived several minutes in and pointed at the reader rather than at
    anything the application did.

    The return types come from BasePage's own annotations, which are already
    injected into the generation prompt. The model is told the type and then
    uses it as the other kind; this is the gate noticing.

    Only the unambiguous direction is flagged: a variable assigned DIRECTLY
    from a helper, then used with a method that cannot exist on that type.
    Anything reassigned, indexed, or passed through another call is left
    alone - inferring further would produce the false positives that get a
    check switched off.
    """
    project_root = Path(project_root or ".")
    kinds = _base_page_return_kinds(project_root)
    if not kinds:
        return []

    errors: list[str] = []
    for gen in generated_files or []:
        path = getattr(gen, "file_path", "") or ""
        if not path.endswith(".py") or path.endswith("base_page.py"):
            continue
        if not (path.startswith("pages/") or path.startswith("tests/step_defs/")):
            continue
        try:
            tree = ast.parse(getattr(gen, "content", "") or "")
        except SyntaxError:
            continue

        for func in ast.walk(tree):
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            # {variable: kind} for names assigned straight from a helper.
            kind_of: dict = {}
            reassigned: set = set()
            for node in ast.walk(func):
                if not (isinstance(node, ast.Assign)
                        and len(node.targets) == 1
                        and isinstance(node.targets[0], ast.Name)):
                    continue
                name = node.targets[0].id
                if (isinstance(node.value, ast.Call)
                        and isinstance(node.value.func, ast.Attribute)
                        and node.value.func.attr in kinds):
                    if name in kind_of:
                        reassigned.add(name)
                    kind_of[name] = (kinds[node.value.func.attr],
                                     node.value.func.attr)
                elif name in kind_of:
                    reassigned.add(name)

            for node in ast.walk(func):
                if not (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and isinstance(node.func.value, ast.Name)):
                    continue
                entry = kind_of.get(node.func.value.id)
                if entry is None or node.func.value.id in reassigned:
                    continue
                kind, helper = entry
                method = node.func.attr

                wrong = ((kind == "list" and method in _STR_ONLY_METHODS)
                         or (kind == "str" and method in _LIST_ONLY_METHODS))
                if not wrong:
                    continue

                other = "str" if kind == "list" else "list"
                hint = (
                    f"Pick the entry you want first - "
                    f"`{node.func.value.id}[0]` for the first row, or index it "
                    f"by the row you located - then call `.{method}()` on that."
                    if kind == "list" else
                    f"`{helper}()` returns a single value; there is nothing to "
                    f"`.{method}()` onto."
                )
                errors.append(
                    f"Helper return type error in '{path}' line {node.lineno}: "
                    f"`{node.func.value.id}` comes from `{helper}()`, which "
                    f"returns a {kind}, and `.{method}()` is a {other} method. "
                    f"Python raises AttributeError the moment this line runs - "
                    f"not a timing problem and not an application problem, so "
                    f"no wait and no screenshot helps. BasePage declares the "
                    f"return type and the generation prompt shows it. {hint}"
                )
    return errors


def validate_row_scoped_selectors(generated_files: list, project_root=None) -> list[str]:
    """Fail a cell selector that cannot resolve inside the row it is scoped to.

    The inventory is one flat map of selectors, so nothing in it says whether
    a key is meant to be used from the page root or from inside a row. A key
    written as `#container .cell` is correct from the page and empty from a
    row, and both readings look identical in the file.

    Caught here by comparing the two keys the call actually pairs: if the cell
    selector repeats the row selector's own leading id or class, it is
    anchored above the row and cannot match beneath it.
    """
    project_root = Path(project_root or ".")
    try:
        inventory = _load_configured_inventory(project_root) or {}
    except Exception:                                     # noqa: BLE001
        return []
    if not inventory:
        return []

    errors: list[str] = []
    for gen in generated_files or []:
        path = getattr(gen, "file_path", "") or ""
        if not (path.startswith("pages/") and path.endswith(".py")):
            continue
        if path.endswith("base_page.py"):
            continue
        try:
            tree = ast.parse(getattr(gen, "content", "") or "")
        except SyntaxError:
            continue

        page_name = _inventory_page_of(tree)
        elements = (((inventory.get("pages") or {}).get(page_name) or {})
                    .get("elements") or {})
        if not elements:
            continue

        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in _ROW_SCOPED_HELPERS):
                continue
            keys = [_sel_key_of(arg) for arg in node.args[:2]]
            if len(keys) < 2 or not all(keys):
                continue
            row_key, cell_key = keys
            row_sel = str(elements.get(row_key, ""))
            cell_sel = str(elements.get(cell_key, ""))
            if not row_sel or not cell_sel:
                continue

            # The row selector's own anchor - its first id or class token.
            anchor_match = re.match(r"\s*([#.][\w-]+)", row_sel)
            if not anchor_match:
                continue
            anchor_token = anchor_match.group(1)
            if anchor_token not in cell_sel:
                continue

            errors.append(
                f"Row-scoped selector error in '{path}' line {node.lineno}: "
                f"`{node.func.attr}()` evaluates `{cell_key}` INSIDE one row "
                f"of `{row_key}`, but `{cell_key}` is `{cell_sel!r}` - anchored "
                f"on `{anchor_token}`, which `{row_key}` (`{row_sel!r}`) sits "
                f"UNDER. Scoped to a row, that matches nothing, and the run "
                f"fails thirty seconds later with a timeout naming a locator "
                f"that reads perfectly well on its own. The cell selector must "
                f"be RELATIVE to the row: drop the `{anchor_token}` prefix in "
                f"the inventory so `{cell_key}` describes the cell, not the "
                f"path to it from the page root."
            )
    return errors


def _sel_key_of(node) -> Optional[str]:
    """The literal key inside a `self.sel("key")` argument, if that is what it is."""
    if (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "sel"
            and node.args
            and isinstance(node.args[0], ast.Constant)):
        return node.args[0].value
    return None


def _inventory_page_of(tree) -> Optional[str]:
    """The INVENTORY_PAGE a generated page object declares."""
    for cls in tree.body:
        if not isinstance(cls, ast.ClassDef):
            continue
        for stmt in cls.body:
            if not isinstance(stmt, ast.Assign):
                continue
            for target in stmt.targets:
                if (isinstance(target, ast.Name)
                        and target.id == "INVENTORY_PAGE"
                        and isinstance(stmt.value, ast.Constant)):
                    return stmt.value.value
    return None


def _rows_families(inventory: dict, page_name: str) -> set:
    """The ROW CONTAINER on this page, if the inventory declares one.

    Not every family is a row. `multi_match` means "matches several
    elements", which covers two different things:

        a row container   - one element per record, holding several cells
        a column of fields - one element per record, holding ONE value

    The reader-naming rule exists for the first: reading a container's text
    returns every cell concatenated, so a method named after one field can
    never match. Reading a COLUMN's text with get_all_texts() returns exactly
    that field, once per record, which is correct and common.

    This returned every multi_match key, so it flagged both. A page object
    reading a column of names was rejected on every run - "promises result
    but reads TEXT from <the names column>" - and the only way past it was to
    stop reading the column, which is the one legal thing to do with it.

    So the container is DECLARED, per page, under `row_family`. A page that
    declares none has no rows and the rule does not apply there: silence is
    the safe answer, because a false rejection here has no legal escape.
    """
    page = ((inventory or {}).get("pages") or {}).get(page_name) or {}
    declared = page.get("row_family")
    if not declared:
        return set()
    families = {k for k in (page.get("multi_match") or []) if k}
    if isinstance(declared, str):
        return {declared} & families if families else {declared}
    return {k for k in declared if k}


def _returns_a_value(func: ast.AST) -> bool:
    """True if this function returns something - i.e. it is a READER.

    Judged by behaviour and by annotation, either being enough. `-> None` is
    a declaration that nothing comes back; a body with no `return <value>`
    says the same thing without saying it.
    """
    annotation = getattr(func, "returns", None)
    if isinstance(annotation, ast.Constant) and annotation.value is None:
        return False
    if isinstance(annotation, ast.Name) and annotation.id == "None":
        return False
    for node in ast.walk(func):
        if isinstance(node, ast.Return) and node.value is not None:
            return True
    return False


def _promised_nouns(method_name: str) -> set:
    """The words a reader's name promises to return."""
    parts = [w for w in method_name.strip("_").split("_") if w]
    return {w for w in parts if w not in _READER_VERBS}


def validate_readers_return_what_they_name(
        generated_files: list, project_root=None) -> list[str]:
    """Fail a reader named for a field that returns whole-row text."""
    project_root = project_root or Path(".")
    try:
        inventory = _load_configured_inventory(Path(project_root)) or {}
    except Exception:                                     # noqa: BLE001
        return []
    if not inventory:
        return []

    errors: list[str] = []
    for f in generated_files or []:
        path = (getattr(f, "file_path", "") or "").replace("\\", "/")
        if not (path.startswith("pages/") and path.endswith(".py")):
            continue
        if path.endswith("base_page.py"):
            continue
        try:
            tree = ast.parse(getattr(f, "content", "") or "")
        except SyntaxError:
            continue

        for cls in ast.walk(tree):
            if not isinstance(cls, ast.ClassDef):
                continue
            page_name = ""
            for stmt in cls.body:
                if (isinstance(stmt, ast.Assign)
                        and any(getattr(t, "id", "") == "INVENTORY_PAGE"
                                for t in stmt.targets)
                        and isinstance(stmt.value, ast.Constant)):
                    page_name = str(stmt.value.value)
            families = _rows_families(inventory, page_name)
            if not families:
                continue

            for fn in cls.body:
                if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if fn.name.startswith("_"):
                    continue

                # Which family keys does this method read, and does it read
                # them as TEXT?
                keys = {
                    n.args[0].value
                    for n in ast.walk(fn)
                    if isinstance(n, ast.Call)
                    and getattr(n.func, "attr", "") == "sel"
                    and n.args and isinstance(n.args[0], ast.Constant)
                    and isinstance(n.args[0].value, str)
                }
                read_as_text = any(
                    getattr(n.func, "attr", "") in _TEXT_READERS
                    for n in ast.walk(fn) if isinstance(n, ast.Call)
                )
                touched = keys & families
                if not touched or not read_as_text:
                    continue

                # An ACTION is not a reader.
                #
                # This check asks whether a reader's NAME matches what it
                # RETURNS. A method that returns nothing promises nothing, and
                # judging it by the same rule turns every verb in its name
                # into a field it failed to produce: `clear_the_basket()` was
                # read as promising "empty" and "cart".
                #
                # Both names in `_starting_state.establishing_calls` -
                # the clearing methods the framework itself asks for - are
                # verb phrases, so the framework was rejecting the names it
                # mandates. A run spent all four repair attempts on it.
                if not _returns_a_value(fn):
                    continue

                promised = _promised_nouns(fn.name)
                if not promised:
                    continue
                # Honest if the name describes the row itself, or if every
                # promised word appears in the key it reads.
                if promised & _ROW_LEVEL_WORDS:
                    continue
                key_words = {w for k in touched for w in k.split("_")}
                if promised <= key_words:
                    continue

                unmatched = ", ".join(sorted(promised - key_words))
                key = sorted(touched)[0]
                errors.append(
                    f"Reader naming error in '{path}' line {fn.lineno}: "
                    f"`{fn.name}()` promises {unmatched} but reads TEXT from "
                    f"`{key}`, which the inventory lists under multi_match - "
                    f"a whole row, not one field. The return value is every "
                    f"cell concatenated, so a caller comparing it for "
                    f"equality against one field's value can never match, on "
                    f"any data, in any run. Read the cell instead: "
                    f"BasePage.get_cell_text(<row family>, row_index, "
                    f"cell_index) or get_column_values(<row family>, "
                    f"<cell selector>), with find_row_index_by_text() to "
                    f"locate the row. If the inventory describes no cell for "
                    f"{unmatched}, then it is NOT readable on this page - say "
                    f"so rather than naming a method after it, and assert "
                    f"something this page can actually show."
                )
    return errors


# ─────────────────────────────────────────────────────────────────────────
# confirm_arrival() belongs on the DESTINATION's page object
#
# It re-issues the navigation to the url THIS page object declares. That is
# right at the end of a method that clicks a control expected to land HERE,
# which is what its docstring says.
#
# A shared navigation object is the exception, and it is the common case: its
# links go everywhere EXCEPT its own page. A generated `go_to_<somewhere>()`
# ending in confirm_arrival() asserted the browser was on the navigation
# object's own url, decided a correct landing was a failure, and navigated
# back - so a run that had reached the listing was returned to the home page
# and the next step waited its full timeout for a control that only exists on
# the listing. Three scenarios failed that way, each blaming its own selector.
#
# BasePage now refuses to re-issue when the browser is on another page the
# inventory declares, so the damage is contained at run time. This stops it
# being written: the method NAMES a destination, and if that destination is
# not this page object's own page, confirm_arrival() here is asserting the
# wrong thing.
# ─────────────────────────────────────────────────────────────────────────

_GOES_ELSEWHERE = re.compile(
    r"^(?:go_to|goto|open|navigate_to|visit)_(?P<dest>\w+)$")


def validate_confirm_arrival_targets_this_page(
        generated_files: list, project_root=None) -> list[str]:
    """Fail confirm_arrival() in a method that navigates somewhere else."""
    project_root = project_root or Path(".")
    try:
        inventory = _load_configured_inventory(Path(project_root)) or {}
    except Exception:                                     # noqa: BLE001
        return []
    page_names = set((inventory.get("pages") or {}).keys())
    if not page_names:
        return []

    errors: list[str] = []
    for f in generated_files or []:
        path = (getattr(f, "file_path", "") or "").replace("\\", "/")
        if not (path.startswith("pages/") and path.endswith(".py")):
            continue
        if path.endswith("base_page.py"):
            continue
        try:
            tree = ast.parse(getattr(f, "content", "") or "")
        except SyntaxError:
            continue

        for cls in ast.walk(tree):
            if not isinstance(cls, ast.ClassDef):
                continue
            own = ""
            for stmt in cls.body:
                if (isinstance(stmt, ast.Assign)
                        and any(getattr(t, "id", "") == "INVENTORY_PAGE"
                                for t in stmt.targets)
                        and isinstance(stmt.value, ast.Constant)):
                    own = str(stmt.value.value)
            if not own:
                continue

            for fn in cls.body:
                if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                calls_confirm = any(
                    getattr(n.func, "attr", "") == "confirm_arrival"
                    for n in ast.walk(fn) if isinstance(n, ast.Call))
                if not calls_confirm:
                    continue
                match = _GOES_ELSEWHERE.match(fn.name)
                if not match:
                    continue
                dest = match.group("dest")
                # Honest when the method goes to this object's own page.
                own_words = set(own.split("_"))
                if dest in own_words or set(dest.split("_")) & own_words:
                    continue
                # Only complain when the name points at a page that EXISTS -
                # otherwise the word is just part of a verb phrase.
                if dest not in page_names and f"{dest}_page" not in page_names:
                    continue
                errors.append(
                    f"Arrival check error in '{path}' line {fn.lineno}: "
                    f"`{fn.name}()` navigates to '{dest}', but it calls "
                    f"confirm_arrival() on `{cls.name}`, whose INVENTORY_PAGE "
                    f"is '{own}'. confirm_arrival() re-issues the navigation "
                    f"to the url THIS page object declares, so on a correct "
                    f"landing it decides the run went wrong and navigates "
                    f"BACK - leaving the page the click had just reached. The "
                    f"next step then times out on a control that only exists "
                    f"at the destination, and blames its own selector. Either "
                    f"drop the call, or make it on the page object for "
                    f"'{dest}' - confirm_arrival() belongs where you ARRIVE, "
                    f"not where you clicked."
                )
    return errors


def validate_page_method_names_are_specific(generated_files: list) -> list[str]:
    """Fail a public page-object method whose name is a bare verb."""
    errors: list[str] = []
    for f in generated_files or []:
        path = getattr(f, "file_path", "") or ""
        if not path.startswith("pages/") or not path.endswith(".py"):
            continue
        if path.endswith("base_page.py"):
            continue
        try:
            tree = ast.parse(getattr(f, "content", "") or "")
        except SyntaxError:
            continue

        for cls in tree.body:
            if not isinstance(cls, ast.ClassDef):
                continue
            for node in cls.body:
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                name = node.name
                if name.startswith("_") or name in _MANDATED_METHOD_NAMES:
                    continue
                if "_" in name:
                    continue

                # A lone intransitive verb is fine UNTIL something shares its
                # stem, which is the moment the collision becomes real.
                shares_stem = any(
                    isinstance(sibling, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and sibling.name.startswith(f"{name}_")
                    for sibling in cls.body
                )
                if name in _INTRANSITIVE_ACTIONS and not shares_stem:
                    continue

                errors.append(
                    f"Method naming error in '{path}' line {node.lineno}: "
                    f"{cls.name}.{name}() is a bare verb and does not say what it acts on. Name it "
                    f"{name}_<what>() - on this page, what does {name}() "
                    f"{name}? A bare verb also collides with every "
                    f"{name}_<something>() method added beside it later: the "
                    f"duplicate-method check drops the page's own noun, so "
                    f"'{name}' and '{name}_<noun>' reduce to the same thing "
                    f"and a legitimate pair gets rejected as a duplicate."
                )
    return errors


# ─────────────────────────────────────────────────────────────────────────
# One entry point for the three rules about a page-object METHOD's shape
#
# These three judge the same thing from three angles: what a method DEFINITION
# on a page object is allowed to look like. They take the same input, run in
# the same walk, and every one of them fires on the same kind of code review
# comment. Reading them as one cluster is easier than remembering three names.
#
# What is NOT here, deliberately:
#
#   validate_method_resolution      judges a CALL in a step definition against
#                                   the page object it names. Different input,
#                                   different failure, different fix - folding
#                                   it in would hide that.
#   validate_page_object_selectors  judges the SELECTORS a method uses, not the
#                                   method itself.
#
# Each rule keeps its own function, its own error prefix and its own tests. The
# prefix matters: the repair loop routes on it, and a merged prefix would tell
# the model "something about this method is wrong" instead of which thing.
# ─────────────────────────────────────────────────────────────────────────

def validate_page_object_methods(generated_files: list) -> list[str]:
    """Every rule about how a page-object method may be defined.

    Runs, in order:
      - no two methods meaning the same thing on one class
      - no bare verb that does not say what it acts on
      - no question-shaped method built on a non-waiting probe

    Returns the concatenation, unchanged. Calling the three directly is still
    supported and still tested; this exists so a caller has one thing to wire
    and one place to read about the cluster.
    """
    return (validate_no_duplicate_page_object_methods(generated_files)
            + validate_page_method_names_are_specific(generated_files)
            + validate_predicates_wait(generated_files))


# ─────────────────────────────────────────────────────────────────────────
# A parsed step parameter compared against the wrong type
#
# pytest-bdd's `{name:d}` hands the step an int. A page-object reader annotated
# `-> str` hands it a string. Comparing them is always False:
#
#     @then(parsers.parse("the quantity should be {quantity:d}"))
#     def assert_quantity(cart_page, record_name, quantity):
#         actual = cart_page.get_quantity(record_name)   # -> str
#         assert actual == quantity                       # "2" == 2, never true
#
# This is the worst shape a test can have. It does not error, it does not
# flake - it fails every single time, including when the application is
# perfectly correct, so the failure points at the app and the app is fine.
#
# Both halves are declared: the format spec is in the decorator, the return
# type is in the page object's annotation. Nothing has to be inferred.
# ─────────────────────────────────────────────────────────────────────────

_PARSER_TYPES = {"d": "int", "n": "int", "f": "float", "e": "float", "g": "float"}


def _all_parsed_params(func: ast.AST) -> set:
    """Every placeholder name in the step decorator, typed or not.

    `{name}` and `{name:d}` both appear in the step SENTENCE, which is what
    the feature file reads. A sentence that names a value promises the body
    checks it.
    """
    names: set = set()
    for dec in getattr(func, "decorator_list", []):
        for node in ast.walk(dec):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                names.update(re.findall(r"\{(\w+)(?::\w+)?\}", node.value))
    return names


def _names_used_in_body(func: ast.AST) -> set:
    """Identifiers the body actually reads, ignoring the signature itself."""
    used: set = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used.add(node.id)
        elif isinstance(node, ast.JoinedStr):
            for value in node.values:
                if isinstance(value, ast.FormattedValue):
                    for inner in ast.walk(value):
                        if isinstance(inner, ast.Name):
                            used.add(inner.id)
    return used


# Comparisons that cannot fail. A count is non-negative by construction, so
# `>= 0` is a sentence-shaped nothing: it passes whatever the page did.
def _assertion_cannot_fail(test: ast.AST) -> Optional[str]:
    """Why this assertion can never fail, or None if it can."""
    if isinstance(test, ast.Constant) and test.value:
        return f"`assert {test.value!r}` is a constant"

    # `assert <anything> or True` - the second operand decides, always.
    # A run produced `assert page.assert_row_count(n) is None or True, ""`,
    # which is a real call wrapped in a tautology. The call does the work; the
    # assert around it reports success whatever happened, and an empty message
    # leaves nothing to read when it does.
    if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.Or):
        for operand in test.values:
            if isinstance(operand, ast.Constant) and operand.value:
                return (f"`or {operand.value!r}` makes the whole expression "
                        f"true regardless of the rest")

    # `assert <call that returns None> is None` - true by the callee's
    # signature, not by anything the page did.
    if (isinstance(test, ast.Compare) and len(test.ops) == 1
            and isinstance(test.ops[0], ast.Is)
            and isinstance(test.comparators[0], ast.Constant)
            and test.comparators[0].value is None
            and isinstance(test.left, ast.Call)):
        return ("comparing a call against None asserts the signature, not the "
                "behaviour - a method returning None passes this every time")

    if isinstance(test, ast.Compare) and len(test.ops) == 1:
        left, op, right = test.left, test.ops[0], test.comparators[0]

        zero = (isinstance(right, ast.Constant) and right.value == 0)
        counts = (isinstance(left, ast.Call)
                  and isinstance(left.func, ast.Attribute)
                  and ("count" in left.func.attr.lower()
                       or left.func.attr in ("get_row_count", "get_count")))
        if zero and counts and isinstance(op, ast.GtE):
            return ("a count is never negative, so `>= 0` holds however the "
                    "page behaved")
        if (isinstance(op, ast.Eq)
                and ast.dump(left) == ast.dump(right)):
            return "both sides are the same expression"
    return None


def _parsed_param_types(func: ast.AST) -> dict:
    """{param_name: python_type} for typed placeholders in the step decorator."""
    types: dict = {}
    for dec in getattr(func, "decorator_list", []):
        for node in ast.walk(dec):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for m in re.finditer(r"\{(\w+):(\w+)\}", node.value):
                    kind = _PARSER_TYPES.get(m.group(2))
                    if kind:
                        types[m.group(1)] = kind
    return types


def _page_method_return_types(generated_files: list, project_root) -> dict:
    """{(ClassName, method): annotation} for page objects, generated or on disk."""
    sources: dict = {}
    try:
        for path in sorted(Path(project_root).glob("pages/*.py")):
            sources[f"pages/{path.name}"] = path.read_text(encoding="utf-8")
    except Exception:                                     # noqa: BLE001
        pass
    for f in generated_files or []:
        path = getattr(f, "file_path", "") or ""
        if path.startswith("pages/") and path.endswith(".py"):
            sources[path] = getattr(f, "content", "") or ""

    out: dict = {}
    for source in sources.values():
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for cls in tree.body:
            if not isinstance(cls, ast.ClassDef):
                continue
            for node in cls.body:
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                ann = node.returns
                if isinstance(ann, ast.Name):
                    out[(cls.name, node.name)] = ann.id
    return out


def validate_step_parameter_types(generated_files: list, project_root=None) -> list[str]:
    """Fail a step definition that promises more than its body checks.

    Three shapes, all of which produce a test that passes when it should not:

    1. A parsed parameter compared against a mistyped reader - `"2" == 2` is
       always False, so the test fails even when the application is correct.

    2. A parameter the SENTENCE names and the body never reads. The step text
       is what the feature file says the test verifies; capturing a value and
       ignoring it means the scenario passes for every value of it.

    3. An assertion that cannot fail - `assert <count>() >= 0` is true however
       the page behaved.

    Two and three are the worse pair. A test that fails wrongly gets fixed; a
    test that passes wrongly is trusted, and stays in the suite reporting
    coverage it does not have.
    """
    project_root = project_root or Path(".")
    returns = _page_method_return_types(generated_files, project_root)
    if not returns:
        return []
    by_method: dict = {}
    for (cls, method), ann in returns.items():
        by_method.setdefault(method, set()).add(ann)

    errors: list[str] = []
    for f in generated_files or []:
        path = getattr(f, "file_path", "") or ""
        if not path.startswith("tests/step_defs/") or not path.endswith(".py"):
            continue
        try:
            tree = ast.parse(getattr(f, "content", "") or "")
        except SyntaxError:
            continue

        for func in ast.walk(tree):
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            # (2) a value the sentence names and the body ignores
            promised = _all_parsed_params(func)
            if promised:
                used = _names_used_in_body(func)
                ignored = sorted(promised - used)
                if ignored:
                    errors.append(
                        f"Step promise error in '{path}' line {func.lineno}: "
                        f"the step text captures {', '.join(repr(n) for n in ignored)} "
                        f"and `{func.name}` never reads "
                        f"{'them' if len(ignored) > 1 else 'it'}. The sentence "
                        f"in the feature file says the test checks that value; "
                        f"the body does not, so the scenario passes for every "
                        f"value of it. Either assert on it, or take it out of "
                        f"the step text so the feature stops claiming a check "
                        f"that is not there."
                    )

            # (3) an assertion that cannot fail
            for node in ast.walk(func):
                if not isinstance(node, ast.Assert):
                    continue
                why = _assertion_cannot_fail(node.test)
                if why:
                    errors.append(
                        f"Vacuous assertion error in '{path}' line "
                        f"{node.lineno}: this assertion cannot fail - {why}. "
                        f"It reports a passing check while verifying nothing, "
                        f"which is worse than no assertion at all: the suite "
                        f"claims coverage the run never had. Assert the thing "
                        f"the step's sentence promises - if the page cannot "
                        f"show it, say so and change the sentence."
                    )

            parsed = _parsed_param_types(func)
            if not parsed:
                continue

            # locals assigned from a page-object call, with that call's return type
            local_types: dict = {}
            for node in ast.walk(func):
                if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                    continue
                target = node.targets[0]
                call = node.value
                if not (isinstance(target, ast.Name) and isinstance(call, ast.Call)
                        and isinstance(call.func, ast.Attribute)):
                    continue
                anns = by_method.get(call.func.attr)
                if anns and len(anns) == 1:
                    local_types[target.id] = next(iter(anns))

            for node in ast.walk(func):
                if not isinstance(node, ast.Compare):
                    continue
                if not any(isinstance(op, (ast.Eq, ast.NotEq)) for op in node.ops):
                    continue
                sides = [node.left] + list(node.comparators)
                found: list = []
                for side in sides:
                    if isinstance(side, ast.Name):
                        if side.id in local_types:
                            found.append(("reader", side.id, local_types[side.id]))
                        elif side.id in parsed:
                            found.append(("param", side.id, parsed[side.id]))
                    elif (isinstance(side, ast.Call)
                          and isinstance(side.func, ast.Attribute)):
                        anns = by_method.get(side.func.attr)
                        if anns and len(anns) == 1:
                            found.append(("reader", side.func.attr + "()",
                                          next(iter(anns))))
                if len(found) < 2:
                    continue
                kinds = {t for _, _, t in found}
                if len(kinds) < 2:
                    continue

                reader = next((x for x in found if x[0] == "reader"), None)
                param = next((x for x in found if x[0] == "param"), None)
                if not (reader and param):
                    continue
                errors.append(
                    f"Step parameter type error in '{path}' line {node.lineno}: "
                    f"`{param[1]}` is parsed as {param[2]} by the step decorator, "
                    f"but `{reader[1]}` returns {reader[2]}. Comparing them is "
                    f"ALWAYS False - the test fails even when the application is "
                    f"correct, every run, so the failure points at the app and the "
                    f"app is fine. Convert one side explicitly: "
                    f"`{'int(' + reader[1] + ')' if reader[2] == 'str' else 'str(' + param[1] + ')'}`, "
                    f"or change the reader's return type."
                )
    return errors