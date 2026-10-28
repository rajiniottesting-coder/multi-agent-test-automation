"""No workflow pastes text a contributor chooses into a shell script.

Found by actionlint while F-30 was built: Story Done on merge pasted the pull
request's branch name into its `run:` script. A branch name may hold shell
syntax (`$(...)`), so anyone who can push a branch could run commands in a job
that holds the Jira, model and repository secrets. Such text reaches a script
as an environment variable instead, which the shell never executes.

The untrusted fields are actionlint's (its `expression` rule): names, titles,
bodies, messages and labels people type. Manual-run inputs, numbers and SHAs
are not among them. When actionlint is installed, it runs on every workflow too.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))

_UNTRUSTED = re.compile(
    r"github\.head_ref"
    r"|github\.event\.[\w.*\[\]]*\.(?:head\.ref|head\.label|default_branch|title|body"
    r"|message|page_name|email|name)\b"
    r"|github\.event\.(?:comment|review|review_comment|issue|pull_request|discussion)\.body"
)


def _expressions(text: str) -> list:
    return re.findall(r"\$\{\{(.*?)\}\}", text or "", re.S)


@pytest.mark.parametrize("wf", WORKFLOWS, ids=lambda p: p.name)
def test_no_run_script_pastes_untrusted_text(wf):
    data = yaml.safe_load(wf.read_text(encoding="utf-8"))
    offenders = []
    for name, job in (data.get("jobs") or {}).items():
        for step in job.get("steps") or []:
            for expr in _expressions(step.get("run", "")):
                if _UNTRUSTED.search(expr):
                    offenders.append(f"{name} / {step.get('name')}: ${{{{{expr.strip()}}}}}")
    assert not offenders, ("pass these through `env:` and use the variable in the "
                           "script:\n" + "\n".join(offenders))


def test_the_rule_catches_a_branch_name_in_a_script():
    assert _UNTRUSTED.search(" github.event.pull_request.head.ref || inputs.branch ")
    assert _UNTRUSTED.search(" github.head_ref ")
    assert _UNTRUSTED.search(" github.event.comment.body ")
    assert not _UNTRUSTED.search(" github.event.pull_request.number ")
    assert not _UNTRUSTED.search(" github.event.inputs.dry_run ")


@pytest.mark.skipif(shutil.which("actionlint") is None, reason="actionlint not installed")
def test_actionlint_passes_every_workflow():
    result = subprocess.run(["actionlint", *map(str, WORKFLOWS)], cwd=ROOT,
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
