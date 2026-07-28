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
    "features/login.feature" and "app_inventory/<app>.json" baked
    into Python files. That made the framework specific to one application.

    Now those values come from config, and any agent that needs them
    calls into this module. To onboard a new app, you edit config.yaml
    — never agent code.

Usage:
    from core.app_context import AppContext
    ctx = AppContext.load()
    ref_files = ctx.load_reference_files()       # {feature, step_def, page_object}
    inv = ctx.load_page_inventory_json()         # raw JSON string for prompts
    paths = ctx.reserved_paths_normalized()      # set of "feat/x.feature" strings
    name = ctx.name                              # "MyApp" / "AcmePortal" / etc.
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


def _norm_component(name: str) -> str:
    """Normalize a component name for case/space/hyphen-insensitive matching.

    Same normalization used by Agent 1's module-wise app-context loader
    (backlog 2.1), so a story's Jira Components select inventory pages and
    app-context modules identically. "User Management" -> "user_management".
    """
    return name.strip().lower().replace(" ", "_").replace("-", "_")


# Internal inventory keys that drive our filtering but are NOT content the LLM
# needs — stripped from the injected string to save tokens.
_INVENTORY_META_KEYS = ("components", "always")


def filter_inventory_by_components(
    data: dict, components: Optional[list[str]] = None
) -> dict:
    """Return a copy of the inventory dict with `pages` filtered to the ones
    relevant to `components` (backlog 2.2), and internal tagging keys stripped.

    Rules (mirror the app-context module selection in backlog 2.1):
      - A page is kept if it is flagged ``"always": true`` (shared pages such as
        the menu) OR any of its ``components`` matches a requested component,
        matched case/space/hyphen-insensitively.
      - ``components`` None/empty -> keep ALL pages (default, unchanged).
      - Requested components that match NO page -> keep ALL pages. Safe default:
        never silently drop context.

    Only the ``pages`` block is filtered; ``test_users``, ``common_errors``,
    ``selector_strategy``, ``test_patterns`` etc. are small and always retained.
    The ``components`` / ``always`` per-page keys and the top-level
    ``_inventory_conventions`` note are removed from the returned dict so they
    are not sent to the LLM. The input dict is not mutated.

    Non-dict inputs or an inventory with no usable ``pages`` map are returned
    with only the meta note stripped — no filtering, no crash.
    """
    if not isinstance(data, dict):
        return data

    out = {k: v for k, v in data.items() if k != "_inventory_conventions"}

    pages = out.get("pages")
    if not isinstance(pages, dict) or not pages:
        return out

    requested = {_norm_component(c) for c in (components or []) if c}

    def _strip(page: dict) -> dict:
        return {k: v for k, v in page.items() if k not in _INVENTORY_META_KEYS}

    if not requested:
        out["pages"] = {name: _strip(p) for name, p in pages.items()}
        return out

    selected: dict = {}
    for name, page in pages.items():
        if not isinstance(page, dict):
            selected[name] = page
            continue
        if page.get("always") is True:
            selected[name] = _strip(page)
            continue
        page_components = {
            _norm_component(c) for c in (page.get("components") or [])
        }
        if page_components & requested:
            selected[name] = _strip(page)

    # Safe default: if the component filter matched nothing meaningful
    # (only "always" pages, or nothing at all), fall back to the full set so
    # the LLM is never starved of context.
    non_always = {
        name for name, page in pages.items()
        if not (isinstance(page, dict) and page.get("always") is True)
    }
    matched_non_always = set(selected) & non_always
    if not matched_non_always:
        logger.info(
            "Inventory filter: components %s matched no page — injecting the "
            "full inventory (safe default).", list(requested),
        )
        out["pages"] = {name: _strip(p) for name, p in pages.items()}
        return out

    logger.info(
        "Inventory filter: components %s selected %d/%d pages: %s",
        list(requested), len(selected), len(pages), list(selected),
    )
    out["pages"] = selected
    return out


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

    def load_page_inventory_json(self, components: Optional[list[str]] = None) -> str:
        """Read the page inventory JSON as a raw string (for prompt templates
        that interpolate it directly).

        Two behaviours, chosen by the `components` argument:

        1. **Full inventory (default, unchanged).** `components` None or empty
           → the whole inventory is returned, byte-identical to before. Every
           existing caller that passes no argument keeps its current behaviour.
        2. **Component-filtered (backlog 2.2).** When a story's Jira Components
           are passed, only the pages relevant to those components are injected,
           plus any page flagged `"always": true` (shared pages like the menu).
           This mirrors the module-wise app-context selection (backlog 2.1) and
           cuts Agent 2's inventory-dominated input tokens on a tagged story.

           A page is kept if any of its `components` matches a requested
           component (case/space/hyphen-insensitive) OR it is marked
           `"always": true`. **Safe default:** if the requested components match
           NO page, the full inventory is returned — context is never silently
           dropped, exactly like the app-context loader.

        Either way the internal tagging keys (`components`, `always`, and the
        top-level `_inventory_conventions` note) are stripped from the string
        sent to the LLM — they drive our filtering, they aren't content the
        model needs — and the result is minified (backlog 2.6). Only the
        prompt string changes; the file on disk stays human-readable.

        A file that is not valid JSON falls back to the raw text unchanged
        (identical to pre-2.6 behaviour) so a malformed inventory can never make
        this method start failing. A *missing* file still raises FileNotFoundError.

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
        raw = path.read_text(encoding="utf-8")

        import json

        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            logger.warning(
                "Page inventory at %s is not valid JSON — injecting raw text "
                "without minification or filtering.", path,
            )
            return raw

        data = filter_inventory_by_components(data, components)
        return json.dumps(data, separators=(",", ":"), ensure_ascii=False)