"""Turn the nightly inventory check into a job summary (inventory_health.yml).

    python -m scripts.inventory_health_report --code <verifier exit code>
        [--output reports/inventory-health.txt] [--app-probe reports/app_probe.json]

The verifier (scripts/verify_locators.py) exits 0 when every selector resolved
to exactly one element, 1 on drift (stale or ambiguous), 2 when it could not
sign in. On anything but 0 the workflow first asks whether the APPLICATION was
up (scripts/app_probe.py, core/app_probe.py - a browser and no model, so no
token is spent). Its report decides the headline:

  not up      "The application is not up - inventory NOT checked", with what
              the browser was shown. Neither drift nor a credential problem:
              31 Oct 2026, the login page loaded with none of its elements and
              the summary blamed the credentials.
  up          the verifier's own reading: drift, or a login that failed on an
              application that is up - the credentials or the login form.
  unknown /   the verifier's reading as before.
  no report

When the verifier did not pass and the application is up, the workflow runs
it once more (X9, 12 Nov 2026: a login form slow to render read as a failed
login; the re-run by hand was green). A second reading that passes is
healthy, and the summary says the first did not (--retry-code).

Exit code 0 only when the inventory is healthy, so the scheduled run's colour
stays what it was; the pipeline health check counts failed nights. The one
exception (--alert, X9): an application that is not up opens the pipeline
health alert APP_DOWN instead of a red run - nothing about the inventory
failed - and a later reading with the application up closes it. When the
alert cannot be posted the run stays red, so it is never silent.
Generic: no application, page or element name lives here.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _probe(path: str | None) -> dict | None:
    if not path:
        return None
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:                                              # noqa: BLE001
        return None
    return data if isinstance(data, dict) else None


def headline(code: str, probe: dict | None) -> tuple:
    """(lines, exit code) for the verifier's exit code and the application check."""
    code = (code or "").strip()
    if code == "0":
        return (["## ✅ Inventory healthy", "",
                 "Every selector read as the inventory expects against the "
                 "live application: one element, or what its declaration "
                 "states (removed, conditional, planned, a family) - the "
                 "verifier output names the keys declared removed.", ""], 0)
    if probe and probe.get("available") is False:
        found = probe.get("summary") or probe.get("problem") or "the application was not up"
        return (["## ⚠️ The application is not up — inventory NOT checked", "",
                 "The application health check (the pages and elements in "
                 "`app_under_test.health_check`) found the application not serving "
                 "its own pages, so the verifier's findings say nothing about the "
                 "inventory. This is **not** inventory drift and **not** a "
                 "credential problem: change nothing in the inventory.", "",
                 f"**What the check found:** {found}", "",
                 "If it persists, check the application from a browser. The next "
                 "scheduled run checks again.", ""], 1)
    up = bool(probe and probe.get("available") is True)
    if code == "2":
        lines = ["## ⚠️ Login failed — inventory NOT checked", "",
                 "The verifier could not sign in, so it refused to produce a "
                 "report: every page would have redirected to the login screen "
                 "and every selector would read as stale. This is a credential "
                 "or availability problem, **not** inventory drift.", ""]
        lines += (["The application health check found the application **up**, so "
                   "check `APP_USER_REGISTERED` / `APP_PASSWORD` and the login "
                   "form's selectors.", ""] if up else
                  ["Check `APP_USER_REGISTERED` / `APP_PASSWORD`, and that the "
                   "application is up.", ""])
        return lines, 1
    if code == "1":
        return (["## ❌ Selector drift detected", "",
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
                 "these failures.", ""], 1)
    return ([f"## ❌ Verifier did not complete (exit {code!r})", "",
             "The check crashed rather than reporting a result. The output "
             "below is whatever it managed to produce.", ""], 1)


def render(code: str, body: str, probe: dict | None) -> tuple:
    """(summary text, exit code)."""
    lines, exit_code = headline(code, probe)
    if body.strip():
        lines += ["<details><summary>Verifier output</summary>", "",
                  "```", body.strip()[:8000], "```", "", "</details>", ""]
    else:
        lines += ["_The verifier produced no output._", ""]
    return "\n".join(lines), exit_code


APP_DOWN = "application-unavailable-inventory-health"


def _first_problem(body: str) -> str:
    """The first line of the verifier's output that says what went wrong."""
    lines = [l.strip() for l in body.splitlines() if l.strip()]
    for wanted in (lambda t: t.startswith("ERROR") or "FAILED" in t,
                   lambda t: t.startswith(("STALE", "AMBIG"))):
        found = next((t for t in lines if wanted(t)), None)
        if found:
            return found[:200]
    return lines[0][:200] if lines else ""


def retried_note(first_code: str, first_body: str) -> list:
    """The lines saying a second reading was needed."""
    found = _first_problem(first_body)
    return ["> The first reading did not pass (exit " + repr(first_code) + ")"
            + (f": `{found}`" if found else "") + ". The application was up, so the "
            "inventory was verified once more - the result above is that second reading. "
            "One such night is noise; the pipeline health issue counts repeats.", ""]


def alert_app_down(probe: dict | None, healthy_reading: bool, run_url: str) -> bool | None:
    """Open APP_DOWN when the application is not up, close it when it is.
    True: the alert is open (posted now or before); False: closed or nothing
    to do; None: the tracker could not be reached."""
    try:
        from core import pipeline_health as ph
        from integrations.tracker import get_tracker
        tracker = get_tracker()
        if probe and probe.get("available") is False:
            found = probe.get("summary") or probe.get("problem") or "the application was not up"
            ph.raise_alert(tracker, APP_DOWN,
                           "The nightly inventory check found the application unavailable",
                           f"Run: {run_url}\n\nWhat the check found: {str(found)[:800]}\n\n"
                           "The inventory was not checked. This alert closes on the next "
                           "inventory check with the application up.")
            return APP_DOWN in ph.open_alerts(tracker)      # posted, now or before
        if healthy_reading or (probe and probe.get("available") is True):
            ph.resolve_alert(tracker, APP_DOWN, f"The application was up again: {run_url}")
        return False
    except Exception as e:                                         # noqa: BLE001
        from core.redaction import error_text
        print(f"::warning::Pipeline health alert not reached: {error_text(e)}")
        return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--code", default=os.environ.get("CODE", ""))
    ap.add_argument("--output", default="reports/inventory-health.txt")
    ap.add_argument("--app-probe", default=None)
    ap.add_argument("--retry-code", default=os.environ.get("RETRY_CODE", ""),
                    help="the second reading's exit code, when the verifier ran again")
    ap.add_argument("--retry-output", default="reports/inventory-health-retry.txt")
    ap.add_argument("--alert", action="store_true",
                    help="an application that is not up opens a pipeline health alert "
                         "instead of failing the run")
    ap.add_argument("--run-url", default="")
    args = ap.parse_args(argv)
    out = Path(args.output)
    body = out.read_text(encoding="utf-8", errors="replace") if out.exists() else ""
    probe = _probe(args.app_probe)
    code, first = args.code, None
    retry_out = Path(args.retry_output)
    if (args.retry_code or "").strip() and (args.code or "").strip() != "0":
        first, first_body = args.code, body
        code = args.retry_code.strip()
        body = retry_out.read_text(encoding="utf-8", errors="replace") if retry_out.exists() else ""
    text, exit_code = render(code, body, probe)
    if first is not None:
        text += "\n" + "\n".join(retried_note(first, first_body))
    if args.alert:
        state = alert_app_down(probe, code == "0", args.run_url)
        if state is True and code != "0":
            text += ("\nThe pipeline health issue carries this as an alert, so the run "
                     "is not marked failed: nothing about the inventory failed.\n")
            exit_code = 0
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    print(text)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
