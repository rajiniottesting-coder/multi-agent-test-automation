"""
Configuration package.

Provides centralized utilities for project configuration, paths,
environment-variable validation, and branch-name validation.

Usage in agents:
    from config import validate_required_env, extract_jira_key, is_valid_branch_for_pipeline
    validate_required_env(["JIRA_URL", "JIRA_API_TOKEN", "OPENAI_API_KEY"])
    key = extract_jira_key("auto/PROJ-123-feature")  # → "PROJ-123"
"""
import os
import re


# ─────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────

# Jira issue key pattern. Matches the standard Atlassian format:
#   - One or more uppercase letters (the project prefix)
#   - A hyphen
#   - One or more digits (the issue number)
#
# This works for ANY project prefix:
#   SCRUM-1, PROJ-123, MOBILE-42, BACKEND-5678, INFRA-1, EPIC-3, etc.
#
# Anchored with word boundaries so it doesn't accidentally match inside
# a larger word (e.g., would not match "MYAPP-VERSION-1" as a key).
JIRA_KEY_PATTERN = re.compile(r"\b([A-Z][A-Z0-9_]*-\d+)\b")

# Required environment variables for the full pipeline (every agent).
# Centralized here so individual agents don't drift on what they require.
REQUIRED_JIRA_ENV_VARS = ["JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_PROJECT_KEY"]
REQUIRED_LLM_ENV_VARS = ["OPENAI_API_KEY", "OPENAI_API_BASE"]
REQUIRED_GITHUB_ENV_VARS = ["GITHUB_TOKEN", "GITHUB_REPO"]


# ─────────────────────────────────────────────────────────────
# Errors
# ─────────────────────────────────────────────────────────────

class MissingEnvVarError(RuntimeError):
    """Raised when required environment variables are not set.

    We use a dedicated exception type (instead of plain RuntimeError) so
    callers and tests can catch it specifically.
    """
    pass


class InvalidBranchNameError(ValueError):
    """Raised when a branch name doesn't follow the Jira-key convention.

    The pipeline assumes branches contain a Jira key like PROJ-123 so that
    Agent 5 (Reporter) can map a CI run back to the correct Jira story.
    Branches without a key are valid for ad-hoc work but are skipped by
    the AI pipeline (no comment posted).
    """
    pass


# ─────────────────────────────────────────────────────────────
# Environment validation
# ─────────────────────────────────────────────────────────────

def validate_required_env(required_vars: list[str]) -> None:
    """Verify that all listed environment variables are set and non-empty.

    Why this exists:
        Without it, missing config produces cryptic downstream errors
        (e.g., a 401 from Jira because JIRA_API_TOKEN is empty, or a
        confusing AttributeError because some os.getenv() returned None).
        Validating up-front means agents fail FAST with a clear, actionable
        message instead of failing LATE somewhere deep in a tool call.

    Args:
        required_vars: Names of env vars that MUST be set.

    Raises:
        MissingEnvVarError: if any listed variable is missing or empty.
                            The message lists ALL missing vars at once
                            (not just the first), so the user can fix
                            everything in one go.
    """
    missing = [name for name in required_vars if not os.getenv(name)]
    if missing:
        raise MissingEnvVarError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            f"For local dev, set them in .env (see .env.example for the format). "
            f"For CI, add them as repository secrets in GitHub Settings → "
            f"Secrets and variables → Actions. "
            f"For a full reference, see docs/CONFIGURATION.md."
        )


# ─────────────────────────────────────────────────────────────
# Branch-name validation
# ─────────────────────────────────────────────────────────────

def extract_jira_key(branch_name: str | None) -> str | None:
    """Find a Jira key in a branch name. Returns the key or None.

    Examples:
        extract_jira_key("auto/SCRUM-5-login")        → "SCRUM-5"
        extract_jira_key("feature/PROD-1234-foo")     → "PROD-1234"
        extract_jira_key("PROJ-99-bare-key")          → "PROJ-99"
        extract_jira_key("hotfix/MOBILE-42-urgent")   → "MOBILE-42"
        extract_jira_key("feature/no-key-here")       → None
        extract_jira_key("main")                      → None
        extract_jira_key("")                          → None
        extract_jira_key(None)                        → None

    The Jira key can appear anywhere in the branch name; the regex finds
    the FIRST match. This is permissive by design — teams have different
    branch-naming conventions (`auto/`, `feature/`, `bugfix/`, etc.) and
    we don't want to lock anyone in.
    """
    if not branch_name:
        return None
    match = JIRA_KEY_PATTERN.search(branch_name)
    return match.group(1) if match else None


def is_valid_branch_for_pipeline(branch_name: str | None) -> bool:
    """Check whether a branch name has a Jira key embedded.

    Used by Agent 5 (Reporter) to decide whether to post results to Jira.
    Branches without a key are treated as ad-hoc / non-pipeline work and
    are skipped (gracefully, with a log message — not as an error).

    See docs/BRANCH_NAMING.md for the recommended convention.
    """
    return extract_jira_key(branch_name) is not None


def assert_valid_branch_for_pipeline(branch_name: str | None) -> str:
    """Strict version: extract Jira key from branch or raise InvalidBranchNameError.

    Used by Agent 2 (Coder) when CREATING branches — it must produce a name
    that matches the convention so downstream agents can work with it. If
    Agent 2 ever generated a branch like 'auto/feature-with-no-key', this
    would catch it before the branch is pushed to GitHub.

    Returns:
        The extracted Jira key.

    Raises:
        InvalidBranchNameError: if no key is found.
    """
    key = extract_jira_key(branch_name)
    if not key:
        raise InvalidBranchNameError(
            f"Branch name {branch_name!r} does not contain a Jira key. "
            f"Branches must include a key in the format PREFIX-NUMBER "
            f"(e.g., 'auto/PROJ-123-feature'). "
            f"See docs/BRANCH_NAMING.md for the full convention."
        )
    return key