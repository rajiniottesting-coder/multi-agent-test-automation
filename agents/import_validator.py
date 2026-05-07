"""
Import resolution validator.

PURPOSE:
    Verify that every `from X import Y` and `import X` in generated Python
    files (step defs, page objects, etc.) actually refers to something that
    will exist when the PR is merged. Catches the failure mode where the
    LLM hallucinates a page object class import for a file that was never
    planned and never created.

THE FAILURE MODE THIS CATCHES:
    Step def files imported `pages.product_detail_page.ProductDetailPage`
    but `pages/product_detail_page.py` was never planned, never created,
    and didn't exist in the repo. Tests crashed at collection time with
    `ModuleNotFoundError`.

DESIGN PRINCIPLES (app-agnostic, reusable across projects):

    1. NO HARDCODED PROJECT KNOWLEDGE.
       Stdlib detection uses Python's built-in `sys.stdlib_module_names`.
       Third-party detection reads requirements.txt — whatever's listed is
       considered importable.
       Repo-internal imports check the actual filesystem at the project
       root and the planned-files batch.

    2. STATIC ANALYSIS ONLY.
       Uses Python's `ast` module to parse imports. No code execution.
       Safe to run on any input.

    3. CLEAR ERROR STRINGS.
       Errors include the exact import statement, what was searched,
       and what's available — formatted in the same style as the
       coverage validator so the existing repair loop can consume them.

    4. SCOPE IS LIMITED.
       Only flags imports that clearly cannot resolve. Doesn't try to
       verify that the imported NAME (e.g., `ProductDetailPage` class)
       exists inside a file — that would require executing the file.
       Module-level resolution is enough to catch the common LLM mistake.

USAGE:
    from agents.import_validator import validate_imports_resolvable
    errors = validate_imports_resolvable(generated_files, project_root)
    # errors is a list[str]; empty means all imports resolve
"""
from __future__ import annotations

import ast
import logging
import re
import sys
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)


# Standard-library top-level module names. sys.stdlib_module_names is the
# authoritative source — Python 3.10+ ships it as a frozenset.
_STDLIB_MODULES = frozenset(sys.stdlib_module_names)

# Pattern to extract top-level package name from a requirements.txt line.
# Handles: pkg==1.2, pkg>=1.0, pkg, pkg[extras]==1.0, pkg ; marker, comments
_REQUIREMENT_NAME_PATTERN = re.compile(r"^\s*([a-zA-Z0-9_\-\.]+)")


def _read_requirements(project_root: Path) -> set[str]:
    """Parse requirements.txt and return the set of top-level package names.

    These names are normalized to lowercase + dashes-to-underscores so
    `langchain-google-genai` matches imports like `langchain_google_genai`.

    Returns empty set if requirements.txt is missing — that's a graceful
    degradation; the validator just won't recognize third-party imports.
    """
    req_path = project_root / "requirements.txt"
    if not req_path.exists():
        return set()

    pkgs: set[str] = set()
    for raw_line in req_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        # Skip pip directives like `-r other.txt`, `--index-url`, etc.
        if line.startswith("-"):
            continue
        match = _REQUIREMENT_NAME_PATTERN.match(line)
        if not match:
            continue
        name = match.group(1).lower().replace("-", "_")
        pkgs.add(name)

        # Common Python convention: package distribution name often differs
        # from import name. We can't know all mappings without metadata,
        # but we record both forms (with and without underscore variants)
        # for the most common case.
        pkgs.add(name.replace("_", ""))

    return pkgs


# A handful of well-known import-name vs. distribution-name mismatches.
# Kept tiny and ONLY for cases where the convention truly differs — most
# packages are auto-detected from requirements.txt without this map.
# Adding to this map is not strictly app-specific; these mappings are
# universal Python ecosystem facts.
_KNOWN_IMPORT_ALIASES: dict[str, str] = {
    # import name -> distribution name
    "github": "pygithub",
    "yaml": "pyyaml",
    "dotenv": "python_dotenv",
    "jwt": "pyjwt",
    "google": "google_genai",  # google.* parents map to google-* dists
}


def _is_third_party_known(top_module: str, requirements: set[str]) -> bool:
    """Check if a top-level module name is a third-party dependency."""
    candidate = top_module.lower()
    if candidate in requirements:
        return True
    # Try alias map for known import-name vs dist-name mismatches
    aliased = _KNOWN_IMPORT_ALIASES.get(candidate)
    if aliased and aliased in requirements:
        return True
    return False


def _module_to_repo_path(module_path: str) -> list[str]:
    """Translate a dotted module path to candidate repo file paths.

    `pages.cart_page` -> ['pages/cart_page.py', 'pages/cart_page/__init__.py']
    """
    parts = module_path.split(".")
    return [
        "/".join(parts) + ".py",
        "/".join(parts) + "/__init__.py",
    ]


def _module_exists_in_repo(
    module_path: str, project_root: Path, planned_paths: set[str]
) -> bool:
    """Check whether a module path resolves to a file in the repo OR a
    file that's planned to be created in this generation batch."""
    candidates = _module_to_repo_path(module_path)
    for candidate in candidates:
        if (project_root / candidate).exists():
            return True
        # Match against planned files (normalized, forward-slash)
        normalized = candidate.replace("\\", "/").lstrip("./")
        if normalized in planned_paths:
            return True
    return False


def _extract_imports_from_source(source: str) -> list[tuple[str, int]]:
    """Parse a Python source string and return list of (module_path, lineno).

    For `import a.b.c` -> ('a.b.c', lineno)
    For `from a.b import c, d` -> ('a.b', lineno) (one entry per from-line)
    For `from . import x` (relative) -> skipped; relative imports are not
        validated here because their resolution depends on the importing
        file's package which is harder to determine and rarely the source
        of LLM hallucinations.

    Malformed source won't crash — returns empty list and logs a warning.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        logger.warning(
            f"Could not parse Python source for import analysis: {e}. "
            f"Skipping import validation for this file (other validators "
            f"will likely catch the syntax error itself)."
        )
        return []

    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            # Skip relative imports — `level > 0` means `from .` or `from ..`
            if node.level and node.level > 0:
                continue
            if node.module:
                out.append((node.module, node.lineno))
    return out


def validate_imports_resolvable(
    generated_files: Iterable,
    project_root: Path,
) -> list[str]:
    """Verify every import in generated .py files resolves to something real.

    "Real" means one of:
      - Python standard library (auto-detected via sys.stdlib_module_names)
      - Third-party package listed in requirements.txt
      - Existing file in the repo at project_root
      - File being created in this generation batch

    Args:
        generated_files: iterable of GeneratedFile-like objects with
                        `file_path` and `content` attributes (same shape
                        used by other Agent 2 validators)
        project_root: absolute path to the repo root, for filesystem checks

    Returns:
        List of human-readable error strings, one per unresolvable import.
        Empty list = all imports resolve. The error format mirrors the
        coverage validator so the existing repair loop can consume them
        without changes.
    """
    errors: list[str] = []
    files_list = list(generated_files)

    if not files_list:
        return errors

    requirements = _read_requirements(project_root)

    # Set of paths being created in this batch — for cross-file imports
    # within the same generation
    planned_paths = {
        getattr(gf, "file_path", "").replace("\\", "/").lstrip("./")
        for gf in files_list
    }

    for gf in files_list:
        path = getattr(gf, "file_path", "")
        content = getattr(gf, "content", "")

        # Only validate Python files
        if not path.endswith(".py"):
            continue
        if not content:
            continue

        for module_path, lineno in _extract_imports_from_source(content):
            top_module = module_path.split(".")[0]

            # 1. Standard library — auto-detected, no project config needed
            if top_module in _STDLIB_MODULES:
                continue

            # 2. Third-party from requirements.txt
            if _is_third_party_known(top_module, requirements):
                continue

            # 3. Repo-internal: existing file or planned file
            if _module_exists_in_repo(module_path, project_root, planned_paths):
                continue

            # Couldn't resolve. Build a helpful error in a format the
            # existing repair loop can parse (uses the same `error in
            # '<path>':` prefix shape).
            candidate_paths = _module_to_repo_path(module_path)
            errors.append(
                f"Import resolution error in '{path}': "
                f"line {lineno} has `import {module_path}` (or `from "
                f"{module_path} import ...`) but module `{module_path}` "
                f"does not exist. Searched: {', '.join(candidate_paths)} "
                f"(none found on disk and not in this generation batch). "
                f"This will fail with ModuleNotFoundError at test "
                f"collection time. Either add the missing file to the "
                f"plan, or remove this import and reference an existing "
                f"module."
            )

    return errors