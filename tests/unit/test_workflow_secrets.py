"""Identifiers must not be stored as GitHub Secrets.

WHAT HAPPENED
    JIRA_BOARD_ID was a repository Secret whose value is "1". GitHub masks
    EVERY occurrence of a secret's value anywhere in a log, so every literal
    "1" was replaced by ***:

        ***2:52:00 [INFO] ... in=3***294 ... cost=$***.36***6

    Timestamps, token counts, costs and issue keys all became unreadable. Two
    debugging sessions were spent reading around it, and the token figures that
    answer "is prompt caching working" were among the casualties.

    A board id and a project key appear in every Jira URL. Marking them secret
    protects nothing and costs the readability of every log the pipeline
    produces.

THE RULE
    Secrets are for CREDENTIALS. Identifiers go in `vars`, which GitHub does
    not mask. The shorter and more numeric a value, the more damage masking it
    does - a one-character secret redacts that character everywhere.
"""
import re
from pathlib import Path

import pytest

_WORKFLOWS = sorted((Path(__file__).resolve().parents[2]
                     / ".github" / "workflows").glob("*.yml"))

# Names that are identifiers, not credentials. A token, password or key is a
# credential however it is named; these are not.
_MUST_NOT_BE_SECRET = {
    "JIRA_BOARD_ID",     # a small integer - masks that digit everywhere
    "JIRA_PROJECT_KEY",  # appears in every issue key the logs print
    "JIRA_URL",          # the address of the tracker, not access to it
    "GH_REPO",           # owner/name - it is in the browser address bar
    "APP_CLIENT_ID",     # the agents' GitHub App (F-30): public, in the App's URL
}


@pytest.mark.parametrize("workflow", _WORKFLOWS, ids=lambda p: p.name)
def test_identifiers_are_vars_not_secrets(workflow):
    body = workflow.read_text(encoding="utf-8")
    offenders = [
        name for name in _MUST_NOT_BE_SECRET
        if re.search(rf"{name}:\s*\$\{{\{{\s*secrets\.", body)
    ]
    assert not offenders, (
        f"{workflow.name} passes {sorted(offenders)} as a SECRET. GitHub masks "
        f"every occurrence of a secret's value across the whole log, so a short "
        f"or numeric identifier redacts itself everywhere it appears - "
        f"including timestamps, token counts and costs. Use "
        f"${{{{ vars.<NAME> }}}} instead."
    )


@pytest.mark.parametrize("workflow", _WORKFLOWS, ids=lambda p: p.name)
def test_credentials_are_still_secrets(workflow):
    """The mirror. Relaxing the rule above must not leak a real credential."""
    body = workflow.read_text(encoding="utf-8")
    leaked = [
        m.group(1)
        for m in re.finditer(r"([A-Z_]*(?:TOKEN|PASSWORD|KEY|SECRET)[A-Z_]*):\s*"
                             r"\$\{\{\s*vars\.", body)
        if m.group(1) != "JIRA_PROJECT_KEY"      # a key by name only
    ]
    assert not leaked, (
        f"{workflow.name} passes {sorted(leaked)} as a plain var. Credentials "
        f"must stay secrets - masking exists for exactly these."
    )


def test_the_rule_is_written_down_somewhere_a_reader_will_find_it():
    guide = (Path(__file__).resolve().parents[2] / "docs" / "GUIDE.md")
    if not guide.is_file():
        pytest.skip("no GUIDE.md in this checkout")
    body = guide.read_text(encoding="utf-8")
    assert "vars." in body and "mask" in body.lower(), (
        "GUIDE.md does not explain why identifiers go in vars rather than "
        "secrets - the next person setting up a project will repeat it."
    )