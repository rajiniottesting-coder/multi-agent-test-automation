"""An agent started with `python -m <module>` is one module, however it is imported.

Run that way, the file is `__main__`; another module importing it by name
would load a second copy with its own classes and state, so an exception
raised in one copy is not caught by an `except` in the other. 10 Nov 2026:
Agent 2's change-story splice raised the copy's SpliceNeedsPageMethods and
run() - in __main__ - never caught it.

The guard: every module a workflow starts with `python -m` that some other
module of the framework imports must alias itself under its own name when it
is __main__. Generic: it reads the workflows and the imports, no names.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_DIRS = ("agents", "core", "scripts", "validators", "integrations", "inventory_tools")


def _entry_modules() -> set:
    found = set()
    for wf in (ROOT / ".github" / "workflows").glob("*.yml"):
        found |= set(re.findall(r"python -m ((?:agents|core|scripts)\.\w+)", wf.read_text()))
    return found


def _imported_elsewhere(module: str) -> list:
    own = ROOT / (module.replace(".", "/") + ".py")
    pattern = re.compile(rf"(?:from\s+{re.escape(module)}\s+import|import\s+{re.escape(module)}\b)")
    hits = []
    for d in _DIRS:
        for py in (ROOT / d).rglob("*.py"):
            if py != own and pattern.search(py.read_text(encoding="utf-8", errors="ignore")):
                hits.append(str(py.relative_to(ROOT)))
    return hits


def test_every_entry_module_imported_elsewhere_is_one_module():
    missing = []
    for module in sorted(_entry_modules()):
        path = ROOT / (module.replace(".", "/") + ".py")
        if not path.is_file() or not _imported_elsewhere(module):
            continue
        alias = f'sys.modules.setdefault("{module}", sys.modules[__name__])'
        if alias not in path.read_text(encoding="utf-8"):
            missing.append(f"{module} (imported by {', '.join(_imported_elsewhere(module)[:3])})")
    assert not missing, ("started with python -m and imported by name elsewhere, without "
                         "aliasing itself when __main__: " + "; ".join(missing))


def test_the_guard_sees_the_known_case():
    assert "agents.agent2_coder" in _entry_modules()
    assert _imported_elsewhere("agents.agent2_coder")


def test_started_as_main_the_named_import_is_the_same_module():
    code = ("import runpy, sys; sys.argv = ['x', '--help']\n"
            "try:\n    runpy.run_module('agents.agent2_coder', run_name='__main__', alter_sys=True)\n"
            "except SystemExit:\n    pass\n"
            "import agents.agent2_coder as named\n"
            "print('SAME' if named.SpliceNeedsPageMethods is sys.modules['agents.agent2_coder']"
            ".SpliceNeedsPageMethods and named.__name__ == '__main__' else 'COPY')\n")
    env = {"PYTHONPATH": str(ROOT), "PATH": "/usr/bin:/bin"}
    import os
    env.update({k: os.environ[k] for k in os.environ if k.endswith("_API_KEY") or k.startswith(("JIRA", "GITHUB", "HOME"))})
    for v in ("OPENAI_API_KEY", "JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_PROJECT_KEY",
              "GITHUB_TOKEN", "GITHUB_REPO"):
        env.setdefault(v, "stub")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                         capture_output=True, text=True, timeout=120)
    assert out.stdout.strip().splitlines()[-1:] == ["SAME"], out.stdout[-500:] + out.stderr[-1500:]
