"""The agents' workflow scripts pass optional flags as bash arrays: an empty
one passes nothing, and a flag with a value stays one argument each.

14 Nov 2026: shellcheck (run by actionlint) reported the unquoted flags. One
was a real bug: `SPRINT_FLAG="--sprint ${{ inputs.sprint }}"` expanded
unquoted, so a run by hand for a sprint whose name has spaces passed
`--sprint`, then each word as its own argument, and the agent refused it.
The script is executed here, with `python` stubbed to record its arguments.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def _scan_step(workflow: str) -> str:
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8"))
    for job in wf["jobs"].values():
        for step in job["steps"]:
            if "--scan" in (step.get("run") or "") and "--sprint" in step["run"]:
                return step["run"]
    raise AssertionError(f"{workflow}: no scan step with --sprint")


def _argv(script: str, inputs: dict, tmp_path: Path) -> list:
    for name, value in inputs.items():
        script = script.replace("${{ github.event.inputs.%s }}" % name, value)
    script = script.replace("${{ github.event_name }}", "workflow_dispatch")
    out = tmp_path / "argv.txt"
    stub = f'python() {{ printf "%s\\n" "$@" > "{out}"; }}\n'
    subprocess.run(["bash", "-e", "-c", stub + script], check=True, capture_output=True)
    return out.read_text(encoding="utf-8").splitlines()


@pytest.mark.parametrize("workflow", ["agent1_analyst.yml", "agent2_coder.yml"])
def test_a_sprint_name_with_spaces_stays_one_argument(workflow, tmp_path):
    argv = _argv(_scan_step(workflow),
                 {"sprint": "Sprint 7 (release)", "dry_run": "true", "story_key": ""}, tmp_path)
    assert argv[-3:] == ["--dry-run", "--sprint", "Sprint 7 (release)"]


@pytest.mark.parametrize("workflow", ["agent1_analyst.yml", "agent2_coder.yml"])
def test_no_optional_flag_passes_no_empty_argument(workflow, tmp_path):
    argv = _argv(_scan_step(workflow), {"sprint": "", "dry_run": "false", "story_key": ""},
                 tmp_path)
    assert argv[-1] == "--scan" and "" not in argv
