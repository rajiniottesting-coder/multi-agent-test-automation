"""The checks behind the pipeline health issue (F-23).

Each check returns Finding(alert_id, problem, title, detail): `problem` True
opens the alert on the health issue, False closes it (core/pipeline_health.py
posts only on a change). scripts/pipeline_health_check.py runs them on a
schedule.

  workflows    a scheduled workflow whose last `consecutive_failures`
               scheduled runs all failed. The workflows are read from the
               repository's own workflow files, so a new scheduled workflow is
               watched without a code change.
  schedules    a scheduled workflow none of whose scheduled runs the repo
               host started in the last `schedule_window_hours`, although its
               cron lines asked for at least `schedule_min_expected`. A host
               may drop scheduled runs of a quiet repository; a run never
               started fails nothing, so the failure check cannot see it.
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


# ── scheduled runs the host never started ────────────────────

_DOW_SUNDAY = 7


def _field(text: str, low: int, high: int) -> set | None:
    """The values a cron field allows: `*`, `a`, `a-b`, `*/n`, `a-b/n`, lists.
    None when it cannot be read."""
    out: set = set()
    for part in text.split(","):
        rng, _sep, step = part.partition("/")
        try:
            n = int(step) if step else 1
            if rng == "*":
                a, b = low, high
            elif "-" in rng:
                a, b = (int(x) for x in rng.split("-", 1))
            else:
                a = b = int(rng)
        except ValueError:
            return None
        if n < 1 or a > b or a < low or b > high:
            return None
        out.update(range(a, b + 1, n))
    return out


def cron_fires(expr: str, start: _dt.datetime, end: _dt.datetime) -> int | None:
    """How many minutes in (start, end] a five-field cron line (UTC) names.
    None when the line cannot be read. Day of month and day of week, both
    restricted, match either - the usual cron rule."""
    parts = (expr or "").split()
    if len(parts) != 5:
        return None
    fields = [_field(parts[0], 0, 59), _field(parts[1], 0, 23), _field(parts[2], 1, 31),
              _field(parts[3], 1, 12), _field(parts[4], 0, _DOW_SUNDAY)]
    if any(f is None for f in fields):
        return None
    minute, hour, dom, month, dow = fields
    dow = {d % 7 for d in dow}
    dom_any, dow_any = parts[2] == "*", parts[4] == "*"
    t = start.replace(second=0, microsecond=0) + _dt.timedelta(minutes=1)
    count = 0
    while t <= end:
        if t.minute in minute and t.hour in hour and t.month in month:
            day_ok = t.day in dom
            week_ok = (t.isoweekday() % 7) in dow
            if (day_ok and week_ok) if (dom_any or dow_any) else (day_ok or week_ok):
                count += 1
        t += _dt.timedelta(minutes=1)
    return count


def schedule_lines(path: Path) -> list:
    """The cron lines of one workflow file."""
    import yaml
    try:
        on = _triggers(yaml.safe_load(Path(path).read_text(encoding="utf-8")))
    except Exception:                                              # noqa: BLE001
        return []
    sched = on.get("schedule") if isinstance(on, dict) else None
    return [s["cron"] for s in sched or [] if isinstance(s, dict) and s.get("cron")]


def _when(stamp) -> _dt.datetime | None:
    try:
        t = _dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=_dt.timezone.utc)


def schedule_findings(host, root: Path, now: _dt.datetime, window_hours: float,
                      min_expected: int) -> list:
    """One Finding per scheduled workflow whose runs can be judged: its cron
    lines asked for `expected` runs in the window; `started` of them began.
    No finding (the alert stays as it is) when the runs read do not reach
    back to the window's start, or a cron line cannot be read."""
    out = []
    start = now - _dt.timedelta(hours=window_hours)
    for name in scheduled_workflows(root):
        counts = [cron_fires(c, start, now)
                  for c in schedule_lines(Path(root) / ".github" / "workflows" / name)]
        if not counts or any(c is None for c in counts):
            continue
        expected = sum(counts)
        try:
            runs = host.get_workflow_runs(name, "main", limit=100)
        except Exception as e:                                     # noqa: BLE001
            logger.warning("Runs of %s not read: %s", name, e)
            continue
        times = [(_when(r.get("created_at")), r.get("event")) for r in runs or []]
        started = sum(1 for t, ev in times if ev == "schedule" and t and t > start)
        reaches = len(times) < 100 or any(t and t <= start for t, _ev in times)
        if not started and not reaches:
            continue                          # cannot tell: more runs than were read
        silent = expected >= min_expected and started == 0
        out.append(Finding(
            f"workflow-not-starting:{name}", silent,
            f"No scheduled run of {name} started in the last {window_hours:g} hours" if silent
            else f"Scheduled runs of {name} start again",
            f"Its schedule asked for {expected} runs in the last {window_hours:g} hours and the "
            "repository host started none. Nothing failed, so no other check sees it. Work "
            "still starts through the hand-offs and by hand; check the workflow is enabled and "
            "the schedule unchanged. It closes by itself once a scheduled run starts."))
    return out


# ── credentials ──────────────────────────────────────────────

def expiry_finding(alert_id: str, what: str, expires: str | None, now: _dt.datetime,
                   warn_days: int) -> Finding | None:
    """A warning when `expires` (a date the provider gave) is within `warn_days`."""
    if not expires:
        # The provider gave no date: the credential does not expire, so an
        # earlier warning (a token since replaced) can close.
        return Finding(alert_id, False, f"{what} has no expiry date")
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


def repo_host_findings(host_factory, now: _dt.datetime, warn_days: int,
                       per_run: bool = False) -> list:
    """The repo host's credentials: refused, or close to expiry.

    per_run: the token was created for this run (a GitHub App's installation
    token, F-30) - it expires within the hour by design and nobody replaces
    it, so there is no expiry to warn about (an earlier warning closes). What
    can break is the App itself; then creating the token fails the run before
    this check, and GitHub tells the workflow's owner."""
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
    if per_run:
        return out + [Finding("credential-expiry:repo-host", False,
                              "The repo host token is created for each run")]
    exp = expiry_finding("credential-expiry:repo-host", "The repo host token",
                         (info or {}).get("expires"), now, warn_days)
    return out + ([exp] if exp else [])


def check_model(mode: str, models=None) -> Finding | None:
    """The model endpoint answers with the pipeline's key. None when off.

    `models`: every model the agents use (blank -> LLM_MODEL). 4 Nov 2026: the
    check probed the light model and reported "answers" while the gateway
    refused the coding model with HTTP 402 - a refusal can be per model."""
    mode = (mode or "off").strip().lower()
    if mode == "off":
        return None
    alert = "credential:model"
    names = list(dict.fromkeys(m.strip() for m in (models or []) if m and m.strip())) or [None]
    refused, unknown = [], 0
    for name in names:
        problem = _probe_model(mode, name)
        if problem is None:
            unknown += 1
        elif problem:
            refused.append(f"{name or os.getenv('LLM_MODEL', 'the model')}: {problem}")
    if refused:
        return Finding(alert, True, "The model endpoint refused the pipeline's request",
                       "; ".join(refused)[:800] + ". Agents that call the model stop until "
                       "this is fixed: check the key, its spend limit at the provider (per "
                       "model, if the provider sets one), and OPENAI_API_BASE.")
    if unknown == len(names):
        return None
    return Finding(alert, False, "The model endpoint answers")


def _probe_model(mode: str, name: str | None):
    """"" when `name` answers, the refusal (redacted) when it does not, None
    when nothing is known (the pipeline's own budget stopped the probe)."""
    try:
        if mode == "models":
            import requests
            base = (os.getenv("OPENAI_API_BASE") or _client_default_base()).rstrip("/")
            resp = requests.get(f"{base}/models", timeout=30,
                                headers={"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY', '')}"})
            if resp.status_code >= 400:
                raise RuntimeError(f"HTTP {resp.status_code}")
        else:
            from core import llm_client
            saved = os.environ.get("LLM_MODEL")
            if name:
                os.environ["LLM_MODEL"] = name
            try:
                client = llm_client.LLMClient(temperature=0.0, max_output_tokens=1)
                response = client._call_with_quota_check(client.llm.invoke,
                                                         [("user", "Reply with OK.")])
            finally:
                if saved is None:
                    os.environ.pop("LLM_MODEL", None)
                else:
                    os.environ["LLM_MODEL"] = saved
            llm_client._record_usage(response, "health check")
    except BaseException as e:                                     # noqa: BLE001
        if isinstance(e, (KeyboardInterrupt, SystemExit)):
            raise
        from core.spend_budget import PROVIDER, BudgetExceeded
        if isinstance(e, BudgetExceeded) and e.scope != PROVIDER:
            # The pipeline's own budget stopped the check: nothing is known
            # about the key, so the alert is left as it is. The provider
            # refusing for money IS what this check is for.
            logger.info("Model endpoint not checked: %s", e)
            return None
        return f"{type(e).__name__}: {_redact(str(e))[:400]}"
    return ""


def _client_default_base() -> str:
    """The endpoint the model client itself uses when OPENAI_API_BASE is unset
    - owned by the client library, the same one LLMClient talks to, so the
    check never names a provider of its own."""
    from openai import OpenAI
    return str(OpenAI(api_key="unused").base_url)


def _redact(text: str) -> str:
    """No secret value, token-shaped string, private key or email address in an
    alert (core/redaction.py - the same rules as Agent 3's failure note)."""
    from core.redaction import redact
    return redact(text)
