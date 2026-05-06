"""
Test Inventory — scan existing .feature files to discover what's already covered.

This module is the foundation of Agent 2's deduplication awareness. Before
Agent 2 generates code for a new test case, it asks the inventory:
"does any existing scenario already cover this?"

WHY THIS EXISTS:
    Earlier versions of Agent 2 had no awareness of existing tests. When
    SCRUM-5 was reprocessed, Agent 2 generated `test_login_validation.py`
    alongside the existing `test_login.py` — duplicating coverage of the
    login feature area. This module solves that by parsing existing
    .feature files and exposing a clean lookup API.

DESIGN CHOICES:
    1. We use simple regex parsing instead of pulling in `gherkin-official`
       to keep dependencies minimal. The Gherkin format is stable and
       these patterns cover everything Agent 2 generates.
    2. Matching is by NORMALIZED scenario title (case-insensitive,
       whitespace-collapsed). This catches obvious duplicates without
       needing semantic similarity (which would require an LLM call).
    3. The module is read-only. It never modifies files. Safe to call
       from anywhere, anytime.
    4. Empty/missing directories return empty inventory rather than
       erroring. This keeps Agent 2's flow simple — first-ever run with
       no features dir still works.

USAGE:
    from agents.test_inventory import scan_features_dir, find_matching_scenario
    from config.paths import FEATURES_DIR

    inventory = scan_features_dir(FEATURES_DIR)
    match = find_matching_scenario("Successful login with standard user", inventory)
    if match:
        print(f"Already covered by: {match['file']} :: {match['scenario']}")
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger("test_inventory")


# ─── Gherkin parsing patterns ───────────────────────────────────────────
# These regexes target the pytest-bdd flavor of Gherkin we use in this repo.
# Each pattern captures the title text (everything after the keyword + colon).
#
# WHY MULTILINE FLAG: scenarios start at the beginning of a line (after
# leading whitespace). Without re.MULTILINE, ^ would only match start-of-string.
#
# WHY \s* INSIDE: handles indentation (Gherkin scenarios are typically
# indented under the Feature block, so the actual `Scenario:` keyword
# appears with leading spaces).

_SCENARIO_PATTERN = re.compile(
    r"^\s*Scenario\s*:\s*(.+?)\s*$",
    re.MULTILINE,
)

_SCENARIO_OUTLINE_PATTERN = re.compile(
    r"^\s*Scenario\s+Outline\s*:\s*(.+?)\s*$",
    re.MULTILINE | re.IGNORECASE,
)


# ─── Public API ─────────────────────────────────────────────────────────


def normalize_scenario_name(raw: str) -> str:
    """
    Normalize a scenario name for case- and whitespace-insensitive matching.

    The same logical test case can be expressed as:
        "Successful login with standard user"
        "  Successful  login with  standard user  "
        "successful login with standard user"
        "SUCCESSFUL LOGIN WITH STANDARD USER"

    All of these should match. This function reduces them to a canonical form:
        - Strip leading/trailing whitespace
        - Lowercase everything
        - Collapse internal whitespace runs to single spaces

    We deliberately do NOT remove punctuation or do stemming — those would
    over-match and incorrectly skip legitimately new test cases.

    Args:
        raw: The scenario name as it appears in the .feature file or as a
             Test Case title from Jira.

    Returns:
        A normalized lowercase string suitable for direct equality comparison.
    """
    if not raw:
        return ""
    # collapse all whitespace runs (tabs, newlines, multiple spaces) into single spaces
    collapsed = re.sub(r"\s+", " ", raw)
    return collapsed.strip().lower()


def _parse_feature_file(feature_file: Path) -> list[str]:
    """
    Parse a single .feature file and extract scenario titles.

    Catches both `Scenario:` and `Scenario Outline:` keywords. Comments
    (lines starting with #) are naturally skipped because the regex
    requires the keyword at the (whitespace-prefixed) start of a line.

    Args:
        feature_file: Path to a .feature file. Must exist.

    Returns:
        List of scenario title strings, in the order they appear in the file.
        Returns empty list if the file has no scenarios (e.g., feature with
        only Background or empty feature).
    """
    try:
        content = feature_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        logger.warning(f"Could not read {feature_file}: {e}")
        return []

    titles = []
    titles.extend(_SCENARIO_PATTERN.findall(content))
    titles.extend(_SCENARIO_OUTLINE_PATTERN.findall(content))

    # Strip any quotes or trailing punctuation the LLM might have added
    titles = [t.strip().strip('"').strip("'") for t in titles]

    # Filter out empty matches (defensive — shouldn't happen with our regex)
    titles = [t for t in titles if t]

    return titles


def scan_features_dir(features_dir: Path) -> dict:
    """
    Scan a features directory and build an inventory of all existing scenarios.

    This is the single source of truth for "what tests already exist" in the
    repo. Agent 2 calls this before deciding what to generate.

    Args:
        features_dir: Path to the features/ directory. May not exist yet
                     (first-ever run); that's not an error.

    Returns:
        A dict with three keys:
        {
            "files": [str],                    # filenames of all .feature files found
            "scenarios_by_file": {str: [str]}, # filename → list of scenario titles
            "all_scenarios": [str],            # flat list of every scenario across all files
        }

        All values use ORIGINAL (un-normalized) scenario titles for human
        readability in logs. Use `normalize_scenario_name()` before matching.
    """
    inventory = {
        "files": [],
        "scenarios_by_file": {},
        "all_scenarios": [],
    }

    if not features_dir.exists():
        logger.info(f"Features directory does not exist: {features_dir} (returning empty inventory)")
        return inventory

    if not features_dir.is_dir():
        logger.warning(f"Features path is not a directory: {features_dir}")
        return inventory

    feature_files = sorted(features_dir.glob("*.feature"))

    if not feature_files:
        logger.info(f"No .feature files found in {features_dir} (returning empty inventory)")
        return inventory

    for feature_file in feature_files:
        filename = feature_file.name
        scenarios = _parse_feature_file(feature_file)

        inventory["files"].append(filename)
        inventory["scenarios_by_file"][filename] = scenarios
        inventory["all_scenarios"].extend(scenarios)

    logger.info(
        f"Scanned {len(inventory['files'])} feature file(s); "
        f"found {len(inventory['all_scenarios'])} scenario(s) total"
    )
    return inventory


def find_matching_scenario(
    test_case_title: str, inventory: dict
) -> Optional[dict]:
    """
    Check whether a test case title matches any existing scenario in the inventory.

    This is the decision point Agent 2 calls for each Test Case from Jira:
    "should I generate code for this, or skip because it's already covered?"

    Matching is by NORMALIZED title (see `normalize_scenario_name`). We do
    not attempt semantic matching here — that would require an LLM call and
    would over-match in subtle ways that incorrectly skip new coverage.

    Args:
        test_case_title: The title of the Jira Test Case being considered.
        inventory: The inventory dict returned by `scan_features_dir`.

    Returns:
        None if no match found (test case is new, generate it).
        Or a dict with three keys describing the match:
        {
            "file": str,         # which .feature file contains the existing scenario
            "scenario": str,     # the original (un-normalized) scenario title
            "match_type": str,   # "exact" (case/whitespace insensitive)
        }
    """
    if not test_case_title:
        return None

    normalized_target = normalize_scenario_name(test_case_title)

    if not normalized_target:
        return None

    for filename, scenarios in inventory.get("scenarios_by_file", {}).items():
        for scenario in scenarios:
            if normalize_scenario_name(scenario) == normalized_target:
                return {
                    "file": filename,
                    "scenario": scenario,
                    "match_type": "exact",
                }

    return None


def filter_duplicate_test_cases(
    test_cases: list, inventory: dict
) -> tuple:
    """
    Split a list of test cases into 'new' (need code generation) and
    'skipped' (already covered by existing scenarios).

    This is the function Agent 2 calls to decide what work needs doing.
    It uses `find_matching_scenario` for each test case and partitions
    the input accordingly.

    INPUT SHAPE:
        test_cases is the list Agent 2 already produces from Jira:
            [
                {"key": "SCRUM-9", "summary": "...", "description": "..."},
                {"key": "SCRUM-10", "summary": "...", "description": "..."},
                ...
            ]
        We match against the `summary` field, which is the test case title.

    REGENERATION SEMANTICS (Phase 6):
        This function does NOT know about the `ai-regenerate` label. When
        Agent 2 detects regeneration mode, it should call this function
        with an EMPTY inventory dict — that way every test case ends up in
        `new_cases` and gets fresh code generation. Keeping the regenerate
        decision OUT of this function makes the function easier to test
        and respects single-responsibility.

    Args:
        test_cases: List of test case dicts (each with at least a "summary" key).
        inventory: Inventory dict from `scan_features_dir`.

    Returns:
        Tuple of (new_cases, skipped_cases):
          - new_cases: list of test case dicts that have NO matching existing
                       scenario; these are what Agent 2 should generate code for.
          - skipped_cases: list of dicts describing skipped cases:
              {
                  "test_case": <original test case dict>,
                  "matched_file": str,
                  "matched_scenario": str,
              }
            Agent 2 should log these so the user can see what was skipped
            and why. Empty list means nothing was skipped.

        Note: a test case with no "summary" key or empty summary is treated
        as "new" — we never silently skip something we can't evaluate.
    """
    new_cases = []
    skipped_cases = []

    if not test_cases:
        return new_cases, skipped_cases

    for tc in test_cases:
        # Defensive: each test case should be a dict with a "summary" field.
        # If it isn't, treat it as "new" (don't lose work) and let downstream
        # validation catch the malformed case. Erroring here would fail an
        # entire batch on one bad input.
        title = tc.get("summary", "") if isinstance(tc, dict) else ""

        match = find_matching_scenario(title, inventory)

        if match is None:
            # No existing scenario matches — this is genuinely new.
            new_cases.append(tc)
        else:
            # An existing scenario already covers this test case.
            # Record it so Agent 2 can log "skipped X because Y already exists".
            skipped_cases.append({
                "test_case": tc,
                "matched_file": match["file"],
                "matched_scenario": match["scenario"],
            })

    return new_cases, skipped_cases


# ─── Filename consistency validator (Phase 4) ──────────────────────────


# Pattern matching `feature_path("...")` or `feature_path('...')` calls in
# Python step definition files. We extract the argument string to compare
# against actual feature filenames.
_FEATURE_PATH_CALL_PATTERN = re.compile(
    r"""feature_path\s*\(\s*['"]([^'"]+)['"]\s*\)""",
)


def validate_filename_consistency(generated_files: list) -> list:
    """
    Verify that step definition files reference feature files that actually
    exist in the same generation batch. Auto-correct unambiguous mismatches
    in-place; return errors only for ambiguous cases.

    BACKGROUND — THE BUG THIS CATCHES:
        - features/login-validation.feature (kebab-case)
        - test_login_validation.py uses feature_path("login_validation") (snake_case)
        - pytest-bdd fails: FileNotFoundError at collection
        - The PR LOOKS fine but tests crash on `pytest --collect-only`

    The validator runs AFTER LLM generation, BEFORE the PR is created.

    AUTO-CORRECTION (added 2026-05-06):
        Smaller LLMs (e.g., gemini-2.5-flash-lite) sometimes slip and use
        kebab-case inside `feature_path()` even when the feature filename
        is snake_case. Rather than hard-failing every time, we now attempt
        a CONSERVATIVE auto-correction:

            1. If the step def references `feature_path("login-validation")`
               but only `login_validation` exists in the batch (variant of
               the same name, just different separator), auto-fix the
               step def's content to use the correct snake_case form.

            2. The fix is logged loudly so the user can see the LLM's
               mistake and the system's correction in the audit trail.

            3. If the correction is AMBIGUOUS (e.g., multiple feature
               files, no clear single match), we still hard-fail —
               better to alert than guess wrong.

    The auto-correction MUTATES `generated_files` in place. The caller's
    `output.files_to_create` list will have the corrected content when
    it's committed to the branch. (We do this rather than returning a
    new list because Agent 2 already holds the reference and a swap
    would require more invasive refactoring.)

    Args:
        generated_files: List of GeneratedFile objects with `file_path`
                        and `content` attributes. (Same shape as Agent 2's
                        `generated_files` list.) Mutated in place if
                        auto-correction is applied.

    Returns:
        List of human-readable error messages for issues that COULD NOT
        be auto-corrected. Empty list means all good (either no issues,
        or all issues were auto-corrected). Non-empty list means at least
        one mismatch was ambiguous and the caller should ABORT.

    NOTE: To learn about auto-corrections that DID happen, the caller
    should check the module logger (we log INFO-level messages for each
    correction). We don't return them in a separate list to keep the
    public signature stable — callers that don't care can ignore the
    log lines, callers that do care can inspect the log.
    """
    errors = []

    if not generated_files:
        return errors

    # Build the set of feature names that ARE being created in this batch.
    # Strip "features/" prefix and ".feature" suffix to get the bare name
    # that step defs would reference via feature_path().
    feature_names_in_batch = set()
    for gf in generated_files:
        path = getattr(gf, "file_path", "")
        if path.startswith("features/") and path.endswith(".feature"):
            bare_name = path[len("features/"):-len(".feature")]
            feature_names_in_batch.add(bare_name)

    # Now check each step def file's feature_path() calls
    for gf in generated_files:
        path = getattr(gf, "file_path", "")
        content = getattr(gf, "content", "")

        # Only check Python files in tests/step_defs/
        if not path.startswith("tests/step_defs/") or not path.endswith(".py"):
            continue

        if not content:
            continue

        # Find all feature_path("name") references
        matches = _FEATURE_PATH_CALL_PATTERN.findall(content)
        if not matches:
            # Step def doesn't use feature_path() — could be a helper module
            # or pytest-bdd is wired up differently. Not our problem to flag.
            continue

        for referenced_name in matches:
            if referenced_name in feature_names_in_batch:
                # Exact match — no problem
                continue

            # Mismatch detected. Can we auto-correct?
            correction = _try_autocorrect_feature_name(
                referenced_name, feature_names_in_batch
            )

            if correction is not None:
                # Auto-fix: rewrite the step def's content to use the
                # correct name. Log loudly for audit trail.
                logger.warning(
                    f"Auto-correcting filename mismatch in '{path}': "
                    f"feature_path(\"{referenced_name}\") -> "
                    f"feature_path(\"{correction}\") "
                    f"(LLM produced wrong separator style; available "
                    f"feature files: {sorted(feature_names_in_batch)})"
                )
                # Mutate gf.content in place. We replace BOTH quote styles
                # (single and double) defensively.
                new_content = content.replace(
                    f'feature_path("{referenced_name}")',
                    f'feature_path("{correction}")',
                ).replace(
                    f"feature_path('{referenced_name}')",
                    f"feature_path('{correction}')",
                )
                # Persist the corrected content back to the GeneratedFile.
                # Pydantic models are usually frozen; if so, this will raise
                # and we'll fall back to error. If not frozen, the mutation
                # sticks and the corrected content reaches the commit.
                try:
                    gf.content = new_content
                    content = new_content  # so subsequent checks in this loop see the fix
                except (AttributeError, TypeError) as exc:
                    # Frozen / immutable model — can't mutate. Fall back to error.
                    errors.append(
                        f"Filename consistency error: step def '{path}' references "
                        f"feature_path(\"{referenced_name}\"), which doesn't match any "
                        f"feature file in this batch. Auto-correction to '{correction}' "
                        f"was attempted but failed because the model is immutable: {exc}. "
                        f"Available feature files in batch: "
                        f"{sorted(feature_names_in_batch) or '[none]'}"
                    )
            else:
                # Ambiguous — could not safely guess the right answer.
                errors.append(
                    f"Filename consistency error: step def '{path}' references "
                    f"feature_path(\"{referenced_name}\"), but no "
                    f"features/{referenced_name}.feature exists in this batch "
                    f"and no unambiguous correction is available. "
                    f"Available feature files in batch: "
                    f"{sorted(feature_names_in_batch) or '[none]'}"
                )

    return errors


def _try_autocorrect_feature_name(
    referenced: str, available: set[str]
) -> str | None:
    """
    Try to find an unambiguous correction for a kebab-vs-snake-case mismatch.

    Returns the corrected name if EXACTLY ONE candidate matches via
    separator-style normalization, otherwise None.

    Examples:
        referenced="login-validation", available={"login_validation"}
            -> returns "login_validation" (kebab→snake variant match)

        referenced="login_validation", available={"login-validation"}
            -> returns "login-validation" (snake→kebab variant match)

        referenced="login-validation", available={"login_validation", "login_errors"}
            -> returns "login_validation" (still unambiguous: only login_validation
               matches when separators are normalized)

        referenced="loginValidation", available={"login_validation"}
            -> returns None (camelCase doesn't normalize; we don't guess)

        referenced="checkout", available={"login_validation"}
            -> returns None (totally different name; we don't guess)

    DESIGN: We only auto-correct separator-style mismatches (`-` vs `_`).
    We never guess between semantically different names. Conservative
    correction is the principle: when in doubt, alert the human.
    """
    # Normalize the referenced name by replacing both - and _ with a
    # placeholder, so "login-validation" and "login_validation" become
    # the same canonical key.
    def _normalize(name: str) -> str:
        return name.replace("-", "|").replace("_", "|").lower()

    referenced_key = _normalize(referenced)
    matches = [
        candidate for candidate in available
        if _normalize(candidate) == referenced_key
    ]

    if len(matches) == 1:
        return matches[0]

    # Either zero matches (totally different name) or multiple matches
    # (somehow several feature files normalize to the same key — would
    # be a different bug). Either way, don't guess.
    return None

# ===========================================================================
# Phase 8: Step Definition Coverage Validator (ADR-010)
# ===========================================================================
# This validator solves the failure mode we hit on PR #9: the LLM generated
# a Gherkin feature file with step phrases, but FORGOT to generate matching
# @given/@when/@then decorators in the corresponding step def file. Tests
# then failed at collection time with `StepDefinitionNotFoundError`.
#
# DESIGN PRINCIPLES (so this is reusable across projects, not just SauceDemo):
#
#   1. NO HARDCODED PHRASES. The validator works for any feature/step def
#      pair regardless of domain (login, cart, checkout, payment, anything).
#
#   2. UNDERSTANDS pytest-bdd's GRAMMAR, not just strings. Decorators with
#      `parsers.parse('...{var}...')` are matched against feature steps by
#      converting the placeholders to regex wildcards.
#
#   3. HANDLES Gherkin's `And`/`But` keywords correctly. These inherit the
#      previous step's type (Given/When/Then), so a feature step like
#      "And I should see the title" must match a @then decorator if the
#      previous step was a Then.
#
#   4. DEFENSIVE on edge cases. Background blocks, Scenario Outline tables,
#      tagged scenarios, comments — all handled per Gherkin spec.
#
#   5. PAIRS feature files with step def files via filename convention:
#      features/login_validation.feature  <->  tests/step_defs/test_login_validation.py
#      This convention is enforced by the existing filename validator
#      (Phase 4), so this validator can rely on it.
# ===========================================================================

# Match a step line in a .feature file. Captures the keyword and the rest.
# Examples matched:
#   "  Given I am on the login page"     -> ("Given", "I am on the login page")
#   "  When I click the button"           -> ("When", "I click the button")
#   "  And I see the error"               -> ("And", "I see the error")
_FEATURE_STEP_PATTERN = re.compile(
    r'^\s*(Given|When|Then|And|But)\s+(.+?)\s*$',
    re.MULTILINE,
)

# Match a decorator on a step def. Captures the type and the phrase pattern.
# Examples matched:
#   '@given("I am on the login page")'                      -> ("given", "I am on the login page", False)
#   "@when(parsers.parse('I click {item}'))"                -> ("when", "I click {item}", True)
#   '@then(parsers.cfparse("I see {n:d} items"))'          -> ("then", "I see {n:d} items", True)
# The third group True/False indicates whether placeholders are present
# (i.e., it's a parsers.parse() call vs. a bare string).
_DECORATOR_PARSER_PATTERN = re.compile(
    r'@(given|when|then)\s*\(\s*parsers\.\w+\s*\(\s*[\'"](.+?)[\'"]\s*\)\s*\)',
    re.DOTALL,
)
_DECORATOR_STRING_PATTERN = re.compile(
    r'@(given|when|then)\s*\(\s*[\'"](.+?)[\'"]\s*\)',
    re.DOTALL,
)


def _extract_feature_steps(feature_content: str) -> list[tuple[str, str]]:
    """Extract steps from a .feature file content as (resolved_keyword, phrase) pairs.

    `And`/`But` keywords are resolved to the previous concrete keyword
    (Given/When/Then) since pytest-bdd dispatches them that way.

    Background steps ARE included — they need step defs too.
    Scenario Outline `Examples:` tables are stripped (they're data, not steps).

    Returns:
        List of tuples like:
            [('given', 'I am on the login page'),
             ('when', 'I click "Login"'),
             ('then', 'I see the dashboard'),
             ('then', 'I see the title "Products")]   # And -> Then
    """
    steps = []
    last_concrete_keyword = None  # 'given', 'when', or 'then'
    inside_examples = False

    for line in feature_content.splitlines():
        stripped = line.strip()

        # Skip blank lines and comments
        if not stripped or stripped.startswith('#'):
            continue

        # Detect Scenario Outline data tables — skip until we hit a non-table line
        if stripped.startswith('Examples:'):
            inside_examples = True
            continue
        if inside_examples:
            if stripped.startswith('|'):
                continue  # data row
            else:
                inside_examples = False  # exited the table

        # Try to match a step
        match = _FEATURE_STEP_PATTERN.match(line)
        if not match:
            continue

        keyword, phrase = match.group(1), match.group(2)
        keyword_lower = keyword.lower()

        if keyword_lower in ('given', 'when', 'then'):
            last_concrete_keyword = keyword_lower
            steps.append((keyword_lower, phrase))
        elif keyword_lower in ('and', 'but'):
            # Inherit previous keyword. If there's no previous (malformed
            # feature), we record None and let downstream matching fail
            # — that's a separate bug from missing step defs.
            steps.append((last_concrete_keyword, phrase))

    return steps


def _extract_decorator_phrases(step_def_content: str) -> list[tuple[str, str, bool]]:
    """Extract step decorators from a step def file as (type, phrase, has_placeholders) tuples.

    Returns:
        List of tuples like:
            [('given', 'I am on the login page', False),
             ('when', 'I log in as "{user}" with password "{pw}"', True),
             ('then', 'I see the inventory page', False)]

    The `has_placeholders` flag tells the matcher whether to do regex matching
    (placeholders present) or exact string matching (no placeholders).
    """
    decorators = []

    # Find parsers.parse(...) decorators first — they have placeholders
    for match in _DECORATOR_PARSER_PATTERN.finditer(step_def_content):
        kind, phrase = match.group(1), match.group(2)
        decorators.append((kind, phrase, True))

    # Then find bare-string decorators. Exclude any that overlap with
    # parsers.parse decorators (the parser pattern would have caught them).
    # We do this by tracking the spans we already matched.
    parser_spans = [
        (m.start(), m.end())
        for m in _DECORATOR_PARSER_PATTERN.finditer(step_def_content)
    ]

    for match in _DECORATOR_STRING_PATTERN.finditer(step_def_content):
        # Skip if this match falls inside an already-captured parser decorator
        if any(start <= match.start() < end for start, end in parser_spans):
            continue
        kind, phrase = match.group(1), match.group(2)
        decorators.append((kind, phrase, False))

    return decorators


def _phrase_matches(feature_phrase: str, decorator_phrase: str, has_placeholders: bool) -> bool:
    """Check if a feature step phrase matches a decorator's pattern.

    For bare-string decorators (no placeholders), match is exact equality.

    For parsers.parse() decorators with `{var}` or `{var:type}` placeholders,
    we convert the decorator phrase to a regex by replacing each `{...}` with
    a wildcard, then test the feature phrase against it.

    Examples:
        feature: 'I log in as "alice" with password "secret"'
        decorator: 'I log in as "{user}" with password "{pw}"'  (has_placeholders=True)
        -> regex: r'^I log in as "[^"]+" with password "[^"]+"$'
        -> matches: True

        feature: 'I see 5 items'
        decorator: 'I see {n:d} items'  (has_placeholders=True)
        -> regex: r'^I see .+ items$'
        -> matches: True

    Wildcard choice: we use `[^"]+` if the placeholder is between quotes
    (the common case in Gherkin) and `.+?` otherwise. This avoids greedy
    matches that would wrongly accept totally different feature steps.
    """
    if not has_placeholders:
        return feature_phrase.strip() == decorator_phrase.strip()

    # Build a regex from the decorator phrase
    regex_parts = []
    i = 0
    while i < len(decorator_phrase):
        char = decorator_phrase[i]
        if char == '{':
            # Find the closing brace
            close = decorator_phrase.find('}', i)
            if close == -1:
                # Malformed decorator — fall back to literal char
                regex_parts.append(re.escape(char))
                i += 1
                continue
            # Check whether this placeholder sits between quotes
            # ("...{var}..." pattern is common in Gherkin)
            preceded_by_quote = i > 0 and decorator_phrase[i - 1] == '"'
            followed_by_quote = close + 1 < len(decorator_phrase) and decorator_phrase[close + 1] == '"'
            if preceded_by_quote and followed_by_quote:
                # Match anything between the quotes including empty strings.
                # Empty values are common in validation tests like
                # `When I log in with username "" and password "secret_sauce"`.
                regex_parts.append('[^"]*')
            else:
                regex_parts.append('.+?')
            i = close + 1
        else:
            regex_parts.append(re.escape(char))
            i += 1

    pattern = '^' + ''.join(regex_parts) + '$'
    try:
        return bool(re.match(pattern, feature_phrase.strip()))
    except re.error:
        # Pathological regex (shouldn't happen with our construction, but
        # defend against future surprises). Fall back to "no match" so
        # the validator alerts rather than silently passing.
        return False


def validate_step_definitions_complete(generated_files: list) -> list:
    """Verify every step phrase in generated .feature files has a matching
    @given/@when/@then decorator in the corresponding step def file.

    PAIRING CONVENTION:
        features/X.feature  pairs with  tests/step_defs/test_X.py
        (This is enforced by the Phase 4 filename consistency validator.)

    HARD-FAIL BEHAVIOR:
        Returns a list of error strings — one per missing step. Empty list
        means every step in every feature has a matching decorator. The
        caller should ABORT the PR if errors are returned, since the tests
        would fail at collection time with StepDefinitionNotFoundError.

    REUSABLE FOR ANY PROJECT:
        Makes no assumptions about domain (works for login, cart, checkout,
        payment processing, anything). Understands pytest-bdd's grammar
        including `And`/`But` keyword inheritance, parsers.parse() with
        placeholders, and quote-bounded variable capture.

    Args:
        generated_files: List of objects with `file_path` and `content`
                        attributes (same shape as Agent 2's
                        `generated_files`). Both .feature files and
                        step def .py files should be in the list.

    Returns:
        List of human-readable error messages, one per missing step
        definition. Empty list means complete coverage.
    """
    errors = []

    if not generated_files:
        return errors

    # Index all files by path for quick pairing
    by_path = {}
    for gf in generated_files:
        path = getattr(gf, "file_path", "")
        content = getattr(gf, "content", "") or ""
        by_path[path] = content

    # For each feature file, find its paired step def file
    for path, content in by_path.items():
        if not (path.startswith("features/") and path.endswith(".feature")):
            continue

        # Derive the expected step def path
        feature_basename = path[len("features/"):-len(".feature")]
        expected_step_def = f"tests/step_defs/test_{feature_basename}.py"

        if expected_step_def not in by_path:
            # No paired step def file in this batch. This is the Phase 4
            # filename validator's territory — it will catch it. Skip
            # here to avoid double-reporting.
            continue

        step_def_content = by_path[expected_step_def]

        # Extract steps from feature and decorators from step def
        feature_steps = _extract_feature_steps(content)
        decorators = _extract_decorator_phrases(step_def_content)

        # Track unique missing steps (avoid duplicate errors when the same
        # step appears in multiple scenarios)
        already_reported = set()

        for step_keyword, step_phrase in feature_steps:
            if step_keyword is None:
                # Malformed feature (And/But with no preceding Given/When/Then).
                # Out of scope for this validator.
                continue

            # Look for a matching decorator
            matched = False
            for dec_kind, dec_phrase, has_placeholders in decorators:
                if dec_kind != step_keyword:
                    continue
                if _phrase_matches(step_phrase, dec_phrase, has_placeholders):
                    matched = True
                    break

            if not matched:
                # Build a stable error key so we don't report the same
                # missing step multiple times (e.g., same step in 3 scenarios)
                error_key = (step_keyword, step_phrase)
                if error_key in already_reported:
                    continue
                already_reported.add(error_key)

                errors.append(
                    f"Step coverage error in '{expected_step_def}': "
                    f"feature step `{step_keyword.capitalize()} {step_phrase}` "
                    f"(from '{path}') has no matching @{step_keyword}() decorator. "
                    f"pytest-bdd would fail with StepDefinitionNotFoundError at "
                    f"test collection time."
                )

    return errors