"""The browser install survives unreachable package mirrors.

11 Nov 2026: runners could not resolve the package mirrors; the install
failed, the self-test after it was skipped and the run was red although every
test passed. Every workflow installs through scripts/install_browser.sh: the
full install twice, then the browser alone - passing only if it starts.
"""
import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "install_browser.sh"


def test_no_workflow_installs_the_browser_without_the_retry():
    for wf in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        text = wf.read_text(encoding="utf-8")
        assert "playwright install" not in text, f"{wf.name}: use scripts/install_browser.sh"


def _fake(tmp_path, with_deps_fails, plain_ok=True, launch_ok=True):
    log = tmp_path / "log"
    log.write_text("")
    exe = tmp_path / "playwright"
    exe.write_text(f"""#!/usr/bin/env bash
echo "$*" >> {log}
n=$(grep -c -- --with-deps {log})
if [ "$2" = "--with-deps" ]; then [ $n -gt {with_deps_fails} ]; else {'true' if plain_ok else 'false'}; fi
""")
    py = tmp_path / "python"                        # the launch check
    py.write_text(f"#!/usr/bin/env bash\ncat > /dev/null\necho launch >> {log}\n"
                  f"{'exit 0' if launch_ok else 'exit 1'}\n")
    sleep = tmp_path / "sleep"                      # no real waiting in a unit test
    sleep.write_text("#!/usr/bin/env bash\nexit 0\n")
    for f in (exe, py, sleep):
        f.chmod(f.stat().st_mode | stat.S_IEXEC)
    env = dict(os.environ, PATH=f"{tmp_path}:{os.environ['PATH']}")
    return env, log


def _run(env, *args):
    return subprocess.run(["bash", str(SCRIPT), *args], env=env, capture_output=True, text=True)


def test_a_temporary_failure_is_tried_again(tmp_path):
    env, log = _fake(tmp_path, with_deps_fails=1)
    out = _run(env, "chromium")
    assert out.returncode == 0
    assert log.read_text().splitlines() == ["install --with-deps chromium"] * 2


def test_unreachable_mirrors_pass_only_when_the_browser_starts(tmp_path):
    env, log = _fake(tmp_path, with_deps_fails=9)
    out = _run(env)
    assert out.returncode == 0, out.stdout
    assert log.read_text().splitlines() == ["install --with-deps chromium"] * 2 + [
        "install chromium", "launch"]
    assert "starts without the freshly installed OS packages" in out.stdout


def test_a_browser_that_does_not_start_fails_the_step(tmp_path):
    env, _ = _fake(tmp_path, with_deps_fails=9, launch_ok=False)
    out = _run(env)
    assert out.returncode == 1 and "::error::chromium could not be installed" in out.stdout
    env, _ = _fake(tmp_path / "x" if (tmp_path / "x").mkdir() is None else tmp_path,
                   with_deps_fails=9, plain_ok=False)
    assert _run(env).returncode == 1


def test_a_hanging_install_is_cut_off(tmp_path):
    """apt waits about ten minutes on unresolvable mirrors; each try is cut off."""
    env, log = _fake(tmp_path, with_deps_fails=0)
    hang = tmp_path / "playwright"
    hang.write_text(f"#!/usr/bin/env bash\necho \"$*\" >> {log}\n"
                    "if [ \"$2\" = \"--with-deps\" ]; then exec /bin/sleep 30; fi\n")
    out = subprocess.run(["bash", str(SCRIPT)], env=dict(env, INSTALL_TIMEOUT="1"),
                         capture_output=True, text=True, timeout=20)
    assert out.returncode == 0
    assert log.read_text().splitlines() == ["install --with-deps chromium"] * 2 + [
        "install chromium", "launch"]
    assert "took over 1s" in out.stdout
