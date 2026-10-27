"""Model spend budgets: per story and per day (F-24).

WHY
    Nothing limited what the pipeline could spend. A story stuck in a
    regenerate loop, or a busy day, ran until the provider's key budget was
    exhausted - twice ($30, then $15 caps) - and then EVERY agent stopped,
    including the reviews of unrelated pull requests.

WHAT (config.yaml `budget`, core/ops_settings.py)
    per_story_usd   a story's model cost since its ledger's last reset (the
                    usage ledger, core/usage_ledger.py) plus this run's.
    per_day_usd     the whole pipeline's cost today (`timezone`): EVERY model
                    call counts - story agents, reviews of framework PRs,
                    context and inventory proposals, Agent 0, the health check.
    warn_at         a pipeline health alert when the day passes this share;
                    Agent 5's cost line marks a story past it.

    Checked before EVERY model call (core.llm_client.LLMClient
    ._call_with_quota_check). Over a limit, BudgetExceeded is raised before the
    call - nothing is spent - and the message says which limit, how much, and
    what to do.

    BudgetExceeded derives from BaseException on purpose: the agents retry,
    repair and record failures with `except Exception`, and a budget stop
    caught there would be retried (each retry stopped again at no cost) and
    then reported as the wrong problem - a gate failure, a blocked story. Only
    the places that know what a stop means catch it: story_usage, the scan
    loops and the agents' entry points.

    A story over its budget is labelled `hold_label` (every agent's selection
    excludes it) with one `[budget:hold]` comment saying how much it spent.
    Removing the label allows it one more `per_story_usd`. A day over its
    budget opens a health alert; scans stop starting stories (green - the
    alert is the notice) and resume the next day.

    How the day is counted: each process records its spend at exit as one
    append-only record on the pipeline health issue
    (`spend.<YYYYMMDD>.<micro-USD>.<unique>`), so a day's total is one listing
    of keys and two runs never overwrite each other. A process reads the day's
    total once, at its first model call, and adds its own spend; runs going on
    at the same time are not seen until they finish, so the limit can be
    passed by what concurrent runs spend - bounded by one run each.

WHEN IT APPLIES
    In CI (GITHUB_ACTIONS=true) and never inside a pytest test, unless
    PIPELINE_BUDGET=on (force, e.g. a local run) or =off (disable). Without
    pricing (LLM_PRICE_*_PER_1M) no cost is known: nothing is enforced, and the
    log says so once.
"""
from __future__ import annotations

import atexit
import datetime as _dt
import logging
import os
import re
import sys

from core.ops_settings import section

logger = logging.getLogger(__name__)

HOLD_MARKER = "[budget:hold]"
SPEND_PREFIX = "spend"
_HOLD_RE = re.compile(r"^\[budget:hold\]\s+spent:\s*([\d.]+)", re.M)


class BudgetExceeded(BaseException):
    """A model call was stopped by a spend budget. See the module docstring
    for why this is not an Exception."""

    def __init__(self, scope: str, message: str, story: str | None = None,
                 spent: float | None = None, limit: float | None = None):
        super().__init__(message)
        self.scope, self.story, self.spent, self.limit = scope, story, spent, limit


def _fresh_state() -> dict:
    return {"tracker": None, "tracker_failed": False, "day": None, "day_prior": None,
            "day_base": 0.0, "story": None, "recorded": 0.0, "registered": False,
            "warned": set(), "alerted": set()}


_state = _fresh_state()


def reset() -> None:
    """For tests: forget everything this process learned (and record nothing
    at exit)."""
    atexit.unregister(record_run)
    _state.clear()
    _state.update(_fresh_state())


def settings() -> dict:
    return section("budget")


def active() -> bool:
    forced = (os.getenv("PIPELINE_BUDGET") or "").strip().lower()
    if forced in ("off", "0", "false", "no"):
        return False
    if not settings().get("enabled", True):
        return False
    if forced in ("on", "1", "true", "yes"):
        return True
    return os.getenv("GITHUB_ACTIONS") == "true" and "PYTEST_CURRENT_TEST" not in os.environ


def _warn_once(key: str, message: str, *args) -> None:
    if key not in _state["warned"]:
        _state["warned"].add(key)
        logger.warning(message, *args)


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def day_of(now: _dt.datetime) -> str:
    """YYYYMMDD of `now` in the budget's time zone (UTC when unknown)."""
    tz_name = settings().get("timezone") or "UTC"
    try:
        from zoneinfo import ZoneInfo
        return now.astimezone(ZoneInfo(tz_name)).strftime("%Y%m%d")
    except Exception:                                              # noqa: BLE001
        _warn_once("tz", "budget.timezone %r is unknown; the day is counted in UTC.", tz_name)
        return now.astimezone(_dt.timezone.utc).strftime("%Y%m%d")


def _lifetime():
    from core import llm_client
    return llm_client.lifetime_cost_usd()


def _tracker():
    if _state["tracker"] is None and not _state["tracker_failed"]:
        try:
            from integrations.tracker import get_tracker
            _state["tracker"] = get_tracker()
        except Exception as e:                                     # noqa: BLE001
            _state["tracker_failed"] = True
            _warn_once("tracker", "Spend budget: no tracker (%s) - the day's spend is not "
                       "counted or recorded.", e)
    return _state["tracker"]


def current_tracker():
    """The tracker the budget reads and records with (built when needed)."""
    return _tracker()


def use_tracker(tracker) -> None:
    """Let the budget use the caller's tracker instead of building one."""
    if tracker is not None and _state["tracker"] is None:
        _state["tracker"] = tracker


# ── the day ───────────────────────────────────────────────────

def _micro(key: str, prefix: str) -> int:
    try:
        return int(key[len(prefix):].split(".")[1])
    except (IndexError, ValueError):
        return 0


def day_spent(tracker, day: str, issue: str | None = None) -> float | None:
    """USD recorded for `day` on the health issue, or None when unreadable."""
    from core import pipeline_health
    issue = issue or pipeline_health.issue_key(tracker, create=False)
    if issue is None:
        return 0.0
    from integrations.tracker import capability
    if capability(tracker, "property_keys") is None:
        return None
    prefix = f"{SPEND_PREFIX}.{day}."
    keys = pipeline_health.record_keys(tracker, SPEND_PREFIX, issue)
    return sum(_micro(k, SPEND_PREFIX + ".") for k in keys if k.startswith(prefix)) / 1_000_000


def day_summary(tracker, issue: str, now: _dt.datetime) -> dict | None:
    """{"day", "spent", "limit"} for the health issue's description."""
    s = settings()
    if not s.get("enabled", True):
        return None
    day = day_of(now)
    spent = day_spent(tracker, day, issue)
    if spent is None:
        return None
    return {"day": f"{day[:4]}-{day[4:6]}-{day[6:]}", "spent": spent,
            "limit": float(s["per_day_usd"])}


def _load_day(now: _dt.datetime) -> None:
    day = day_of(now)
    if _state["day"] == day:
        return
    # The first day this process sees owns everything it spent; when the day
    # turns while it runs, what it spent before belongs to the day before.
    _state["day_base"] = (_lifetime() or 0.0) if _state["day"] is not None else 0.0
    _state["day"] = day
    tracker = _tracker()
    _state["day_prior"] = day_spent(tracker, day) if tracker is not None else None
    if _state["day_prior"] is None:
        _warn_once("day", "Spend budget: today's spend cannot be read - only this run's own "
                   "spend counts toward budget.per_day_usd.")
    if not _state["registered"]:
        atexit.register(record_run)
        _state["registered"] = True


def record_run() -> bool:
    """Record this process's spend not yet recorded (at exit). Never raises."""
    try:
        spent = _lifetime()
        if spent is None or not active():
            return False
        delta = spent - _state["recorded"]
        if delta <= 0:
            return False
        tracker = _tracker()
        if tracker is None:
            return False
        from core import llm_client, pipeline_health
        value = {"usd": round(delta, 6), "calls": llm_client.lifetime_calls(),
                 "run": os.getenv("GITHUB_RUN_ID", ""), "workflow": os.getenv("GITHUB_WORKFLOW", ""),
                 "job": os.getenv("GITHUB_JOB", "")}
        if pipeline_health.record(tracker, SPEND_PREFIX,
                                  [day_of(_now()), int(round(delta * 1_000_000))], value):
            _state["recorded"] = spent
            return True
    except Exception as e:                                         # noqa: BLE001
        logger.warning("Spend not recorded: %s", e)
    return False


# ── the story ─────────────────────────────────────────────────

def hold_state(comments: list, labels: list, hold_label: str) -> tuple:
    """(spent at the last hold or None, held now?) from the comments after the
    ledger's last reset and the story's labels."""
    from core.usage_ledger import _comments_after_last_reset
    spent = None
    for body in _comments_after_last_reset(comments or []):
        m = _HOLD_RE.search(body or "")
        if m:
            spent = float(m.group(1))
    return spent, hold_label in (labels or [])


def begin_story(story_key: str, tracker=None) -> None:
    """Start counting `story_key`'s budget for the calls that follow."""
    _state["story"] = None
    if not story_key or not active():
        return
    s = settings()
    use_tracker(tracker)
    tracker = _tracker()
    if tracker is None:
        return
    try:
        from core.usage_ledger import aggregate_story_usage
        comments = tracker.get_comments(story_key)
        prior = aggregate_story_usage(comments).get("total_cost_usd") or 0.0
        labels = (tracker.get_story(story_key) or {}).get("labels") or []
        held_at, held = hold_state(comments, labels, s["hold_label"])
    except Exception as e:                                         # noqa: BLE001
        logger.warning("Story budget of %s not read (%s); not enforced for it.", story_key, e)
        return
    per_story = float(s["per_story_usd"])
    if held_at is None:
        allowance = per_story
    else:
        allowance = held_at + (0.0 if held else per_story)
    _state["story"] = {"key": story_key, "prior": float(prior), "base": _lifetime() or 0.0,
                       "allowance": allowance, "tracker": tracker}


def end_story() -> None:
    _state["story"] = None


def story_spent() -> float | None:
    """The current story's cost so far (ledger + this run), None when not counted."""
    story = _state["story"]
    spent = _lifetime()
    if not story or spent is None:
        return None
    return story["prior"] + spent - story["base"]


def hold_story(tracker, exc: BudgetExceeded) -> bool:
    """Label the story and post one `[budget:hold]` comment. Never raises."""
    if exc.scope != "story" or not exc.story:
        return False
    s = settings()
    try:
        labels = (tracker.get_story(exc.story) or {}).get("labels") or []
        if s["hold_label"] in labels:
            return False                                   # already held: nothing new to say
        tracker.add_comment(exc.story, (
            f"{HOLD_MARKER} spent: {exc.spent:.4f} limit: {exc.limit:.2f}\n"
            f"Model spend for this story reached its budget: ${exc.spent:.2f} of "
            f"${exc.limit:.2f}. No agent works on it while it carries the label "
            f"`{s['hold_label']}`.\n"
            f"To continue: remove the label - the story may then spend another "
            f"${float(s['per_story_usd']):.2f} (budget.per_story_usd). To stop: nothing more "
            f"to do."))
        tracker.add_label(exc.story, s["hold_label"])
        return True
    except Exception as e:                                         # noqa: BLE001
        logger.warning("Budget hold on %s not recorded: %s", exc.story, e)
        return False


# ── the check before every model call ────────────────────────

def _alert(alert_id: str, title: str, detail: str) -> None:
    if alert_id in _state["alerted"]:
        return
    _state["alerted"].add(alert_id)
    tracker = _tracker()
    if tracker is None:
        return
    try:
        from core import pipeline_health
        pipeline_health.raise_alert(tracker, alert_id, title, detail)
    except Exception as e:                                         # noqa: BLE001
        logger.warning("Budget alert %s not posted: %s", alert_id, e)


def check_before_call() -> None:
    """Raise BudgetExceeded when the next model call would start over a limit."""
    if not active():
        return
    spent = _lifetime()
    if spent is None:
        _warn_once("pricing", "Spend budget: LLM_PRICE_INPUT_PER_1M / LLM_PRICE_OUTPUT_PER_1M "
                   "are not set, so no cost is known and no budget is enforced.")
        return
    s = settings()
    now = _now()
    _load_day(now)
    day, per_day = _state["day"], float(s["per_day_usd"])
    # Without a readable day total only this process's own spend counts.
    today = (_state["day_prior"] or 0.0) + spent - _state["day_base"]
    when = f"{day[:4]}-{day[4:6]}-{day[6:]}"
    if today >= per_day:
        _alert(f"budget-day-{day}", f"Daily model budget reached: ${today:.2f} of "
                                    f"${per_day:.2f} ({when})",
               "Agents stop before their next model call until the day ends "
               f"({s.get('timezone') or 'UTC'}); scans resume then. Pull request reviews "
               "wait too. To continue today, raise budget.per_day_usd in config.yaml.")
        _install_excepthook()
        raise BudgetExceeded(
            "day", f"Daily model budget reached: ${today:.2f} of ${per_day:.2f} on {when} "
                   f"(budget.per_day_usd). Runs resume when the day ends "
                   f"({s.get('timezone') or 'UTC'}), or raise budget.per_day_usd.",
            spent=today, limit=per_day)
    if today >= float(s["warn_at"]) * per_day:
        _alert(f"budget-warn-{day}", f"Model spend passed {float(s['warn_at']):.0%} of the "
                                     f"daily budget: ${today:.2f} of ${per_day:.2f} ({when})",
               "Nothing has stopped. At the limit, agents stop before their next model "
               "call until the day ends.")
    story = _state["story"]
    if story:
        total = story["prior"] + spent - story["base"]
        if total >= story["allowance"]:
            _install_excepthook()
            raise BudgetExceeded(
                "story", f"Story {story['key']} reached its model budget: ${total:.2f} of "
                         f"${story['allowance']:.2f} (budget.per_story_usd). It is held "
                         f"(label {s['hold_label']}); remove the label to allow it another "
                         f"${float(s['per_story_usd']):.2f}.",
                story=story["key"], spent=total, limit=story["allowance"])


def _install_excepthook() -> None:
    """An uncaught budget stop prints its reason, not a traceback."""
    if getattr(sys.excepthook, "_budget", False):
        return
    previous = sys.excepthook

    def hook(kind, value, tb):
        if isinstance(value, BudgetExceeded):
            print(f"[BUDGET] {value}", file=sys.stderr)
            return
        previous(kind, value, tb)
    hook._budget = True
    sys.excepthook = hook
