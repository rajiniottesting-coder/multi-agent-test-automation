"""
The agent0_impact workflow's gate job installs only pyyaml, so it can read
agents.agent0_impact.enabled in seconds on every scheduled run, including the
many runs where Agent 0 is off. That holds only while the code it runs imports
nothing beyond pyyaml and the standard library. These tests run the gate's own
snippet, taken from the workflow file, with every other third-party import
blocked: a future import that would break the gate fails here, in CI, rather
than on the schedule.
"""
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "agent0_impact.yml"

_BLOCK_THIRD_PARTY = '''
import sys
ALLOWED = {"yaml", "core", "config"}
class _Block:
    def find_spec(self, name, path=None, target=None):
        top = name.split(".")[0]
        if top in sys.stdlib_module_names or top in ALLOWED or top.startswith("_"):
            return None
        raise ImportError(f"the gate job does not install {top!r} (imported as {name!r})")
sys.meta_path.insert(0, _Block())
'''


def _gate_run() -> str:
    jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    return "\n".join(step.get("run", "") for step in jobs["gate"]["steps"])


def _gate_snippet(run: str) -> str:
    m = re.search(r"<<'PYEOF'[^\n]*\n(.*?)\n\s*PYEOF", run, re.DOTALL)
    assert m, "gate step no longer runs a PYEOF heredoc - update this test"
    return "\n".join(line.strip() for line in m.group(1).splitlines())


def test_gate_installs_only_pyyaml():
    installs = re.findall(r"pip install ([^\n]+)", _gate_run())
    packages = {w for line in installs for w in line.split() if not w.startswith("-")}
    assert packages == {"pyyaml"}


def test_gate_snippet_runs_with_only_pyyaml_and_the_stdlib():
    code = _BLOCK_THIRD_PARTY + _gate_snippet(_gate_run())
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True,
                         text=True, timeout=60, check=False)
    assert out.returncode == 0, out.stderr
    assert re.fullmatch(r"enabled=(true|false)\n", out.stdout), out.stdout


def test_reconcile_has_one_ungated_job():
    """C7 must run while Agent 0 is off or in shadow mode (a person can hand
    over in phase C), and in exactly one place, so two concurrent runs can
    never count as the two scans that trigger an undo."""
    jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]

    def runs(job):
        return "\n".join(step.get("run", "") for step in job["steps"])

    with_reconcile = [name for name, job in jobs.items() if "impact_reconcile" in runs(job)]
    assert with_reconcile == ["reconcile"]
    assert "needs" not in jobs["reconcile"] and "gate" not in jobs["reconcile"].get("if", "")
