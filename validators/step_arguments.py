"""A step carries no data table or doc string the runner cannot read.

10 Nov 2026: a generated step was followed by a data table of the values it
checks. The gate matched the step's own line to its definition and passed;
at run time every attempt failed with StepDefinitionNotFoundError. The pinned
pytest-bdd (7.x) reads the lines under a step as part of the step's text, so
`Then the list shows the following` + `| A |` is a step no definition is
written for. pytest-bdd 8 reads them as a step argument instead - the rule
applies only below that version.

Values belong in the step wording (one step per value) or, for the same
steps over several values, a Scenario Outline with an Examples table.

Generic: reads only Gherkin structure; nothing here names an application.
"""
from __future__ import annotations

import re

_PREFIX = "Step argument error"
_STEP = re.compile(r"^\s*(Given|When|Then|And|But)\s+(.+?)\s*$")
_EXAMPLES = re.compile(r"^\s*(Examples|Scenarios)\s*:")
_BLOCK = re.compile(r"^\s*(Feature|Background|Rule|Scenario Outline|Scenario Template|"
                    r"Scenario|Example)\s*:")


def runner_reads_step_arguments() -> bool:
    """True when the installed pytest-bdd passes a table / doc string to the
    step as an argument (8.x), False when it reads them as step text (7.x)."""
    try:
        from importlib.metadata import version
        return int(version("pytest-bdd").split(".")[0]) >= 8
    except Exception:                                              # noqa: BLE001
        return False


def validate_steps_carry_no_table_or_doc_string(generated_files) -> list:
    if runner_reads_step_arguments():
        return []
    errors = []
    for f in generated_files or []:
        path = getattr(f, "file_path", "") or ""
        if not (path.startswith("features/") and path.endswith(".feature")):
            continue
        last_step, in_examples, reported = None, False, set()
        for line in (getattr(f, "content", "") or "").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("@"):
                continue
            if _EXAMPLES.match(line):
                in_examples, last_step = True, None
                continue
            if _BLOCK.match(line):
                in_examples, last_step = False, None
                continue
            m = _STEP.match(line)
            if m:
                in_examples, last_step = False, f"{m.group(1)} {m.group(2)}"
                continue
            if in_examples or last_step is None or last_step in reported:
                continue
            if stripped.startswith("|") or stripped.startswith('"""') or stripped.startswith("```"):
                kind = "a data table" if stripped.startswith("|") else "a doc string"
                reported.add(last_step)
                errors.append(
                    f"{_PREFIX} in '{path}': the step `{last_step}` is followed by {kind}. "
                    "This project's pytest-bdd (7.x) reads those lines as part of the step's "
                    "text, so no step definition matches it at run time "
                    "(StepDefinitionNotFoundError). Put each value in the step wording (one "
                    "step per value), or use a Scenario Outline with an Examples table.")
    return errors
