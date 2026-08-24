"""
Agent 2 — Coder.

Role:
    Reads approved Test Cases from Jira, uses an LLM to generate Playwright +
    BDD + POM automation code, and opens a Pull Request on GitHub.

Architecture (TWO-STAGE):
    STAGE 1: Plan — LLM produces a CodePlan (structured): file paths, types,
             purposes, PR title, branch name. NO code content yet.
    STAGE 2: Generate — for EACH file in the plan, make a separate LLM call
             (text mode) to produce that file's content. Extract code from
             the response (handles markdown fences).

Defenses:
    - Reserved-path guard: refuses to overwrite reference files even if the
      LLM plans to. Reserved paths come from app_under_test config — NOT
      hardcoded — so the framework works for any app.
    - Filename-consistency validator: catches mismatches between feature
      file names and step-def feature_path() arguments.
    - Step-definition coverage validator: catches Gherkin steps without
      matching @given/@when/@then decorators.
    - Branch-name validator: ensures every PR branch contains a Jira key.
    - Dry-run mode: preview without touching GitHub.
    - Windows-safe printing: ASCII-only output (no emoji) to work in cp1252.

Usage:
    python -m agents.agent2_coder --story SCRUM-5 --dry-run
    python -m agents.agent2_coder --story SCRUM-5
    python -m agents.agent2_coder --scan

FULL FLAG REFERENCE
-------------------
Every flag, its default and its purpose:

    python -m agents.agent2_coder --help

That is the authoritative list - this docstring shows only the common
cases. --help also carries copy-pasteable examples.
"""
import argparse
import ast
from types import SimpleNamespace
import hashlib
import logging
import re
from pathlib import Path
import sys
from dataclasses import dataclass, field
from typing import Optional
import yaml

from core.app_context import AppContext
from integrations.tracker import get_tracker
from core.board_status import move_card_for_label
from integrations.repo_host import get_repo_host
from validators.import_validator import validate_imports_resolvable
from validators.method_resolution_validator import (
    validate_method_resolution,
    validate_page_object_selectors,
    validate_no_duplicate_page_object_methods,
    validate_page_object_methods,
    validate_persistent_pages_can_be_cleared,
    validate_confirm_arrival_targets_this_page,
    validate_readers_return_what_they_name,
    validate_row_scoped_selectors,
    validate_fills_confirm_their_page,
    validate_step_parameter_types,
    validate_step_claims_are_verified,
    validate_readiness_probe,
    validate_predicates_wait,
    validate_no_selectors_in_step_defs,
    validate_persistent_state_assertions,
    validate_page_method_names_are_specific,
)
from core.llm_client import LLMClient, OutputTruncatedError
from core.schemas import CodePlan, GeneratedFile, CodeGenerationOutput
from validators.gherkin_analyzer import (
    validate_step_coverage,
    validate_no_duplicate_step_definitions,
    scan_features_dir,
    filter_duplicate_test_cases,
    validate_filename_consistency,
    validate_feature_file_structure,
    validate_examples_hold_data_not_placeholders,
    validate_step_definitions_complete,
    validate_no_unused_step_definitions,
    detect_drifted_steps,
    _extract_feature_steps,
    validate_fixtures_exist,
    _extract_feature_steps,
    _extract_decorator_phrases,
    _phrase_matches,
)
from config import (
    REQUIRED_GITHUB_ENV_VARS,
    REQUIRED_JIRA_ENV_VARS,
    REQUIRED_LLM_ENV_VARS,
    assert_valid_branch_for_pipeline,
    validate_required_env,
)
from config.paths import PROMPTS_DIR, CONFIG_YAML, FEATURES_DIR, PROJECT_ROOT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("agent2_coder")


# ═══════════════════════════════════════════════════════════════════════════
# INCREMENTAL UPDATE SUPPORT (ai-update label)
# ═══════════════════════════════════════════════════════════════════════════
# This section provides the building blocks for the surgical-update flow:
#
#   - JIRA marker comments: `# JIRA: SCRUM-22 (hash: a4f9c2e1)` above each
#     Scenario, used to identify which scenario belongs to which Test Case
#     and whether the Test Case description has changed since the scenario
#     was last generated.
#
#   - Feature file surgeon: parses Gherkin into scenario blocks, splices/
#     appends/removes individual scenarios while preserving the rest of
#     the file byte-for-byte.
#
# These could live in separate modules but are inlined here to minimize
# file-count changes at this stage of the project. The section is
# self-contained — only stdlib + already-imported modules — and could be
# extracted into its own file later without changing call sites (other
# than imports).
# ═══════════════════════════════════════════════════════════════════════════

# Regex anchored on the JIRA marker comment. Tolerates extra whitespace.
# Examples it matches:
#   "# JIRA: SCRUM-22 (hash: a4f9c2e1)"
#   "    # JIRA: PROJ-7 (hash: abcdef12)"
# Does NOT match without the hash — we want to distinguish OUR markers
# from human-added Jira-key comments.
_JIRA_MARKER_RE = re.compile(
    r"^\s*#\s*JIRA:\s*([A-Z][A-Z0-9_]*-\d+)\s*\(hash:\s*([0-9a-f]{8})\s*\)\s*$",
    re.IGNORECASE,
)

# Keywords that start a top-level block within a feature file.
# Order matters: "Scenario Outline" must be checked before "Scenario".
_GHERKIN_BLOCK_KEYWORDS = (
    "Scenario Outline:",
    "Scenario:",
    "Background:",
    "Examples:",
)


def compute_description_hash(description: str) -> str:
    """Stable 8-char hex hash of a Test Case description.

    Whitespace is normalized before hashing so trivial reformatting in
    Jira (extra blank lines, trailing spaces) doesn't trigger spurious
    updates.
    """
    if description is None:
        description = ""
    normalized = re.sub(r"\s+", " ", description).strip()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return digest[:8]


def format_marker(jira_key: str, description: str) -> str:
    """Build a JIRA marker comment line (no trailing newline)."""
    h = compute_description_hash(description)
    return f"# JIRA: {jira_key} (hash: {h})"


def parse_marker(line: str) -> Optional[tuple[str, str]]:
    """Parse a single line as a JIRA marker.

    Returns (jira_key, hash) if the line is a marker, else None.
    """
    m = _JIRA_MARKER_RE.match(line or "")
    if not m:
        return None
    return m.group(1).upper(), m.group(2).lower()


@dataclass
class ScenarioBlock:
    """A parsed block of lines from a feature file.

    Lines include their trailing newline so they can be reassembled
    losslessly via "".join(b.lines).
    """
    kind: str
    lines: list[str] = field(default_factory=list)
    jira_key: Optional[str] = None
    jira_hash: Optional[str] = None
    marker_line_index: Optional[int] = None

    def text(self) -> str:
        return "".join(self.lines)


def _starts_block(line: str) -> bool:
    stripped = line.lstrip()
    return any(stripped.startswith(kw) for kw in _GHERKIN_BLOCK_KEYWORDS)


def _build_block(lines: list[str]) -> ScenarioBlock:
    if not lines:
        return ScenarioBlock(kind="header", lines=[])
    first = lines[0].lstrip()
    if first.startswith("Scenario Outline:") or first.startswith("Scenario:"):
        kind = "scenario"
    elif first.startswith("Background:"):
        kind = "background"
    elif first.startswith("Examples:"):
        kind = "examples"
    else:
        kind = "header"
    return ScenarioBlock(kind=kind, lines=list(lines))


def _migrate_marker_from_previous(
    previous_blocks: list[ScenarioBlock],
    header_lines: list[str],
    current_block: ScenarioBlock,
) -> None:
    """Pull a JIRA marker comment from the end of the previous block onto
    the current block, so each scenario owns its own marker.

    Also handles the case where the marker is already inside current_block
    (typical for content the LLM just generated for us in
    `_generate_single_scenario`).
    """
    # 1. Marker already inside current_block?
    for idx, line in enumerate(current_block.lines):
        if _starts_block(line):
            break
        parsed = parse_marker(line)
        if parsed:
            current_block.jira_key, current_block.jira_hash = parsed
            current_block.marker_line_index = idx
            return

    # 2. Marker at the trailing edge of the previous owner?
    source_lines = previous_blocks[-1].lines if previous_blocks else header_lines
    j = len(source_lines) - 1
    while j >= 0 and source_lines[j].strip() == "":
        j -= 1
    if j < 0:
        return
    parsed = parse_marker(source_lines[j])
    if not parsed:
        return
    candidate = source_lines[j]
    del source_lines[j]
    current_block.lines.insert(0, candidate)
    current_block.jira_key, current_block.jira_hash = parsed
    current_block.marker_line_index = 0


def parse_feature_file(content: str) -> tuple[list[str], list[ScenarioBlock]]:
    """Split a feature file's content into (header_lines, blocks).

    The original content can be reassembled losslessly:
        "".join(header_lines) + "".join(b.text() for b in blocks)
    """
    if not content:
        return [], []
    lines = content.splitlines(keepends=True)
    first_block_idx = next(
        (i for i, line in enumerate(lines) if _starts_block(line)), None
    )
    if first_block_idx is None:
        return lines, []
    header = lines[:first_block_idx]
    body = lines[first_block_idx:]
    block_starts = [i for i, line in enumerate(body) if _starts_block(line)]
    blocks: list[ScenarioBlock] = []
    for idx, start in enumerate(block_starts):
        end = block_starts[idx + 1] if idx + 1 < len(block_starts) else len(body)
        block = _build_block(body[start:end])
        _migrate_marker_from_previous(blocks, header, block)
        blocks.append(block)
    return header, blocks


def splice_scenario(
    original_content: str,
    jira_key: str,
    new_scenario_text: str,
    new_hash: str,  # accepted for caller sanity-check; not enforced
) -> str:
    """Replace the scenario block owned by `jira_key` with new content.

    Returns the modified file content. If jira_key is not found, returns
    the original content unchanged (callers should treat as 'append').

    Raises ValueError if `new_scenario_text` doesn't carry a marker
    matching jira_key — refusing to splice unmarkered content prevents
    orphan scenarios.
    """
    _new_hash = new_hash  # explicit no-op; documents intent
    header, blocks = parse_feature_file(original_content)

    # Sanity-check the replacement before mutating anything
    new_block_lines = new_scenario_text.splitlines(keepends=True)
    new_block = _build_block(new_block_lines)
    _migrate_marker_from_previous([], [], new_block)
    if new_block.jira_key != jira_key:
        raise ValueError(
            f"Replacement scenario text claims JIRA key {new_block.jira_key!r} "
            f"but caller asked to splice {jira_key!r}. Refusing to splice — "
            "this would create an orphan scenario."
        )

    target_idx = next(
        (i for i, b in enumerate(blocks) if b.jira_key == jira_key), None
    )
    if target_idx is None:
        logger.warning(
            f"Cannot splice scenario for {jira_key}: no existing block "
            "with that JIRA marker found. Caller should append, not splice."
        )
        return original_content

    blocks[target_idx] = new_block
    return "".join(header) + "".join(b.text() for b in blocks)


def append_scenario(original_content: str, new_scenario_text: str) -> str:
    """Append a brand-new scenario block to the end of a feature file."""
    if not original_content.endswith("\n"):
        original_content += "\n"
    if not new_scenario_text.startswith("\n"):
        new_scenario_text = "\n" + new_scenario_text
    return original_content + new_scenario_text


def remove_scenario(original_content: str, jira_key: str) -> str:
    """Remove the scenario block owned by `jira_key`. No-op if absent."""
    header, blocks = parse_feature_file(original_content)
    survivors = [b for b in blocks if b.jira_key != jira_key]
    if len(survivors) == len(blocks):
        logger.info(f"remove_scenario: no block found for {jira_key}, no-op.")
        return original_content
    return "".join(header) + "".join(b.text() for b in survivors)


def classify_test_cases(test_cases: list[dict], feature_content: str) -> dict:
    """Classify each Test Case as unchanged/modified/new + find orphans.

    Returns a dict with keys: unchanged, modified, new (lists of test
    case dicts) and orphan_keys (list of Jira keys present in the file
    but with no matching current Test Case).
    """
    _h, blocks = parse_feature_file(feature_content or "")
    file_hashes: dict[str, str] = {
        b.jira_key: (b.jira_hash or "") for b in blocks if b.jira_key
    }
    unchanged, modified, new = [], [], []
    jira_keys_seen: set[str] = set()

    for tc in test_cases:
        key = tc["key"]
        jira_keys_seen.add(key)
        current_hash = compute_description_hash(tc.get("description", ""))
        if key not in file_hashes:
            new.append(tc)
        elif file_hashes[key] == current_hash:
            unchanged.append(tc)
        else:
            modified.append(tc)

    orphan_keys = sorted(k for k in file_hashes.keys() if k not in jira_keys_seen)
    return {
        "unchanged": unchanged,
        "modified": modified,
        "new": new,
        "orphan_keys": orphan_keys,
    }


# ═══════════════════════════════════════════════════════════════════════════
# END INCREMENTAL UPDATE SUPPORT
# ═══════════════════════════════════════════════════════════════════════════


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------
def _normalize_path(p: str) -> str:
    """Convert backslashes to forward slashes and strip leading ./ for comparison."""
    return p.replace("\\", "/").lstrip("./")


def validate_paths_against_policy(plan: CodePlan, ctx: AppContext) -> None:
    """Enforce the two-tier file policy on the LLM's plan.

    Tier 1 — RESERVED: never touched. If the plan includes any reserved path,
        abort. These are the reference files the LLM uses as a style baseline.

    Tier 2 — EXTENDABLE: may be modified to add new methods. The plan must
        mark these with `is_new_file=False` so it's an explicit, conscious
        modification (not an accidental overwrite). If the LLM marks an
        extendable file as `is_new_file=True`, that means "create from
        scratch" which would wipe existing methods — also abort.

    Tier 3 — NEW: every other path. LLM creates fresh.

    Reserved/extendable lists come from `app_under_test.*` in config.yaml,
    so this check stays correct regardless of which app is being tested.
    """
    reserved = ctx.reserved_paths_normalized()
    extendable = ctx.extendable_paths_normalized()

    reserved_collisions: list[str] = []
    extendable_misclassified: list[str] = []  # marked is_new_file=True for an existing extendable file

    for fp in plan.files_to_create:
        normalized = _normalize_path(fp.file_path)
        if normalized in reserved:
            reserved_collisions.append(fp.file_path)
        elif normalized in extendable and fp.is_new_file:
            extendable_misclassified.append(fp.file_path)

    if reserved_collisions:
        raise ValueError(
            f"LLM tried to overwrite reserved reference files: "
            f"{reserved_collisions}. These files are protected by "
            f"app_under_test.reserved_paths in config.yaml — they're the "
            f"style baseline the LLM mimics, and must never be modified. "
            f"The LLM should have used different file paths for new tests, "
            f"or marked an extendable page object for modification instead."
        )

    if extendable_misclassified:
        raise ValueError(
            f"LLM marked existing extendable file(s) as new "
            f"(is_new_file=True): {extendable_misclassified}. These are "
            f"existing page objects listed in app_under_test.extendable_paths. "
            f"They may be MODIFIED (is_new_file=False) to add new methods, "
            f"but never CREATED from scratch — that would wipe existing "
            f"methods. Fix the plan to set is_new_file=False for these files."
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def load_prompt(prompt_file: str) -> str:
    return (PROMPTS_DIR / prompt_file).read_text(encoding="utf-8")


def load_test_cases_for_story(jira, story_key: str) -> list[dict]:
    """Delegate to the tracker adapter - no query language in agent code."""
    return jira.get_linked_test_cases(story_key)


def format_test_cases_for_prompt(test_cases: list[dict]) -> str:
    blocks = [
        f"## {tc['key']}: {tc['summary']}\n\n{tc['description']}\n"
        for tc in test_cases
    ]
    return "\n---\n".join(blocks)


def extract_code_from_response(response_text: str) -> str:
    """Extract code from a markdown response. Handles fenced and bare code.

    PRO QUIRK FIX (v12e): Pro occasionally emits doubled or tripled
    backtick fences — e.g., six backticks instead of three at fence
    boundaries. This happens when Pro's internal reasoning included
    nested code blocks and the final response over-escapes the fence.

    Concrete example from a real failed run (May 12 cron):
        Pro emitted: <6-backticks>gherkin\\n...content...<6-backticks>
        Expected:    <3-backticks>gherkin\\n...content...<3-backticks>

    Without normalization, the regex matches the FIRST three backticks
    against the immediately-adjacent SECOND three backticks, capturing
    an empty body and returning 1 char. We collapse any run of 4+
    backticks to exactly 3 before extraction.

    Safe because valid Gherkin / Python / Markdown / YAML / etc. never
    contains a run of 4 or more consecutive backticks at a fence boundary.
    """
    # Normalize over-escaped fences (Pro's six-backtick variant → three).
    normalized = re.sub(r"`{4,}", "```", response_text)

    pattern = r"```(?:\w+)?\n?(.*?)```"
    matches = re.findall(pattern, normalized, re.DOTALL)
    if matches:
        return matches[0].strip() + "\n"
    return normalized.strip() + "\n"


def load_agent_config(agent_key: str = "agent2_coder") -> dict:
    with open(CONFIG_YAML) as f:
        full_config = yaml.safe_load(f)
    return full_config.get("agents", {}).get(agent_key, {})


def _build_reserved_paths_block(ctx: AppContext) -> str:
    """Render the reserved-paths list as a markdown bullet block for the
    Stage 1 plan prompt."""
    if not ctx.reserved_paths:
        return "(none — no reserved paths configured)"
    return "\n".join(f"- `{p}` -- RESERVED (must NOT be modified)" for p in ctx.reserved_paths)


def _build_extendable_paths_block(ctx: AppContext) -> str:
    """Render the extendable-paths list as a markdown bullet block for the
    Stage 1 plan prompt. Tells the LLM these existing files MAY be extended."""
    if not ctx.extendable_paths:
        return "(none — no extendable paths configured)"
    return "\n".join(
        f"- `{p}` -- EXTENDABLE (MAY add new methods; "
        f"set is_new_file=False; do NOT remove existing methods)"
        for p in ctx.extendable_paths
    )


def _read_extendable_file_content(file_path: str) -> str:
    """Read the current content of an extendable file so Stage 2 can preserve
    existing methods when adding new ones.

    Falls back to a placeholder if the file doesn't exist on disk —
    extendable files SHOULD exist already, but a missing file is non-fatal
    (the LLM will just create it fresh).
    """
    abs_path = PROJECT_ROOT / file_path
    if not abs_path.exists():
        logger.warning(
            f"Extendable file '{file_path}' not found on disk. The LLM will "
            f"have no existing-content reference; it may create new methods "
            f"without preserving anything. Configured under "
            f"app_under_test.extendable_paths in config.yaml."
        )
        return f"# (file '{file_path}' does not exist yet — generate fresh content)"
    return abs_path.read_text(encoding="utf-8")


def _build_starting_state_block(project_root=None) -> str:
    """The starting-state CONTRACT, rendered from the inventory.

    WHY THIS EXISTS

        The prompt tells Agent 2 that owning a starting state is a three-file
        decision and that one of the three is "a clearing method on the page
        object". It never said what that method is CALLED. The name lives in
        the inventory under `_starting_state.establishing_calls`, and
        `filter_inventory_by_components` strips every top-level key beginning
        with an underscore before the inventory is sent - so the one block
        naming it was deleted from the model's context on the way in.

        The app-context module then pointed at it by name: "using the method
        the inventory names under `_starting_state.establishing_calls`". A
        pointer to a block that had been removed.

        Meanwhile the validator demanded exactly those names, and the repair
        remedy printed them. So the model was asked to produce a method whose
        required name it had never been shown, was corrected against that
        name, and could not comply. Several stories failed that way, and it
        read like the model refusing to take an exit it had never been told
        about.

        Stripping `_`-prefixed keys is right - they are notes to a human and
        should not spend tokens. The mistake was that one of them had stopped
        being a note and become a contract. So it is rendered explicitly,
        here, as instructions rather than as JSON.

    Derived entirely from the inventory, so it is correct for whatever
    application is configured. An inventory that declares nothing produces an
    empty block and the prompt is unchanged.
    """
    try:
        from validators.method_resolution_validator import (
            _load_configured_inventory,
        )
        root = Path(project_root or PROJECT_ROOT)
        inventory = _load_configured_inventory(root) or {}
    except Exception:                                     # noqa: BLE001
        return ""

    block = inventory.get("_starting_state") or {}
    fixtures = [f for f in (block.get("fresh_identity_fixtures") or []) if f]
    calls = [c for c in (block.get("establishing_calls") or []) if c]
    if not fixtures and not calls:
        return ""

    pages = inventory.get("pages") or {}
    persistent = {
        name: page.get("page_object_class") or ""
        for name, page in pages.items()
        if isinstance(page, dict) and page.get("persistent_state")
    }
    if not persistent:
        return ""

    lines = [
        "The pages below hold state the application KEEPS against the "
        "signed-in user. A scenario cannot assert an absolute state on one "
        "of them unless it OWNS that state first, and these are the ONLY "
        "ways this application can establish it.",
        "",
    ]
    for name, cls in sorted(persistent.items()):
        lines.append(f"- inventory page `{name}` -> `{cls or '<its page object>'}`")
    lines.append("")

    if calls:
        chosen = sorted(calls)[0]
        lines += [
            f"CLEARING CALL - required name: `{chosen}()`"
            + (f"  (accepted alternatives: {', '.join(sorted(calls))})"
               if len(calls) > 1 else ""),
            "",
            "When you generate the page object for a page listed above, give "
            "it this method, with this exact name. Write it even if the "
            "current story never calls it: the name is fixed by the "
            "inventory, a later repair CANNOT add it (a repair regenerates "
            "the feature and the step definitions, never the page object), "
            "and every persistent-state error message tells the reader to "
            "call it. A page object without it makes that advice a lie.",
            "",
            "    def " + chosen + "(self) -> None:",
            '        """Remove every entry, leaving the collection genuinely empty.',
            "",
            "        Bind this to a Given. After it, an ABSOLUTE assertion is",
            "        honest, because the scenario put the state there itself.",
            '        """',
            "        # re-read after each removal: the list re-renders",
            "",
            "Then a scenario may own its state:",
            "",
            "    Given <the collection> is empty        # in the .feature",
            "    <page>." + chosen + "()                # in the step definition",
            "",
        ]
    if fixtures:
        lines += [
            "FRESH IDENTITY - fixtures: "
            + ", ".join(f"`{f}`" for f in sorted(fixtures)),
            "A step that requests one of these fixtures establishes a "
            "genuinely new account, so its state starts empty.",
            "",
        ]
    if not fixtures:
        lines += [
            "There is NO fresh-identity fixture in this application. Do not "
            "write a step that claims to register a new account - the "
            "inventory cannot express it, and half a registration flow fails "
            "at run time.",
            "",
        ]
    return "\n".join(lines).rstrip()


def _build_readable_values_block() -> str:
    """What this application can actually SHOW, for the feature-file stage.

    A Gherkin sentence naming a value is a promise that something can read it.
    The feature file is written FIRST, so it is the only stage that can
    decide not to promise something - and until now it was never told what
    the inventory holds.

    A run promised "with quantity N" for a page whose inventory had no
    quantity element. Nothing downstream could satisfy it: the page object
    had no legal reader, so it invented a selector and was rejected, dropped
    the method, and the step definition calling it broke. Four repair
    attempts oscillated between the two files and the story was abandoned.

    Every later stage inherits the feature's promises and none of them can
    withdraw one. This is where a promise has to be affordable.
    """
    try:
        # Imported here, as elsewhere in this module: the validator owns
        # inventory loading, and a module-level import would make the
        # agent depend on it at import time for one optional block.
        from validators.method_resolution_validator import (
            _load_configured_inventory,
        )
        inventory = _load_configured_inventory(PROJECT_ROOT) or {}
    except Exception:                                     # noqa: BLE001
        return ""

    pages = inventory.get("pages") or {}
    if not pages:
        return ""

    lines = [
        "",
        "## What this application can be asked to SHOW",
        "",
        "Every value a scenario names has to be readable from one of these",
        "elements. Nothing downstream can add one: the page objects may only",
        "use these keys, and the step definitions may only call what the page",
        "objects provide. A sentence naming something absent from this list",
        "cannot be satisfied by anyone, and the story fails.",
        "",
    ]
    for name, entry in sorted(pages.items()):
        if not isinstance(entry, dict):
            continue
        keys = sorted((entry.get("elements") or {}).keys())
        if not keys:
            continue
        lines.append(f"  {name}: {', '.join(keys)}")
    lines += [
        "",
        "If a scenario needs something not listed, say so in `notes` and write",
        "the scenario around what IS listed. Do not promise it and leave the",
        "rest of the pipeline to discover there is no way to keep the promise.",
        "",
    ]
    return "\n".join(lines)


def _build_promised_values_block(file_plan, already_generated) -> str:
    """The values this batch's feature sentences NAME, for the page objects.

    A Gherkin sentence like `... with quantity {n}` is a promise that the test
    checks a quantity. Something has to be able to READ one, and the only file
    that can offer it is a page object - written after the feature and before
    the step definitions that will need it.

    Returns "" when there is no feature file in the batch, which is the normal
    case for a story extending existing coverage.
    """
    feature = next(
        (f for f in (already_generated or [])
         if (getattr(f, "file_path", "") or "").endswith(".feature")),
        None,
    )
    if feature is None:
        return ""

    try:
        from validators.gherkin_analyzer import _extract_feature_steps
        steps = _extract_feature_steps(getattr(feature, "content", "") or "")
    except Exception:                                     # noqa: BLE001
        return ""

    named: list = []
    for _keyword, phrase in steps:
        for placeholder in re.findall(r"[<{]([\w ]+)[>}]", phrase):
            if placeholder not in named:
                named.append(placeholder)
        for quoted in re.findall(r'"([^"]{1,40})"', phrase):
            label = quoted.strip()
            if label and label not in named:
                named.append(label)

    lines = [
        "",
        "## What the feature file in this batch promises",
        "",
        "These scenarios are already written and are AUTHORITATIVE. The step",
        "definitions come after you and can only call methods you provide -",
        "they cannot add one, and they cannot reword a sentence.",
        "",
    ]
    for _keyword, phrase in steps:
        lines.append(f"  - {phrase}")
    if named:
        lines += [
            "",
            "Values these sentences name: " + ", ".join(repr(n) for n in named[:20]),
        ]
    lines += [
        "",
        "For every value a sentence names, one of this batch's page objects",
        "must expose a way to READ it. A sentence promising a quantity needs a",
        "quantity reader; a sentence promising a count needs a count reader.",
        "Leave one out and the step definition has nothing legal to call.",
        "",
    ]
    return "\n".join(lines)


def _build_base_page_helpers_block(project_root=None) -> str:
    """List BasePage's public method signatures for the Stage-2 prompt.

    Why this exists:
        Page objects inherit from BasePage, which carries ~70 helpers covering
        every control type (dropdowns, checkboxes, uploads, hover menus,
        drag-and-drop, tables, dialogs, frames). The prompt tells the LLM to
        PREFER these helpers, but without the list it cannot know what exists
        and falls back to raw Playwright — so the helpers go unused and each
        page object reinvents them slightly differently.

        Signatures only (never bodies): enough to call correctly, cheap in
        tokens, and it cannot drift because it is read from the real file.

    Returns "" when BasePage cannot be read, so the prompt degrades to its
    previous behaviour rather than failing.
    """
    import ast as _ast
    from pathlib import Path as _Path

    root = _Path(project_root) if project_root else PROJECT_ROOT
    base_path = root / "pages" / "base_page.py"
    try:
        tree = _ast.parse(base_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return ""

    class_node = next(
        (n for n in tree.body
         if isinstance(n, _ast.ClassDef) and n.name == "BasePage"), None)
    if class_node is None:
        return ""

    lines: list[str] = []
    for node in class_node.body:
        if not isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
            continue
        if node.name.startswith("_"):
            continue                      # private/internal helpers
        try:
            sig = _ast.unparse(node.args)
        except Exception:
            continue
        sig = sig.replace("self, ", "").replace("self", "").strip()
        returns = ""
        if node.returns is not None:
            try:
                returns = f" -> {_ast.unparse(node.returns)}"
            except Exception:
                returns = ""
        doc = (_ast.get_docstring(node) or "").strip().split("\n")[0]
        entry = f"  self.{node.name}({sig}){returns}"
        lines.append(f"{entry}  # {doc}" if doc else entry)

    if not lines:
        return ""

    return (
        "## Inherited BasePage helpers (call these, do NOT reimplement)\n\n"
        "Every page object inherits these. PREFER them over raw `self.page.*`\n"
        "calls — they handle waits, iframes and DOM quirks consistently.\n"
        "Locators may use the ' >>> ' iframe chain, e.g.\n"
        "'iframe#pay >>> [data-test=card]'.\n\n"
        "```python\n" + "\n".join(lines) + "\n```\n\n"
        "If you need a GENERIC helper that is not listed here, do NOT add it to\n"
        "BasePage yourself (it is a reserved, human-owned file) and do NOT\n"
        "silently write raw Playwright for it. Implement it as a method on the\n"
        "page object you are writing, and record it in your `notes` field as:\n"
        "'BASEPAGE-REQUEST: <name>(<args>) - <one-line purpose>' so a human can\n"
        "promote it into BasePage for future runs.\n"
    )


def _existing_page_objects_on_main(gh, plan_paths: set[str],
                                   branch: str | None = None) -> list:
    """Page objects already committed, as pseudo-GeneratedFile records.

    Why this exists:
        `_build_sibling_page_object_context` only ever saw files generated in
        the SAME run, so a story that reuses a page object from an earlier
        story got no ground truth about its methods and the model invented
        names. That is the gap `key_methods` was filling by hand - a
        specification written before the code existed, which then had to be
        kept in step with it.

        The page object on disk IS the contract. Reading it removes the
        duplicate source of truth: fix the code and the constraint follows.

    Fails soft in every direction. A missing file, an unreadable repo, an
    unparseable module - each yields nothing rather than raising, because a
    thinner prompt is a far better outcome than a failed story.
    """
    # Read the STORY'S OWN BRANCH first where one exists, falling back to main.
    # A re-run - a fix pushed onto an open PR, or `ai-update` on a story already
    # coded - must see the methods that run wrote, not the older ones on main,
    # or it renames its own work. Cross-branch redundancy is a different problem
    # and is caught by validate_no_duplicate_page_object_methods at the gate.
    out = []
    branches = [b for b in (branch, "main") if b]
    paths, source = [], None
    for candidate in branches:
        try:
            found = gh.list_files_in_directory("pages", branch=candidate)
        except Exception:                                 # noqa: BLE001
            continue
        if found:
            paths, source = found, candidate
            break
    if not paths:
        logger.debug("Could not list pages/ on %s; no existing-page context.",
                     " or ".join(branches))
        return out

    for path in paths or []:
        if not path.endswith("_page.py") or path.endswith("base_page.py"):
            continue
        if path in plan_paths:
            continue        # being written this run - the batch copy wins
        try:
            content = gh.get_file_content(path, branch=source)
        except Exception:                                 # noqa: BLE001
            # Present in the listing but unreadable on this branch - fall back
            # to main rather than losing the file's context entirely.
            try:
                content = gh.get_file_content(path, branch="main")
            except Exception:                             # noqa: BLE001
                continue
        if content:
            out.append(SimpleNamespace(file_path=path, content=content))
    return out


def _build_sibling_page_object_context(
    already_generated: list[GeneratedFile],
) -> str:
    """Build a method-signature summary of page-object files already generated
    in this batch.

    Why this exists (Hotfix v5):
        When the LLM generates `inventory_page.py` and `test_logout.py` in
        the same Agent 2 run, it tends to "forget" the exact method names
        it used in the page object by the time it writes the step def.
        Result: AttributeError at test time (e.g., page object defines
        `click_logout()` but step def calls `click_logout_link()`).

        Injecting the actual method signatures from already-generated
        sibling files into the step-def prompt gives the LLM ground truth
        to copy from instead of guessing.

    This is a PREVENTION mechanism. The method_resolution_validator is
    the DETECTION safety net that catches what the prompt misses.

    Args:
        already_generated: GeneratedFile objects produced earlier in this
            batch. Page-object files are extracted; everything else
            ignored.

    Returns:
        A markdown block summarizing each page-object class's method
        signatures. Empty string if no page objects are in the batch yet.
    """
    import ast as _ast

    page_objects: list[tuple[str, str, list[str]]] = []
    for f in already_generated:
        path = getattr(f, "file_path", "")
        content = getattr(f, "content", "")
        if not path.startswith("pages/") or not path.endswith(".py"):
            continue
        if not content:
            continue
        try:
            tree = _ast.parse(content)
        except SyntaxError:
            continue
        for node in _ast.walk(tree):
            if not isinstance(node, _ast.ClassDef):
                continue
            method_sigs: list[str] = []
            for item in node.body:
                if isinstance(item, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                    if item.name.startswith("_"):
                        continue
                    # Build a simple signature string
                    args = [a.arg for a in item.args.args if a.arg != "self"]
                    sig = f"{item.name}({', '.join(args)})"
                    method_sigs.append(sig)
            if method_sigs:
                page_objects.append((node.name, path, method_sigs))

    if not page_objects:
        return ""

    lines = [
        "# Page Object Methods Available in This Batch (USE THESE EXACT NAMES)",
        "",
        "The following page-object classes were generated earlier in this run.",
        "If your step definitions call methods on these classes, you MUST use",
        "the EXACT method names listed below. Do not invent variations.",
        "",
    ]
    for class_name, path, sigs in page_objects:
        lines.append(f"## `{class_name}` (in `{path}`)")
        lines.append("```python")
        for sig in sigs:
            lines.append(f"    def {sig}: ...")
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


def _sort_files_for_generation(
    files_to_create: list,
) -> list:
    """Return file plans reordered so page objects come BEFORE step
    definitions.

    Why: when generating step-def files, the prompt can include the
    actual method signatures from page-object files already generated
    in this batch (see `_build_sibling_page_object_context`). For that
    to work, the page objects need to be generated first.

    Order within each group is preserved so that any plan-encoded
    intent (e.g., "feature first, then steps") still applies within
    its category.

    Order:
        1. feature files
        2. page_object files
        3. step_definitions files
        4. everything else
    """
    order = {"feature": 0, "page_object": 1, "step_definitions": 2, "other": 3}
    return sorted(
        files_to_create,
        key=lambda fp: (order.get(getattr(fp, "file_type", "other"), 3), 0),
    )


# ---------------------------------------------------------------------------
# Helpers for the self-correcting repair loop
# ---------------------------------------------------------------------------
# Maximum number of validator errors to show verbatim in the feedback prompt.
# Beyond this we summarize, because dumping 20+ verbose error messages into
# the prompt confuses smaller LLMs and they produce truncated output.
_MAX_FEEDBACK_ERRORS_VERBATIM = 8

# Below this length, regenerated content is treated as "the LLM gave up".
# Real step def files are at least 1500 chars; under 500 means the LLM
# returned a stub or fragment.
_DEGRADED_OUTPUT_CHAR_THRESHOLD = 500


# ─────────────────────────────────────────────────────────────────────────
# Backlog 2.3 — error-type-aware repair guidance
#
# The repair loop used to send one generic "add your missing @given/@when/@then"
# instruction for every failure. That's the right hint for a coverage miss and
# actively misleading for an import error or a hallucinated page method. Here we
# classify each validator error by its emitted prefix and give the LLM a hint
# targeted at that failure class, so a repair attempt fixes the actual problem
# instead of guessing. Purely additive and app-agnostic: it keys only off the
# validators' own error strings.
# ─────────────────────────────────────────────────────────────────────────

# Ordered (label, substring-that-identifies-the-class, targeted repair hint).
# First matching substring wins, so more specific strings come first.
_ERROR_TYPE_RULES: list[tuple[str, str, str]] = [
    (
        "selector_inventory",
        "selector inventory error",
        "- SELECTOR NOT FROM THE INVENTORY: a page object below either hard-codes "
        "a selector string or calls self.sel() with a key the inventory does not "
        "have. Page objects resolve EVERY selector through self.sel(\"<key>\"), and "
        "the key must already exist on that page in the app inventory shown above. "
        "If the element you need is genuinely absent from the inventory, do NOT "
        "invent a selector and do NOT invent a key: drop the behaviour and state "
        "the missing element in `notes` so a human can add it. A literal selector "
        "is rejected even when a comment calls it a temporary fallback.",
    ),
    (
        "duplicate_step",
        "duplicate step",
        "- DUPLICATE STEP DEFINITION: a step listed below is also defined in "
        "another step-def file. This is SAFE and expected — pytest-bdd steps are "
        "module-scoped fixtures, so each module resolves its own copy and they "
        "never collide. Do NOT delete your declaration. Declare every step your "
        "feature uses in YOUR file; never omit one assuming it is inherited.",
    ),
    (
        "import_resolution",
        "import resolution error",
        "- BROKEN IMPORT: an import below points at a module/name that does not "
        "exist. Import only from files that actually exist in this repo (page "
        "objects under `pages/`, helpers you can see). Fix the import path or "
        "remove the import — never invent a module.",
    ),
    (
        "method_resolution",
        "method resolution error",
        "- UNKNOWN PAGE METHOD: you called a method that does not exist on the "
        "page-object class. Call ONLY methods shown in the page inventory / the "
        "sibling page-object signatures above. If the behaviour is genuinely "
        "missing, add the method to the page object rather than calling a name "
        "that isn't there.",
    ),
    (
        "filename_consistency",
        "filename consistency error",
        "- FILENAME MISMATCH: the step-def file references a feature/module name "
        "that doesn't line up with its filename. Make the feature name and the "
        "`test_<flow>.py` filename consistent, per the naming convention.",
    ),
    (
        "gherkin_structure",
        "gherkin structure error",
        "- MALFORMED GHERKIN: a step in the feature file is not well-formed "
        "(keyword/indentation). Emit only valid `Given/When/Then/And/But` steps "
        "with correct indentation.",
    ),
    (
        "step_coverage",
        "step coverage error",
        "- MISSING STEP DEFINITION: every Gherkin step in the feature file needs "
        "a matching `@given/@when/@then` decorator (And/But inherit the previous "
        "keyword). Add a decorated function for each step listed below. Use "
        "`parsers.parse()` for parameterized steps and a plain string otherwise.",
    ),
]

# Fallback hint for any error whose class we don't recognise.
_ERROR_TYPE_FALLBACK = (
    "- Address the validator message below exactly as stated; output a "
    "complete, working file."
)


def _classify_error(error: str) -> str:
    """Return the error-class label for a single validator error string."""
    low = error.lower()
    for label, needle, _hint in _ERROR_TYPE_RULES:
        if needle in low:
            return label
    return "other"


def _build_error_type_guidance(errors: list[str]) -> str:
    """Build a de-duplicated, type-specific repair instruction block for exactly
    the error classes present in `errors` (backlog 2.3).

    Only the hints for classes that actually appear are included, in the fixed
    order of `_ERROR_TYPE_RULES`, so the LLM sees a focused directive per real
    failure rather than a generic catch-all. Returns the fallback hint if no
    class is recognised, and "" for an empty error list.
    """
    if not errors:
        return ""
    present = {_classify_error(e) for e in errors}
    hints = [hint for label, _needle, hint in _ERROR_TYPE_RULES if label in present]
    if not hints:
        return _ERROR_TYPE_FALLBACK
    if "other" in present:
        hints.append(_ERROR_TYPE_FALLBACK)
    return "\n".join(hints)


_MAX_FEEDBACK_CHARS = 900


def _trim_error(error: str) -> str:
    """Shorten one validator error WITHOUT destroying it.

    This replaced `error.split(":", 2)[-1].strip()[:150]`, which was written
    for a single error shape and silently mangled every other one. A selector
    error reads:

        Selector inventory error in 'pages/x_page.py': class XPage calls
        self.sel('a_key'), but 'a_key' is not an element on inventory page
        'x'. Available keys: <eleven names>. Do not invent the key - ...

    Two colons in, the split lands after "Available keys", so `[-1]` is the
    KEY LIST and nothing else. Truncated at 150 characters it arrived as a
    fragment beginning mid-sentence and ending mid-word, naming neither the
    file, nor the offending key, nor what was wrong with it. That fragment
    was the entire repair instruction. The model changed nothing, twice, and
    the run was abandoned as unrepairable.

    The repair message is the voice with the LAST WORD - it is what the model
    reads after a rejection - so it is the one place a summary must not lose
    the answer. Keep the head, not the tail; cut at a sentence boundary; and
    give it room. Nine hundred characters costs a rounding error in tokens
    against a failed story.
    """
    text = " ".join((error or "").split())
    if len(text) <= _MAX_FEEDBACK_CHARS:
        return text
    cut = text[:_MAX_FEEDBACK_CHARS]
    boundary = max(cut.rfind(". "), cut.rfind("; "))
    if boundary > _MAX_FEEDBACK_CHARS // 2:
        cut = cut[:boundary + 1]
    return cut.rstrip() + " [...]"


def _summarize_validator_feedback(errors: list[str]) -> str:
    """Compact validator errors into a prompt-friendly summary.

    Two regimes, and which one applies depends on how MANY errors there are.

    With a handful, the model gets each error WHOLE. With dozens - a step-def
    file that missed a whole feature - it gets the first few plus a count, so
    it sees the pattern instead of drowning in repetition.

    The phrase-only extraction used to apply to every count, and that lost a
    story. One coverage error became thirty-four characters:

        - When I am on the listing page

    No statement of what was wrong with it. The model had already written a
    decorator carrying that exact text - under the wrong KEYWORD - so it read
    the feedback, found the phrase in its own file, and correctly changed
    nothing. The repair loop then abandoned the story for "changing nothing".

    Everything the model needed was in the error it never saw: `has no
    matching @when() decorator`. Brevity is only worth buying when there is
    repetition to cut; with one error there is nothing to save and everything
    to lose.

    This is app-agnostic — operates only on the validator's own
    error strings, no project-specific knowledge.
    """
    # The phrase alone, for the many-errors regime where the pattern is the
    # message and each line is one more instance of it.
    step_phrase_pattern = re.compile(r"feature step `([^`]+)`")

    def _phrase_only(err: str) -> str:
        match = step_phrase_pattern.search(err)
        return match.group(1) if match else _trim_error(err)

    if len(errors) <= _MAX_FEEDBACK_ERRORS_VERBATIM:
        # Few enough to read. Send them whole - the keyword, the file and the
        # consequence are all in there, and any of them may be the fix.
        return "\n".join(f"  - {_trim_error(err)}" for err in errors)

    # MANY ERRORS: is it ONE problem repeated, or several different ones?
    #
    # The compaction above assumed the former - "the pattern is the message
    # and each line is one more instance of it" - and appended a tail naming
    # the single remedy that pattern needs. That holds only while every error
    # IS the same kind.
    #
    # A repair arrived with 18: eleven steps missing a decorator, and seven
    # step definitions that were defined and unused. Opposite remedies - add
    # these, delete those. All 18 were flattened to bare phrases, the first
    # eight sent, and the tail told the model that every error meant a
    # decorator was MISSING and it should write more. None of the seven
    # "delete this" errors reached it at all. So it added decorators, which
    # created more unused ones, and the next attempt looked the same. The
    # feedback was not merely lossy, it pointed the wrong way.
    #
    # So homogeneity is checked rather than assumed. One class keeps the old
    # behaviour exactly - it was right for what it was built for. Several
    # classes get whole errors dealt round-robin, so no class can be crowded
    # out by a noisier one, and a tail that counts each class instead of
    # prescribing one fix.
    by_class: dict = {}
    for err in errors:
        match = re.match(r"\s*([A-Za-z][A-Za-z \-]*?error)\s+in\s+'", err or "")
        key = match.group(1).lower() if match else "other"
        by_class.setdefault(key, []).append(err)

    if len(by_class) == 1:
        extracted: list[str] = [_phrase_only(err) for err in errors]
        head = "\n".join(
            f"  - {phrase}" for phrase in extracted[:_MAX_FEEDBACK_ERRORS_VERBATIM]
        )
        remaining = len(extracted) - _MAX_FEEDBACK_ERRORS_VERBATIM
        return (
            f"{head}\n"
            f"  ... and {remaining} more similar error(s). The pattern is the "
            f"same: each Gherkin step in the feature file needs a matching "
            f"decorator. Re-read the feature file and write a decorator for "
            f"every Given / When / Then / And / But line."
        )

    # Round-robin so every class is represented before any class gets a
    # second slot. A class that happens to be listed first cannot use up the
    # budget and silence the others.
    picked: list = []
    shown: dict = {key: 0 for key in by_class}
    while len(picked) < _MAX_FEEDBACK_ERRORS_VERBATIM:
        progressed = False
        for key, group in by_class.items():
            if shown[key] < len(group) and len(picked) < _MAX_FEEDBACK_ERRORS_VERBATIM:
                picked.append(group[shown[key]])
                shown[key] += 1
                progressed = True
        if not progressed:
            break

    head = "\n".join(f"  - {_trim_error(err)}" for err in picked)
    hidden = [
        f"{len(group) - shown[key]} more {key}"
        for key, group in by_class.items() if len(group) - shown[key] > 0
    ]
    tail = (
        f"\n  ... and {', '.join(hidden)}." if hidden else ""
    )
    return (
        f"{head}{tail}\n"
        f"  These are {len(by_class)} DIFFERENT kinds of problem and their "
        f"fixes are different - one may ask you to add something and another "
        f"to remove something. Read each line above and satisfy every kind, "
        f"not only the first. Fixing one kind while ignoring another leaves "
        f"the file failing on the next attempt."
    )


def _looks_like_useful_python(content: str) -> bool:
    """Quick check: does this look like real, parseable Python code?

    Returns False if content is too short, doesn't have any decorators
    suggesting it's a step def, or fails to parse at all. Used to decide
    whether to show a previous attempt to the LLM (broken prior attempts
    confuse it more than they help).
    """
    if not content or len(content) < _DEGRADED_OUTPUT_CHAR_THRESHOLD:
        return False
    if "@given" not in content and "@when" not in content and "@then" not in content:
        # Probably not a step def file at all — could be a page object,
        # which we don't want to gate on this. Just check it parses.
        pass
    try:
        ast.parse(content)
    except SyntaxError:
        return False
    return True


def _content_is_wellformed(content: str, file_path: str = "") -> bool:
    """Is this content valid FOR ITS OWN FORMAT?

    WHY THE PATH IS A PARAMETER NOW
        This was `ast.parse(content)` for everything the repair loop touched,
        which was correct for as long as everything it touched was Python.
        The moment a validator started routing errors to a `.feature` file,
        the loop regenerated Gherkin and asked Python's parser to approve it.
        No feature file has ever parsed as Python or ever will, so a perfectly
        good regeneration was declared degraded and the WHOLE repair loop
        aborted - on the first attempt, before the step definition it was
        supposed to fix downstream had a turn.

        The check had simply never seen a non-Python file, because the routing
        that produces one had itself never worked.

    Unknown extensions get the length check only. Guessing a grammar for a
    format this function does not know is how it went wrong the first time.
    """
    if not content or len(content) < _DEGRADED_OUTPUT_CHAR_THRESHOLD:
        return False

    suffix = (file_path or "").rsplit(".", 1)[-1].lower() if "." in (file_path or "") else ""

    if suffix == "feature":
        # Gherkin: a feature file that still declares a Feature and at least
        # one Scenario is structurally intact. Anything finer belongs to the
        # feature-structure validator, which runs on it anyway.
        text = content.lstrip()
        return "Feature:" in text and ("Scenario:" in text
                                       or "Scenario Outline:" in text)

    if suffix in {"py", ""}:
        try:
            ast.parse(content)
        except SyntaxError:
            return False
        return True

    return True


def _is_degraded_regeneration(new_content: str, prior_content: str,
                              file_path: str = "") -> bool:
    """Detect if a regeneration produced clearly worse output than before.

    Signals of degradation:
      - New content is malformed FOR ITS OWN FORMAT (LLM gave up mid-output)
      - New content is dramatically smaller than prior (truncated stub)

    Used to abort the repair loop early instead of compounding garbage
    on garbage. App-agnostic — looks only at the output itself.
    """
    if not new_content or len(new_content) < _DEGRADED_OUTPUT_CHAR_THRESHOLD:
        return True

    if not _content_is_wellformed(new_content, file_path):
        return True

    # If new content is less than 30% the size of the prior real attempt,
    # that's a strong signal the LLM is producing fragments
    if (
        prior_content
        and _content_is_wellformed(prior_content, file_path)
        and len(new_content) < 0.3 * len(prior_content)
    ):
        return True

    return False


# ---------------------------------------------------------------------------
# STAGE 1: Build the plan
# ---------------------------------------------------------------------------
def build_plan(
    llm: LLMClient,
    test_cases: list[dict],
    references: dict,
    page_inventory: str,
    ctx: AppContext,
) -> CodePlan:
    """Stage 1: Get a structured plan describing what files to create. NO code yet."""
    prompt_template = load_prompt("agent2_coder_plan.md")
    user_prompt = (
        prompt_template
        .replace("{app_name}", ctx.name)
        .replace("{reserved_paths_block}", _build_reserved_paths_block(ctx))
        .replace("{extendable_paths_block}", _build_extendable_paths_block(ctx))
        .replace("{reference_feature_path}", ctx.reference_feature)
        .replace("{reference_step_def_path}", ctx.reference_step_def)
        .replace("{reference_page_object_path}", ctx.reference_page_object)
        .replace("{reference_feature_content}", references["feature"])
        .replace("{reference_step_def_content}", references["step_def"])
        .replace("{reference_page_object_content}", references["page_object"])
        .replace("{page_inventory_json}", page_inventory)
        .replace("{test_cases_text}", format_test_cases_for_prompt(test_cases))
    )

    prompt_chars = len(user_prompt)
    logger.info(
        f"Stage 1 (plan) prompt size: {prompt_chars:,} chars "
        f"(~{prompt_chars // 4:,} tokens)"
    )

    plan: CodePlan = llm.invoke_structured(
        system_prompt="You are a Senior Test Automation Engineer (SDET).",
        user_prompt=user_prompt,
        output_schema=CodePlan,
    )

    logger.info(f"Stage 1 complete: {len(plan.files_to_create)} files planned")
    for fp in plan.files_to_create:
        logger.info(f"  - {fp.file_path} [{fp.file_type}] -- {fp.purpose}")

    # Defensive guard: enforce the two-tier reserved/extendable policy
    validate_paths_against_policy(plan, ctx)
    return plan


# ---------------------------------------------------------------------------
# STAGE 2: Generate each file's content
# ---------------------------------------------------------------------------

# ─────────────────────────────────────────────────────────────────────────────
# Prompt caching for Stage 2
# ─────────────────────────────────────────────────────────────────────────────
#
# generate_file_content() is the hot path: once per generated file, plus once
# per repair attempt. Every one of those calls resends the same instruction
# text, which is ~93% of the template. Splitting it into a cached system
# prefix turns those repeats into cache reads.
#
# The split is declared in the prompt itself, not here, so an editor can move
# the boundary without touching Python.

_CACHE_MARKER = "<!-- ===== CACHE BREAKPOINT: everything below is static ===== -->"

# Newline used when assembling prompt blocks in this module.
NL_JOIN = "\n"

# Providers will not cache a prefix below roughly 1,024 tokens. Caching a
# shorter span is worse than not caching: the write premium is charged and no
# read ever hits. ~4 chars/token, with headroom.
_MIN_CACHEABLE_CHARS = 4500

# Every placeholder generate_file_content substitutes. None may appear below
# the marker: a substituted value there would change the cached prefix on
# every call, so each call would pay the cache-WRITE premium and no read would
# ever hit - strictly worse than not caching. Checked at runtime and by a test.
_SUBSTITUTED_PLACEHOLDERS = (
    "{app_name}", "{file_path}", "{file_type}", "{file_purpose}",
    "{feature_name}", "{existing_file_block}", "{validator_feedback_block}",
    "{sibling_page_objects_block}", "{base_page_helpers_block}",
    "{authoritative_steps_block}",
    "{reference_feature_path}", "{reference_step_def_path}",
    "{reference_page_object_path}", "{reference_feature_content}",
    "{reference_step_def_content}", "{reference_page_object_content}",
    "{page_inventory_json}", "{test_cases_text}",
    "{starting_state_block}",
)

_GENERATE_SYSTEM_ROLE = (
    "You are a Senior Test Automation Engineer (SDET). "
    "Produce complete, working code."
)


def _split_prompt_for_cache(template: str) -> tuple:
    """Split the generate template into (variable_part, static_part).

    Degrades to (template, "") - the exact pre-caching behaviour - when the
    marker is missing or when a substituted placeholder has leaked below it.
    Caching is an optimisation; it must never be why a run fails.
    """
    if _CACHE_MARKER not in template:
        return template, ""
    variable_part, static_part = template.split(_CACHE_MARKER, 1)
    if len(static_part) < _MIN_CACHEABLE_CHARS:
        logger.warning(
            "Prompt cache disabled: only %d chars below the cache marker, "
            "under the ~%d providers require to cache a prefix at all. "
            "A shorter prefix pays the cache-WRITE premium and never reads "
            "back. Move the marker up.",
            len(static_part), _MIN_CACHEABLE_CHARS,
        )
        return template, ""
    leaked = [p for p in _SUBSTITUTED_PLACEHOLDERS if p in static_part]
    if leaked:
        logger.warning(
            "Prompt cache disabled: %s found BELOW the cache marker in "
            "agent2_coder_generate.md. A substituted value there changes the "
            "cached prefix every call, which costs more than no caching. "
            "Move it above the marker.",
            ", ".join(leaked),
        )
        return template, ""
    return variable_part, static_part



def _build_authoritative_steps_block(file_plan, already_generated) -> str:
    """Authoritative step list for a step-def file, from the batch's feature.

    WHY THIS EXISTS:
        The feature file and its step-def file are generated in SEPARATE LLM
        calls, and the step-def call previously received only the raw test
        cases - not the feature file generated moments earlier. The model
        re-derived every Gherkin phrase independently, and each wording
        difference between the two derivations became a coverage error plus
        an unused-step error. Observed live: 25-27 validator errors on the
        FIRST attempt, all of one class, before any repair had run.

        This mirrors Hotfix v5, which injects sibling page-object method
        signatures for exactly the same reason (cross-file naming drift).

    THE GUARANTEE:
        Steps are extracted with _extract_feature_steps - the SAME function
        validate_step_definitions_complete uses. What the model is told to
        implement and what the validator will demand are therefore the same
        set by construction, not by hope.

    Pairing: features/X.feature for tests/step_defs/test_X.py, matching the
    validators' stem convention. Fallback: if the batch generated exactly one
    feature file, it is the pair regardless of stem. Zero features, or
    several with no stem match, returns '' - guessing would inject the wrong
    contract, which is worse than none.
    """
    if getattr(file_plan, "file_type", "") != "step_definitions":
        return ""
    features = [
        f for f in (already_generated or [])
        if f.file_path.endswith(".feature")
    ]
    if not features:
        return ""
    stem = Path(file_plan.file_path).stem
    want = stem[5:] if stem.startswith("test_") else stem
    paired = [f for f in features if Path(f.file_path).stem == want]
    if not paired and len(features) == 1:
        paired = features
    if len(paired) != 1:
        return ""
    feature = paired[0]
    steps = _extract_feature_steps(feature.content)
    if not steps:
        return ""
    # De-duplicate on (KEYWORD, phrase), not phrase alone.
    #
    # Keying on the phrase dropped the second keyword silently. A feature
    # using one phrase as both a Given and a When produced a list containing
    # only the first, and this block tells the model the list is EXACTLY the
    # steps and that it must not write decorators for anything absent from
    # it. So the model was forbidden from writing the very step the coverage
    # validator then demanded, and four repair attempts could not resolve a
    # contradiction between the instruction and the gate.
    #
    # The comment it replaces - "one decorator serves every occurrence" - is
    # true of repeated occurrences under the SAME keyword and false across
    # keywords: pytest-bdd matches on keyword and text together, so a @given
    # does not satisfy a When step.
    #
    # The same mistake was fixed in the generation prompt's own final
    # checklist. This block is the stronger of the two, because it forbids
    # adding what it omits.
    seen: set = set()
    lines: list = []
    for keyword, phrase in steps:
        key = phrase.strip()
        if not key or (keyword, key) in seen:
            continue                # same keyword AND text: one decorator serves both
        seen.add((keyword, key))
        lines.append(f"  {len(seen)}. [{keyword}] {phrase}")
    if not lines:
        return ""
    return NL_JOIN.join([
        "## AUTHORITATIVE STEP LIST (from the feature file in this batch)",
        "",
        f"`{feature.file_path}` was generated moments ago and contains EXACTLY",
        "these unique steps:",
        "",
        *lines,
        "",
        "HARD REQUIREMENTS for this step-definitions file:",
        "1. Write EXACTLY ONE decorator for each listed [KEYWORD] + phrase",
        "   PAIR. A phrase listed under two keywords needs BOTH decorators -",
        "   stack them on one function:",
        "",
        "       @given(\"...\")",
        "       @when(\"...\")",
        "       def step(...):",
        "",
        "   That is correct pytest-bdd and both scenarios pass. Copy the",
        "   phrase VERBATIM, or use a parsers.parse/parsers.re pattern that",
        "   matches it exactly (for steps containing quoted values).",
        "2. Do NOT invent decorators for phrases that are not in this list.",
        "3. Do NOT rephrase, reorder words, add or drop articles, or change",
        "   tense. The list above is the contract the validators will check",
        "   this file against - any deviation is a guaranteed validation",
        "   failure.",
    ])

def generate_file_content(
    llm: LLMClient,
    file_plan,
    plan: CodePlan,
    test_cases: list[dict],
    references: dict,
    page_inventory: str,
    ctx: AppContext,
    validator_feedback: list[str] | None = None,
    previous_attempt: str | None = None,
    already_generated: list[GeneratedFile] | None = None,
    existing_page_objects: list | None = None,
) -> str:
    """Stage 2: For ONE file in the plan, get its full content as raw text.

    For files marked as extending an existing path (is_new_file=False AND
    in extendable_paths), the current file content is injected into the
    prompt under a dedicated section so the LLM preserves existing methods.

    For step-definitions files, when `already_generated` contains page-
    object files from earlier in this batch, their method signatures are
    injected so the LLM uses the exact method names (preventing the
    cross-file naming mismatches that v5 was created to address).

    Repair mode (when validator_feedback is provided):
        After a validator finds problems, this function can be called again
        with the validator's error messages and the previous attempt's
        content. The prompt then includes a "Validator Feedback" section
        telling the LLM exactly what to fix. This is app-agnostic — the
        feedback strings come from the validator, which works on any
        feature/step pair.
    """
    related_test_cases = [
        tc for tc in test_cases if tc["key"] in file_plan.related_test_cases
    ]
    if not related_test_cases:
        related_test_cases = test_cases

    # If this file is being EXTENDED (not created fresh), give the LLM
    # the current content so it doesn't accidentally remove existing methods.
    extendable = ctx.extendable_paths_normalized()
    is_extending_existing = (
        not file_plan.is_new_file
        and _normalize_path(file_plan.file_path) in extendable
    )
    if is_extending_existing:
        existing_content = _read_extendable_file_content(file_plan.file_path)
        existing_block = (
            f"# EXTENDING EXISTING FILE — preserve all methods below\n\n"
            f"You are MODIFYING an existing file. The current content is shown\n"
            f"below. You MUST keep every existing method and its signature\n"
            f"intact. ADD new methods alongside them. Do NOT remove or rename\n"
            f"any existing code.\n\n"
            f"## Current content of `{file_plan.file_path}`:\n"
            f"```python\n{existing_content}\n```\n"
        )
        logger.info(
            f"Stage 2: extending existing file '{file_plan.file_path}' — "
            f"injecting {len(existing_content)} chars of current content."
        )
    else:
        existing_block = ""

    # If this is a REPAIR call, inject validator feedback so the LLM knows
    # exactly what to fix. The feedback strings are produced by the validator
    # and reference specific Gherkin steps that need decorators.
    feedback_block = ""
    if validator_feedback:
        feedback_summary = _summarize_validator_feedback(validator_feedback)

        # Only show previous attempt if it looks like real code. A tiny or
        # syntactically-broken previous attempt only confuses the LLM further;
        # better to ask for a fresh generation guided by the feedback alone.
        prev_attempt_block = ""
        if previous_attempt and _looks_like_useful_python(previous_attempt):
            prev_attempt_block = (
                f"\n\n## Your previous attempt (which had the issues above):\n"
                f"```\n{previous_attempt}\n```\n"
                f"\nProduce a CORRECTED version of this file. Keep what was "
                f"right; fix what the validator flagged."
            )

        # Backlog 2.3 — targeted guidance for the exact failure class(es) the
        # validators flagged, instead of one generic step-coverage instruction.
        type_guidance = _build_error_type_guidance(validator_feedback)

        feedback_block = (
            f"\n\n# CRITICAL: Fix these validation issues\n\n"
            f"Your previous attempt was rejected. Issues:\n\n"
            f"{feedback_summary}\n\n"
            f"HOW TO FIX (targeted to what actually failed):\n"
            f"{type_guidance}\n"
            f"- Output a COMPLETE, working file — not a fragment\n"
            f"{prev_attempt_block}\n"
        )
        logger.info(
            f"  Repair mode: {len(validator_feedback)} validator error(s) "
            f"summarized into {len(feedback_summary)} chars of feedback for "
            f"'{file_plan.file_path}'."
        )

    # Build the sibling page-object methods block (Hotfix v5 prevention).
    # Only relevant for step-definitions files — feature files and page
    # objects don't need it.
    # BasePage helper signatures — injected ONLY for page objects, which are
    # the only files that call them. Step defs must go through page-object
    # METHODS (the POM boundary), so sending them this list would be both
    # wasted tokens and a nudge toward breaking that rule.
    base_helpers_block = ""
    if file_plan.file_type == "feature":
        # The only stage that can decline to promise something.
        base_helpers_block = _build_readable_values_block()
        if base_helpers_block:
            logger.info(
                "Stage 2: injecting the inventory's readable elements "
                "into the feature prompt so a scenario cannot promise "
                "a value nothing can show."
            )
    if file_plan.file_type == "page_object":
        base_helpers_block = _build_base_page_helpers_block()
        # The feature file is generated BEFORE page objects, and step
        # definitions AFTER them. So this is the only stage that can
        # see what the sentences promise and still decide what the
        # page will be able to show.
        #
        # Without it, a sentence naming a value no page object exposes
        # leaves the step-def stage with no legal move: it cannot add a
        # method (page objects are already written) and it cannot
        # reword the sentence (the feature is authoritative). A run
        # invented the reader it needed, was told it did not exist, and
        # then wrapped the call in a tautology to get past the gate.
        promised_block = _build_promised_values_block(file_plan, already_generated)
        if promised_block:
            base_helpers_block = base_helpers_block + promised_block
            logger.info(
                "Stage 2: injecting the feature's promised values into "
                "the page-object prompt so a reader exists for each."
            )
        if base_helpers_block:
            logger.info(
                "Stage 2: injecting %d BasePage helper signatures into "
                "page-object prompt.",
                base_helpers_block.count("\n  self."),
            )

    sibling_block = ""
    authoritative_steps_block = ""
    # Page objects ALREADY ON MAIN count as siblings too. Previously only files
    # generated in this same run were shown, so a story reusing a page object
    # from an earlier story saw nothing and the model invented method names -
    # the gap `key_methods` was filling by hand. `existing_page_objects` is
    # passed in by the caller; when it is absent (any unit test, any caller
    # that has no repo handle) behaviour is exactly as before.
    _siblings = list(already_generated or []) + list(existing_page_objects or [])
    if file_plan.file_type in ("step_definitions", "page_object") and _siblings:
        sibling_block = _build_sibling_page_object_context(_siblings)
    if file_plan.file_type == "step_definitions" and already_generated:
        authoritative_steps_block = _build_authoritative_steps_block(
            file_plan, already_generated)
        if authoritative_steps_block:
            logger.info(
                "Stage 2: injecting authoritative step list from the batch's "
                "feature file into the step-def prompt."
            )
        if sibling_block:
            logger.info(
                f"Stage 2: injecting method signatures from "
                f"{sum(1 for f in already_generated if f.file_path.startswith('pages/'))} "
                f"sibling page-object file(s) into step-def prompt."
            )

    prompt_template = load_prompt("agent2_coder_generate.md")
    variable_template, static_rules = _split_prompt_for_cache(prompt_template)
    user_prompt = (
        variable_template
        .replace("{app_name}", ctx.name)
        .replace("{file_path}", file_plan.file_path)
        .replace("{file_type}", file_plan.file_type)
        .replace("{file_purpose}", file_plan.purpose)
        .replace("{feature_name}", plan.feature_name)
        .replace("{existing_file_block}", existing_block)
        .replace("{validator_feedback_block}", feedback_block)
        .replace("{sibling_page_objects_block}", sibling_block)
        .replace("{authoritative_steps_block}", authoritative_steps_block)
        .replace("{base_page_helpers_block}", base_helpers_block)
        .replace("{starting_state_block}", _build_starting_state_block())
        .replace("{reference_feature_path}", ctx.reference_feature)
        .replace("{reference_step_def_path}", ctx.reference_step_def)
        .replace("{reference_page_object_path}", ctx.reference_page_object)
        .replace("{reference_feature_content}", references["feature"])
        .replace("{reference_step_def_content}", references["step_def"])
        .replace("{reference_page_object_content}", references["page_object"])
        .replace("{page_inventory_json}", page_inventory)
        .replace("{test_cases_text}", format_test_cases_for_prompt(related_test_cases))
    )

    logger.info(f"Stage 2: generating content for {file_plan.file_path}...")
    system_prompt = _GENERATE_SYSTEM_ROLE
    if static_rules:
        system_prompt = f"{_GENERATE_SYSTEM_ROLE}\n\n{static_rules}"
    response = llm.invoke_text(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        cache_prefix=bool(static_rules),
    )
    content = extract_code_from_response(response)
    logger.info(f"  Generated {len(content)} chars for {file_plan.file_path}")

    # Empty-output guard (Day 8 fix). Pro models can return HTTP 200 with
    # near-zero visible content when their thinking budget is exhausted on
    # complex prompts. Without this guard, Agent 2 logs "success", commits a
    # 1-char file, opens a PR, and only Agent 3 (or a human reviewer) catches
    # the empty file. We refuse to proceed: <30 chars cannot be a valid
    # feature, page object, or step-def file (the smallest valid feature is
    # roughly "Feature: x\nScenario: y\nGiven z\n" ~ 35 chars).
    MIN_CONTENT_CHARS = 30
    if len(content.strip()) < MIN_CONTENT_CHARS:
        # Diagnostic dump (Day 9): the llm_client diagnostic checks raw
        # response length, but extract_code_from_response can reduce a
        # long-but-empty response (e.g., preamble + empty fence) to 1
        # char. That bypasses the upstream diagnostic. Dump everything
        # we know HERE, where we definitely have the problem in hand.
        logger.error("─── EMPTY OUTPUT DIAGNOSTIC ───")
        logger.error("file_path=%s", file_plan.file_path)
        logger.error("raw response length: %d chars", len(response))
        # Show raw response in chunks so long preambles are visible. Cap
        # at 3000 chars total to keep logs readable.
        raw_for_log = response if len(response) <= 3000 else (
            response[:1500] + f"\n... [truncated {len(response) - 3000} chars] ...\n" + response[-1500:]
        )
        logger.error("raw response (repr):\n%r", raw_for_log)
        logger.error("post-extraction content (repr): %r", content)
        # Also count fences — empty fence pair is the most common shape
        fence_count = response.count("```")
        logger.error("triple-backtick count in raw response: %d (pairs of empty fences = bad)", fence_count)
        logger.error("─── END EMPTY OUTPUT DIAGNOSTIC ───")
        raise ValueError(
            f"LLM returned suspiciously short content for "
            f"'{file_plan.file_path}' ({len(content)} chars). This usually "
            f"means the model exhausted its output token budget on internal "
            f"reasoning ('thinking') before producing visible output. "
            f"For Pro models, ensure max_output_tokens is at least 32768 "
            f"(see _code_gen_max_output_tokens in llm_client.py). "
            f"See the EMPTY OUTPUT DIAGNOSTIC block above for the raw "
            f"response. Aborting before we commit an empty file."
        )
    return content


# ---------------------------------------------------------------------------
# Helpers for the run() workflow — extracted to keep run() readable
# ---------------------------------------------------------------------------
def _select_new_test_cases(
    test_cases: list[dict],
    is_regenerate: bool,
) -> tuple[list[dict], list[dict]]:
    """Filter out test cases already covered by existing scenarios.

    Returns (new_test_cases, skipped_test_cases). In regenerate mode, dedup
    is bypassed and all test cases are returned as new.
    """
    if is_regenerate:
        logger.info(
            f"Regeneration mode: bypassing dedup check. "
            f"All {len(test_cases)} test cases will be regenerated from scratch."
        )
        return test_cases, []

    inventory = scan_features_dir(FEATURES_DIR)
    new_cases, skipped = filter_duplicate_test_cases(test_cases, inventory)

    if skipped:
        logger.info(
            f"Dedup: {len(skipped)} of {len(test_cases)} test cases "
            f"already covered by existing scenarios. Skipping these."
        )
        for skip in skipped:
            tc = skip["test_case"]
            logger.info(
                f"  - {tc.get('key', '?')}: '{tc.get('summary', '?')}' "
                f"already covered by '{skip['matched_scenario']}' "
                f"in {skip['matched_file']}"
            )

    return new_cases, skipped


def _validate_generated_files(
    generated_files: list[GeneratedFile],
    story_id: str,
) -> None:
    """Run all final validators.

    Catches the failure modes Agent 2 has historically had:
      - PR #7: kebab-case feature filename vs snake_case feature_path() ref
      - PR #9: feature steps without matching @given/@when/@then decorators
      - SCRUM-13: imports referencing modules that don't exist

    Raises ValueError if any validator finds problems.

    NOTE: This is the FINAL validation, run after any retry attempts.
    By the time this raises, the LLM has already been given a chance
    to self-correct via _attempt_step_coverage_repair.
    """
    consistency_errors = validate_filename_consistency(generated_files)
    if consistency_errors:
        logger.error(
            f"Filename consistency check FAILED with "
            f"{len(consistency_errors)} error(s):"
        )
        for err in consistency_errors:
            logger.error(f"  - {err}")
        raise ValueError(
            f"Filename consistency validation failed for {story_id}: "
            f"{len(consistency_errors)} mismatch(es) between feature files "
            f"and step definitions. See logs for details."
        )

    structure_errors = validate_feature_file_structure(generated_files)
    if structure_errors:
        logger.error(
            f"Feature file structure check FAILED with "
            f"{len(structure_errors)} error(s):"
        )
        for err in structure_errors:
            logger.error(f"  - {err}")
        raise ValueError(
            f"Feature file structure validation failed for {story_id}: "
            f"{len(structure_errors)} step(s) appear outside any "
            f"Scenario/Background/Examples block. pytest-bdd would fail at "
            f"test collection time. See logs for details."
        )

    coverage_errors = validate_step_definitions_complete(generated_files)
    if coverage_errors:
        logger.error(
            f"Step definition coverage check FAILED with "
            f"{len(coverage_errors)} error(s) AFTER retry:"
        )
        for err in coverage_errors:
            logger.error(f"  - {err}")
        raise ValueError(
            f"Step definition coverage validation failed for {story_id}: "
            f"{len(coverage_errors)} feature step(s) without matching "
            f"@given/@when/@then decorator(s) — even after the LLM was "
            f"given the validator's feedback for self-correction. This "
            f"usually means the LLM model is too weak (try a more capable "
            f"model) or the feature file has unusually complex "
            f"steps. See logs for details."
        )

    duplicate_step_errors = validate_no_duplicate_step_definitions(
        generated_files, PROJECT_ROOT
    )
    if duplicate_step_errors:
        logger.error(
            f"Duplicate step-definition check FAILED with "
            f"{len(duplicate_step_errors)} error(s) AFTER retry:"
        )
        for err in duplicate_step_errors:
            logger.error(f"  - {err}")
        raise ValueError(
            f"Duplicate step-definition validation failed for {story_id}: "
            f"{len(duplicate_step_errors)} step(s) are declared in more than "
            f"one step-def file. NOTE (ADR-013): this path is unreachable — "
            f"cross-file duplication is safe in pytest-bdd. See logs."
        )

    import_errors = validate_imports_resolvable(generated_files, PROJECT_ROOT)
    if import_errors:
        logger.error(
            f"Import resolution check FAILED with "
            f"{len(import_errors)} error(s) AFTER retry:"
        )
        for err in import_errors:
            logger.error(f"  - {err}")
        raise ValueError(
            f"Import resolution validation failed for {story_id}: "
            f"{len(import_errors)} import(s) reference module(s) that don't "
            f"exist in the repo, in this generation batch, or in "
            f"requirements.txt — even after the LLM was given the "
            f"validator's feedback for self-correction. The LLM likely "
            f"hallucinated a page object class import. See logs for details."
        )

    method_errors = validate_method_resolution(generated_files, PROJECT_ROOT)
    if method_errors:
        logger.error(
            f"Method resolution check FAILED with "
            f"{len(method_errors)} error(s) AFTER retry:"
        )
        for err in method_errors:
            logger.error(f"  - {err}")
        raise ValueError(
            f"Method resolution validation failed for {story_id}: "
            f"{len(method_errors)} step-def method call(s) reference page-object "
            f"method(s) that don't exist on the corresponding class — even "
            f"after the LLM was given the validator's feedback for self-"
            f"correction. The LLM likely used inconsistent method names "
            f"between the page object and the step def file (e.g., defined "
            f"`click_logout()` in the page object but called "
            f"`click_logout_link()` in the step def). See logs for details."
        )

    selector_errors = validate_page_object_selectors(
        generated_files, PROJECT_ROOT
    )
    if selector_errors:
        logger.error(
            f"Page-object selector check FAILED with "
            f"{len(selector_errors)} error(s) AFTER retry:"
        )
        for err in selector_errors:
            logger.error(f"  - {err}")
        raise ValueError(
            f"Page-object selector validation failed for {story_id}: "
            f"{len(selector_errors)} selector(s) in the generated page "
            f"object(s) are hard-coded literals or reference an inventory key "
            f"that does not exist — even after the LLM was given the "
            f"validator's feedback. The app inventory is the single source of "
            f"truth for selectors; the same rule is enforced by "
            f"tests/unit/test_page_object_selectors.py, so shipping this "
            f"would fail Agent 4's unit gate on the story PR instead. If the "
            f"element is genuinely missing from the inventory, add it there "
            f"(and verify it with `python -m scripts.verify_locators`) rather "
            f"than letting a literal through. See logs for details."
        )

    # These two were previously wired only into the repair loop. That meant a
    # run could log "Final validator will raise", exhaust its retries, and
    # then open a PR carrying the very errors it had just reported - turning a
    # caught problem into a shipped one. A PR must never open with a known
    # collection-time failure.
    unused_step_errors = validate_no_unused_step_definitions(generated_files)
    if unused_step_errors:
        logger.error(
            f"Unused step-definition check FAILED with "
            f"{len(unused_step_errors)} error(s) AFTER retry:"
        )
        for err in unused_step_errors:
            logger.error(f"  - {err}")
        raise ValueError(
            f"Unused step-definition validation failed for {story_id}: "
            f"{len(unused_step_errors)} decorator(s) are defined but no "
            f"scenario uses them — even after the LLM was given the "
            f"validator's feedback. This usually means the LLM emitted two "
            f"phrasings of the same step and wired only one into the feature "
            f"file. See logs for details."
        )

    fixture_errors = validate_fixtures_exist(generated_files, PROJECT_ROOT)
    if fixture_errors:
        logger.error(
            f"Fixture resolution check FAILED with "
            f"{len(fixture_errors)} error(s) AFTER retry:"
        )
        for err in fixture_errors:
            logger.error(f"  - {err}")
        raise ValueError(
            f"Fixture resolution validation failed for {story_id}: "
            f"{len(fixture_errors)} step definition(s) request a fixture that "
            f"no conftest declares and no page object provides. pytest "
            f"resolves fixtures at collection time, so every scenario in the "
            f"file would error before running. If the fixture should come "
            f"from a page object, that page object must be in the plan; if it "
            f"needs custom setup, add it to conftest by hand. See logs."
        )



# ---------------------------------------------------------------------------
# Self-correcting retry loop (handles weak-model step coverage failures)
# ---------------------------------------------------------------------------
    # Everything the repair loop can find, the gate must be able to stop.
    #
    # Six checks lived only in _collect_repairable_errors: they were detected,
    # fed to the repair loop, and when four attempts failed the loop logged
    # "Final validator will raise" and returned the files anyway. Nothing
    # raised. The pull request opened with the defect the framework had already
    # named - a persistent-state assertion on a shared account, in the run that
    # exposed this.
    #
    # Reported LAST so the specific messages above keep their own wording and
    # their own remediation advice; this is the backstop for the rest.
    remaining = _collect_repairable_errors(generated_files)
    if remaining:
        logger.error(
            f"Final gate FAILED with {len(remaining)} unrepaired error(s):"
        )
        for err in remaining:
            logger.error(f"  - {err}")
        raise ValueError(
            f"Validation failed for {story_id}: {len(remaining)} error(s) "
            f"remain after the repair loop exhausted its attempts. These were "
            f"detected and the model was given the feedback; it could not "
            f"satisfy them. Shipping anyway would open a pull request "
            f"containing a defect this framework had already named. "
            f"See logs for each error and the file it belongs to."
        )

def _group_validator_errors_by_file(
    validator_errors: list[str],
) -> dict[str, list[str]]:
    """Group validator error messages by the file they refer to.

    Validator errors follow the convention: `<error type> in '<file_path>':`
    so we extract the file path with a single regex that matches any error
    prefix. This works for:
      - `Step coverage error in '...':` (coverage validator)
      - `Import resolution error in '...':` (import validator)
      - any future validators that follow the same convention

    The line-number segment is optional: the selector validator reports
    `... error in '<path>' line 125:` so it can point at the offending call,
    and without tolerating that the error matched nothing, was dropped here,
    and the file never got a repair attempt (SCRUM-103, 31 Jul 2026).

    Returns: {file_path: [error_messages_for_that_file]}
    """
    grouped: dict[str, list[str]] = {}
    # Match `<words> error in '<path>'[ line N]:` regardless of the emitter
    pattern = re.compile(r"error in '([^']+)'(?: line \d+)?:")
    for err in validator_errors:
        match = pattern.search(err)
        if not match:
            # Validator returned an error in an unexpected format — skip;
            # final validation will still raise it, just no targeted retry.
            continue
        path = match.group(1)
        grouped.setdefault(path, []).append(err)
    return grouped


# Backward-compat alias — older tests reference the old name
_group_coverage_errors_by_step_def = _group_validator_errors_by_file


def _rules_persisting(before, after) -> list:
    """Rule names that fired both before and after a repair attempt.

    Keyed on the RULE, not the message, because the message carries the step
    text and the step text is exactly what a stuck model changes. Every error
    this project raises opens with `<Rule name> error in '<path>'`, so the
    rule is the text before " error in ".
    """
    def rules(errors):
        found = set()
        for error in errors or ():
            head = str(error).split(" error in ", 1)[0].strip()
            if head and len(head) < 60:
                found.add(head)
        return found

    return sorted(rules(before) & rules(after))


def _not_converging_hint(persisting: list) -> str:
    """Say what a rule surviving several attempts usually means.

    A list of symptoms is what the gate already prints. What a reader needs
    is the reading: a rule that survives repeated rewording is one the
    generated code cannot satisfy, and that is nearly always because the TEST
    CASE asks for something this application cannot show. No amount of
    regeneration fixes that.
    """
    if not persisting:
        return ""
    return (
        f" {', '.join(persisting)} survived every attempt. A rule that "
        f"outlives repeated rewording is one the code cannot satisfy: usually "
        f"the test case asks for something this application cannot show - an "
        f"exact count on state the app keeps between runs, or a flow the "
        f"inventory does not describe. Regenerating will not fix it. Check the "
        f"test case against the inventory, and if it cannot be automated as "
        f"written, say so on the Jira issue rather than relabelling the step "
        f"until the gate stops noticing."
    )


def _collect_repairable_errors(generated_files: list[GeneratedFile]) -> list[str]:
    """Aggregate errors from all validators that the repair loop can act on.

    Currently combines:
      - Step-definition coverage validator (missing @given/@when/@then)
      - Import resolution validator (imports referencing non-existent modules)
      - Method resolution validator (calls to methods that don't exist on
        the page object class — catches cross-file naming inconsistency
        and hallucinated methods)

    All produce errors in the `<type> error in '<path>':` format so the
    repair loop's grouper can target the right file.

    Future validators can be plumbed here as long as they emit errors in
    the same format.
    """
    errors: list[str] = []
    # Page-object selector errors ARE repairable and were missing here.
    # They were enforced only by the final gate, so the model got four
    # attempts at whatever else was wrong and ZERO at the page object, then
    # the run died on feedback it had never been shown (SCRUM-103).
    errors.extend(validate_page_object_selectors(generated_files, PROJECT_ROOT))
    errors.extend(validate_row_scoped_selectors(generated_files, PROJECT_ROOT))
    errors.extend(validate_examples_hold_data_not_placeholders(generated_files))
    errors.extend(validate_fills_confirm_their_page(generated_files, PROJECT_ROOT))
    # Two stories editing one page object branch from main independently, so
    # neither sees the other's work and both may add their own name for one
    # behaviour. Git merges the additions cleanly when they land apart, and
    # nothing else notices.
    # Three rules about what a page-object METHOD DEFINITION may look like:
    # no two methods meaning the same thing, no bare verb, no question-shaped
    # method built on a non-waiting probe. One entry point, three prefixes -
    # the repair loop still routes each to the rule it broke.
    errors.extend(validate_page_object_methods(generated_files))
    # A readiness probe must hold in every state the page can be in. The
    # generator cannot know which element does; a human who has seen the page
    # in each state declares it, and this makes that declaration binding.
    errors.extend(validate_readiness_probe(generated_files, PROJECT_ROOT))
    errors.extend(validate_no_selectors_in_step_defs(generated_files))
    errors.extend(validate_persistent_state_assertions(generated_files, PROJECT_ROOT))
    errors.extend(validate_step_parameter_types(generated_files, PROJECT_ROOT))
    errors.extend(validate_persistent_pages_can_be_cleared(
        generated_files, PROJECT_ROOT))
    errors.extend(validate_readers_return_what_they_name(
        generated_files, PROJECT_ROOT))
    errors.extend(validate_confirm_arrival_targets_this_page(
        generated_files, PROJECT_ROOT))
    errors.extend(validate_step_claims_are_verified(generated_files, PROJECT_ROOT))
    errors.extend(validate_feature_file_structure(generated_files))
    # Coverage, unused decorators and the drift between them are one question
    # asked three ways, so they are combined where they live rather than here.
    # The pairing rule - a drifted pair suppresses both halves and speaks once
    # - moved into validate_step_coverage() verbatim; a test runs the old
    # composition and the new one against the same input and requires the same
    # output.
    errors.extend(validate_step_coverage(generated_files))
    errors.extend(validate_fixtures_exist(generated_files, PROJECT_ROOT))
    errors.extend(validate_imports_resolvable(generated_files, PROJECT_ROOT))
    errors.extend(validate_method_resolution(generated_files, PROJECT_ROOT))
    # Duplicate step-defs across files (SCRUM-54 lesson). repair_format=True so
    # the loop can target and regenerate the offending GENERATED file with the
    # feedback baked in, rather than only catching it at final validation.
    errors.extend(
        validate_no_duplicate_step_definitions(
            generated_files, PROJECT_ROOT, repair_format=True
        )
    )
    return errors


def _attempt_step_coverage_repair(
    generated_files: list[GeneratedFile],
    llm: LLMClient,
    plan: CodePlan,
    test_cases: list[dict],
    references: dict,
    page_inventory: str,
    ctx: AppContext,
    max_retries: int = 4,
) -> list[GeneratedFile]:
    """If validators find issues in the generated files, give the LLM up to
    `max_retries` chances to fix them with explicit feedback.

    Handles two failure modes today:
      - Missing step decorators (coverage validator)
      - Unresolvable imports (import validator)

    Both kinds of errors are app-agnostic: the validators work on any
    feature/step pair and any Python imports. The repair simply re-invokes
    Stage 2 for the broken file with a "Validator Feedback" section.

    Why retry instead of hard-fail:
        Weaker LLMs often slip up on complex validation constraints.
        Validators catch it, but the old behavior was to abort the whole
        run, wasting work already done on other files. Retrying ONLY the
        broken file is targeted, cheap, and usually succeeds.

    Cost: each retry = 1 LLM call per broken file. Capped at `max_retries`
    iterations. Worst case for a typical 1-broken-file run is 2 extra calls.
    """
    previous_errors: set[str] | None = None
    previous_count: int | None = None
    for attempt in range(1, max_retries + 1):
        all_errors = _collect_repairable_errors(generated_files)

        # NO-PROGRESS ABORT. A run on 31 Jul 2026 spent all four attempts on
        # one unused step definition, produced near-identical output each
        # time, fixed nothing and cost $1.74. If an attempt leaves the error
        # set exactly as it found it, the model is not converging and further
        # attempts only buy tokens. Stop and let the final gate report it.
        current = set(all_errors)
        if previous_errors is not None and current and current == previous_errors:
            logger.warning(
                "Repair attempt %d changed nothing — the same %d error(s) "
                "came back verbatim. Abandoning repair; the final validation "
                "gate will report them.", attempt - 1, len(current),
            )
            return generated_files
        # NOT-CONVERGING ABORT.
        #
        # The check above compares error STRINGS, so it only fires when the
        # model changes nothing at all. A run went 15 -> 8 -> 6 -> 7 errors
        # across four attempts and never tripped it, because each attempt
        # REWORDED the offending step:
        #
        #     there should be exactly one row for "<x>"
        #     the collection should contain exactly one row for "<x>"
        #     the collection should have exactly one row for "<x>"
        #
        # Six variations of one sentence, each a fresh string, each failing
        # the same rule. That is what a model does when it can neither
        # satisfy a rule nor decline: it renames the thing and hopes.
        #
        # A count that stops falling is the better signal - it does not care
        # how the wording moved.
        if previous_count is not None and len(current) >= previous_count:
            persisting = _rules_persisting(previous_errors, current)
            logger.warning(
                "Repair attempt %d did not reduce the error count (%d -> %d). "
                "The model is not converging: further attempts buy tokens, "
                "not fixes.%s Abandoning repair; the final validation gate "
                "will report what remains.",
                attempt - 1, previous_count, len(current),
                _not_converging_hint(persisting),
            )
            return generated_files

        previous_errors = current
        previous_count = len(current)

        if not all_errors:
            if attempt > 1:
                logger.info(
                    f"Validator repair succeeded after {attempt - 1} "
                    f"retry attempt(s). All issues resolved."
                )
            return generated_files

        grouped = _group_validator_errors_by_file(all_errors)
        if not grouped:
            # Errors couldn't be parsed — let final validation handle it
            logger.warning(
                f"Validators produced {len(all_errors)} error(s) but no "
                f"targetable file was identified. Skipping repair."
            )
            return generated_files

        logger.warning(
            f"Validators found {len(all_errors)} issue(s) across "
            f"{len(grouped)} file(s). "
            f"Attempting repair (attempt {attempt}/{max_retries})..."
        )

        for step_def_path, errors_for_this_file in grouped.items():
            # Find the corresponding GeneratedFile to repair
            target_idx = next(
                (i for i, gf in enumerate(generated_files)
                 if _normalize_path(gf.file_path) == _normalize_path(step_def_path)),
                None,
            )
            if target_idx is None:
                logger.warning(
                    f"Validator flagged '{step_def_path}' but it's not in "
                    f"the generated batch. Cannot repair."
                )
                continue

            # Find the matching FilePlan for prompt context
            target_plan = next(
                (fp for fp in plan.files_to_create
                 if _normalize_path(fp.file_path) == _normalize_path(step_def_path)),
                None,
            )
            if target_plan is None:
                logger.warning(
                    f"No FilePlan found for '{step_def_path}'. Cannot repair."
                )
                continue

            logger.info(
                f"  Repairing '{step_def_path}' with "
                f"{len(errors_for_this_file)} feedback item(s)..."
            )
            # Log every item, not just the count. Costs no tokens - this
            # goes to stdout, never into a prompt. Note the contrast with
            # the "summarized into N chars" line below: only the first
            # _MAX_FEEDBACK_ERRORS_VERBATIM reach the model, so seeing the
            # full list here is the only way to know what was collapsed.
            for feedback_item in errors_for_this_file:
                logger.info(f"    - {feedback_item}")
            try:
                prior_content = generated_files[target_idx].content
                # Pass siblings (excluding the one being repaired) so the
                # repair prompt also gets accurate method signatures.
                siblings_for_repair = [
                    f for i, f in enumerate(generated_files) if i != target_idx
                ]
                repaired_content = generate_file_content(
                    llm,
                    target_plan,
                    plan,
                    test_cases,
                    references,
                    page_inventory,
                    ctx,
                    validator_feedback=errors_for_this_file,
                    previous_attempt=prior_content,
                    already_generated=siblings_for_repair,
                )
                # If the LLM produced clearly-degraded output (truncated stub,
                # syntax errors, fraction of prior size), the prior attempt
                # is actually our best bet. Keep it and abort the repair loop
                # so we don't compound garbage on garbage.
                if _is_degraded_regeneration(
                        repaired_content, prior_content, step_def_path):
                    logger.error(
                        f"  Repair produced degraded output for "
                        f"'{step_def_path}' ({len(repaired_content)} chars vs "
                        f"prior {len(prior_content)} chars, syntax-valid="
                        f"{_content_is_wellformed(repaired_content, step_def_path)}). "
                        f"Aborting repair to avoid wasting more LLM calls. "
                        f"Final validator will raise on the prior attempt."
                    )
                    return generated_files
                generated_files[target_idx] = GeneratedFile(
                    file_path=generated_files[target_idx].file_path,
                    content=repaired_content,
                    is_new_file=generated_files[target_idx].is_new_file,
                    purpose=generated_files[target_idx].purpose,
                )
            except OutputTruncatedError:
                # A budget breach is not a repairable failure. Every further
                # attempt would truncate at the identical cap, so swallowing
                # this would burn the remaining retries and then report a
                # validator error that never mentions the real cause.
                raise
            except Exception as e:
                logger.error(
                    f"  Repair attempt for '{step_def_path}' failed: {e}. "
                    f"Will let final validation surface the issue."
                )

    # Hit max_retries without full success — final validator will raise.
    final_errors = _collect_repairable_errors(generated_files)
    if final_errors:
        logger.warning(
            f"Validator repair exhausted {max_retries} retry attempt(s); "
            f"{len(final_errors)} error(s) remain. Final validator will raise."
        )
    return generated_files


def _print_dry_run_preview(output: CodeGenerationOutput) -> None:
    """ASCII-safe preview of generated code (Windows cp1252 compatible)."""
    print("\n" + "=" * 60)
    print("DRY RUN -- Generated code preview")
    print("=" * 60)
    print(f"\n[Branch]    {output.branch_name}")
    print(f"[PR Title]  {output.pr_title}")
    print(f"[Feature]   {output.feature_name}")

    print(f"\n[PR Body]")
    print("-" * 60)
    print(output.pr_body.encode("ascii", "replace").decode("ascii"))

    if output.notes:
        print(f"\n[Notes from LLM]")
        print("-" * 60)
        print(output.notes.encode("ascii", "replace").decode("ascii"))

    for f in output.files:
        print(f"\n{'=' * 60}")
        status = "NEW" if f.is_new_file else "UPDATE"
        print(f"[FILE]  {f.file_path}  ({status})")
        if f.purpose:
            print(f"   Purpose: {f.purpose.encode('ascii', 'replace').decode('ascii')}")
        print(f"   Size: {len(f.content)} chars")
        print(f"   Preview (first 30 lines):")
        print(f"{'-' * 60}")
        lines = f.content.split("\n")
        for i, line in enumerate(lines[:30], 1):
            safe_line = line.encode("ascii", "replace").decode("ascii")
            print(f"   {i:3} | {safe_line}")
        if len(lines) > 30:
            print(f"   ... (and {len(lines) - 30} more lines)")


def _resolve_unused_revision_branch(gh, base_branch: str) -> str:
    """Find the lowest unused -revN suffix for a regeneration branch.

    Starts from rev2 (rev1 = original). Used so the original PR stays open
    as historical record while the regen creates a new branch + PR.
    """
    rev_n = 2
    while gh.branch_exists(f"{base_branch}-rev{rev_n}"):
        rev_n += 1
    return f"{base_branch}-rev{rev_n}"


# ---------------------------------------------------------------------------
# JIRA marker injection (used by both normal mode and regen mode)
# ---------------------------------------------------------------------------
def _ensure_jira_markers_on_feature_files(
    generated_files: list, test_cases: list[dict]
) -> list:
    """Inject `# JIRA: <KEY> (hash: <H>)` markers above each Scenario in
    every generated feature file. Idempotent: existing markers are
    refreshed in place; new ones are inserted.

    Matching strategy — ORDER-BASED with title-similarity safety check:
        Scenarios generated by the LLM follow the order of the Test Cases
        provided in the prompt. So scenarios[i] maps to test_cases[i].
        This is robust against LLM paraphrasing (e.g., Pro adding "Verify"
        prefixes, dropping articles), which would break exact-string matching.

        For each positional pair we do a token-overlap similarity check
        (≥0.3) as a sanity guard. Low similarity → skip rather than
        guess. This avoids mislabeling.

        If a scenario already carries a marker (e.g., from a previous
        ai-update splice), we refresh by the EXISTING key, not by
        position — so reordered scenarios stay correctly labelled.

    This is framework-generic: no app names, no project-specific keywords.
    """
    if not test_cases:
        return generated_files

    rewritten = []
    for gf in generated_files:
        if not gf.file_path.endswith(".feature"):
            rewritten.append(gf)
            continue
        new_content = _inject_markers_into_feature(gf.content, test_cases)
        if new_content != gf.content:
            logger.info(f"Injected JIRA markers into {gf.file_path}")
        else:
            logger.info(
                f"JIRA marker injection ran on {gf.file_path} but produced "
                "no changes — either markers already present and current, "
                "or positional/similarity matching skipped all scenarios. "
                "Check earlier log for warnings."
            )
        rewritten.append(GeneratedFile(
            file_path=gf.file_path,
            content=new_content,
            is_new_file=gf.is_new_file,
            purpose=gf.purpose,
        ))
    return rewritten


# Stopwords for token-overlap similarity. Generic English filler words,
# nothing app-specific.
_TITLE_STOPWORDS = frozenset({
    "the", "a", "an", "is", "to", "of", "in", "on", "at", "and", "or",
    "for", "from", "with", "after", "before", "i", "be", "should", "will",
    "can", "able", "as", "by", "into", "out", "that", "this", "these",
    "those", "it", "its", "verify", "test", "ensure", "check",
})


def _title_similarity(a: str, b: str) -> float:
    """Token-overlap similarity in [0, 1]. Framework-generic.

    Compares normalized token sets (Jaccard index). Handles paraphrasing
    where content words are preserved but connectives change.
    """
    def _tokens(s: str) -> set[str]:
        s = re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())
        return {t for t in s.split() if t and t not in _TITLE_STOPWORDS}

    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _inject_markers_into_feature(content: str, test_cases: list[dict]) -> str:
    """Add/refresh JIRA markers above each scenario. Returns new content.

    Algorithm:
      1. Scan the file for scenario start lines, and detect any existing
         markers above each.
      2. For each (scenario, test_case) position-pair:
         - If existing marker present → refresh hash (preserve key).
         - Else verify title-similarity >= 0.3, then insert marker.
         - Else log warning and skip (safer than mislabeling).
      3. Apply edits to a copy of the lines (refreshes in place, inserts
         done in reverse order so indices stay valid).
    """
    lines = content.splitlines(keepends=True)

    # First pass: locate scenario lines and any existing markers above them
    scenario_starts: list[int] = []
    existing_marker_above: dict[int, tuple[int, tuple[str, str]]] = {}
    # maps scenario_line_idx -> (marker_line_idx, (key, hash))

    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("Scenario Outline:") or stripped.startswith("Scenario:"):
            scenario_starts.append(i)
            j = i - 1
            while j >= 0 and lines[j].strip() == "":
                j -= 1
            if j >= 0:
                parsed = parse_marker(lines[j])
                if parsed:
                    existing_marker_above[i] = (j, parsed)

    if not scenario_starts:
        return content

    n_scenarios = len(scenario_starts)
    n_cases = len(test_cases)
    if n_scenarios != n_cases:
        logger.warning(
            f"Feature file has {n_scenarios} scenarios but {n_cases} test case(s) "
            f"were provided. Will pair the first {min(n_scenarios, n_cases)} positionally."
        )

    out_lines = list(lines)
    refreshes: list[tuple[int, str]] = []   # (line_idx, new_line)
    inserts: list[tuple[int, str]] = []     # (insert_at_idx, marker_line)

    # Pair each scenario with the test case it MATCHES, not the one at the same
    # index.
    #
    # Positional pairing assumes the feature file lists scenarios in the order
    # the test cases arrived. A run arrived with the two lists exactly
    # reversed - scenario 1 opposite the last case, scenario 4 opposite the
    # first - so every pair scored under 0.07, every marker was skipped, and
    # the feature file shipped with no traceability at all. `ai-update` cannot
    # splice a scenario that has no marker, so that story lost incremental
    # updates permanently over a sort order.
    #
    # Greedy best-match, highest score first, each case claimed once. When the
    # orders already agree the best match IS the positional one, so nothing
    # changes for a run that was working. The 0.3 floor still applies to the
    # best available pair: a scenario with no plausible case stays unmarkered
    # rather than mislabelled, which was the right call and stays the default.
    _claimed: set = set()
    _pairing: dict = {}
    for _idx in scenario_starts[:min(n_scenarios, n_cases)]:
        if _idx in existing_marker_above:
            continue                       # keeps its own key; handled below
        _line = lines[_idx]
        _title = _line.lstrip().partition(":")[2].strip()
        _scored = sorted(
            ((_title_similarity(_title, c.get("summary", "")), i)
             for i, c in enumerate(test_cases)),
            key=lambda pair: -pair[0],
        )
        _pairing[_idx] = _scored

    _chosen: dict = {}
    _ranked = sorted(
        ((scores[0][0], idx) for idx, scores in _pairing.items() if scores),
        key=lambda pair: -pair[0],
    )
    for _, _idx in _ranked:
        for _score, _i in _pairing[_idx]:
            if _i not in _claimed:
                _claimed.add(_i)
                _chosen[_idx] = (_score, test_cases[_i])
                break

    for k in range(min(n_scenarios, n_cases)):
        scenario_idx = scenario_starts[k]
        tc = test_cases[k]

        if scenario_idx in existing_marker_above:
            # Already-markered scenario: refresh hash by EXISTING key (not
            # by position), so an ai-update reorder doesn't relabel.
            marker_idx, (existing_key, _existing_hash) = existing_marker_above[scenario_idx]
            matching_tc = next((t for t in test_cases if t["key"] == existing_key), None)
            if matching_tc is None:
                # Key no longer in Jira — leave the orphan marker alone.
                # The ai-update flow can detect and remove orphans later.
                continue
            old_line = out_lines[marker_idx]
            indent = old_line[: len(old_line) - len(old_line.lstrip())]
            new_marker = format_marker(matching_tc["key"], matching_tc.get("description", ""))
            refreshes.append((marker_idx, f"{indent}{new_marker}\n"))
            continue

        # No existing marker: best-match, gated by title-similarity.
        scenario_line = lines[scenario_idx]
        title = scenario_line.lstrip().partition(":")[2].strip()
        sim, tc = _chosen.get(scenario_idx, (0.0, tc))

        # If only one pair exists, accept it unconditionally (no ambiguity).
        if min(n_scenarios, n_cases) > 1 and sim < 0.3:
            logger.warning(
                f"Skipping marker for scenario #{k+1} '{title[:60]}' — "
                f"low title similarity ({sim:.2f}) with {tc['key']} "
                f"'{tc.get('summary', '')[:60]}'. Likely scenario reorder; "
                "leave it unmarkered rather than mislabel. ai-update won't "
                "splice this scenario until a marker is added."
            )
            continue

        indent = scenario_line[: len(scenario_line) - len(scenario_line.lstrip())]
        new_marker = format_marker(tc["key"], tc.get("description", ""))
        inserts.append((scenario_idx, f"{indent}{new_marker}\n"))

    # Apply edits. Refreshes don't shift indices.
    for idx, new_line in refreshes:
        out_lines[idx] = new_line
    # Inserts shift everything after — go in reverse so earlier indices stay valid.
    for insert_pos, marker_line in sorted(inserts, key=lambda p: -p[0]):
        out_lines.insert(insert_pos, marker_line)

    # Name the test cases that ended up with no scenario.
    #
    # The count mismatch was warned about earlier - "3 scenarios but 4 test
    # case(s)" - and that told nobody WHICH one was left out. The story then
    # opened a pull request claiming four test cases and delivering three,
    # and the gap was invisible until somebody counted.
    #
    # Fewer scenarios than cases is sometimes deliberate: two cases can share
    # one scenario. So this is a warning, not a gate - but it now names the
    # case, so the decision is a decision rather than an oversight.
    _unpaired = [tc for _i, tc in enumerate(test_cases) if _i not in _claimed]
    if _unpaired:
        logger.warning(
            "%d test case(s) got no scenario of their own: %s. If that is "
            "deliberate - one scenario covering several cases - say so in the "
            "pull request body. If it is not, the story is shipping less "
            "coverage than it claims.",
            len(_unpaired),
            ", ".join(
                str((tc or {}).get("key") or (tc or {}).get("summary") or tc)[:60]
                for tc in _unpaired
            ),
        )

    return "".join(out_lines)


# ---------------------------------------------------------------------------
# Incremental update flow (ai-update label) — surgical scenario splicing
# ---------------------------------------------------------------------------
def _find_unused_update_branch(gh, base_branch: str) -> str:
    """Find the lowest unused -updateN suffix for an incremental-update branch."""
    n = 2
    while gh.branch_exists(f"{base_branch}-update{n}"):
        n += 1
    return f"{base_branch}-update{n}"


def _locate_feature_file_for_story(
    story_id: str, test_cases: list[dict]
) -> Optional[str]:
    """Find the feature file on `main` containing scenarios for this story.

    Looks for a file whose existing JIRA markers reference any Test Case
    key linked to this Story. Returns the project-relative path or None
    if no such file exists.
    """
    _ = story_id  # currently used only for logging context
    inventory = scan_features_dir()
    test_keys = {tc["key"] for tc in test_cases}
    for filename in inventory.get("scenarios_by_file", {}).keys():
        full_path = FEATURES_DIR / filename
        if not full_path.exists():
            continue
        content = full_path.read_text(encoding="utf-8")
        _h, blocks = parse_feature_file(content)
        markers_in_file = {b.jira_key for b in blocks if b.jira_key}
        if markers_in_file & test_keys:
            return f"features/{filename}"
    return None


def _generate_single_scenario(
    llm: LLMClient,
    feature_file_path: str,
    test_case: dict,
    ctx: AppContext,  # reserved for future use; intentionally unused for now
    existing_feature_content: str,
) -> str:
    """Ask the LLM for ONE Scenario block for ONE Test Case."""
    _ = ctx  # reserved
    jira_key = test_case["key"]
    summary = test_case.get("summary", "")
    description = test_case.get("description", "")
    marker = format_marker(jira_key, description)

    system = (
        "You are a Senior SDET. Produce ONE Gherkin Scenario block — "
        "no Feature header, no Background, no Examples, no surrounding text."
    )
    user = (
        f"Existing feature file `{feature_file_path}` (for style and context only):\n"
        f"```gherkin\n{existing_feature_content}\n```\n\n"
        f"Generate ONE Scenario block for Jira Test Case {jira_key}:\n"
        f"  Summary: {summary}\n"
        f"  Description:\n{description}\n\n"
        "Hard requirements for the output:\n"
        f"  1. The VERY FIRST line of your output MUST be exactly:\n     {marker}\n"
        "  2. The SECOND line MUST be `  Scenario: <title>` (two-space indent).\n"
        "  3. Steps follow on subsequent lines with four-space indent.\n"
        "  4. Do NOT emit Feature:, Background:, or Examples: keywords.\n"
        "  5. Reuse step phrasing that already exists in the file when applicable, "
        "to avoid forcing new step-definition functions.\n"
    )
    response = llm.invoke_text(system_prompt=system, user_prompt=user)
    return extract_code_from_response(response)


def _regenerate_step_defs_whole(
    llm: LLMClient,
    feature_file_path: str,
    new_feature_content: str,
    step_defs_path: str,
    ctx: AppContext,
    references: dict,
    page_inventory: str,
    existing_page_objects: list | None = None,
) -> str:
    """Regenerate the step-defs file whole based on the spliced feature."""
    from core.schemas import FilePlan

    _h, blocks = parse_feature_file(new_feature_content)
    synthetic_tcs = []
    for b in blocks:
        if b.kind != "scenario":
            continue
        title = ""
        for line in b.lines:
            stripped = line.lstrip()
            if stripped.startswith("Scenario:") or stripped.startswith("Scenario Outline:"):
                title = stripped.split(":", 1)[1].strip()
                break
        synthetic_tcs.append({
            "key": b.jira_key or "UNKNOWN",
            "summary": title or "scenario",
            "description": b.text(),
        })

    file_plan = FilePlan(
        file_path=step_defs_path,
        file_type="step_definitions",
        purpose=f"Regenerated step defs after scenario splice in {feature_file_path}",
        is_new_file=False,
    )
    minimal_plan = CodePlan(
        feature_name="incremental-update",
        branch_name="auto/placeholder",
        pr_title="placeholder",
        pr_body="placeholder",
        files_to_create=[file_plan],
        notes="Step-def regeneration triggered by ai-update.",
    )
    # ai-update regenerates a step def against page objects that ALREADY
    # EXIST. This is the case where invented method names hurt most, because
    # nothing else in the batch defines them - so pass the real signatures.
    return generate_file_content(
        llm, file_plan, minimal_plan,
        synthetic_tcs, references, page_inventory, ctx,
        existing_page_objects=existing_page_objects,
    )


# ─────────────────────────────────────────────────────────────────────────
# Backlog 2.4 — update-mode step-def splicing
#
# ai-update already splices the FEATURE file scenario-by-scenario. The step-def
# file, however, was fully regenerated on every update (`_regenerate_step_defs_whole`),
# which re-writes already-passing step functions and burns output tokens even when
# a change added no new steps. This splice keeps the existing step-def file and
# only adds definitions for steps the spliced feature introduces:
#
#   Tier A — the existing file already covers every step  -> keep it unchanged
#            (ZERO LLM calls). The common case for value/wording tweaks.
#   Tier B — some steps are new -> generate ONLY those functions and append them,
#            leaving passing functions untouched.
#   Tier C — anything ambiguous (no file on main, unparseable, LLM returned
#            nothing usable, result still uncovered, or a duplicate collision)
#            -> fall back to `_regenerate_step_defs_whole` (today's behaviour).
#
# The Tier-C fallback plus post-splice re-validation means a splice can never ship
# broken step defs: worst case we regenerate the whole file exactly as before.
# App-agnostic — uses only the generic Gherkin/step-def matching primitives.
# ─────────────────────────────────────────────────────────────────────────

_STEP_DECORATOR_NAMES = {"given", "when", "then"}


def _is_parseable_step_def(content: str) -> bool:
    """True if `content` is a real, parseable step-def file we can splice into:
    non-empty, valid Python, and containing at least one step decorator.

    Distinct from `_looks_like_useful_python` (which also enforces a minimum
    size to detect *degraded LLM output*). A legitimate one-scenario step-def
    file can be small, so the splice gate must not reject it on size alone.
    """
    if not content or not content.strip():
        return False
    try:
        ast.parse(content)
    except SyntaxError:
        return False
    return any(dec in content for dec in ("@given", "@when", "@then"))


def _missing_feature_steps(
    feature_content: str, step_def_content: str
) -> list[tuple[str, str]]:
    """Return the (keyword, phrase) steps in `feature_content` that have NO
    matching decorator in `step_def_content`, de-duplicated, order-preserved.

    Uses the same extraction + matching backends as the coverage validator, so
    "covered" here means what pytest-bdd would resolve at runtime.
    """
    required = _extract_feature_steps(feature_content)
    decorators = _extract_decorator_phrases(step_def_content)
    missing: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for keyword, phrase in required:
        if keyword is None:  # malformed And/But with no prior concrete keyword
            continue
        covered = any(
            dec_kind == keyword and _phrase_matches(phrase, dec_phrase, ptype)
            for dec_kind, dec_phrase, ptype in decorators
        )
        key = (keyword, phrase)
        if not covered and key not in seen:
            seen.add(key)
            missing.append(key)
    return missing


def _extract_new_step_functions(snippet: str) -> list[str]:
    """Extract decorated step-definition function blocks (source text, decorators
    included) from an LLM snippet. Returns [] if it doesn't parse or has none."""
    code = extract_code_from_response(snippet)
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    lines = code.splitlines()
    blocks: list[str] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        deco_names: set[str] = set()
        for d in node.decorator_list:
            f = d.func if isinstance(d, ast.Call) else d
            name = getattr(f, "id", None) or getattr(f, "attr", None)
            if name:
                deco_names.add(name)
        if not (deco_names & _STEP_DECORATOR_NAMES):
            continue
        start = min([node.lineno] + [d.lineno for d in node.decorator_list]) - 1
        end = node.end_lineno
        blocks.append("\n".join(lines[start:end]))
    return blocks


def _ensure_parsers_import(content: str) -> str:
    """Insert `from pytest_bdd import parsers` after the last top-level import
    if the content uses `parsers.` but never imports it. Best-effort; returns
    content unchanged if no import anchor is found."""
    lines = content.splitlines()
    last_import = None
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("import ") or s.startswith("from "):
            last_import = i
    if last_import is None:
        return content
    lines.insert(last_import + 1, "from pytest_bdd import parsers")
    return "\n".join(lines)


def _generate_missing_step_functions(
    llm: LLMClient,
    existing_step_defs: str,
    feature_content: str,
    missing_steps: list[tuple[str, str]],
    step_defs_path: str,
) -> str:
    """Ask the LLM for ONLY the new step functions needed for `missing_steps`."""
    missing_block = "\n".join(f"  - {kw.capitalize()}: {phrase}" for kw, phrase in missing_steps)
    system = (
        "You are a Senior SDET. Output ONLY new pytest-bdd step-definition "
        "functions — no imports, no fixtures, no existing functions, no prose, "
        "no markdown fences."
    )
    user = (
        f"Existing step-def file `{step_defs_path}` (for style, fixtures and "
        f"imports already available — do NOT repeat any of it):\n"
        f"```python\n{existing_step_defs}\n```\n\n"
        f"Feature file the steps come from (for context):\n"
        f"```gherkin\n{feature_content}\n```\n\n"
        f"These feature steps have NO matching decorator yet. Write ONE decorated "
        f"function per step, and NOTHING else:\n{missing_block}\n\n"
        "Hard requirements:\n"
        "  1. Emit ONLY the new @given/@when/@then function(s) — no import lines, "
        "no @pytest.fixture, no scenarios(...) call, no existing functions.\n"
        "  2. Match the decorator keyword to the step keyword shown above.\n"
        "  3. Reuse the page-object fixtures and `parsers` already imported in the "
        "existing file (they are in scope). Use parsers.parse() for parameterised "
        "steps, a plain string otherwise.\n"
        "  4. Declare every step the feature uses; steps are module-scoped, so duplicates are safe.\n"
    )
    return llm.invoke_text(system_prompt=system, user_prompt=user)


def _splice_step_defs_incremental(
    llm: LLMClient,
    gh,
    feature_file_path: str,
    spliced_feature_content: str,
    step_defs_path: str,
    ctx: AppContext,
    references: dict,
    page_inventory: str,
    branch: str | None = None,
) -> tuple[str, str]:
    """Produce the step-def file for an ai-update by splicing (backlog 2.4).

    Returns (content, mode) where mode is one of:
      - "unchanged"   : existing file already covered the feature (0 LLM calls)
      - "spliced"     : only the new step functions were appended
      - "regenerated" : fell back to whole-file regeneration (Tier C)
    """
    def _whole() -> tuple[str, str]:
        # ai-update regenerates against page objects that already exist on
        # main, so their real method signatures are the ground truth here.
        # Fails soft: no repo, no context, same behaviour as before.
        try:
            _existing = _existing_page_objects_on_main(
                gh, {step_defs_path}, branch=branch)
        except Exception:                                      # noqa: BLE001
            _existing = []
        return (
            _regenerate_step_defs_whole(
                llm, feature_file_path, spliced_feature_content,
                step_defs_path, ctx, references, page_inventory,
                existing_page_objects=_existing,
            ),
            "regenerated",
        )

    # Tier C pre-check: need a usable existing file on main to splice into.
    try:
        existing = gh.get_file_content(step_defs_path, branch="main")
    except Exception as e:
        logger.info(
            "Splice: could not read %s from main (%s) — regenerating whole.",
            step_defs_path, type(e).__name__,
        )
        return _whole()
    if not existing or not _is_parseable_step_def(existing):
        logger.info(
            "Splice: existing %s is missing or not usable Python — regenerating whole.",
            step_defs_path,
        )
        return _whole()

    missing = _missing_feature_steps(spliced_feature_content, existing)

    # Tier A: nothing new to define — keep the passing file exactly as-is.
    if not missing:
        logger.info(
            "Splice: existing step defs already cover the spliced feature — "
            "keeping %s unchanged (0 LLM calls).", step_defs_path,
        )
        return existing, "unchanged"

    # Tier B: generate ONLY the missing step functions and append them.
    logger.info(
        "Splice: %d new step(s) need definitions in %s: %s",
        len(missing), step_defs_path, [p for _, p in missing],
    )
    snippet = _generate_missing_step_functions(
        llm, existing, spliced_feature_content, missing, step_defs_path
    )
    new_funcs = _extract_new_step_functions(snippet)
    if not new_funcs:
        logger.warning(
            "Splice: LLM returned no usable step function(s) — regenerating whole."
        )
        return _whole()

    spliced = existing.rstrip() + "\n\n\n" + "\n\n\n".join(new_funcs) + "\n"
    if "parsers." in "\n".join(new_funcs) and "parsers" not in existing:
        spliced = _ensure_parsers_import(spliced)

    # Post-splice safety net — any doubt falls back to whole regeneration.
    if not _is_parseable_step_def(spliced):
        logger.warning("Splice: spliced result did not parse — regenerating whole.")
        return _whole()
    still_missing = _missing_feature_steps(spliced_feature_content, spliced)
    if still_missing:
        logger.warning(
            "Splice: %d step(s) still uncovered after splice — regenerating whole.",
            len(still_missing),
        )
        return _whole()
    dup = validate_no_duplicate_step_definitions(
        [GeneratedFile(
            file_path=step_defs_path, content=spliced,
            is_new_file=False, purpose="incremental splice",
        )],
        PROJECT_ROOT,
    )
    if dup:
        logger.warning(
            "Splice: duplicate step-def collision after splice — regenerating "
            "whole. First: %s", dup[0][:140],
        )
        return _whole()

    logger.info(
        "Splice: appended %d new step function(s) to %s; existing functions "
        "untouched.", len(new_funcs), step_defs_path,
    )
    return spliced, "spliced"


def run_update(story_id: str, dry_run: bool = False) -> dict:
    """Surgical incremental-update flow triggered by the `ai-update` label.

    Reads the existing feature file on main, classifies linked Test Cases
    as unchanged/modified/new, regenerates only the changed scenarios,
    splices them in, opens a new PR on an auto/...-updateN branch.
    """
    logger.info(
        f"=== Agent 2 (Coder) UPDATE mode for {story_id} (dry_run={dry_run}) ==="
    )
    ctx = AppContext.load()
    logger.info(f"App under test: {ctx.name} ({ctx.base_url})")

    jira = get_tracker()
    story = jira.get_story(story_id)
    test_cases = load_test_cases_for_story(jira, story_id)
    if not test_cases:
        logger.warning(f"No Test Cases linked to {story_id}. Run Agent 1 first.")
        return {"story_id": story_id, "status": "no_test_cases", "files_generated": 0}

    feature_file_path = _locate_feature_file_for_story(story_id, test_cases)
    if feature_file_path is None:
        logger.error(
            f"ai-update mode requires existing scenarios for {story_id} carrying "
            "JIRA markers, but none were found. This story has never been "
            "processed with markers — use normal mode or ai-regenerate to do "
            "an initial markered generation."
        )
        return {
            "story_id": story_id,
            "status": "no_markered_file",
            "files_generated": 0,
        }
    logger.info(f"Update target feature file: {feature_file_path}")

    gh = get_repo_host()
    try:
        existing_content = gh.get_file_content(feature_file_path, branch="main")
    except Exception as e:
        logger.error(f"Could not read {feature_file_path} from main: {e}")
        raise

    classification = classify_test_cases(test_cases, existing_content)
    logger.info(
        "Classification: unchanged=%d modified=%d new=%d orphan=%d",
        len(classification["unchanged"]),
        len(classification["modified"]),
        len(classification["new"]),
        len(classification["orphan_keys"]),
    )
    for tc in classification["modified"]:
        logger.info(f"  MODIFIED: {tc['key']} — {tc.get('summary', '')}")
    for tc in classification["new"]:
        logger.info(f"  NEW:      {tc['key']} — {tc.get('summary', '')}")
    for key in classification["orphan_keys"]:
        logger.info(f"  ORPHAN:   {key} (will be removed from feature file)")

    if not classification["modified"] and not classification["new"] and not classification["orphan_keys"]:
        logger.info(
            f"All {len(test_cases)} test cases for {story_id} are unchanged and "
            "no orphan scenarios. Nothing to update — exiting without a PR."
        )
        if not dry_run:
            agent_config = load_agent_config()
            update_label = agent_config.get("update_label", "ai-update")
            try:
                jira.remove_label(story_id, update_label)
                logger.info(f"Removed label '{update_label}' from {story_id} (no-op consumed)")
            except Exception as e:
                logger.warning(f"Could not remove label '{update_label}': {e}")
        return {
            "story_id": story_id,
            "status": "noop_all_unchanged",
            "scenarios_modified": 0,
            "scenarios_added": 0,
            "scenarios_removed": 0,
            "files_generated": 0,
        }

    references = ctx.load_reference_files()
    # Backlog 2.2 — inject only the pages relevant to this story's Jira
    # Components. Safe default (no/unknown components) = full inventory.
    page_inventory = ctx.load_page_inventory_json(story.get("components"))
    llm = LLMClient(temperature=0.2)

    spliced_content = existing_content

    # Remove orphans FIRST so they don't confuse the LLM about which steps exist.
    for orphan_key in classification["orphan_keys"]:
        spliced_content = remove_scenario(spliced_content, orphan_key)

    for tc in classification["modified"]:
        logger.info(f"Generating replacement scenario for {tc['key']}...")
        new_scenario_text = _generate_single_scenario(
            llm, feature_file_path, tc, ctx, spliced_content
        )
        new_hash = compute_description_hash(tc.get("description", ""))
        spliced_content = splice_scenario(
            spliced_content, tc["key"], new_scenario_text, new_hash
        )

    for tc in classification["new"]:
        logger.info(f"Generating new scenario for {tc['key']}...")
        new_scenario_text = _generate_single_scenario(
            llm, feature_file_path, tc, ctx, spliced_content
        )
        spliced_content = append_scenario(spliced_content, new_scenario_text)

    feature_stem = feature_file_path.split("/")[-1].rsplit(".", 1)[0]
    step_defs_path = f"tests/step_defs/test_{feature_stem}.py"
    logger.info(f"Updating {step_defs_path} for the spliced feature file...")
    # Backlog 2.4 — splice only the new step functions in (keeping passing ones
    # untouched); falls back to a whole regeneration on any ambiguity.
    new_step_defs_content, step_defs_mode = _splice_step_defs_incremental(
        llm, gh, feature_file_path, spliced_content,
        step_defs_path, ctx, references, page_inventory,
    )
    logger.info(f"Step-def update mode: {step_defs_mode}")

    # ════════════════════════════════════════════════════════════════════
    # ORPHAN CLEANUP — detect dead page-object methods left behind by
    # the removed scenarios, and comment them out (NOT delete) so the
    # human reviewer sees the audit trail. App-agnostic.
    #
    # This entire block is wrapped in try/except: orphan cleanup is a
    # nice-to-have. If it fails for any reason (network, parsing, etc.),
    # we log and continue with the surgical update without it. The PR
    # opens either way.
    # ════════════════════════════════════════════════════════════════════
    from validators.orphan_cleanup import cleanup_orphans_after_removal

    orphan_step_defs_found: list = []
    orphan_page_methods_found: list = []
    modified_page_files: dict[str, str] = {}

    if classification["orphan_keys"]:
        try:
            # Collect ALL step def files in the project (not just the one we
            # regenerated) so that orphan detection sees the full picture.
            all_step_def_files: dict[str, str] = {step_defs_path: new_step_defs_content}
            try:
                existing_step_def_paths = gh.list_files_in_directory(
                    "tests/step_defs", branch="main"
                )
            except (AttributeError, Exception) as e:
                logger.debug(
                    f"Could not list sibling step_def files for orphan detection: {e}. "
                    f"Falling back to single-file detection."
                )
                existing_step_def_paths = []

            for sd_path in existing_step_def_paths:
                if sd_path == step_defs_path or not sd_path.endswith(".py"):
                    continue
                if sd_path.endswith("/__init__.py"):
                    continue
                try:
                    all_step_def_files[sd_path] = gh.get_file_content(sd_path, branch="main")
                except Exception:
                    logger.debug(f"Could not read {sd_path}, skipping.")

            # Collect page object files we are ALLOWED to modify
            # (extendable_paths from app config). base_page.py is excluded
            # via reserved_file_paths because it holds universal helpers.
            extendable = ctx.extendable_paths_normalized()
            page_object_files: dict[str, str] = {}
            for ext_path in extendable:
                if not ext_path.startswith("pages/") or not ext_path.endswith(".py"):
                    continue
                try:
                    page_object_files[ext_path] = gh.get_file_content(ext_path, branch="main")
                except Exception as e:
                    logger.debug(f"Could not read {ext_path}: {e}")

            reserved = {"pages/base_page.py"}  # universal helpers — never orphan

            (
                _,
                updated_pages,
                orphan_step_defs_found,
                orphan_page_methods_found,
            ) = cleanup_orphans_after_removal(
                old_feature_content=existing_content,
                new_feature_content=spliced_content,
                removed_jira_keys=classification["orphan_keys"],
                step_def_files=all_step_def_files,
                page_object_files=page_object_files,
                reserved_file_paths=reserved,
            )

            # If any page object files were modified, record them for the PR.
            for path, new_content in updated_pages.items():
                if path in page_object_files and new_content != page_object_files[path]:
                    modified_page_files[path] = new_content

            logger.info(
                f"Orphan cleanup: detected {len(orphan_step_defs_found)} dead step def(s), "
                f"{len(orphan_page_methods_found)} dead page method(s); "
                f"{len(modified_page_files)} page file(s) modified."
            )
        except Exception as e:
            logger.warning(
                f"Orphan cleanup failed with {type(e).__name__}: {e}. "
                f"Continuing with surgical update; page objects unchanged. "
                f"You can run with `ai-regenerate` later to do a full regen."
            )
            orphan_step_defs_found = []
            orphan_page_methods_found = []
            modified_page_files = {}

    generated_files = [
        GeneratedFile(
            file_path=feature_file_path,
            content=spliced_content,
            is_new_file=False,
            purpose="Incremental update: spliced scenario changes",
        ),
        GeneratedFile(
            file_path=step_defs_path,
            content=new_step_defs_content,
            is_new_file=False,
            purpose=f"Incremental update: step defs ({step_defs_mode})",
        ),
    ]
    for page_path, page_content in modified_page_files.items():
        generated_files.append(GeneratedFile(
            file_path=page_path,
            content=page_content,
            is_new_file=False,
            purpose="Incremental update: orphan method(s) commented out",
        ))

    _validate_generated_files(generated_files, story_id)

    base_branch = f"auto/{story_id}-{feature_stem.replace('_', '-')}"
    update_branch = _find_unused_update_branch(gh, base_branch)
    pr_title = f"feat({feature_stem}): incremental update to test scenarios"
    mod_keys = [tc["key"] for tc in classification["modified"]]
    new_keys = [tc["key"] for tc in classification["new"]]
    pr_body_parts = ["This PR contains a surgical update to existing test scenarios."]
    if mod_keys:
        pr_body_parts.append(f"\n**Modified scenarios:** {', '.join(mod_keys)}")
    if new_keys:
        pr_body_parts.append(f"\n**New scenarios:** {', '.join(new_keys)}")
    if classification["orphan_keys"]:
        pr_body_parts.append(
            f"\n**Removed scenarios (no longer in Jira):** "
            f"{', '.join(classification['orphan_keys'])}"
        )
    if orphan_step_defs_found:
        orphan_func_names = ", ".join(
            f"`{o.function_name}`" for o in orphan_step_defs_found
        )
        pr_body_parts.append(
            f"\n**Orphan step definitions detected and removed by regeneration:** "
            f"{orphan_func_names}"
        )
    if orphan_page_methods_found:
        orphan_method_summary = ", ".join(
            f"`{o.class_name}.{o.method_name}`" for o in orphan_page_methods_found
        )
        pr_body_parts.append(
            f"\n**Orphan page methods (commented out for human review):** "
            f"{orphan_method_summary}"
        )
        pr_body_parts.append(
            "\n\n> ⚠️ Orphan page-object methods were detected and commented "
            "out with `# AI-ORPHAN:` banners. Review the page object diffs — "
            "if a method might be useful for upcoming scenarios, uncomment it. "
            "Otherwise delete it in a follow-up commit."
        )
    pr_body_parts.append(
        "\n\nUnchanged scenarios are preserved byte-for-byte. "
        "If new page-object methods are needed for surviving scenarios, "
        "use the `ai-regenerate` label for a full regeneration."
    )
    pr_body = "".join(pr_body_parts)

    if dry_run:
        logger.warning("DRY RUN -- skipping branch/commit/PR creation")
        print(f"\n[DRY RUN] Would create branch: {update_branch}")
        print(f"[DRY RUN] PR title: {pr_title}")
        print(f"[DRY RUN] Files to commit:")
        for gf in generated_files:
            print(f"  - {gf.file_path} ({len(gf.content)} chars)")
        return {
            "story_id": story_id,
            "status": "update_dry_run",
            "scenarios_modified": len(mod_keys),
            "scenarios_added": len(new_keys),
            "scenarios_removed": len(classification["orphan_keys"]),
            "files_generated": len(generated_files),
            "branch_name": update_branch,
        }

    assert_valid_branch_for_pipeline(update_branch)
    gh.create_branch(update_branch, from_branch="main")
    for gf in generated_files:
        gh.create_or_update_file(
            path=gf.file_path,
            content=gf.content,
            commit_message=f"chore(update): {gf.purpose}",
            branch=update_branch,
        )
    pr_url = gh.open_pull_request(
        head_branch=update_branch,
        base_branch="main",
        title=pr_title,
        body=pr_body,
    )

    agent_config = load_agent_config()
    update_label = agent_config.get("update_label", "ai-update")
    try:
        jira.remove_label(story_id, update_label)
        logger.info(f"Removed label '{update_label}' from {story_id} (one-shot consumed)")
    except Exception as e:
        logger.warning(f"Could not remove label '{update_label}': {e}")

    logger.info(
        f"=== Agent 2 UPDATE complete for {story_id}. "
        f"Modified={len(mod_keys)} New={len(new_keys)} Removed={len(classification['orphan_keys'])} ==="
    )
    from core.llm_client import log_usage_summary, reset_usage
    usage = log_usage_summary(f"story {story_id} (update)")
    reset_usage()  # per-story numbers in scan mode
    if not dry_run:
        from core.usage_ledger import post_usage_to_story
        post_usage_to_story(story_id, "Agent 2 (Coder, incremental update)", usage, jira=jira)
    return {
        "story_id": story_id,
        "status": "update_pr_opened",
        "llm_usage": usage,
        "scenarios_modified": len(mod_keys),
        "scenarios_added": len(new_keys),
        "scenarios_removed": len(classification["orphan_keys"]),
        "files_generated": len(generated_files),
        "branch_name": update_branch,
        "pr_url": pr_url,
    }


# ---------------------------------------------------------------------------
# Core agent workflow
# ---------------------------------------------------------------------------
def run(story_id: str, dry_run: bool = False, is_regenerate: bool = False) -> dict:
    """Main agent flow — Stage 1 plan, then Stage 2 per-file generation.

    Args:
        story_id: Jira story key (e.g., "SCRUM-5")
        dry_run: If True, don't create branch/commits/PR. Print preview.
        is_regenerate: If True, this is a REGENERATION run triggered by the
            `ai-regenerate` label. Skips dedup, uses -revN branch suffix,
            removes the regenerate label after success.
    """
    mode_label = "REGENERATE" if is_regenerate else "normal"
    logger.info(
        f"=== Agent 2 (Coder) starting for {story_id} "
        f"(mode={mode_label}, dry_run={dry_run}) ==="
    )

    ctx = AppContext.load()
    logger.info(f"App under test: {ctx.name} ({ctx.base_url})")

    # 1. INPUT
    jira = get_tracker()

    # Guard: --story must name a STORY, not a Test Case. Scan mode filters on
    # issue type "Story" via the tracker selection rule, but the manual --story
    # path has no such filter,
    # so a Test Case key would be accepted and then baked into the branch name
    # (auto/<TESTCASE-KEY>-...). That breaks traceability: Agents 3/4/5 fire on
    # pull_request events which carry only a branch name, and Agent 5 recovers
    # the story key FROM that branch to know where to report. Escalate to the
    # parent Story when we can; keep the original key when we cannot.
    parent_story = jira.get_parent_story_key(story_id)
    if parent_story:
        logger.warning(
            f"{story_id} is a Test Case, not a Story. Using its parent Story "
            f"{parent_story} instead — branch names and Agent 5 reporting must "
            f"be keyed on the Story."
        )
        story_id = parent_story

    # CRASH-WINDOW GUARD. `ai-coded` is added only AFTER the PR is created, so a
    # runner killed in between leaves the story looking un-coded and the next
    # tick would redo the whole thing: a full set of LLM calls (~$0.37) thrown
    # away, then a failure at PR creation because the PR already exists.
    #
    # An open auto/<STORY>-* PR IS the completion marker - it is created by the
    # same call the label follows. Finding one means the work landed; the label
    # is simply missing, so repair it and stop. Two cheap API calls, before any
    # LLM spend. Skipped in regenerate/update mode, where a NEW PR on a -revN /
    # -updateN branch is the intended outcome.
    if not is_regenerate:
        existing_pr = get_repo_host().find_open_pr_for_story(story_id)
        if existing_pr:
            completion_label = load_agent_config().get("completion_label", "ai-coded")
            logger.warning(
                f"{story_id} already has an open PR (#{existing_pr['number']}, "
                f"{existing_pr['head_ref']}) but is not labelled '{completion_label}' - "
                f"a previous run was interrupted after opening the PR. Repairing the "
                f"label and stopping instead of regenerating."
            )
            if not dry_run:
                jira.add_label(story_id, completion_label)
            return {"story_id": story_id, "status": "already_coded",
                    "pr_number": existing_pr["number"], "files_generated": 0}

    story = jira.get_story(story_id)
    test_cases = load_test_cases_for_story(jira, story_id)

    if not test_cases:
        logger.warning(f"No Test Cases linked to {story_id}. Run Agent 1 first.")
        return {"story_id": story_id, "status": "no_test_cases", "files_generated": 0}

    # 1b. DEDUP (skipped in regenerate mode)
    new_test_cases, skipped_test_cases = _select_new_test_cases(test_cases, is_regenerate)

    if not new_test_cases:
        # Every approved test case is already covered. No work needed.
        logger.info(
            f"All {len(test_cases)} test cases for {story_id} are already covered "
            "by existing scenarios. No new code generation needed."
        )
        if not dry_run:
            agent_config = load_agent_config()
            completion_label = agent_config.get("completion_label", "ai-coded")
            jira.add_label(story_id, completion_label)
            logger.info(f"Marked {story_id} with label '{completion_label}' (no work needed)")
        return {
            "story_id": story_id,
            "status": "skipped_all_duplicates",
            "files_generated": 0,
            "skipped_count": len(skipped_test_cases),
        }

    if len(new_test_cases) < len(test_cases):
        logger.info(
            f"Generating code for {len(new_test_cases)} new case(s); "
            f"{len(skipped_test_cases)} skipped as duplicates."
        )

    # 2. CONTEXT — read references and inventory once
    references = ctx.load_reference_files()
    # Backlog 2.2 — inject only the pages relevant to this story's Jira
    # Components. Safe default (no/unknown components) = full inventory.
    page_inventory = ctx.load_page_inventory_json(story.get("components"))
    llm = LLMClient(temperature=0.2)

    # 3. STAGE 1: PLAN
    plan = build_plan(llm, new_test_cases, references, page_inventory, ctx)

    # 4. STAGE 2: GENERATE PER-FILE CONTENT
    # Order page objects BEFORE step definitions so the step-def prompt
    # can include the actual method signatures from page objects already
    # generated in this batch (Hotfix v5 — prevents cross-file naming
    # mismatches like `click_logout()` vs `click_logout_link()`).
    ordered_files = _sort_files_for_generation(plan.files_to_create)

    # Page objects already committed on main. Fetched ONCE, before the loop:
    # they do not change while this batch is generated, and a per-file fetch
    # would multiply API calls for no benefit. Fails soft to an empty list, in
    # which case behaviour is exactly as it was before.
    _plan_paths = {f.file_path for f in ordered_files}
    existing_pos: list = []
    try:
        existing_pos = _existing_page_objects_on_main(
            gh, _plan_paths, branch=getattr(plan, "branch_name", None))
        if existing_pos:
            logger.info("Stage 2: injecting method signatures from %d existing "
                        "page object(s).", len(existing_pos))
    except Exception as exc:                                   # noqa: BLE001
        logger.debug("No existing-page-object context: %s", exc)

    generated_files: list[GeneratedFile] = []
    for file_plan in ordered_files:
        try:
            content = generate_file_content(
                llm, file_plan, plan, new_test_cases, references, page_inventory, ctx,
                already_generated=generated_files,
                existing_page_objects=existing_pos,
            )
            generated_files.append(GeneratedFile(
                file_path=file_plan.file_path,
                content=content,
                is_new_file=file_plan.is_new_file,
                purpose=file_plan.purpose,
            ))
        except Exception as e:
            logger.error(f"Failed to generate {file_plan.file_path}: {e}")
            raise

    output = CodeGenerationOutput(
        feature_name=plan.feature_name,
        branch_name=plan.branch_name,
        pr_title=plan.pr_title,
        pr_body=plan.pr_body,
        files=generated_files,
        notes=plan.notes,
    )

    # 4b. SELF-CORRECTING REPAIR (handles weak-model coverage misses)
    # If validator finds missing decorators, give the LLM up to 2 chances
    # to fix the broken step def file with explicit feedback. Only the
    # broken file is regenerated (cheap), and the cap bounds total cost.
    generated_files = _attempt_step_coverage_repair(
        generated_files,
        llm,
        plan,
        new_test_cases,
        references,
        page_inventory,
        ctx,
        max_retries=4,
    )
    output = CodeGenerationOutput(
        feature_name=plan.feature_name,
        branch_name=plan.branch_name,
        pr_title=plan.pr_title,
        pr_body=plan.pr_body,
        files=generated_files,
        notes=plan.notes,
    )

    # 4d. INJECT JIRA MARKERS into feature files. Markers are
    # deterministic comment lines above each Scenario naming the Jira
    # Test Case + hash. Prerequisite for the ai-update flow to identify
    # which scenario maps to which Test Case. Injected here (post-gen)
    # rather than relying on the LLM to emit them — deterministic > persuaded.
    generated_files = _ensure_jira_markers_on_feature_files(
        generated_files, new_test_cases
    )
    # CRITICAL: rebuild `output` so the commit loop below uses the post-injection
    # file list, not the stale pre-injection list. (Previous bug: markers were
    # injected into `generated_files` but `output.files` still pointed at the
    # old list, so committed files had no markers.)
    output = CodeGenerationOutput(
        feature_name=plan.feature_name,
        branch_name=plan.branch_name,
        pr_title=plan.pr_title,
        pr_body=plan.pr_body,
        files=generated_files,
        notes=plan.notes,
    )

    # ════════════════════════════════════════════════════════════════════
    # 4e. ORPHAN CLEANUP (REGENERATE MODE ONLY)
    #
    # In regenerate mode, the LLM rewrites the feature, step defs, and
    # page objects from scratch — but the LLM is INSTRUCTED to preserve
    # existing page-object methods (extendable_paths rule). So if Test
    # Cases were deleted from Jira before this regen, their page-object
    # methods stay alive as dead code.
    #
    # We detect those by comparing OLD feature content (on main) with
    # the freshly-generated NEW feature content. Methods uniquely tied
    # to scenarios that no longer exist get commented out.
    #
    # Normal mode (first-time coding of a story) has no old feature
    # to diff against, so cleanup is skipped there.
    # ════════════════════════════════════════════════════════════════════
    orphan_regen_step_defs: list = []
    orphan_regen_page_methods: list = []
    if is_regenerate:
        try:
            from validators.orphan_cleanup import cleanup_orphans_after_removal

            _gh_for_read = get_repo_host()

            # Find generated feature file content
            new_feature_files: dict[str, str] = {}
            new_step_def_files: dict[str, str] = {}
            new_page_object_files: dict[str, str] = {}
            for gf in generated_files:
                if gf.file_path.startswith("features/") and gf.file_path.endswith(".feature"):
                    new_feature_files[gf.file_path] = gf.content
                elif gf.file_path.startswith("tests/step_defs/") and gf.file_path.endswith(".py"):
                    new_step_def_files[gf.file_path] = gf.content
                elif gf.file_path.startswith("pages/") and gf.file_path.endswith(".py"):
                    new_page_object_files[gf.file_path] = gf.content

            # For each feature file we just generated, fetch the OLD copy
            # from main (if it exists) and run orphan detection.
            for feature_path, new_feature_content in new_feature_files.items():
                try:
                    old_feature_content = _gh_for_read.get_file_content(
                        feature_path, branch="main"
                    )
                except Exception:
                    # File didn't exist on main → brand-new feature, no orphans possible
                    logger.debug(
                        f"Regenerate: feature {feature_path} is new on main; "
                        f"no orphan detection needed."
                    )
                    continue

                # Use the existing classify_test_cases logic to find orphan keys
                old_classification = classify_test_cases(test_cases, old_feature_content)
                orphan_keys = old_classification["orphan_keys"]
                if not orphan_keys:
                    logger.debug(
                        f"Regenerate: no orphan Jira keys for {feature_path}; "
                        f"no cleanup needed."
                    )
                    continue

                logger.info(
                    f"Regenerate: {len(orphan_keys)} orphan Jira key(s) "
                    f"for {feature_path}: {orphan_keys}"
                )

                # Read page object files that we did NOT regenerate (LLM left them
                # alone). These need orphan-method scanning too.
                extendable = ctx.extendable_paths_normalized()
                all_page_object_files: dict[str, str] = dict(new_page_object_files)
                for ext_path in extendable:
                    if ext_path in all_page_object_files:
                        continue  # already have the freshly-generated version
                    if not ext_path.startswith("pages/") or not ext_path.endswith(".py"):
                        continue
                    try:
                        all_page_object_files[ext_path] = _gh_for_read.get_file_content(
                            ext_path, branch="main"
                        )
                    except Exception as e:
                        logger.debug(f"Could not read {ext_path}: {e}")

                reserved = {"pages/base_page.py"}  # universal helpers — never orphan

                (
                    _,
                    updated_pages,
                    orphan_defs,
                    orphan_methods,
                ) = cleanup_orphans_after_removal(
                    old_feature_content=old_feature_content,
                    new_feature_content=new_feature_content,
                    removed_jira_keys=orphan_keys,
                    step_def_files=new_step_def_files,
                    page_object_files=all_page_object_files,
                    reserved_file_paths=reserved,
                )

                orphan_regen_step_defs.extend(orphan_defs)
                orphan_regen_page_methods.extend(orphan_methods)

                # Apply page-object updates: if any page file got commented edits,
                # add or replace it in generated_files.
                for path, new_content in updated_pages.items():
                    if path not in all_page_object_files:
                        continue
                    if new_content == all_page_object_files[path]:
                        continue  # unchanged
                    # Update or append to generated_files
                    replaced = False
                    for i, gf in enumerate(generated_files):
                        if gf.file_path == path:
                            generated_files[i] = GeneratedFile(
                                file_path=path,
                                content=new_content,
                                is_new_file=False,
                                purpose=f"{gf.purpose} (+ orphan method(s) commented out)",
                            )
                            replaced = True
                            break
                    if not replaced:
                        generated_files.append(GeneratedFile(
                            file_path=path,
                            content=new_content,
                            is_new_file=False,
                            purpose="Regenerate: orphan method(s) commented out",
                        ))

            if orphan_regen_step_defs or orphan_regen_page_methods:
                logger.info(
                    f"Regenerate orphan cleanup: {len(orphan_regen_step_defs)} dead "
                    f"step def(s), {len(orphan_regen_page_methods)} dead page method(s) "
                    f"detected and annotated."
                )
                # Rebuild `output` to include the page-object edits
                output = CodeGenerationOutput(
                    feature_name=plan.feature_name,
                    branch_name=plan.branch_name,
                    pr_title=plan.pr_title,
                    pr_body=plan.pr_body,
                    files=generated_files,
                    notes=plan.notes,
                )
        except Exception as e:
            logger.warning(
                f"Regenerate orphan cleanup failed with {type(e).__name__}: {e}. "
                f"Continuing with regeneration; page objects may contain dead methods. "
                f"You can run with `ai-update` later to clean them up."
            )
            orphan_regen_step_defs = []
            orphan_regen_page_methods = []

    # 4c. FINAL VALIDATION (after any repair attempts)
    _validate_generated_files(generated_files, story_id)

    # 5. ACT
    if dry_run:
        logger.warning("DRY RUN -- skipping branch/commit/PR creation")
        _print_dry_run_preview(output)
        return {
            "story_id": story_id,
            "files_generated": len(output.files),
            "status": "code_generated_dry_run",
        }

    # Real run — branch must contain a Jira key for downstream agents to work
    branch_key = assert_valid_branch_for_pipeline(output.branch_name)

    # ...and it must be THIS story's key, not one of its test cases.
    #
    # The plan prompt asks for `auto/<jira-key>-<feature>` without saying which
    # key, so the model used whichever appeared first in its input - the test
    # cases. A story about a shopping session became
    # `auto/<TESTCASE>-shopping-session` while the story itself was a
    # different key.
    #
    # Three places then disagreed about who owns the work: the branch said one
    # thing, the PR body another, the board a third. Agent 5 reads the BRANCH,
    # so the usage ledger posted its cost comment to a test case - and the
    # story's Jira page quietly had no record of what it cost.
    #
    # Corrected rather than rejected. The model chose a reasonable key from an
    # ambiguous instruction; failing the story over a name would waste a
    # generation that is otherwise fine.
    if branch_key != story_id:
        corrected = output.branch_name.replace(branch_key, story_id, 1)
        logger.warning(
            "Branch %r is named after %s, which is not the story being "
            "processed (%s) - almost certainly one of its test cases. "
            "Renaming to %r so the branch, the pull request and the board "
            "agree, and so Agent 5 posts usage to the story.",
            output.branch_name, branch_key, story_id, corrected,
        )
        output.branch_name = corrected
        assert_valid_branch_for_pipeline(output.branch_name)

    gh = get_repo_host()

    # REGENERATE: append -revN suffix so we don't reuse the existing branch.
    if is_regenerate:
        new_branch_name = _resolve_unused_revision_branch(gh, output.branch_name)
        logger.info(
            f"Regeneration: changed branch from '{output.branch_name}' to "
            f"'{new_branch_name}' to preserve old PR as historical record"
        )
        output.branch_name = new_branch_name

    # PARTIAL-BRANCH GUARD (crash WINDOW A). Files are committed one at a time,
    # so a crash inside the loop below leaves some present and others missing.
    # create_branch() is idempotent and would happily REUSE that branch - but
    # this run may produce a DIFFERENT set of files (a test case was deleted,
    # the plan changed), and any file from the abandoned attempt would survive
    # into the PR without ever being generated or validated by this run.
    #
    # Discarding is safe here precisely because no PR exists: the crash-window
    # guard at the top of run() already returned early if one did, so nothing
    # under human review can be destroyed. All-or-nothing beats a silent mix of
    # two attempts.
    if not dry_run and gh.branch_exists(output.branch_name):
        logger.warning(
            f"Branch '{output.branch_name}' already exists with no open PR - "
            f"a previous attempt was interrupted mid-commit. Discarding it so "
            f"this run starts from a clean base."
        )
        gh.delete_branch(output.branch_name)

    gh.create_branch(output.branch_name, from_branch="main")

    for f in output.files:
        commit_msg = f"[Agent 2] {'Add' if f.is_new_file else 'Update'} {f.file_path}"
        gh.create_or_update_file(
            path=f.file_path,
            content=f.content,
            commit_message=commit_msg,
            branch=output.branch_name,
        )

    pr_body_with_footer = (
        output.pr_body
        + f"\n\n---\n*This PR was automatically generated by Agent 2 (Coder) from {story_id}.*"
    )
    # If regen orphan cleanup found anything, append it to the PR body.
    if is_regenerate and (orphan_regen_step_defs or orphan_regen_page_methods):
        orphan_section_parts = ["\n\n---\n## Orphan code cleanup (regenerate mode)\n"]
        if orphan_regen_step_defs:
            funcs = ", ".join(f"`{o.function_name}`" for o in orphan_regen_step_defs)
            orphan_section_parts.append(
                f"\n**Orphan step definitions detected (omitted from regeneration):** {funcs}\n"
            )
        if orphan_regen_page_methods:
            methods = ", ".join(
                f"`{o.class_name}.{o.method_name}`"
                for o in orphan_regen_page_methods
            )
            orphan_section_parts.append(
                f"\n**Orphan page methods (commented out for human review):** {methods}\n"
                f"\n> ⚠️ Orphan page-object methods were detected because their "
                f"underlying Jira Test Cases were deleted before this regeneration. "
                f"They are commented out with `# AI-ORPHAN:` banners. Review the "
                f"page object diffs — if a method might be useful for upcoming "
                f"scenarios, uncomment it. Otherwise delete it in a follow-up commit.\n"
            )
        pr_body_with_footer = pr_body_with_footer + "".join(orphan_section_parts)

    pr_url = gh.open_pull_request(
        title=output.pr_title,
        body=pr_body_with_footer,
        head_branch=output.branch_name,
        base_branch="main",
    )

    # Idempotency markers: tag the parent story so the next --scan run skips it.
    agent_config = load_agent_config()
    completion_label = agent_config.get("completion_label", "ai-coded")
    jira.add_label(story_id, completion_label)
    logger.info(f"Marked {story_id} with label '{completion_label}' (idempotency)")
    # Board hygiene: follow the label with a column move. Opt-in; never fatal.
    move_card_for_label(jira, story_id, completion_label)

    if is_regenerate:
        regenerate_label = agent_config.get("regenerate_label", "ai-regenerate")
        jira.remove_label(story_id, regenerate_label)
        logger.info(f"Removed label '{regenerate_label}' from {story_id} (one-shot consumed)")

    from core.llm_client import log_usage_summary, reset_usage
    usage = log_usage_summary(f"story {story_id}")
    reset_usage()  # per-story numbers in scan mode
    if not dry_run:
        from core.usage_ledger import post_usage_to_story
        mode = "regenerate" if is_regenerate else "initial"
        post_usage_to_story(story_id, f"Agent 2 (Coder, {mode})", usage, jira=jira)

    result = {
        "story_id": story_id,
        "files_generated": len(output.files),
        "branch_name": output.branch_name,
        "pr_url": pr_url,
        "status": "pr_opened",
        "llm_usage": usage,
    }

    logger.info(f"=== Agent 2 (Coder) complete. PR: {pr_url} ===")
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
_SCAN_MARKERS = {
    "pr_opened": "OK",
    "skipped_all_duplicates": "SKIP",
    "failed": "FAIL",
}


def _scan_summary_lines(results: list[dict]) -> list[str]:
    """One line per story, saying what happened and - on failure - why.

    A scan of several stories used to end with `[FAIL] <STORY>: failed`.
    The reason was captured into the result dict by the loop's except clause
    and then never printed, so reading a multi-story run meant scrolling back
    through the log of every OTHER story to find the traceback.

    That matters more the more stories run at once, which is the whole point
    of scanning several.
    """
    counts: dict = {}
    for r in results:
        counts[r.get("status", "unknown")] = counts.get(r.get("status", "unknown"), 0) + 1

    tally = ", ".join(f"{n} {status.replace('_', ' ')}"
                      for status, n in sorted(counts.items()))
    lines = [f"Agent 2 scan finished - {len(results)} story/stories: {tally}"]

    for r in results:
        status = r.get("status", "unknown")
        marker = _SCAN_MARKERS.get(status, "??")
        story = r.get("story_id", "?")
        detail = ""
        if r.get("pr_url"):
            detail = f" -> {r['pr_url']}"
        elif r.get("branch_name"):
            detail = f" (branch {r['branch_name']})"
        lines.append(f"[{marker}] {story}: {status}{detail}")

        # The reason, on the line below, indented. One story's failure should
        # be readable without hunting for it among the others.
        error = (r.get("error") or "").strip()
        if error:
            first = error.splitlines()[0]
            lines.append(f"       {first[:300]}")
    return lines


def _print_scan_summary(results: list[dict]) -> None:
    lines = _scan_summary_lines(results)
    print("\n" + "=" * 60)
    for line in lines:
        print(f"   {line}" if not line.startswith("Agent 2") else f"[OK] {line}")
    print("=" * 60)

    # Also into the CI job summary, where a multi-story run is actually read.
    # Without this the only record is the log, and the log of a five-story
    # scan is long enough that nobody reaches the end of it.
    import os

    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    try:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write("\n## Agent 2 (Coder)\n\n")
            handle.write(f"{lines[0]}\n\n")
            for line in lines[1:]:
                if line.startswith("["):
                    handle.write(f"- `{line}`\n")
                else:
                    handle.write(f"  - {line.strip()}\n")
    except Exception:                                     # noqa: BLE001
        logger.debug("could not write the scan summary to GITHUB_STEP_SUMMARY")


def main():
    parser = argparse.ArgumentParser(
        description="Agent 2 (Coder): Generate test code from Jira test cases",
        epilog=("examples:\n  one story        --story SCRUM-5\n  preview only     --story SCRUM-5 --dry-run\n\nreads ref: main - a framework change only takes effect once MERGED."),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--story", help="Process all test cases of a specific story")
    group.add_argument("--scan", action="store_true", help="Scan mode (config-driven)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Don't create branch/PR, just preview")
    parser.add_argument("--update", action="store_true",
                        help="Treat --story as an INCREMENTAL UPDATE: splice "
                             "only modified/new scenarios, leave others untouched. "
                             "Requires existing JIRA markers in the feature file.")
    parser.add_argument(
        "--sprint",
        default=None,
        metavar="SPRINT",
        help=(
            "Override the sprint filter for this scan run only. "
            "Accepts a sprint name (e.g. 'Sprint 10'), a numeric sprint ID, "
            "or 'openSprints' for the currently active sprint. "
            "Overrides the 'sprint' key in config.yaml. "
            "Applied to all three scan passes (normal, regen, update). "
            "Ignored when --story is used."
        ),
    )
    args = parser.parse_args()

    # Fast-fail on missing config — much clearer than a 401 deep in a tool call
    validate_required_env(
        REQUIRED_JIRA_ENV_VARS + REQUIRED_LLM_ENV_VARS + REQUIRED_GITHUB_ENV_VARS
    )

    try:
        if args.story:
            if args.update:
                result = run_update(args.story, dry_run=args.dry_run)
            else:
                result = run(args.story, dry_run=args.dry_run)
            print("\n" + "=" * 60)
            print(f"[OK] Agent 2 finished -- story: {result['story_id']}")
            print(f"   Files generated: {result.get('files_generated', 0)}")
            print(f"   Status: {result['status']}")
            if result.get("pr_url"):
                print(f"   PR: {result['pr_url']}")
            print("=" * 60)
            return

        # Scan mode: three passes (normal + regenerate + update).
        agent_config = load_agent_config()
        normal_selection = agent_config.get("selection", {})
        regen_selection = agent_config.get("regenerate_selection", {})
        update_selection = agent_config.get("update_selection", {})
        max_stories = agent_config.get("max_stories_per_run", 5)

        if not normal_selection:
            logger.error(
                "No 'selection' config found for agent2_coder in config.yaml. "
                "Add an 'agents.agent2_coder.selection' block or use --story KEY instead."
            )
            sys.exit(1)

        # Log the effective sprint so it's visible in CI logs
        effective_sprint = args.sprint or normal_selection.get("sprint")
        if effective_sprint:
            logger.info(
                f"Sprint scope: {effective_sprint!r} "
                f"(source: {'--sprint flag' if args.sprint else 'config.yaml'}) "
                f"— applied to all three scan passes."
            )
        else:
            logger.info("Sprint scope: ALL sprints (no sprint filter configured).")

        jira = get_tracker()

        logger.info("Scan pass 1/3: looking for first-time stories (normal mode)")
        normal_stories = jira.find_stories_to_process(
            normal_selection, max_results=max_stories, sprint_override=args.sprint
        )

        regen_stories = []
        if regen_selection:
            logger.info("Scan pass 2/3: looking for stories with ai-regenerate label")
            regen_stories = jira.find_stories_to_process(
                regen_selection, max_results=max_stories, sprint_override=args.sprint
            )
        else:
            logger.info(
                "No 'regenerate_selection' config — skipping regen pass. "
                "Add 'agents.agent2_coder.regenerate_selection' to enable."
            )

        update_stories = []
        if update_selection:
            logger.info("Scan pass 3/3: looking for stories with ai-update label")
            update_stories = jira.find_stories_to_process(
                update_selection, max_results=max_stories, sprint_override=args.sprint
            )
        else:
            logger.info(
                "No 'update_selection' config — skipping update pass. "
                "Add 'agents.agent2_coder.update_selection' to enable incremental updates."
            )

        total_count = len(normal_stories) + len(regen_stories) + len(update_stories)
        if total_count == 0:
            logger.info(
                f"No stories found. "
                f"Normal: required={normal_selection.get('required_labels', [])}, "
                f"excluded={normal_selection.get('excluded_labels', [])}. "
                f"Regen requires 'ai-regenerate'. "
                f"Update requires 'ai-update'. "
                f"Tip: ensure parent story has 'ai-processed' AND 'human-approved' labels."
            )
            print("\n[OK] Agent 2 scan complete -- no stories to process.")
            sys.exit(0)

        logger.info(
            f"Found {len(normal_stories)} normal + {len(regen_stories)} regen "
            f"+ {len(update_stories)} update = {total_count} stories to process."
        )

        results = []
        for story in normal_stories:
            try:
                result = run(story["key"], dry_run=args.dry_run, is_regenerate=False)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed processing {story['key']} (normal): {e}", exc_info=True)
                results.append({
                    "story_id": story["key"],
                    "status": "failed",
                    "mode": "normal",
                    "error": str(e),
                })

        for story in regen_stories:
            if any(r.get("story_id") == story["key"] for r in results):
                logger.warning(
                    f"Skipping {story['key']} in regen pass — already processed in normal pass. "
                    "Check config: regenerate_selection should require ai-regenerate label."
                )
                continue
            try:
                result = run(story["key"], dry_run=args.dry_run, is_regenerate=True)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed processing {story['key']} (regen): {e}", exc_info=True)
                results.append({
                    "story_id": story["key"],
                    "status": "failed",
                    "mode": "regenerate",
                    "error": str(e),
                })

        for story in update_stories:
            if any(r.get("story_id") == story["key"] for r in results):
                logger.warning(
                    f"Skipping {story['key']} in update pass — already processed earlier. "
                    "Check config: update_selection should require ai-update and exclude ai-regenerate."
                )
                continue
            try:
                result = run_update(story["key"], dry_run=args.dry_run)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed processing {story['key']} (update): {e}", exc_info=True)
                results.append({
                    "story_id": story["key"],
                    "status": "failed",
                    "mode": "update",
                    "error": str(e),
                })

        _print_scan_summary(results)

        # A failed story must not report success. Scan mode deliberately
        # catches per-story errors so one bad story cannot halt the batch,
        # but the process still has to signal failure - otherwise a cron
        # run goes green while producing nothing, indefinitely.
        failed = [r for r in results if r.get("status") == "failed"]
        if failed:
            logger.error(
                "%d of %d story/stories failed: %s",
                len(failed), len(results),
                ", ".join(str(r.get('story_id')) for r in failed),
            )
            sys.exit(1)

    except SystemExit:
        raise               # our own exit(1) above - not an unexpected error
    except Exception as e:
        logger.error(f"Agent 2 failed: {type(e).__name__}: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()