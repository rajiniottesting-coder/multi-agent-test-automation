"""
Application Under Test (AUT) — centralized config loader.

This module is the SINGLE place where agents read information about the
application being tested. It reads the `app_under_test` block from
config.yaml and exposes typed accessors for:
  - reference files (feature/step-def/page-object the LLM mimics)
  - reserved paths (files Agent 2 must never overwrite)
  - the page inventory JSON (selectors, methods, pages)
  - the base URL and app name

Why this module exists:
    Before this refactor, agent code had hardcoded paths like
    "features/login.feature" and "app_inventory/saucedemo.json" baked
    into Python files. That made the framework SauceDemo-specific.

    Now those values come from config, and any agent that needs them
    calls into this module. To onboard a new app, you edit config.yaml
    — never agent code.

Usage:
    from agents.app_context import AppContext
    ctx = AppContext.load()
    ref_files = ctx.load_reference_files()       # {feature, step_def, page_object}
    inv = ctx.load_page_inventory_json()         # raw JSON string for prompts
    paths = ctx.reserved_paths_normalized()      # set of "feat/x.feature" strings
    name = ctx.name                              # "SauceDemo" / "MyApp" / etc.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

from config.paths import CONFIG_YAML, PROJECT_ROOT

logger = logging.getLogger(__name__)


def _normalize_path(p: str) -> str:
    """Convert backslashes to forward slashes and strip leading ./ — for
    case-insensitive comparison against LLM-generated file paths.

    This is the same normalization Agent 2 used to inline; pulled here
    so reserved-path checks always use the same logic.
    """
    return p.replace("\\", "/").lstrip("./")


@dataclass(frozen=True)
class AppContext:
    """Immutable view of the `app_under_test` block in config.yaml.

    Construct via `AppContext.load()` — that handles config reading and
    validation. Direct construction is also supported for tests.
    """
    name: str
    base_url: str
    inventory_file: str
    reference_feature: str
    reference_step_def: str
    reference_page_object: str
    reserved_paths: tuple[str, ...]
    extendable_paths: tuple[str, ...]

    # ─────────────────────────────────────────────────────────────
    # Construction
    # ─────────────────────────────────────────────────────────────

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "AppContext":
        """Load the AUT config from config.yaml (or a custom path).

        Raises:
            ValueError: if the `app_under_test` block is missing or
                        required fields are absent.
        """
        path = config_path or CONFIG_YAML
        with open(path) as f:
            full_config = yaml.safe_load(f) or {}

        aut = full_config.get("app_under_test")
        if not aut:
            raise ValueError(
                f"Missing 'app_under_test' block in {path}. "
                f"This block defines the app being tested (name, base_url, "
                f"reference files, reserved paths). See the example config "
                f"in this repo or docs/GUIDE.md 'Onboarding a new app'."
            )

        ref_files = aut.get("reference_files", {})

        # Required fields — fail loudly if any are missing rather than
        # silently producing broken downstream behavior.
        required_str_fields = {
            "name": aut.get("name"),
            "base_url": aut.get("base_url"),
            "inventory_file": aut.get("inventory_file"),
            "reference_files.feature": ref_files.get("feature"),
            "reference_files.step_def": ref_files.get("step_def"),
            "reference_files.page_object": ref_files.get("page_object"),
        }
        missing = [k for k, v in required_str_fields.items() if not v]
        if missing:
            raise ValueError(
                f"Missing required app_under_test field(s) in {path}: "
                f"{', '.join(missing)}. See docs/GUIDE.md 'Onboarding a new app'."
            )

        reserved = aut.get("reserved_paths", []) or []
        if not reserved:
            logger.warning(
                "app_under_test.reserved_paths is empty. Agent 2 will not "
                "protect any reference files from being overwritten by the "
                "LLM. Recommended: include at least your reference files."
            )

        extendable = aut.get("extendable_paths", []) or []
        # extendable is fine to be empty — many apps may not have any
        # page objects yet that need extending. We only log this at debug.
        logger.debug(
            f"AppContext: {len(reserved)} reserved path(s), "
            f"{len(extendable)} extendable path(s)."
        )

        return cls(
            name=aut["name"],
            base_url=aut["base_url"],
            inventory_file=aut["inventory_file"],
            reference_feature=ref_files["feature"],
            reference_step_def=ref_files["step_def"],
            reference_page_object=ref_files["page_object"],
            reserved_paths=tuple(reserved),
            extendable_paths=tuple(extendable),
        )

    # ─────────────────────────────────────────────────────────────
    # Path helpers
    # ─────────────────────────────────────────────────────────────

    def reference_file_paths(self) -> dict[str, Path]:
        """Resolve reference file relative paths to absolute Paths."""
        return {
            "feature": PROJECT_ROOT / self.reference_feature,
            "step_def": PROJECT_ROOT / self.reference_step_def,
            "page_object": PROJECT_ROOT / self.reference_page_object,
        }

    def inventory_path(self) -> Path:
        """Absolute path to the page inventory JSON file."""
        return PROJECT_ROOT / self.inventory_file

    def reserved_paths_normalized(self) -> set[str]:
        """Reserved paths as a set of normalized strings, for membership
        tests against LLM-generated file paths."""
        return {_normalize_path(p) for p in self.reserved_paths}

    def extendable_paths_normalized(self) -> set[str]:
        """Extendable paths as a set of normalized strings.

        These are existing files (typically page objects) that the LLM is
        allowed to modify — adding new methods, but not removing or
        breaking existing ones.
        """
        return {_normalize_path(p) for p in self.extendable_paths}

    # ─────────────────────────────────────────────────────────────
    # Content loaders (used by Agent 2 / Agent 3 prompts)
    # ─────────────────────────────────────────────────────────────

    def load_reference_files(self) -> dict[str, str]:
        """Read the reference files' contents (feature, step_def, page_object).

        Returns a dict matching the prompt template placeholders:
            {"feature": ..., "step_def": ..., "page_object": ...}

        Raises:
            FileNotFoundError: if any reference file is missing on disk.
                The error message includes the config-relative path so the
                user knows which config entry to fix.
        """
        out = {}
        for key, path in self.reference_file_paths().items():
            if not path.exists():
                raise FileNotFoundError(
                    f"Reference file '{key}' not found at {path}. "
                    f"Configured under app_under_test.reference_files.{key} "
                    f"in config.yaml. Either fix the path or create the file."
                )
            out[key] = path.read_text(encoding="utf-8")
        return out

    def load_page_inventory_json(self) -> str:
        """Read the page inventory JSON file as a raw string (for prompt
        templates that interpolate it directly).

        Raises:
            FileNotFoundError: if the inventory file doesn't exist.
        """
        path = self.inventory_path()
        if not path.exists():
            raise FileNotFoundError(
                f"Page inventory file not found at {path}. "
                f"Configured under app_under_test.inventory_file in "
                f"config.yaml. See docs/REUSE_FOR_NEW_PROJECT.md (App inventory JSON schema) for the "
                f"required JSON shape."
            )
        return path.read_text(encoding="utf-8")