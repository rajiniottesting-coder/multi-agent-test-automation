"""The nightly inventory check says when the APPLICATION was not up.

31 Oct 2026: the login page loaded with none of its 11 elements, the verifier
refused to report (correctly), and the summary read "Login failed - check the
credentials" - the night after the application had served its pages without
their content to the nightly test run too. Nothing in the check asked whether
the application was up.

Now, when the verifier does not pass, inventory_health.yml runs the
application health check (core/app_probe.py - a browser, no model, no token)
and scripts/inventory_health_report.py writes the headline: not up - neither
drift nor credentials, change nothing; up with a failed login - the
credentials or the login form. Every other summary is byte-for-byte what the
inline script in the workflow wrote before. Generic names only.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from scripts import inventory_health_report as ihr

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows" / "inventory_health.yml"
DOWN = {"available": False, "problem": "login (x) was served without email_input",
        "summary": "The application is NOT up after 9 check(s): login was served without "
                   "email_input. The browser was at https://a.example/login, titled 'Back "
                   "soon', showing: 'Maintenance'."}
OUTPUT = "  [login] https://a.example/login\n    PAGE DID NOT RENDER\n  ERROR: login FAILED"

# The inline script the workflow ran before this change, kept verbatim as the
# reference for "nothing else changed" - except the healthy sentence, which
# E128 corrected (it said "exactly one element" of keys declared removed,
# conditional, planned or families too).
_BEFORE = r'''
import os
from pathlib import Path

code = (os.environ.get("CODE") or "").strip()
out = Path("reports/inventory-health.txt")
body = out.read_text(encoding="utf-8", errors="replace") if out.exists() else ""
summary = os.environ.get("GITHUB_STEP_SUMMARY")
if code == "0":
    head = ["## ✅ Inventory healthy", "",
            "Every selector read as the inventory expects against the "
            "live application: one element, or what its declaration "
            "states (removed, conditional, planned, a family) - the "
            "verifier output names the keys declared removed.", ""]
    exit_code = 0
elif code == "2":
    head = ["## ⚠️ Login failed — inventory NOT checked", "",
            "The verifier could not sign in, so it refused to produce a "
            "report: every page would have redirected to the login screen "
            "and every selector would read as stale. This is a credential "
            "or availability problem, **not** inventory drift.", "",
            "Check `APP_USER_REGISTERED` / `APP_PASSWORD`, and that the "
            "application is up.", ""]
    exit_code = 1
elif code == "1":
    head = ["## ❌ Selector drift detected", "",
            "One or more selectors no longer resolve to exactly one "
            "element. Read the report below, then:", "",
            "1. Each **AMBIG** line lists what it matched; a contains-match "
            "`text=` selector also gets a `fix:` line. To watch it locally:",
            "   `python -m scripts.verify_locators --page <page> --only-problems`",
            "2. **STALE** (0 matches) — the app changed. Fix that selector "
            "in the inventory by hand.",
            "3. **AMBIG** (>1) — a key meant to be ONE element (a heading, "
            "a message): tighten its selector to that element - use the "
            "`fix:` line when there is one. Never declare it `multi_match` "
            "to silence it: that hides the drift. Only a key meant to be "
            "EVERY match (rows, cards, buttons) belongs in `multi_match`.",
            "4. Keys listed under `conditional` only exist after an "
            "interaction, so a tool that never clicks always reports them "
            "stale. Do not 'fix' those.", "",
            "Do NOT regenerate the inventory to repair this: a fresh draft "
            "carries no `elements_notes`, `multi_match` or `key_methods`, "
            "and promoting one would delete the curation that prevents "
            "these failures.", ""]
    exit_code = 1
else:
    head = [f"## ❌ Verifier did not complete (exit {code!r})", "",
            "The check crashed rather than reporting a result. The output "
            "below is whatever it managed to produce.", ""]
    exit_code = 1
if body.strip():
    head += ["<details><summary>Verifier output</summary>", "",
             "```", body.strip()[:8000], "```", "", "</details>", ""]
else:
    head += ["_The verifier produced no output._", ""]
if summary:
    with open(summary, "a", encoding="utf-8") as f:
        f.write("\n".join(head) + "\n")
print("\n".join(head))
raise SystemExit(exit_code)
'''


def _run(tmp_path, cmd, code, body, probe=None):
    (tmp_path / "reports").mkdir(exist_ok=True)
    out = tmp_path / "reports" / "inventory-health.txt"
    if body is None:
        out.unlink(missing_ok=True)
    else:
        out.write_text(body)
    if probe is not None:
        import json
        (tmp_path / "reports" / "app_probe.json").write_text(json.dumps(probe))
    summary = tmp_path / "summary.md"
    summary.write_text("")
    env = dict(os.environ, CODE=code, GITHUB_STEP_SUMMARY=str(summary), PYTHONPATH=str(ROOT))
    r = subprocess.run(cmd, cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)
    return r.returncode, r.stdout, summary.read_text()


NEW = [sys.executable, "-m", "scripts.inventory_health_report", "--code", "",
       "--output", "reports/inventory-health.txt", "--app-probe", "reports/app_probe.json"]


@pytest.mark.parametrize("code, body", [("0", OUTPUT), ("1", OUTPUT), ("2", OUTPUT),
                                        ("", ""), ("7", None), ("1", "x" * 9000)])
def test_without_an_application_finding_the_summary_is_unchanged(tmp_path, code, body):
    before = _run(tmp_path, [sys.executable, "-c", _BEFORE], code, body)
    new = list(NEW)
    new[4] = code
    after = _run(tmp_path, new, code, body)
    assert after == before


@pytest.mark.parametrize("code", ["1", "2", "", "3"])
def test_an_application_not_up_is_neither_drift_nor_credentials(code):
    text, exit_code = ihr.render(code, OUTPUT, DOWN)
    assert exit_code == 1
    assert text.startswith("## ⚠️ The application is not up — inventory NOT checked")
    assert "change nothing in the inventory" in text and "'Back soon'" in text
    assert "Selector drift" not in text and "APP_PASSWORD" not in text
    assert "PAGE DID NOT RENDER" in text, "the verifier's output is still attached"


def test_a_failed_login_on_an_application_that_is_up_points_at_the_credentials():
    text, _ = ihr.render("2", OUTPUT, {"available": True, "checked": ["login: email_input"]})
    assert "found the application **up**" in text and "APP_PASSWORD" in text
    assert "and that the application is up" not in text


@pytest.mark.parametrize("probe", [None, {"available": "unknown"}, {"junk": 1}])
def test_a_check_that_could_not_run_changes_nothing(probe):
    assert ihr.render("2", OUTPUT, probe) == ihr.render("2", OUTPUT, None)


def test_a_healthy_inventory_stays_healthy_whatever_the_check_says():
    text, exit_code = ihr.render("0", "", DOWN)
    assert exit_code == 0 and text.startswith("## ✅ Inventory healthy")


def test_the_cli_reads_the_check(tmp_path):
    code, out, summary = _run(tmp_path, [*NEW[:4], "2", *NEW[5:]], "2", OUTPUT, probe=DOWN)
    assert code == 1 and "The application is not up" in out and out.strip() == summary.strip()


# ── the workflow ────────────────────────────────────────────────────────────

def _steps():
    return yaml.safe_load(WF.read_text(encoding="utf-8"))["jobs"]["verify"]["steps"]


def test_the_check_runs_only_when_the_verifier_did_not_pass_and_spends_nothing():
    steps = _steps()
    names = [s.get("name") or "" for s in steps]
    i_verify = next(i for i, s in enumerate(steps) if s.get("id") == "verify")
    i_probe = next(i for i, s in enumerate(steps) if s.get("id") == "probe")
    i_report = names.index("Report")
    assert i_verify < i_probe < i_report
    probe = steps[i_probe]
    assert "steps.verify.outputs.code != '0'" in probe["if"]
    assert probe.get("continue-on-error") is True
    assert "scripts.app_probe" in probe["run"] and "reports/app_probe.json" in probe["run"]
    assert "secrets." not in str(probe), "public pages: the check holds no credential"
    assert not any(k for k in (probe.get("env") or {}) if "KEY" in k or "TOKEN" in k), \
        "no model and no token"


def test_the_report_uses_the_script_and_keeps_the_evidence():
    steps = _steps()
    report = next(s for s in steps if s.get("name") == "Report")
    assert report["if"] == "always()"
    assert "scripts.inventory_health_report" in report["run"]
    assert "--app-probe reports/app_probe.json" in report["run"]
    assert "PYEOF" not in WF.read_text(encoding="utf-8"), "one summary, in one tested place"
    upload = next(s for s in steps if "upload-artifact" in str(s.get("uses", "")))
    assert "reports/app_probe.json" in upload["with"]["path"]


def test_the_job_has_time_for_the_wait():
    from core.ops_settings import section
    job = yaml.safe_load(WF.read_text(encoding="utf-8"))["jobs"]["verify"]
    assert int(job["timeout-minutes"]) >= 15 + int(section("app_health")["wait_minutes"]), \
        "the verifier's own run plus the check's wait"
