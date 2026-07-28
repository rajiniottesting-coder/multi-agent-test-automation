"""
Orphan code cleanup for incremental updates.

When the ai-update flow removes scenarios (because their Jira Test Cases
were deleted), dead code is left behind:

  1. Step-def functions whose @given/@when/@then decorators matched ONLY
     phrases in the removed scenarios. (Note: this module returns the list,
     but in production the wider ai-update flow already regenerates the
     entire step-def file from scratch via _regenerate_step_defs_whole,
     which makes the LLM omit these naturally. We still detect them here
     for audit/reporting purposes and as a safety net.)

  2. Page-object methods that were called ONLY from those dead step-def
     functions. These are NOT covered by step-def regeneration — page
     object files are preserved by the ai-update flow on purpose, so a
     human gets to keep useful methods even after deletion.

This module's goal is the second case: find dead page-object methods and
comment them out (not delete) so a reviewer sees the audit trail.

DESIGN PRINCIPLES (must hold for any project, independent of the app under test):
  - No hardcoded class names, file paths, or method names.
  - No assumptions about app domain (banking, CMS, e-commerce all work).
  - Conservative: prefer false negatives ("might be alive") over false
    positives ("definitely dead"). Comment-out is reversible; trust the
    human reviewer.
  - Works for any pytest-bdd project using POM + page objects.
"""
from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from validators.gherkin_analyzer import (
    _extract_decorator_phrases,
    _extract_feature_steps,
    _phrase_matches,
)

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════
# Data classes
# ════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class OrphanStepDef:
    """A step-def function that was only used by removed scenarios."""
    file_path: str           # e.g. "tests/step_defs/test_login.py"
    function_name: str       # e.g. "verify_recovery_email_sent"
    decorator_phrase: str    # e.g. "I should receive a recovery email"
    decorator_kind: str      # 'given' | 'when' | 'then'
    line_start: int          # 1-indexed line where the function def starts
    line_end: int            # 1-indexed line where the function ends


@dataclass(frozen=True)
class OrphanPageMethod:
    """A page-object method that was only called by orphan step defs."""
    file_path: str           # e.g. "pages/login_page.py"
    class_name: str          # e.g. "LoginPage"
    method_name: str         # e.g. "click_recover_password"
    line_start: int
    line_end: int


# ════════════════════════════════════════════════════════════════════
# Step 1: Extract steps from JUST the removed scenarios
# ════════════════════════════════════════════════════════════════════

def extract_steps_in_removed_scenarios(
    old_feature_content: str,
    removed_jira_keys: list[str],
) -> list[tuple[str, str]]:
    """Return [(keyword, phrase), ...] for steps inside the removed scenarios.

    Uses the JIRA marker comments (`# JIRA: KEY hash:...`) in the OLD feature
    content to identify which scenario block belongs to which Jira key, then
    extracts just those blocks' steps with And/But resolved.
    """
    if not removed_jira_keys:
        return []

    # Lazy import to avoid circular dependency (agent2_coder imports this module).
    from agents.agent2_coder import parse_feature_file

    _header, blocks = parse_feature_file(old_feature_content)
    target_keys = set(removed_jira_keys)

    all_steps: list[tuple[str, str]] = []
    for block in blocks:
        if block.kind != "scenario":
            continue
        if block.jira_key not in target_keys:
            continue
        # Reconstruct this scenario's text and parse its steps.
        # _extract_feature_steps handles And/But inheritance correctly.
        scenario_text = block.text()
        all_steps.extend(_extract_feature_steps(scenario_text))

    return all_steps


# ════════════════════════════════════════════════════════════════════
# Step 2: Detect orphan step-def functions
# ════════════════════════════════════════════════════════════════════

def find_orphan_step_defs(
    step_def_files: dict[str, str],
    steps_in_removed_scenarios: list[tuple[str, str]],
    steps_in_surviving_feature: list[tuple[str, str]],
) -> list[OrphanStepDef]:
    """Identify step-def functions used ONLY by removed scenarios.

    Args:
        step_def_files: {file_path: file_content} for all step_def files
            in the project. Typically just one file per feature, but
            the function handles multiple correctly.
        steps_in_removed_scenarios: from extract_steps_in_removed_scenarios()
        steps_in_surviving_feature: from _extract_feature_steps() on the
            POST-removal feature content.

    Returns:
        List of OrphanStepDef objects. Functions whose decorators only
        match removed-scenario steps and not any surviving step.
    """
    orphans: list[OrphanStepDef] = []

    for file_path, content in step_def_files.items():
        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            logger.warning(
                f"Cannot parse {file_path} as Python — skipping orphan detection. {e}"
            )
            continue

        decorators_in_file = _extract_decorator_phrases(content)

        # Walk top-level functions in the file. Each function may carry
        # one or more step decorators. A function is orphan iff EVERY
        # decorator's phrase matches some removed step AND no decorator
        # matches any surviving step.
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            decorator_info = _decorators_on_function(node, decorators_in_file)
            if not decorator_info:
                # Function has no step decorators — not a step def, not relevant.
                continue

            matches_a_removed = False
            matches_a_surviving = False
            primary_decorator: Optional[tuple[str, str, str]] = None

            for kind, phrase, parser_type in decorator_info:
                # Match against removed steps
                for r_kw, r_phrase in steps_in_removed_scenarios:
                    if r_kw == kind and _phrase_matches(r_phrase, phrase, parser_type):
                        matches_a_removed = True
                        if primary_decorator is None:
                            primary_decorator = (kind, phrase, parser_type)
                        break
                # Match against surviving steps
                for s_kw, s_phrase in steps_in_surviving_feature:
                    if s_kw == kind and _phrase_matches(s_phrase, phrase, parser_type):
                        matches_a_surviving = True
                        break
                if matches_a_surviving:
                    break  # Definitive: not orphan; stop checking other decorators.

            if matches_a_removed and not matches_a_surviving:
                # Confirmed orphan
                line_end = _function_end_line(node, content)
                kind, phrase, _ptype = primary_decorator  # type: ignore[misc]
                orphans.append(OrphanStepDef(
                    file_path=file_path,
                    function_name=node.name,
                    decorator_phrase=phrase,
                    decorator_kind=kind,
                    line_start=node.lineno,
                    line_end=line_end,
                ))

    return orphans


def _decorators_on_function(
    func_node: ast.FunctionDef,
    all_decorators: list[tuple[str, str, str]],
) -> list[tuple[str, str, str]]:
    """Return the (kind, phrase, parser_type) tuples for decorators on this function.

    The all_decorators list (from _extract_decorator_phrases) is the
    file-wide list. We match a decorator to a function by checking if any
    of the function's @decorator references one of the step-def names.
    """
    # We need to match by inspecting the AST decorator nodes themselves.
    # Each decorator AST node corresponds to one entry in all_decorators
    # in source order. The simplest correct approach: walk the function's
    # decorators in source order, and for each one that looks like a
    # @given/@when/@then call, pair it with the next-in-order entry from
    # all_decorators.
    #
    # But all_decorators is file-wide, not function-scoped. So we filter
    # by source line: a decorator with end_lineno < func_node.lineno
    # AND start within the few lines immediately preceding the function
    # is one of this function's decorators.
    result: list[tuple[str, str, str]] = []
    for dec_node in func_node.decorator_list:
        if not _is_step_decorator(dec_node):
            continue
        # Find the matching entry in all_decorators by line number.
        # The decorators in the source appear in the same order as in
        # all_decorators, but we can't rely on indexing — we use line info.
        dec_line = getattr(dec_node, 'lineno', None)
        if dec_line is None:
            continue
        # Take the first decorator from all_decorators whose source position
        # could match this line. Since we can't reliably get line info out
        # of the regex-based extractor, we use a different strategy:
        # match by phrase content. Get the phrase from the AST and look it up.
        phrase_from_ast = _phrase_from_decorator_ast(dec_node)
        if phrase_from_ast is None:
            continue
        # Find matching entry
        for kind, phrase, parser_type in all_decorators:
            if phrase == phrase_from_ast:
                result.append((kind, phrase, parser_type))
                break

    return result


def _is_step_decorator(dec_node) -> bool:
    """True if this AST decorator node is @given(...), @when(...), or @then(...)."""
    if isinstance(dec_node, ast.Call):
        func = dec_node.func
        if isinstance(func, ast.Name) and func.id in ('given', 'when', 'then'):
            return True
    return False


def _phrase_from_decorator_ast(dec_node: ast.Call) -> Optional[str]:
    """Extract the phrase string from an @given/@when/@then decorator AST node.

    Handles three forms:
      @given("plain string")
      @given(parsers.parse("template {x}"))
      @given(parsers.re(r"pattern"))
    """
    if not dec_node.args:
        return None
    arg = dec_node.args[0]
    # @given("string literal")
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    # @given(parsers.parse("template"))
    if isinstance(arg, ast.Call):
        if arg.args and isinstance(arg.args[0], ast.Constant) and isinstance(arg.args[0].value, str):
            return arg.args[0].value
    return None


def _function_end_line(func_node: ast.FunctionDef, source: str) -> int:
    """Return the last line of a function body. Uses end_lineno when available."""
    if hasattr(func_node, 'end_lineno') and func_node.end_lineno is not None:
        return func_node.end_lineno
    # Fallback for older Python: walk source from function start and find next
    # top-level def/class/EOF.
    lines = source.splitlines()
    func_indent = len(lines[func_node.lineno - 1]) - len(lines[func_node.lineno - 1].lstrip())
    for i in range(func_node.lineno, len(lines)):
        line = lines[i]
        if line.strip() == "":
            continue
        current_indent = len(line) - len(line.lstrip())
        if current_indent <= func_indent and i > func_node.lineno:
            return i  # 1-indexed line BEFORE the next definition
    return len(lines)


# ════════════════════════════════════════════════════════════════════
# Step 3: Detect orphan page-object methods
# ════════════════════════════════════════════════════════════════════

def find_orphan_page_methods(
    orphan_step_defs: list[OrphanStepDef],
    step_def_files: dict[str, str],
    page_object_files: dict[str, str],
) -> list[OrphanPageMethod]:
    """Identify page-object methods called ONLY from orphan step defs.

    Strategy: collect all method names called inside orphan step def bodies.
    Then, for each page object class, find methods whose name appears in
    that collection AND does not appear in ANY surviving step def.

    Args:
        orphan_step_defs: from find_orphan_step_defs()
        step_def_files: full {path: content} map for ALL step def files
        page_object_files: full {path: content} map for ALL page object files

    Returns:
        List of OrphanPageMethod objects.
    """
    if not orphan_step_defs:
        return []

    # Step 3a: collect method calls inside orphan step def function bodies.
    # We identify orphan funcs by their (file_path, function_name) tuple
    # rather than by line number — name is more robust to edits.
    orphan_function_keys: set[tuple[str, str]] = {
        (o.file_path, o.function_name) for o in orphan_step_defs
    }
    called_from_orphans: set[str] = set()

    for file_path, content in step_def_files.items():
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue
        for func in ast.walk(tree):
            if not isinstance(func, ast.FunctionDef):
                continue
            if (file_path, func.name) not in orphan_function_keys:
                continue
            for sub in ast.walk(func):
                if isinstance(sub, ast.Attribute):
                    # captures things like `login_page.click_button(...)` → 'click_button'
                    called_from_orphans.add(sub.attr)

    # Step 3b: collect method calls from SURVIVING step defs. These methods
    # are definitely alive even if orphan defs also called them.
    called_from_surviving: set[str] = set()
    for file_path, content in step_def_files.items():
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue
        for func in ast.walk(tree):
            if not isinstance(func, ast.FunctionDef):
                continue
            if (file_path, func.name) in orphan_function_keys:
                continue  # Skip orphan funcs — only surviving ones count here.
            for sub in ast.walk(func):
                if isinstance(sub, ast.Attribute):
                    called_from_surviving.add(sub.attr)

    # Method names that are ONLY called from orphan funcs and not from
    # any surviving step def are candidates for orphan page methods.
    candidate_method_names = called_from_orphans - called_from_surviving
    if not candidate_method_names:
        return []

    # Step 3c: find these methods on page-object classes.
    orphans: list[OrphanPageMethod] = []
    for file_path, content in page_object_files.items():
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue
        for cls in ast.walk(tree):
            if not isinstance(cls, ast.ClassDef):
                continue
            for member in cls.body:
                if not isinstance(member, ast.FunctionDef):
                    continue
                if member.name.startswith('_'):
                    continue  # private/dunder — leave alone
                if member.name in candidate_method_names:
                    line_end = _function_end_line(member, content)
                    orphans.append(OrphanPageMethod(
                        file_path=file_path,
                        class_name=cls.name,
                        method_name=member.name,
                        line_start=member.lineno,
                        line_end=line_end,
                    ))

    return orphans


# ════════════════════════════════════════════════════════════════════
# Step 4: Comment-out edits (reversible)
# ════════════════════════════════════════════════════════════════════

ORPHAN_BANNER_TEMPLATE = (
    "# AI-ORPHAN: this {what} appears to no longer be used after "
    "scenario(s) {keys} were removed from Jira. Review before deleting."
)


def comment_out_orphan_step_defs(
    file_content: str,
    orphans_in_this_file: list[OrphanStepDef],
    removed_jira_keys: list[str],
) -> str:
    """Return the step-def file content with orphan funcs commented out.

    Each orphan function (decorators + body) gets prefixed with `# ` and
    preceded by an AI-ORPHAN banner. Imports and shared fixtures are
    untouched.
    """
    if not orphans_in_this_file:
        return file_content
    return _comment_out_blocks(
        file_content,
        blocks=[(o.line_start, o.line_end) for o in orphans_in_this_file],
        what="step-def function",
        keys=removed_jira_keys,
    )


def comment_out_orphan_page_methods(
    file_content: str,
    orphans_in_this_file: list[OrphanPageMethod],
    removed_jira_keys: list[str],
) -> str:
    """Return the page-object file content with orphan methods commented out."""
    if not orphans_in_this_file:
        return file_content
    return _comment_out_blocks(
        file_content,
        blocks=[(o.line_start, o.line_end) for o in orphans_in_this_file],
        what="page-object method",
        keys=removed_jira_keys,
    )


def _comment_out_blocks(
    file_content: str,
    blocks: list[tuple[int, int]],
    what: str,
    keys: list[str],
) -> str:
    """Comment out the given line-ranges, prefixing each block with a banner.

    Blocks are 1-indexed inclusive ranges (line_start, line_end). Decorators
    attached to a function are included automatically by scanning UP from
    line_start for contiguous @decorator and # comment lines (but NOT past
    a blank line, to avoid touching unrelated code above).
    """
    if not blocks:
        return file_content

    lines = file_content.splitlines(keepends=True)
    line_set: set[int] = set()  # 1-indexed line numbers to comment out
    block_starts: list[int] = []  # original starts (for banner placement)

    for start, end in blocks:
        # Walk upward to include @decorators and contiguous comment lines
        # immediately above. Stop at blank line or non-decorator/non-comment.
        actual_start = start
        i = start - 2  # 0-indexed previous line
        while i >= 0:
            stripped = lines[i].strip()
            if stripped == "":
                break
            if stripped.startswith('@') or stripped.startswith('#'):
                actual_start = i + 1  # 1-indexed
                i -= 1
                continue
            break
        block_starts.append(actual_start)
        for ln in range(actual_start, end + 1):
            line_set.add(ln)

    # Build output: insert banner before each block, comment out each line in line_set.
    banner_keys = ", ".join(keys) if keys else "(unknown)"
    banner = ORPHAN_BANNER_TEMPLATE.format(what=what, keys=banner_keys)

    output: list[str] = []
    for i, line in enumerate(lines, start=1):
        if i in block_starts:
            # Insert banner above this line, with the same indent as the line.
            indent = line[: len(line) - len(line.lstrip())]
            output.append(f"{indent}{banner}\n")
        if i in line_set:
            indent = line[: len(line) - len(line.lstrip())]
            stripped_body = line[len(indent):]
            if stripped_body == "" or stripped_body == "\n":
                # Blank line inside a block — keep as-is for readability.
                output.append(line)
            else:
                output.append(f"{indent}# {stripped_body}")
        else:
            output.append(line)

    return "".join(output)


# ════════════════════════════════════════════════════════════════════
# Top-level orchestration helper
# ════════════════════════════════════════════════════════════════════

def cleanup_orphans_after_removal(
    old_feature_content: str,
    new_feature_content: str,
    removed_jira_keys: list[str],
    step_def_files: dict[str, str],
    page_object_files: dict[str, str],
    reserved_file_paths: Optional[set[str]] = None,
) -> tuple[dict[str, str], dict[str, str], list[OrphanStepDef], list[OrphanPageMethod]]:
    """Find and comment out orphan step defs and page methods.

    Top-level entry point. Call this from run_update() AFTER removing
    orphan scenarios from the feature file.

    Args:
        old_feature_content: feature file BEFORE scenario removal
        new_feature_content: feature file AFTER scenario removal
        removed_jira_keys: list of Jira keys whose scenarios were removed
        step_def_files: {path: content} for ALL project step def files
        page_object_files: {path: content} for page object files we are
            ALLOWED to modify (i.e., extendable_paths from config). Files
            outside this set won't be examined at all.
        reserved_file_paths: optional set of files to leave completely alone.
            base_page.py and reference files typically go here.

    Returns:
        4-tuple:
          (updated_step_def_files, updated_page_object_files,
           orphan_step_defs_found, orphan_page_methods_found)
    """
    if not removed_jira_keys:
        return step_def_files, page_object_files, [], []

    reserved = reserved_file_paths or set()

    # Step 1: extract steps from the removed scenarios
    removed_steps = extract_steps_in_removed_scenarios(
        old_feature_content, removed_jira_keys
    )
    if not removed_steps:
        logger.info(
            "No steps found inside removed scenarios — nothing to clean up."
        )
        return step_def_files, page_object_files, [], []

    # Step 2: extract steps from the surviving feature
    surviving_steps = _extract_feature_steps(new_feature_content)

    # Step 3: find orphan step defs
    orphan_defs = find_orphan_step_defs(
        step_def_files=step_def_files,
        steps_in_removed_scenarios=removed_steps,
        steps_in_surviving_feature=surviving_steps,
    )
    logger.info(
        f"Orphan step-def detection: {len(orphan_defs)} found "
        f"after removing {len(removed_jira_keys)} scenario(s)."
    )

    # Step 4: find orphan page methods (only in non-reserved files)
    examinable_pages = {
        p: c for p, c in page_object_files.items() if p not in reserved
    }
    orphan_methods = find_orphan_page_methods(
        orphan_step_defs=orphan_defs,
        step_def_files=step_def_files,
        page_object_files=examinable_pages,
    )
    logger.info(
        f"Orphan page-method detection: {len(orphan_methods)} found."
    )

    # Step 5: apply comment-outs.
    # Note: orphan step defs are reported but NOT commented out by default,
    # because the wider ai-update flow regenerates the entire step-def file
    # via the LLM (see _regenerate_step_defs_whole). Commenting them out
    # here would race with that regeneration.
    #
    # Page methods ARE commented out — page object files are preserved by
    # the ai-update flow, so this is the ONLY place dead methods get caught.
    updated_pages = dict(page_object_files)  # copy
    methods_by_file: dict[str, list[OrphanPageMethod]] = {}
    for m in orphan_methods:
        methods_by_file.setdefault(m.file_path, []).append(m)

    for file_path, methods in methods_by_file.items():
        # Sort by start line DESCENDING so editing one block doesn't shift
        # line numbers for the next.
        methods_sorted = sorted(methods, key=lambda m: m.line_start, reverse=True)
        updated_pages[file_path] = comment_out_orphan_page_methods(
            updated_pages[file_path], methods_sorted, removed_jira_keys
        )

    return step_def_files, updated_pages, orphan_defs, orphan_methods