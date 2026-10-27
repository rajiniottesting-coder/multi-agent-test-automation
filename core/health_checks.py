"""The checks behind the pipeline health issue (F-23).

Each check returns Finding(alert_id, problem, title, detail): `problem` True
opens the alert on the health issue, False closes it (core/pipeline_health.py
posts only on a change). scripts/pipeline_health_check.py runs them on a
schedule.

  workflows    a scheduled workflow whose last `consecutive_failures`
               scheduled runs all failed. The workflows are read from the
               repository's own workflow files, so a new scheduled workflow is
               watched without a code change.
  credentials  the repo host's token (and its expiry, where the host says),
               and the model endpoint. The tracker's own credentials are
               checked first by the script: without them no alert can be posted.

Generic: no workflow, application or provider name is written here.
"""
from __future__ import annotations

import datetime as _dt
import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Conclusions that say how a scheduled run ended. Anything else (cancelled,
# skipped, neutral, still running) says nothing about the workflow's health.
_FAILED = {"failure", "timed_out", "startup_failure"}
_PASSED = {"success"}


@dataclass(frozen=True)
class Finding:
    alert_id: str
    problem: bool
    title: str
    detail: str = ""


# ── scheduled workflows ──────────────────────────────────────

def _triggers(doc: dict):
    # YAML 1.1 reads the bare key `on` as the boolean True.
    return doc.get("on", doc.get(True)) if isinstance(doc, dict) else None


def scheduled_workflows(root: Path) -> list:
    """File names of the workflows that run on a schedule, sorted."""
    import yaml
    out = []
    for path in sorted((Path(root) / ".github" / "workflows").glob("*.y*ml")):
        try:
            on = _triggers(yaml.safe_load(path.read_text(encoding="utf-8")))
        except Exception as e:                                     # noqa: BLE001
            logger.warning("Workflow %s unreadable (%s); not watched.", path.name, e)
            continue
        if isinstance(on, dict) and on.get("schedule"):
            out.append(path.name)
    return out


def failing_streak(runs: list) -> tuple:
    """(failed scheduled runs in a row, newest first; the newest failed run's url)."""
    streak, url = 0, None
    for r in runs or []:
        if r.get("event") != "schedule" or r.get("status") != "completed":
            continue
        if r.get("conclusion") in _FAILED:
            streak += 1
            url = url or r.get("url")
        elif r.get("conclusion") in _PASSED:
            break
    return streak, url


def workflow_findings(host, root: Path, threshold: int, exclude=()) -> list:
    """One Finding per scheduled workflow."""
    out = []
    for name in scheduled_workflows(root):
        if name in exclude:
            continue
        try:
            runs = host.get_workflow_runs(name, "main", limit=50)
        except Exception as e:                                     # noqa: BLE001
            logger.warning("Runs of %s not read: %s", name, e)
            continue
        streak, url = failing_streak(runs)
        failing = streak >= threshold
        out.append(Finding(
            f"workflow-failing:{name}", failing,
            f"Scheduled workflow {name} failed {streak} scheduled runs in a row" if failing
            else f"Scheduled workflow {name} is no longer failing",
            f"Its last {streak} scheduled runs failed (alert after {threshold}). "
            + (f"Latest: {url}. " if url else "")
            + "Open the run to read why; it closes by itself after the next successful "
              "scheduled run."))
    return out


# ── credentials ──────────────────────────────────────────────

def expiry_finding(alert_id: str, what: str, expires: str | None, now: _dt.datetime,
                   warn_days: int) -> Finding | None:
    """A warning when `expires` (a date the provider gave) is within `warn_days`."""
    if not expires:
        return None
    try:
        text = expires.replace(" UTC", "").strip()
        when = _dt.datetime.fromisoformat(text)
        if when.tzinfo is None:
            when = when.replace(tzinfo=_dt.timezone.utc)
    except ValueError:
        logger.warning("Unreadable expiry %r for %s", expires, what)
        return None
    left = (when - now).days
    return Finding(alert_id, left <= warn_days,
                   f"{what} expires in {max(left, 0)} day(s)",
                   f"It expires on {when.date().isoformat()}. Create a new one and replace "
                   f"the secret before then; this alert closes once the new expiry is "
                   f"further away than {warn_days} days.")


def repo_host_findings(host_factory, now: _dt.datetime, warn_days: int) -> list:
    """The repo host's credentials: refused, or close to expiry."""
    from integrations.tracker import capability
    try:
        host = host_factory()
        check = capability(host, "check_access")
        info = check() if check else {"ok": True}
    except Exception as e:                                         # noqa: BLE001
        return [Finding("credential:repo-host", True, "The repo host refused the pipeline's token",
                        f"{type(e).__name__}: {_redact(str(e))}. Every agent that opens or "
                        "reads pull requests stops until the token is replaced.")]
    out = [Finding("credential:repo-host", False, "The repo host accepts the pipeline's token")]
    exp = expiry_finding("credential-expiry:repo-host", "The repo host token",
                         (info or {}).get("expires"), now, warn_days)
    return out + ([exp] if exp else [])


def check_model(mode: str) -> Finding | None:
    """The model endpoint answers with the pipeline's key. None when off."""
    mode = (mode or "off").strip().lower()
    if mode == "off":
        return None
    alert = "credential:model"
    try:
        if mode == "models":
            import requests
            base = (os.getenv("OPENAI_API_BASE") or "https://api.openai.com/v1").rstrip("/")
            resp = requests.get(f"{base}/models", timeout=30,
                                headers={"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY', '')}"})
            if resp.status_code >= 400:
                raise RuntimeError(f"HTTP {resp.status_code}")
        else:
            from core import llm_client
            client = llm_client.LLMClient(temperature=0.0, max_output_tokens=1)
            response = client._call_with_quota_check(client.llm.invoke,
                                                     [("user", "Reply with OK.")])
            llm_client._record_usage(response, "health check")
    except BaseException as e:                                     # noqa: BLE001
        if isinstance(e, (KeyboardInterrupt, SystemExit)):
            raise
        from core.spend_budget import BudgetExceeded
        if isinstance(e, BudgetExceeded):
            # The pipeline's own budget stopped the check: nothing is known
            # about the key, so the alert is left as it is.
            logger.info("Model endpoint not checked: %s", e)
            return None
        return Finding(alert, True, "The model endpoint refused the pipeline's request",
                       f"{type(e).__name__}: {_redact(str(e))[:400]}. Agents that call the "
                       "model stop until this is fixed: check the key, its spend limit at "
                       "the provider, and OPENAI_API_BASE.")
    return Finding(alert, False, "The model endpoint answers")


def _redact(text: str) -> str:
    """No secret value, token-shaped string or email address in an alert."""
    import re
    for name in ("OPENAI_API_KEY", "GITHUB_TOKEN", "GH_PAT", "JIRA_API_TOKEN"):
        value = os.environ.get(name) or ""
        if len(value) >= 8:
            text = text.replace(value, "[redacted]")
    text = re.sub(r"\b(sk|ghp|gho|github_pat)[-_][A-Za-z0-9_\-]{8,}", "[redacted]", text)
    text = re.sub(r"\bKey=\S+", "Key=[redacted]", text)
    return re.sub(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", "[redacted]", text)
