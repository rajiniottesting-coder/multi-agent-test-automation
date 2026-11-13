"""A story's test results over its runs, as a chart on Agent 5's comment (RP10).

Each report Agent 5 posts records the story's counts as a hidden issue property
(`trend.<UTC time>`, append-only - two runs never overwrite each other). From
the second run on, the comment carries a small chart of the last
`reporting.story_trend_points` runs: passed, failed and not judged (outage)
per run, so a reviewer sees the story going red to green - or not - over its
review rounds without opening each report.

Optional capabilities only (set_property, properties, add_attachment);
Matplotlib from requirements-reports.txt. Anything missing: no chart, the
comment is posted as before. Never raises.
"""
from __future__ import annotations

import datetime as _dt
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PREFIX = "trend."
COLORS = {"passed": "#2e7d32", "failed": "#c62828", "outage": "#6a1b9a", "skipped": "#9e9e9e"}


def entry(passed: int, failed: int, skipped: int, outage: int, run_url: str | None,
          commit: str | None, now: _dt.datetime | None = None) -> dict:
    now = now or _dt.datetime.now(_dt.timezone.utc)
    return {"at": now.isoformat(timespec="seconds"), "passed": passed, "failed": failed,
            "skipped": skipped, "outage": outage, "run": run_url, "commit": (commit or "")[:7]}


def record(tracker, story_key: str, item: dict) -> bool:
    from integrations.tracker import capability
    setter = capability(tracker, "set_property")
    if setter is None:
        return False
    try:
        stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")
        setter(story_key, PREFIX + stamp, item)
        return True
    except Exception as e:                                         # noqa: BLE001
        logger.warning("Trend of %s not recorded: %s", story_key, e)
        return False


def history(tracker, story_key: str, points: int) -> list[dict]:
    """The story's last `points` runs, oldest first."""
    from integrations.tracker import capability
    read = capability(tracker, "properties")
    if read is None:
        return []
    try:
        found = read(story_key, PREFIX)
    except Exception as e:                                         # noqa: BLE001
        logger.warning("Trend of %s not read: %s", story_key, e)
        return []
    rows = [v for _k, v in sorted(found.items()) if isinstance(v, dict)]
    return rows[-points:] if points > 0 else rows


def chart(rows: list[dict], path: Path, story_key: str) -> bool:
    """A stacked bar per run. False when Matplotlib is not installed."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        logger.info("Matplotlib not installed: no trend chart.")
        return False
    x = list(range(len(rows)))
    fig, ax = plt.subplots(figsize=(5.6, 2.0), dpi=120)
    bottom = [0] * len(rows)
    for k, c in COLORS.items():
        vals = [int(r.get(k) or 0) for r in rows]
        if any(vals):
            ax.bar(x, vals, bottom=bottom, color=c, label=k, width=0.65)
            bottom = [b + v for b, v in zip(bottom, vals)]
    ax.set_xticks(x, [str(r.get("at", ""))[5:16].replace("T", " ") for r in rows],
                  rotation=35, fontsize=6, ha="right")
    ax.set_ylabel("tests", fontsize=7)
    ax.tick_params(axis="y", labelsize=7)
    ax.set_title(f"{story_key}: results per run", fontsize=8)
    ax.legend(fontsize=6, frameon=False, loc="upper left", bbox_to_anchor=(1.01, 1.0))
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return True


def attach_chart(tracker, story_key: str, item: dict, workdir: Path,
                 settings: dict | None = None) -> str | None:
    """Record this run and, from the `story_trend_min_points`-th run on,
    attach the chart: the markup that shows it in the comment, else None."""
    from integrations.tracker import capability
    try:
        if settings is None:
            from core.ops_settings import section
            settings = section("reporting")
        if not settings.get("story_trend", True):
            return None
        if not record(tracker, story_key, item):
            return None
        rows = history(tracker, story_key, int(settings.get("story_trend_points") or 10))
        if not any(r.get("at") == item["at"] for r in rows):
            rows.append(item)                 # a property read before it is visible
        if len(rows) < int(settings.get("story_trend_min_points") or 2):
            return None
        attach = capability(tracker, "add_attachment")
        if attach is None:
            return None
        workdir.mkdir(parents=True, exist_ok=True)
        name = f"test-trend-{story_key.lower()}-{item['at'][:19].replace(':', '').replace('-', '')}.png"
        path = workdir / name
        if not chart(rows, path, story_key):
            return None
        return attach(story_key, path, name)
    except Exception as e:                                         # noqa: BLE001
        from core.redaction import error_text
        logger.warning("Trend chart of %s skipped: %s", story_key, error_text(e))
        return None
