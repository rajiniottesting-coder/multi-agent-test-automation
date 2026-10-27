"""Pipeline health: one standing tracker issue that people watch (F-23).

WHY
    A scheduled agent that kept failing, an expired credential, a test failing
    on main, a spent model budget: each showed up only as a red run in the
    Actions tab, which nobody is told about. The pipeline could stop quietly.

WHAT
    One issue (`pipeline_health.summary`, labelled `pipeline_health.label`)
    found by its label - created the first time something needs it. People
    WATCH it, so the tracker emails them on each comment:

      comments     one per alert CHANGE - "[health:open] <id>" when a problem
                   starts, "[health:resolved] <id>" when it ends. A problem
                   that persists over many checks posts nothing more. The
                   comments are also the alert state (the last one per id).
      description  the current picture, rewritten on each change: open
                   alerts, flaky tests, today's model spend. Never read back.
      properties   append-only records other features keep here (flaky tests,
                   the day's spend) - hidden, and race-free because no run
                   ever rewrites another's key (OPTIONAL CAPABILITIES in
                   integrations/tracker.py).

    Every function is best-effort: health bookkeeping never fails the run that
    calls it. Generic: no application, workflow or tracker name lives here.
"""
from __future__ import annotations

import datetime as _dt
import logging
import re

from core.ops_settings import section
from integrations.tracker import capability

logger = logging.getLogger(__name__)

OPEN = "[health:open]"
RESOLVED = "[health:resolved]"
_ALERT_LINE = re.compile(r"^\[health:(open|resolved)\]\s+(\S+)")

# One lookup per process and tracker: the issue does not move.
_issue_cache: dict = {}
_warned: set = set()


def settings() -> dict:
    return section("pipeline_health")


def _warn_once(key: str, message: str, *args) -> None:
    if key not in _warned:
        _warned.add(key)
        logger.warning(message, *args)


def _key_number(key: str) -> int:
    try:
        return int(str(key).rsplit("-", 1)[1])
    except (IndexError, ValueError):
        return 1 << 62


def _render(tracker, markdown: str) -> str:
    render = capability(tracker, "render_markdown")
    try:
        return render(markdown) if render else markdown
    except Exception:                                              # noqa: BLE001
        return markdown


def issue_key(tracker, create: bool = True):
    """The health issue's key, creating it when absent (and `create`), or None.

    Found by label. Two runs creating it at the same moment would leave two;
    the oldest (lowest key) is always the one used, so they never split the
    alerts between them.
    """
    s = settings()
    if not s.get("enabled") or tracker is None:
        return None
    cached = _issue_cache.get(id(tracker))
    if cached and cached[0] is tracker:
        return cached[1]
    try:
        found = tracker.find_stories_to_process(
            {"issue_type": s["issue_type"], "required_labels": [s["label"]]}, max_results=10)
        keys = sorted((f["key"] for f in found or [] if f.get("key")), key=_key_number)
    except Exception as e:                                         # noqa: BLE001
        logger.warning("Pipeline health issue not looked up: %s", e)
        return None
    if keys:
        _issue_cache[id(tracker)] = (tracker, keys[0])
        return keys[0]
    if not create:
        return None
    create_issue = capability(tracker, "create_issue")
    if create_issue is None:
        _warn_once("create", "Pipeline health: the tracker cannot create issues "
                   "(create_issue) - alerts are logged only.")
        return None
    try:
        key = create_issue(s["issue_type"], s["summary"], _render(tracker, _intro()), [s["label"]])
    except Exception as e:                                         # noqa: BLE001
        logger.warning("Pipeline health issue not created: %s", e)
        return None
    logger.info("Pipeline health issue created: %s", key)
    _issue_cache[id(tracker)] = (tracker, key)
    return key


def _intro() -> str:
    return ("Maintained by the pipeline. **Watch this issue** to be told when something "
            "needs a person: each problem opens with a comment and closes with one, and "
            "nothing is posted while it simply persists. This description is the current "
            "picture and is rewritten on every change - edits to it are not kept.")


# ── alerts ────────────────────────────────────────────────────

def alert_states(comments) -> dict:
    """{alert id: (state, body)} from the issue's comments - the last one wins."""
    out: dict = {}
    for body in comments or []:
        m = _ALERT_LINE.match((body or "").lstrip())
        if m:
            out[m.group(2)] = (m.group(1), body)
    return out


def open_alerts(tracker) -> dict:
    """{alert id: body} for every alert currently open."""
    key = issue_key(tracker, create=False)
    if not key:
        return {}
    try:
        states = alert_states(tracker.get_comments(key))
    except Exception as e:                                         # noqa: BLE001
        logger.warning("Pipeline health alerts not read: %s", e)
        return {}
    return {a: body for a, (state, body) in states.items() if state == "open"}


def _alert_id(alert_id: str) -> str:
    return re.sub(r"\s+", "-", str(alert_id).strip())


def raise_alert(tracker, alert_id: str, title: str, detail: str = "") -> bool:
    """Open an alert. Posts one comment the first time; nothing while it stays
    open. Returns True when it posted."""
    alert_id = _alert_id(alert_id)
    key = issue_key(tracker)
    if not key:
        logger.warning("ALERT (not posted, no health issue) %s: %s %s", alert_id, title, detail)
        return False
    try:
        state = alert_states(tracker.get_comments(key)).get(alert_id, ("resolved", ""))[0]
        if state == "open":
            return False
        body = f"{OPEN} {alert_id}\n**{title}**" + (f"\n\n{detail}" if detail else "")
        tracker.add_comment(key, _render(tracker, body))
        logger.warning("Pipeline health alert opened on %s - %s: %s", key, alert_id, title)
    except Exception as e:                                         # noqa: BLE001
        logger.warning("Pipeline health alert %s not posted: %s", alert_id, e)
        return False
    refresh_view(tracker)
    return True


def resolve_alert(tracker, alert_id: str, note: str = "") -> bool:
    """Close an open alert with one comment. Nothing when it is not open."""
    alert_id = _alert_id(alert_id)
    key = issue_key(tracker, create=False)
    if not key:
        return False
    try:
        state = alert_states(tracker.get_comments(key)).get(alert_id, ("resolved", ""))[0]
        if state != "open":
            return False
        body = f"{RESOLVED} {alert_id}" + (f"\n{note}" if note else "")
        tracker.add_comment(key, _render(tracker, body))
        logger.info("Pipeline health alert resolved on %s - %s", key, alert_id)
    except Exception as e:                                         # noqa: BLE001
        logger.warning("Pipeline health alert %s not resolved: %s", alert_id, e)
        return False
    refresh_view(tracker)
    return True


def resolve_where(tracker, predicate, note: str = "") -> list:
    """Resolve every open alert whose id satisfies `predicate`."""
    done = []
    for alert_id in sorted(open_alerts(tracker)):
        if predicate(alert_id) and resolve_alert(tracker, alert_id, note):
            done.append(alert_id)
    return done


# ── the description: the current picture ─────────────────────

def _title_of(body: str) -> str:
    m = re.search(r"\*\*(.+?)\*\*|^\*(.+?)\*$", body or "", re.M)
    return (m.group(1) or m.group(2)) if m else ""


def _sections() -> list:
    """(render_view argument, summary function) for each record kept here."""
    from core import flaky_tests
    return [("flaky", flaky_tests.summary)]


def render_view(alerts: dict, flaky: list | None = None, spend: dict | None = None,
                now: _dt.datetime | None = None) -> str:
    """Markdown for the description. `flaky` is [(test, times, last day)],
    `spend` {"day", "spent", "limit"} or None."""
    lines = [_intro(), "", f"## Open alerts ({len(alerts)})", ""]
    if alerts:
        lines += [f"- `{a}` - {_title_of(b) or 'see its comment'}" for a, b in sorted(alerts.items())]
    else:
        lines.append("None.")
    if flaky is not None:
        window = section("flaky_tests").get("window_days", 30)
        lines += ["", f"## Flaky tests (last {window} days)", "",
                  "Failed, then passed when retried once. Counted as passed and kept out "
                  "of defects. A test listed here often is worth fixing or quarantining.", ""]
        if flaky:
            lines += ["| Test | Times | Last seen |", "|---|---|---|"]
            lines += [f"| `{t}` | {n} | {d} |" for t, n, d in flaky[:25]]
            if len(flaky) > 25:
                lines += ["", f"...and {len(flaky) - 25} more."]
        else:
            lines.append("None recorded.")
    now = now or _dt.datetime.now(_dt.timezone.utc)
    lines += ["", f"_Updated {now.strftime('%Y-%m-%d %H:%M')} UTC._"]
    return "\n".join(lines)


def refresh_view(tracker, now: _dt.datetime | None = None) -> bool:
    """Rewrite the description from the alerts, the flaky records and today's
    spend. Last writer wins, and every writer renders the complete state, so
    no record is lost by a concurrent refresh."""
    key = issue_key(tracker, create=False)
    if not key:
        return False
    now = now or _dt.datetime.now(_dt.timezone.utc)
    try:
        text = render_view(open_alerts(tracker), now=now,
                           **{name: fn(tracker, key, now) for name, fn in _sections()})
        tracker.set_description(key, _render(tracker, text))
        return True
    except Exception as e:                                         # noqa: BLE001
        logger.warning("Pipeline health view not refreshed: %s", e)
        return False


# ── append-only records (properties) ─────────────────────────

def record(tracker, prefix: str, parts: list, value) -> bool:
    """Store `value` under a NEW key `<prefix>.<part>.<part>...<unique>` on the
    health issue. Never overwrites: concurrent runs cannot lose each other's
    records. False when the tracker has no properties or the write failed."""
    import uuid
    setter = capability(tracker, "set_property")
    if setter is None:
        _warn_once("props", "Pipeline health: the tracker has no issue properties "
                   "(set_property) - flaky-test and spend records are off.")
        return False
    key = issue_key(tracker)
    if not key:
        return False
    name = ".".join([prefix, *[str(p) for p in parts], uuid.uuid4().hex[:10]])
    try:
        setter(key, name[:255], value)
        return True
    except Exception as e:                                         # noqa: BLE001
        logger.warning("Pipeline health record %s not stored: %s", prefix, e)
        return False


def record_keys(tracker, prefix: str, issue: str | None = None) -> list:
    """Every record key under `prefix.` (one request), [] when unavailable."""
    keys_of = capability(tracker, "property_keys")
    issue = issue or issue_key(tracker, create=False)
    if keys_of is None or not issue:
        return []
    try:
        return [k for k in keys_of(issue) or [] if isinstance(k, str)
                and k.startswith(prefix + ".")]
    except Exception as e:                                         # noqa: BLE001
        logger.warning("Pipeline health records %s not read: %s", prefix, e)
        return []


def prune(tracker, prefix: str, keep_from: str, day_part: int = 1) -> int:
    """Delete records whose day (the `day_part`-th dotted part after the
    prefix, YYYYMMDD) is before `keep_from`. Returns how many were deleted."""
    deleter = capability(tracker, "delete_property")
    issue = issue_key(tracker, create=False)
    if deleter is None or not issue:
        return 0
    gone = 0
    for k in record_keys(tracker, prefix, issue):
        parts = k[len(prefix) + 1:].split(".")
        day = parts[day_part - 1] if len(parts) >= day_part else ""
        if re.fullmatch(r"\d{8}", day) and day < keep_from:
            try:
                deleter(issue, k)
                gone += 1
            except Exception as e:                                 # noqa: BLE001
                logger.warning("Pipeline health record %s not deleted: %s", k, e)
    return gone


def reset_cache() -> None:
    """For tests: forget the looked-up issue and the once-only warnings."""
    _issue_cache.clear()
    _warned.clear()
