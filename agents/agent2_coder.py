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
"""
import argparse
import ast
import hashlib
import logging
import re
import sys
from dataclasses import dataclass, field
from typing import Optional
import yaml

from agents.app_context import AppContext
from agents.jira_client import JiraClient
from agents.github_client import GitHubClient
from agents.import_validator import validate_imports_resolvable
from agents.method_resolution_validator import validate_method_resolution
from agents.llm_client import LLMClient
from agents.schemas import CodePlan, GeneratedFile, CodeGenerationOutput
from agents.test_inventory import (
    scan_features_dir,
    filter_duplicate_test_cases,
    validate_filename_consistency,
    validate_feature_file_structure,
    validate_step_definitions_complete,
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


def load_test_cases_for_story(jira: JiraClient, story_key: str) -> list[dict]:
    jql = (
        f'project = {jira.project_key} AND issuetype = "Test Case" '
        f'AND issue in linkedIssues("{story_key}")'
    )
    logger.info(f"Fetching test cases linked to {story_key}: {jql}")
    issues = jira.client.enhanced_search_issues(jql, maxResults=50)

    test_cases = [
        {
            "key": issue.key,
            "summary": issue.fields.summary,
            "description": issue.fields.description or "",
        }
        for issue in issues
    ]
    logger.info(f"Found {len(test_cases)} test cases linked to {story_key}")
    return test_cases


def format_test_cases_for_prompt(test_cases: list[dict]) -> str:
    blocks = [
        f"## {tc['key']}: {tc['summary']}\n\n{tc['description']}\n"
        for tc in test_cases
    ]
    return "\n---\n".join(blocks)


def extract_code_from_response(response_text: str) -> str:
    """Extract code from a markdown response. Handles fenced and bare code."""
    pattern = r"```(?:\w+)?\n?(.*?)```"
    matches = re.findall(pattern, response_text, re.DOTALL)
    if matches:
        return matches[0].strip() + "\n"
    return response_text.strip() + "\n"


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


def _summarize_validator_feedback(errors: list[str]) -> str:
    """Compact validator errors into a prompt-friendly summary.

    For small error counts (<= _MAX_FEEDBACK_ERRORS_VERBATIM) we just
    extract the salient bit — the Gherkin step phrase that needs a
    decorator — and bullet-list them. For large counts we show the
    first N verbatim plus a count of the remaining, so the LLM sees
    the *pattern* rather than getting buried in repetition.

    This is app-agnostic — operates only on the validator's own
    error strings, no project-specific knowledge.
    """
    # Try to extract just the actionable phrase from each error string
    # (the part after "feature step `..." up to the closing backtick)
    step_phrase_pattern = re.compile(r"feature step `([^`]+)`")

    extracted: list[str] = []
    for err in errors:
        match = step_phrase_pattern.search(err)
        if match:
            extracted.append(match.group(1))
        else:
            # Non-step-coverage error (e.g., import error) — keep first 150 chars
            extracted.append(err.split(":", 2)[-1].strip()[:150])

    if len(extracted) <= _MAX_FEEDBACK_ERRORS_VERBATIM:
        return "\n".join(f"  - {phrase}" for phrase in extracted)

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


def _is_degraded_regeneration(new_content: str, prior_content: str) -> bool:
    """Detect if a regeneration produced clearly worse output than before.

    Signals of degradation:
      - New content fails to parse as Python (LLM gave up mid-output)
      - New content is dramatically smaller than prior (truncated stub)

    Used to abort the repair loop early instead of compounding garbage
    on garbage. App-agnostic — looks only at the output itself.
    """
    if not new_content or len(new_content) < _DEGRADED_OUTPUT_CHAR_THRESHOLD:
        return True

    try:
        ast.parse(new_content)
    except SyntaxError:
        return True

    # If new content is less than 30% the size of the prior real attempt,
    # that's a strong signal the LLM is producing fragments
    if (
        prior_content
        and _looks_like_useful_python(prior_content)
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

        feedback_block = (
            f"\n\n# CRITICAL: Fix these validation issues\n\n"
            f"Your previous attempt was rejected. Issues:\n\n"
            f"{feedback_summary}\n\n"
            f"REQUIREMENTS:\n"
            f"- Every Gherkin step in the feature file MUST have a matching "
            f"  @given/@when/@then decorator (And/But inherits from prior keyword)\n"
            f"- Output a COMPLETE, working Python file — not a fragment\n"
            f"- Use parsers.parse() for parameterized steps, plain strings otherwise"
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
    sibling_block = ""
    if file_plan.file_type == "step_definitions" and already_generated:
        sibling_block = _build_sibling_page_object_context(already_generated)
        if sibling_block:
            logger.info(
                f"Stage 2: injecting method signatures from "
                f"{sum(1 for f in already_generated if f.file_path.startswith('pages/'))} "
                f"sibling page-object file(s) into step-def prompt."
            )

    prompt_template = load_prompt("agent2_coder_generate.md")
    user_prompt = (
        prompt_template
        .replace("{app_name}", ctx.name)
        .replace("{file_path}", file_plan.file_path)
        .replace("{file_type}", file_plan.file_type)
        .replace("{file_purpose}", file_plan.purpose)
        .replace("{feature_name}", plan.feature_name)
        .replace("{existing_file_block}", existing_block)
        .replace("{validator_feedback_block}", feedback_block)
        .replace("{sibling_page_objects_block}", sibling_block)
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
    response = llm.invoke_text(
        system_prompt="You are a Senior Test Automation Engineer (SDET). Produce complete, working code.",
        user_prompt=user_prompt,
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
        raise ValueError(
            f"LLM returned suspiciously short content for "
            f"'{file_plan.file_path}' ({len(content)} chars). This usually "
            f"means the model exhausted its output token budget on internal "
            f"reasoning ('thinking') before producing visible output. "
            f"For Pro models, ensure max_output_tokens is at least 32768 "
            f"(see _code_gen_max_output_tokens in llm_client.py). "
            f"Aborting before we commit an empty file."
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
            f"usually means the LLM model is too weak (try gemini-2.5-flash "
            f"instead of -lite) or the feature file has unusually complex "
            f"steps. See logs for details."
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


# ---------------------------------------------------------------------------
# Self-correcting retry loop (handles weak-model step coverage failures)
# ---------------------------------------------------------------------------
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

    Returns: {file_path: [error_messages_for_that_file]}
    """
    grouped: dict[str, list[str]] = {}
    # Match `<words> error in '<path>':` regardless of which validator emitted it
    pattern = re.compile(r"error in '([^']+)':")
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
    errors.extend(validate_feature_file_structure(generated_files))
    errors.extend(validate_step_definitions_complete(generated_files))
    errors.extend(validate_imports_resolvable(generated_files, PROJECT_ROOT))
    errors.extend(validate_method_resolution(generated_files, PROJECT_ROOT))
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
        Weaker LLMs (gemini-2.5-flash-lite specifically) often slip up.
        Validators catch it, but the old behavior was to abort the whole
        run, wasting work already done on other files. Retrying ONLY the
        broken file is targeted, cheap, and usually succeeds.

    Cost: each retry = 1 LLM call per broken file. Capped at `max_retries`
    iterations. Worst case for a typical 1-broken-file run is 2 extra calls.
    """
    for attempt in range(1, max_retries + 1):
        all_errors = _collect_repairable_errors(generated_files)
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
                if _is_degraded_regeneration(repaired_content, prior_content):
                    logger.error(
                        f"  Repair produced degraded output for "
                        f"'{step_def_path}' ({len(repaired_content)} chars vs "
                        f"prior {len(prior_content)} chars, syntax-valid="
                        f"{_looks_like_useful_python(repaired_content)}). "
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


def _resolve_unused_revision_branch(gh: GitHubClient, base_branch: str) -> str:
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
    every generated feature file. Idempotent: existing correct markers
    are not duplicated; existing markers with stale hashes are refreshed.

    Scenarios whose title matches no Test Case summary are left
    unmarkered (fail loud later, not guess).
    """
    if not test_cases:
        return generated_files

    def _norm(s: str) -> str:
        return re.sub(r"\s+", " ", (s or "").strip().lower())

    title_to_tc = {_norm(tc.get("summary", "")): tc for tc in test_cases}

    rewritten = []
    for gf in generated_files:
        if not gf.file_path.endswith(".feature"):
            rewritten.append(gf)
            continue
        new_content = _inject_markers_into_feature(gf.content, title_to_tc)
        if new_content != gf.content:
            logger.info(f"Injected JIRA markers into {gf.file_path}")
        rewritten.append(GeneratedFile(
            file_path=gf.file_path,
            content=new_content,
            is_new_file=gf.is_new_file,
            purpose=gf.purpose,
        ))
    return rewritten


def _inject_markers_into_feature(content: str, title_to_tc: dict) -> str:
    """Add/refresh JIRA markers above each scenario, idempotently."""
    def _norm(s: str) -> str:
        return re.sub(r"\s+", " ", (s or "").strip().lower())

    lines = content.splitlines(keepends=True)
    out: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        is_scenario = (
            stripped.startswith("Scenario Outline:")
            or stripped.startswith("Scenario:")
        )
        if not is_scenario:
            out.append(line)
            continue

        # Most recent non-blank line in `out` — is it already a marker?
        j = len(out) - 1
        while j >= 0 and out[j].strip() == "":
            j -= 1
        existing_marker = parse_marker(out[j]) if j >= 0 else None

        _kw, _, title = stripped.partition(":")
        tc = title_to_tc.get(_norm(title))
        indent = line[: len(line) - len(line.lstrip())]

        if existing_marker is not None:
            # Refresh the hash if we can match the title to a current TC
            if tc is not None:
                fresh = format_marker(tc["key"], tc.get("description", ""))
                old_indent = out[j][: len(out[j]) - len(out[j].lstrip())]
                out[j] = f"{old_indent}{fresh}\n"
            out.append(line)
            continue

        if tc is not None:
            out.append(f"{indent}{format_marker(tc['key'], tc.get('description', ''))}\n")
        out.append(line)
    return "".join(out)


# ---------------------------------------------------------------------------
# Incremental update flow (ai-update label) — surgical scenario splicing
# ---------------------------------------------------------------------------
def _find_unused_update_branch(gh: GitHubClient, base_branch: str) -> str:
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
) -> str:
    """Regenerate the step-defs file whole based on the spliced feature."""
    from agents.schemas import FilePlan

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
    return generate_file_content(
        llm, file_plan, minimal_plan,
        synthetic_tcs, references, page_inventory, ctx,
    )


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

    jira = JiraClient()
    jira.get_story(story_id)
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

    gh = GitHubClient()
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
    page_inventory = ctx.load_page_inventory_json()
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
    logger.info(f"Regenerating {step_defs_path} based on spliced feature file...")
    new_step_defs_content = _regenerate_step_defs_whole(
        llm, feature_file_path, spliced_content,
        step_defs_path, ctx, references, page_inventory,
    )

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
            purpose="Incremental update: regenerated step defs",
        ),
    ]

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
    pr_body_parts.append(
        "\n\nUnchanged scenarios are preserved byte-for-byte. "
        "Page objects are not modified by ai-update; if new methods are "
        "needed, use the `ai-regenerate` label for a full regeneration."
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
    return {
        "story_id": story_id,
        "status": "update_pr_opened",
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
    jira = JiraClient()
    jira.get_story(story_id)
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
    page_inventory = ctx.load_page_inventory_json()
    llm = LLMClient(temperature=0.2)

    # 3. STAGE 1: PLAN
    plan = build_plan(llm, new_test_cases, references, page_inventory, ctx)

    # 4. STAGE 2: GENERATE PER-FILE CONTENT
    # Order page objects BEFORE step definitions so the step-def prompt
    # can include the actual method signatures from page objects already
    # generated in this batch (Hotfix v5 — prevents cross-file naming
    # mismatches like `click_logout()` vs `click_logout_link()`).
    ordered_files = _sort_files_for_generation(plan.files_to_create)
    generated_files: list[GeneratedFile] = []
    for file_plan in ordered_files:
        try:
            content = generate_file_content(
                llm, file_plan, plan, new_test_cases, references, page_inventory, ctx,
                already_generated=generated_files,
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
    assert_valid_branch_for_pipeline(output.branch_name)

    gh = GitHubClient()

    # REGENERATE: append -revN suffix so we don't reuse the existing branch.
    if is_regenerate:
        new_branch_name = _resolve_unused_revision_branch(gh, output.branch_name)
        logger.info(
            f"Regeneration: changed branch from '{output.branch_name}' to "
            f"'{new_branch_name}' to preserve old PR as historical record"
        )
        output.branch_name = new_branch_name

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

    if is_regenerate:
        regenerate_label = agent_config.get("regenerate_label", "ai-regenerate")
        jira.remove_label(story_id, regenerate_label)
        logger.info(f"Removed label '{regenerate_label}' from {story_id} (one-shot consumed)")

    result = {
        "story_id": story_id,
        "files_generated": len(output.files),
        "branch_name": output.branch_name,
        "pr_url": pr_url,
        "status": "pr_opened",
    }

    logger.info(f"=== Agent 2 (Coder) complete. PR: {pr_url} ===")
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _print_scan_summary(results: list[dict]) -> None:
    print("\n" + "=" * 60)
    print(f"[OK] Agent 2 scan finished -- processed {len(results)} stories")
    for r in results:
        status = r.get("status", "unknown")
        if status == "pr_opened":
            marker = "OK"
        elif status == "skipped_all_duplicates":
            marker = "SKIP"
        elif status == "failed":
            marker = "FAIL"
        else:
            marker = "??"
        pr_info = f" -> {r.get('pr_url')}" if r.get("pr_url") else ""
        print(f"   [{marker}] {r.get('story_id')}: {status}{pr_info}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Agent 2 (Coder): Generate test code from Jira test cases"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--story", help="Process all test cases of a specific story")
    group.add_argument("--scan", action="store_true", help="Scan mode (config-driven)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Don't create branch/PR, just preview")
    parser.add_argument("--update", action="store_true",
                        help="Treat --story as an INCREMENTAL UPDATE: splice "
                             "only modified/new scenarios, leave others untouched. "
                             "Requires existing JIRA markers in the feature file.")
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

        jira = JiraClient()

        logger.info("Scan pass 1/3: looking for first-time stories (normal mode)")
        normal_stories = jira.find_stories_to_process(normal_selection, max_results=max_stories)

        regen_stories = []
        if regen_selection:
            logger.info("Scan pass 2/3: looking for stories with ai-regenerate label")
            regen_stories = jira.find_stories_to_process(regen_selection, max_results=max_stories)
        else:
            logger.info(
                "No 'regenerate_selection' config — skipping regen pass. "
                "Add 'agents.agent2_coder.regenerate_selection' to enable."
            )

        update_stories = []
        if update_selection:
            logger.info("Scan pass 3/3: looking for stories with ai-update label")
            update_stories = jira.find_stories_to_process(update_selection, max_results=max_stories)
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

    except Exception as e:
        logger.error(f"Agent 2 failed: {type(e).__name__}: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()