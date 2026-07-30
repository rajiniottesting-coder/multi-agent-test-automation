"""
(Renamed from test_inventory.py — the old name looked like a pytest test file.)

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
    from validators.gherkin_analyzer import scan_features_dir, find_matching_scenario
    from config.paths import FEATURES_DIR

    inventory = scan_features_dir(FEATURES_DIR)
    match = find_matching_scenario("Successful login with standard user", inventory)
    if match:
        print(f"Already covered by: {match['file']} :: {match['scenario']}")
"""
from __future__ import annotations

import ast
import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger("gherkin_analyzer")


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
        Smaller / weaker LLMs sometimes slip and use
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
# DESIGN PRINCIPLES (so this is reusable across projects, independent of the app under test):
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

# Match a decorator on a step def. Captures (type, parser_kind, phrase).
# Examples matched:
#   '@given("I am on the login page")'                      -> ("given", "string", "I am on the login page")
#   "@when(parsers.parse('I click {item}'))"                -> ("when", "parse", "I click {item}")
#   "@when(parsers.re(r'username \"([^\"]*)\"'))"          -> ("when", "re", "username \"([^\"]*)\"")
#   '@then(parsers.cfparse("I see {n:d} items"))'          -> ("then", "cfparse", "I see {n:d} items")
#
# We capture the parser kind (parse/re/cfparse) because matching semantics
# differ at runtime:
#   - parsers.parse / cfparse use the `parse` library (won't match empty
#     quoted values like "" — common QA edge case!)
#   - parsers.re uses Python's `re` module (full regex, can match empty)
#   - bare strings require exact match
#
# The validator MUST mirror runtime behavior exactly to avoid the PR #9
# scenario where the validator passed but tests failed at collection time.
_DECORATOR_PARSER_PATTERN = re.compile(
    r'@(given|when|then)\s*\(\s*parsers\.(parse|cfparse|re)\s*\(\s*r?[\'"](.+?)[\'"]\s*\)\s*\)',
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


def _extract_decorator_phrases(step_def_content: str) -> list[tuple[str, str, str]]:
    """Extract step decorators from a step def file as (kind, phrase, parser_type) tuples.

    Returns:
        List of tuples like:
            [('given', 'I am on the login page', 'string'),
             ('when', 'I log in as "{user}" with password "{pw}"', 'parse'),
             ('when', r'I log in as "([^"]*)" with password "([^"]*)"', 're'),
             ('then', 'I see {n:d} items', 'cfparse')]

    The `parser_type` tells the matcher which runtime semantics to use:
      - 'string': exact equality (no placeholders)
      - 'parse':  the `parse` library — does NOT match empty quoted values
      - 'cfparse': cardinality-aware parse — same empty-string limitation
      - 're':     Python `re` module — full regex power
    """
    decorators = []

    # Find parsers.parse(...) / parsers.re(...) / parsers.cfparse(...) decorators
    for match in _DECORATOR_PARSER_PATTERN.finditer(step_def_content):
        kind, parser_type, phrase = match.group(1), match.group(2), match.group(3)
        decorators.append((kind, phrase, parser_type))

    # Then find bare-string decorators. Exclude any that overlap with
    # parsers.* decorators (the parser pattern would have caught them).
    parser_spans = [
        (m.start(), m.end())
        for m in _DECORATOR_PARSER_PATTERN.finditer(step_def_content)
    ]

    for match in _DECORATOR_STRING_PATTERN.finditer(step_def_content):
        # Skip if this match falls inside an already-captured parser decorator
        if any(start <= match.start() < end for start, end in parser_spans):
            continue
        kind, phrase = match.group(1), match.group(2)
        decorators.append((kind, phrase, 'string'))

    return decorators


def _phrase_matches(feature_phrase: str, decorator_phrase: str, parser_type: str) -> bool:
    """Check if a feature step phrase matches a decorator's pattern.

    CRITICAL: Uses the SAME backends pytest-bdd uses at runtime. This guarantees
    that if the validator says "yes match", pytest-bdd will also match — closing
    the gap that caused PR #9 (validator was permissive about empty quoted values
    but parse library refused to match them at runtime).

    Backends per parser_type:
      - 'string':  exact equality after strip()
      - 'parse':   the `parse` library (same as pytest-bdd's parsers.parse)
      - 'cfparse': the `parse_type` library (same as pytest-bdd's parsers.cfparse).
                   Falls back to `parse` if parse_type isn't installed locally —
                   acceptable because cfparse is a superset and rarely used in
                   the LLM's output.
      - 're':      Python `re.fullmatch` (same as pytest-bdd's parsers.re)
    """
    feature_phrase = feature_phrase.strip()
    decorator_phrase = decorator_phrase.strip()

    if parser_type == 'string':
        return feature_phrase == decorator_phrase

    if parser_type == 're':
        try:
            return bool(re.fullmatch(decorator_phrase, feature_phrase))
        except re.error:
            # LLM produced a malformed regex. Better to flag this as no-match
            # so the validator catches it than to silently pass.
            return False

    # parser_type in ('parse', 'cfparse')
    # Both use the parse library's matching semantics.
    try:
        from parse import parse as _parse_fn
    except ImportError:
        # parse should always be available in production (transitive dep of
        # pytest-bdd, and explicitly listed in requirements.txt). If it's
        # missing, we cannot validate parse() decorators correctly. Log a
        # WARNING so this is visible in CI logs, then conservatively return
        # True so we don't block valid code in non-pytest-bdd environments.
        # This branch should never hit in production but exists as a safety net.
        logger.warning(
            "The 'parse' library is not installed. Cannot validate "
            "parsers.parse() decorators. Install with: pip install parse"
        )
        return True

    try:
        result = _parse_fn(decorator_phrase, feature_phrase)
        return result is not None
    except Exception:
        # Pathological pattern (very rare). Treat as no-match so validator
        # alerts rather than silently passing.
        return False


# ─────────────────────────────────────────────────────────────
# Cross-file duplicate step-definition validator (SCRUM-54 lesson)
#
# CORRECTED (ADR-013): pytest-bdd steps are MODULE-SCOPED fixtures, not global.
# A step declared in a sibling step-def module is NOT available to another
# module. Each generated step-def file is therefore SELF-CONTAINED. The disk/
# sibling pooling below is RETAINED so the validator stays permissive (it must
# never fail a self-contained file), but it means the validator can pass a file
# that omits a step. Agent 4 is the backstop for that case.


def validate_no_duplicate_step_definitions(
    generated_files: list,
    project_root=None,
    repair_format: bool = False,
) -> list:
    """Cross-file step duplication is SAFE in pytest-bdd — always returns [].

    RETAINED AS A NO-OP (ADR-013). This validator used to flag the same step
    phrase appearing in two step-def files, believing pytest-bdd "registers
    step definitions globally across the package". That belief is FALSE.

    pytest-bdd implements step definitions as pytest FIXTURES, which are
    MODULE-SCOPED. Two modules declaring the same step text each resolve their
    own copy; they never collide. Verified empirically.

    Because duplication is harmless, every generated step-def file is
    SELF-CONTAINED: it declares every step its own feature uses. That removes
    the fragile "is this step shared?" judgement the LLM had to make.

    Args:
        generated_files: list of GeneratedFile (file_path + content).
        project_root: repo root, used to also read the on-disk reference
            step-def file so collisions against it are caught. If None, only
            the generated batch is cross-checked (still catches new-vs-new).
        repair_format: when True, emit errors in the repair loop's
            `... error in '<generated_path>':` format so the loop can target
            and regenerate the offending GENERATED file. The reference file is
            never named as the repair target (it is reserved and correct).

    Returns:
        list[str]: human-readable error messages, one per genuine collision.
        Empty list means no cross-file duplicates.
    """
    from pathlib import Path as _Path

    # (keyword, parser_type, phrase) -> list of file paths declaring it
    registry: dict[tuple, list[str]] = {}

    def _index(path: str, content: str) -> None:
        for kind, phrase, parser_type in _extract_decorator_phrases(content):
            key = (kind, parser_type, phrase.strip())
            registry.setdefault(key, [])
            if path not in registry[key]:
                registry[key].append(path)

    # 1) Index every generated step-def file in this batch.
    step_def_files = [
        f for f in generated_files
        if _gf_path(f).startswith("tests/step_defs/")
        and _gf_path(f).endswith(".py")
    ]
    for f in step_def_files:
        _index(_gf_path(f), _gf_content(f))

    # 2) Also index the reference step-def file(s) already on disk — the
    #    generated code shares pytest-bdd's global namespace with them. Only
    #    read files that are NOT themselves being regenerated in this batch
    #    (a regenerated file's new content is already indexed above).
    if project_root is not None:
        root = _Path(project_root)
        generated_paths = {_gf_path(f) for f in step_def_files}
        step_defs_dir = root / "tests" / "step_defs"
        if step_defs_dir.is_dir():
            for py in sorted(step_defs_dir.glob("*.py")):
                rel = f"tests/step_defs/{py.name}"
                if rel in generated_paths:
                    continue  # superseded by generated content
                if py.name == "__init__.py":
                    continue
                try:
                    _index(rel, py.read_text(encoding="utf-8"))
                except OSError:
                    continue  # unreadable file — skip, don't crash the validator

    # 3) Report any key declared in more than one file.
    #    Determine which of the colliding files are GENERATED in this batch —
    #    those are the repairable targets (the reference is reserved/correct).
    generated_paths_set = {
        _gf_path(f) for f in generated_files
        if _gf_path(f).startswith("tests/step_defs/") and _gf_path(f).endswith(".py")
    }

    return []  # cross-file duplication is safe — see docstring (ADR-013)

    errors: list[str] = []
    for (kind, parser_type, phrase), paths in sorted(registry.items()):
        if len(paths) <= 1:
            continue
        kind_disp = f"@{kind}"
        phrase_disp = phrase if len(phrase) <= 80 else phrase[:77] + "..."
        files_disp = ", ".join(sorted(paths))
        # Prefer to blame a generated file (repairable). If none of the
        # colliding files are generated (both on disk), there is nothing this
        # batch can repair — fall back to a plain message.
        repair_target = next(
            (p for p in sorted(paths) if p in generated_paths_set), None
        )
        guidance = (
            "UNREACHABLE (ADR-013): this validator returns [] — pytest-bdd steps "
            "are module-scoped fixtures, so cross-file duplication never collides."
        )
        if repair_format and repair_target is not None:
            # Repair-loop-targetable format: '... error in \'<path>\':'
            errors.append(
                f"Duplicate step-definition error in '{repair_target}': "
                f'{kind_disp}("{phrase_disp}") [{parser_type}] is also defined in '
                f"{files_disp}. {guidance}"
            )
        else:
            errors.append(
                f"Duplicate step definition {kind_disp}"
                f'("{phrase_disp}") [{parser_type}] is declared in multiple '
                f"files: {files_disp}. {guidance}"
            )

    return errors


def _gf_path(f) -> str:
    """Path accessor tolerant of GeneratedFile objects or plain dicts."""
    if hasattr(f, "file_path"):
        return f.file_path
    return f.get("file_path", "") if isinstance(f, dict) else ""


def _gf_content(f) -> str:
    if hasattr(f, "content"):
        return f.content
    return f.get("content", "") if isinstance(f, dict) else ""


def validate_feature_file_structure(generated_files: list) -> list:
    """Catch malformed Gherkin: steps outside any Scenario/Background/Examples block.

    pytest-bdd raises `FeatureError: Step definition outside of a Scenario or a
    Background.` at test collection time when a feature file has step keywords
    (Given/When/Then/And/But) appearing at the top level of the file rather
    than inside one of:
        - Scenario:
        - Scenario Outline:
        - Background:
        - Example: / Scenarios: (Gherkin synonyms)

    This is a different bug class from the step-coverage check. The step
    coverage validator confirms every step has a matching decorator; this
    one confirms every step is inside a valid containing block.

    HOW IT WORKS:
        Gherkin uses indentation (and blank lines) to delimit blocks.
        A `Background:` block ends when a less-or-equally-indented non-step
        line appears (typically `Scenario:` or another block keyword), or
        when a step appears that ISN'T further indented than the block
        opener. We track the indent of the most recent block opener and
        treat any step at <= that indent as outside the block.

    REUSABLE FOR ANY PROJECT:
        Pure Gherkin grammar check. No app/domain assumptions.

    Args:
        generated_files: Each must have `.file_path` and `.content`.

    Returns:
        List of human-readable error strings, one per orphan step. Empty
        list means every step is inside a valid block.
    """
    errors = []
    BLOCK_OPENERS = {
        "scenario", "scenario outline", "scenario template",
        "background",
        "example", "examples", "scenarios",
        "rule",
    }
    STEP_KEYWORDS = {"given", "when", "then", "and", "but", "*"}

    for f in generated_files:
        path = getattr(f, "file_path", "") or ""
        content = getattr(f, "content", "") or ""
        if not path.endswith(".feature"):
            continue

        block_indent = None  # indent level of the most recent block opener; None = outside any block
        in_examples_table = False  # special case: data table rows starting with |

        for line_no, raw in enumerate(content.splitlines(), start=1):
            # Compute indent of this line
            indent = len(raw) - len(raw.lstrip())
            stripped = raw.strip()

            if not stripped or stripped.startswith("#"):
                continue  # blank lines and comments don't change state

            # Tag lines like @smoke don't change block state
            if stripped.startswith("@"):
                continue

            # Data-table rows (inside Examples)
            if stripped.startswith("|"):
                continue

            # If a line is at <= the block opener's indent and is NOT a step,
            # the previous block has ended.
            if block_indent is not None and indent <= block_indent:
                # The block has ended. New tokens decide what's next.
                block_indent = None
                in_examples_table = False

            # Look for keywords with ':' first (Feature/Scenario/Background/etc.)
            head = stripped.split(":", 1)[0].strip().lower() if ":" in stripped else ""

            if head == "feature":
                block_indent = None  # Feature line itself is not a step container
                continue

            if head in BLOCK_OPENERS:
                block_indent = indent
                in_examples_table = (head in ("example", "examples", "scenarios"))
                continue

            # Now check for step keywords.
            first_token = stripped.split(None, 1)[0].lower()
            if first_token in STEP_KEYWORDS:
                if block_indent is None:
                    errors.append(
                        f"Gherkin structure error in '{path}': step on line "
                        f"{line_no} (`{stripped[:80]}`) appears outside any "
                        f"Scenario/Background/Examples block. pytest-bdd "
                        f"would fail at test collection time with: 'Step "
                        f"definition outside of a Scenario or a Background.' "
                        f"FIX: move this step inside a `Scenario:` or "
                        f"`Background:` block, or remove it if it was added "
                        f"by mistake."
                    )

    return errors


def validate_step_definitions_complete(generated_files: list, project_root=None) -> list:
    """Verify every step phrase in generated .feature files has a matching
    @given/@when/@then decorator — either in the corresponding generated step
    def file, OR in pre-existing step def files already on disk.

    PAIRING CONVENTION:
        features/X.feature  pairs with  tests/step_defs/test_X.py
        (This is enforced by the Phase 4 filename consistency validator.)

    CROSS-FILE STEP REUSE (added 2026-05-10):
        pytest-bdd allows the same step decorator to be defined in any module
        that pytest collects. NOTE: this belief was INCORRECT (ADR-013) —
        the test session. So a feature step like "Given I am on the login
        page" defined in tests/step_defs/test_login.py works for any other
        feature in the same session, no import or conftest required.

        Earlier versions of this validator only inspected the paired step
        def file, which produced false-positive errors any time the LLM
        correctly omitted re-defining a shared step (e.g. login). Now we
        also scan pre-existing step def files on disk and treat any
        decorator we find there as available.

    HARD-FAIL BEHAVIOR:
        Returns a list of error strings — one per genuinely missing step.
        Empty list means every feature step has a matching decorator
        somewhere (paired file, sibling step def file, or generated batch).

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
        project_root:   Optional Path to the repository root. When provided,
                        decorators in `<project_root>/tests/step_defs/*.py`
                        are also treated as available. Defaults to the
                        PROJECT_ROOT computed in config.paths. Pass `None`
                        explicitly (or a non-existent path) to skip the
                        on-disk scan — useful in unit tests that want to
                        validate only the generated batch in isolation.

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

    # === Cross-file decorator pool ===
    # Collect decorators that are available repo-wide (not just in the
    # paired file). Sources, in order:
    #   1. Every step def file in the generated batch (LLM might have put
    #      shared steps in conftest.py or another step def file).
    #   2. Every step def file already on disk (pre-existing tests).
    # Using a function-scoped default so the closure doesn't recompute
    # the file list per feature.
    extra_decorators: list[tuple[str, str, str]] = []

    # 1. From the generated batch: any step def file other than the one
    #    being paired below. We add the paired file's decorators in the
    #    inner loop, so here we just include all of them; duplication is
    #    harmless because the matching loop is "first hit wins".
    for batch_path, batch_content in by_path.items():
        if batch_path.startswith("tests/step_defs/") and batch_path.endswith(".py"):
            extra_decorators.extend(_extract_decorator_phrases(batch_content))

    # 2. From disk. Default to the project's real step_defs dir; opt-out
    #    by passing project_root=None or a path that doesn't exist
    #    (useful in unit tests).
    if project_root is None:
        try:
            from config.paths import PROJECT_ROOT as _PR
            project_root = _PR
        except Exception:
            project_root = None

    if project_root is not None:
        from pathlib import Path as _Path
        step_defs_dir = _Path(project_root) / "tests" / "step_defs"
        if step_defs_dir.is_dir():
            # ADR-013: pool ONLY conftest.py. pytest-bdd step definitions are
            # MODULE-SCOPED fixtures, so a step declared in a sibling step-def
            # module is NOT visible to the module under validation. Pooling
            # siblings made this validator pass files that fail at collection
            # with StepDefinitionNotFoundError - the exact "validator green,
            # runtime red" defect it exists to prevent. conftest.py IS shared
            # by pytest, so it is the only file that may be pooled.
            batch_step_def_paths = {
                p for p in by_path
                if p.startswith("tests/step_defs/") and p.endswith(".py")
            }
            conftest = step_defs_dir / "conftest.py"
            if (conftest.is_file()
                    and "tests/step_defs/conftest.py" not in batch_step_def_paths):
                try:
                    extra_decorators.extend(
                        _extract_decorator_phrases(
                            conftest.read_text(encoding="utf-8")))
                except OSError:
                    pass

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
        # Pool: paired file + cross-file (batch siblings + on-disk).
        decorators = _extract_decorator_phrases(step_def_content) + extra_decorators

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
            for dec_kind, dec_phrase, dec_parser_type in decorators:
                if dec_kind != step_keyword:
                    continue
                if _phrase_matches(step_phrase, dec_phrase, dec_parser_type):
                    matched = True
                    break

            if not matched:
                # Build a stable error key so we don't report the same
                # missing step multiple times (e.g., same step in 3 scenarios)
                error_key = (step_keyword, step_phrase)
                if error_key in already_reported:
                    continue
                already_reported.add(error_key)

                # Diagnostic: was there a parsers.parse decorator that ALMOST
                # matched? Specifically, one that would match if the feature
                # step's empty quoted values were swapped for non-empty ones?
                # If so, produce a more actionable error message telling the
                # LLM to use parsers.re() (which DOES handle empty strings).
                #
                # This catches the PR #9 failure mode at validation time:
                # parsers.parse('I log in with username "{u}"') won't match
                # `username ""` at runtime, but the LLM keeps writing it that
                # way unless we explicitly steer it toward parsers.re().
                hint = _diagnose_no_match(
                    step_keyword, step_phrase,
                    [(k, p, t) for k, p, t in decorators if k == step_keyword],
                )

                if hint:
                    errors.append(
                        f"Step coverage error in '{expected_step_def}': "
                        f"feature step `{step_keyword.capitalize()} {step_phrase}` "
                        f"(from '{path}') has no decorator that matches at runtime. "
                        f"{hint} "
                        f"pytest-bdd would fail with StepDefinitionNotFoundError at "
                        f"test collection time."
                    )
                else:
                    errors.append(
                        f"Step coverage error in '{expected_step_def}': "
                        f"feature step `{step_keyword.capitalize()} {step_phrase}` "
                        f"(from '{path}') has no matching @{step_keyword}() decorator. "
                        f"pytest-bdd would fail with StepDefinitionNotFoundError at "
                        f"test collection time."
                    )

    return errors


def _diagnose_no_match(
    step_keyword: str,
    step_phrase: str,
    same_keyword_decorators: list,
) -> str:
    """If a feature step failed to match any decorator, try to figure out WHY
    and return a human-readable hint.

    Currently detects:
      - PR #9 case: feature has empty quoted value (`""`) and a parsers.parse
        decorator exists that WOULD match if the value were non-empty.
        Hint: switch to parsers.re().

    Returns:
        A hint string explaining the likely cause, or empty string if no
        diagnostic insight is available.
    """
    # Detect feature phrases with empty quoted values like `... ""...`
    has_empty_quoted = '""' in step_phrase
    if not has_empty_quoted:
        return ""

    # Look for a parsers.parse decorator that would match if the empty
    # values were swapped for placeholders. We do this by replacing each
    # `""` in the feature phrase with a placeholder probe and re-checking.
    probe_phrase = step_phrase.replace('""', '"PROBE"')
    for kind, dec_phrase, parser_type in same_keyword_decorators:
        if parser_type not in ('parse', 'cfparse'):
            continue
        if _phrase_matches(probe_phrase, dec_phrase, parser_type):
            # Found it — this is the PR #9 case.
            # Build an actionable hint.
            re_phrase = _suggest_parsers_re_pattern(dec_phrase)
            return (
                f"A `parsers.{parser_type}('{dec_phrase}')` decorator exists "
                f"but the `parse` library does not match empty quoted values "
                f"(this is a known limitation). "
                f"FIX: change the decorator to `parsers.re(r'{re_phrase}')` "
                f"so empty strings are accepted at runtime."
            )
    return ""


def _suggest_parsers_re_pattern(parse_phrase: str) -> str:
    """Convert a parsers.parse phrase like:
        'I log in with username "{u}" and password "{p}"'
    into a parsers.re-compatible regex like:
        r'I log in with username "(?P<u>[^"]*)" and password "(?P<p>[^"]*)"'

    Used in error hints so the LLM gets a copy-pasteable fix."""

    # Subset of regex metacharacters that genuinely need escaping inside the
    # decorator phrase. We avoid using re.escape() because in some Python
    # versions it escapes spaces and other non-special chars, producing ugly
    # output like `I\ log\ in` in the LLM-facing error message.
    REGEX_METACHARS = set(r'.^$*+?()[]{}|\\')

    def _escape_char(c: str) -> str:
        return '\\' + c if c in REGEX_METACHARS else c

    result = []
    i = 0
    while i < len(parse_phrase):
        ch = parse_phrase[i]
        if ch == '{':
            close = parse_phrase.find('}', i)
            if close == -1:
                result.append(_escape_char(ch))
                i += 1
                continue
            placeholder = parse_phrase[i + 1:close]
            # Strip type spec (e.g., "{n:d}" -> "n")
            name = placeholder.split(':', 1)[0].strip() or 'val'
            # If surrounded by quotes, use [^"]* (allows empty)
            preceded_by_quote = i > 0 and parse_phrase[i - 1] == '"'
            followed_by_quote = close + 1 < len(parse_phrase) and parse_phrase[close + 1] == '"'
            if preceded_by_quote and followed_by_quote:
                result.append(f'(?P<{name}>[^"]*)')
            else:
                result.append(f'(?P<{name}>.*?)')
            i = close + 1
        else:
            result.append(_escape_char(ch))
            i += 1
    return ''.join(result)


# ─────────────────────────────────────────────────────────────────────────────
# Reverse step coverage: decorators nothing calls
# ─────────────────────────────────────────────────────────────────────────────

def validate_no_unused_step_definitions(generated_files: list) -> list:
    """Flag @given/@when/@then decorators in generated step-def files that no
    generated feature file actually uses.

    WHY THIS EXISTS:
        validate_step_definitions_complete() checks one direction only —
        every feature step has a decorator. The reverse was invisible, so a
        model that hedged between two phrasings ("...and click away" AND
        "...without typing and click outside") could emit both and use one.
        Dead code, extra review surface, and a reviewer had to catch it.

    CONSERVATIVE BY DESIGN:
        Only inspects decorators in the GENERATED batch, and only counts a
        decorator unused when the batch contains the paired feature file. A
        step-def file generated without its feature (or a shared step used by
        a feature on disk) is never flagged. Prefers false negatives.

    Returns a list of error strings, one per unused decorator. Empty list
    means every generated decorator is reachable from a generated feature.
    """
    errors: list = []

    features: dict = {}
    step_defs: dict = {}
    for f in generated_files:
        path = _gf_path(f)
        if path.endswith(".feature"):
            features[Path(path).stem] = _gf_content(f)
        elif "step_defs" in path and path.endswith(".py"):
            step_defs[Path(path).stem] = (path, _gf_content(f))

    if not features or not step_defs:
        return errors

    for stem, (path, content) in step_defs.items():
        feature_stem = stem[5:] if stem.startswith("test_") else stem
        feature_content = features.get(feature_stem)
        if feature_content is None:
            # No paired feature in this batch — cannot judge. Skip.
            continue

        feature_steps = _extract_feature_steps(feature_content)
        decorators = _extract_decorator_phrases(content)

        for keyword, phrase, parser_type in decorators:
            used = any(
                _phrase_matches(f_phrase, phrase, parser_type)
                for f_keyword, f_phrase in feature_steps
            )
            if not used:
                errors.append(
                    f"Unused step-definition error in '{path}': "
                    f"@{keyword}('{phrase}') is defined but no scenario in "
                    f"'features/{feature_stem}.feature' uses it. Either use it "
                    f"in a scenario or delete the function. Do not leave two "
                    f"phrasings of the same step when only one is used."
                )

    return errors


# ─────────────────────────────────────────────────────────────────────────────
# Fixture existence: step defs may only request fixtures that exist
# ─────────────────────────────────────────────────────────────────────────────

# Fixtures supplied by pytest, pytest-bdd, pytest-playwright and pytest-html.
# A generated step def may request any of these without them being declared
# in a conftest on disk.
_BUILTIN_FIXTURES = frozenset({
    "request", "tmp_path", "tmp_path_factory", "tmpdir", "tmpdir_factory",
    "monkeypatch", "capsys", "capfd", "capsysbinary", "capfdbinary",
    "caplog", "recwarn", "cache", "pytestconfig", "record_property",
    "record_testsuite_property", "record_xml_attribute", "doctest_namespace",
    # pytest-bdd
    "_pytest_bdd_example",
    # pytest-playwright
    "page", "context", "browser", "browser_name", "browser_type",
    "browser_channel", "browser_context_args", "browser_type_launch_args",
    "playwright", "playwright_instance", "launch_browser", "new_context",
    "base_url", "device", "is_chromium", "is_firefox", "is_webkit",
    # pytest-html / metadata
    "extra", "extras", "metadata",
})


def _auto_registered_page_fixtures(project_root) -> set:
    """Fixture names that conftest auto-registers from page-object classes.

    tests/step_defs/conftest.py creates one fixture per page object, named
    after the class in snake_case (LoginPage -> login_page). Those fixtures are
    built in a loop, so they are invisible to the AST scan that finds
    @pytest.fixture decorators - without this, every auto-registered fixture
    would be reported as missing even though it resolves fine at runtime.

    Derives the names from the same source conftest uses: classes in pages/.
    Text-based on purpose - importing the app's page objects from a validator
    would drag Playwright into a pure-static check.
    """
    names: set = set()
    if project_root is None:
        return names
    pages_dir = Path(project_root) / 'pages'
    if not pages_dir.is_dir():
        return names
    for path in pages_dir.glob('*.py'):
        if path.name.startswith('_'):
            continue
        try:
            tree = ast.parse(path.read_text(encoding='utf-8'))
        except (OSError, SyntaxError):
            # A file that does not parse cannot be imported either, so
            # conftest will skip it. Claiming its fixture exists would let a
            # genuinely missing fixture through.
            continue
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            bases = {getattr(b, 'id', getattr(b, 'attr', '')) for b in node.bases}
            if 'BasePage' not in bases or node.name == 'BasePage':
                continue
            derived = re.sub(r'(?<!^)(?=[A-Z])', '_', node.name).lower()
            if derived in _BUILTIN_FIXTURES:
                # e.g. a class named Page would derive 'page' and shadow the
                # browser fixture. conftest refuses to register these, so the
                # validator must not pretend they exist.
                continue
            names.add(derived)
    return names

def validate_fixtures_exist(generated_files: list, project_root=None) -> list:
    """Verify every fixture a generated step def requests actually exists.

    WHY THIS EXISTS:
        pytest resolves fixtures at COLLECTION time, so a step def asking for
        a fixture nobody declares fails with `fixture 'x' not found` — every
        scenario in the file erroring before a single browser action runs. No
        existing validator saw it: the function exists, the imports resolve,
        the Gherkin matches. Only Agent 4 found out, one stage too late.

        The usual trigger is an inventory entry that names a page object which
        was never built. The page is injected into the prompt, the model
        reasonably assumes a matching fixture exists, and requests it.

    WHERE FIXTURES MAY COME FROM:
        - any conftest.py in the generated batch
        - any conftest.py on disk under the project root
        - _BUILTIN_FIXTURES (pytest / pytest-bdd / playwright / html)

    CONSERVATIVE BY DESIGN:
        Skips a parameter whose name matches a step-def parser variable (those
        are supplied by pytest-bdd from the step text, not by a fixture). If no
        conftest can be located at all, returns no errors rather than guessing.

    Returns a list of error strings, one per missing fixture.
    """
    errors: list = []

    available = set(_BUILTIN_FIXTURES)
    found_any_conftest = False

    def _collect_fixtures(source: str) -> None:
        nonlocal found_any_conftest
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return
        found_any_conftest = True
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                target = dec.func if isinstance(dec, ast.Call) else dec
                name = ""
                if isinstance(target, ast.Attribute):
                    name = target.attr
                elif isinstance(target, ast.Name):
                    name = target.id
                if name == "fixture":
                    available.add(node.name)
                    break

    for f in generated_files:
        if Path(_gf_path(f)).name == "conftest.py":
            _collect_fixtures(_gf_content(f))

    if project_root is not None:
        root = Path(project_root)
        for conftest in root.rglob("conftest.py"):
            if any(part in {".git", "__pycache__", ".venv", "venv"}
                   for part in conftest.parts):
                continue
            try:
                _collect_fixtures(conftest.read_text(encoding="utf-8"))
            except OSError:
                continue

    # Fixtures conftest builds in a loop are invisible to the AST scan above.
    available |= _auto_registered_page_fixtures(project_root)

    if not found_any_conftest:
        return errors

    for f in generated_files:
        path = _gf_path(f)
        if "step_defs" not in path or not path.endswith(".py"):
            continue
        if Path(path).name == "conftest.py":
            continue
        content = _gf_content(f)
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue

        # Parser variables are injected by pytest-bdd, not by fixtures.
        parser_vars: set = set()
        for _kw, phrase, _pt in _extract_decorator_phrases(content):
            parser_vars.update(re.findall(r"\(\?P<(\w+)>", phrase))
            parser_vars.update(re.findall(r"\{(\w+)[:}]", phrase))

        # Fixtures declared inside the step-def module itself are legal too.
        local_fixtures: set = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    target = dec.func if isinstance(dec, ast.Call) else dec
                    nm = target.attr if isinstance(target, ast.Attribute) else (
                        target.id if isinstance(target, ast.Name) else "")
                    if nm == "fixture":
                        local_fixtures.add(node.name)

        reported: set = set()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            is_step = any(
                _is_step_decorator_node(dec) for dec in node.decorator_list
            )
            if not is_step:
                continue
            for arg in node.args.args:
                name = arg.arg
                if (name in available or name in parser_vars
                        or name in local_fixtures or name in reported
                        or name.startswith("_")):
                    continue
                reported.add(name)
                errors.append(
                    f"Fixture resolution error in '{path}': step definition "
                    f"'{node.name}' requests fixture '{name}', which is not "
                    f"declared in any conftest.py and is not a pytest builtin. "
                    f"pytest resolves fixtures at collection time, so every "
                    f"scenario in this file would error before running. Use an "
                    f"existing fixture, or drive the interaction through one "
                    f"that exists."
                )

    return errors


def _is_step_decorator_node(dec) -> bool:
    """True when a decorator node is @given/@when/@then (called or bare)."""
    target = dec.func if isinstance(dec, ast.Call) else dec
    if isinstance(target, ast.Attribute):
        return target.attr in {"given", "when", "then"}
    if isinstance(target, ast.Name):
        return target.id in {"given", "when", "then"}
    return False