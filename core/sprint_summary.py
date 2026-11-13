"""The sprint's test summary on the tracker (RP7).

On the active sprint's last day (or when asked, `--sprint-summary force`), the
Reports workflow records one issue per sprint - `Test summary: <sprint>` of
type `reporting.sprint_summary_issue_type`, labelled LABEL - with the numbers
the site shows, a link to the site, and the PDF attached. It is a record, not
work: it is moved to `reporting.sprint_summary_status` at once so it never sits
in the board's open columns.

Once per sprint: an existing summary is left alone; with `force` the current
numbers are added to it as a comment (and the PDF again). Optional capabilities
only (integrations.tracker.capability) - a tracker without them gets no
summary and the log says so. Never raises.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

LABEL = "test-sprint-summary"


def title(sprint: dict) -> str:
    return f"Test summary: {sprint.get('name') or 'sprint'}"


def _pct(v) -> str:
    return "-" if v is None else f"{v * 100:.0f}%"


def summary_markdown(data: dict, site_url: str | None) -> str:
    """The summary's text, in Markdown, from build_site's data."""
    k = data["kpis"]
    sprint = data.get("sprint") or {}
    latest = k.get("latest_run") or {}
    lines = [f"Automated test summary for **{sprint.get('name', 'the sprint')}** "
             f"({str(sprint.get('start') or '')[:10]} to {str(sprint.get('end') or '')[:10]}), "
             f"generated {data['generated']} UTC from the last {data['window_days']} days "
             "of full runs on the default branch.", "",
             "| Measure | Value |", "|---|---|",
             f"| Pass rate, latest run | {_pct(k['latest_pass_rate'])} |",
             f"| Pass rate, window | {_pct(k['window_pass_rate'])} |",
             f"| Runs | {k['runs']} |", f"| Tests in the latest run | {latest.get('tests', k['tests'])} |",
             f"| Flaky passes | {k['flaky']} |",
             f"| Open defects | {data['defects']['total'] if data.get('defects') else 'not read'} |"]
    if latest:
        lines.append(f"| Latest run | {latest.get('passed', 0)} passed, {latest.get('flaky', 0)} flaky, "
                     f"{latest.get('failed', 0)} failed, {latest.get('outage', 0)} outage |")
    failing = [r for r in data.get("by_file") or [] if r.get("failed")]
    risks = [f"{r['name']}: {r['failed']} failing of {r['tests']}" for r in failing]
    risks += [f"{r['test']} flaked {r['flaky']} times in {r['runs']} runs"
              for r in (data.get("flaky") or [])[:5]]
    sm = data.get("traceability_summary")
    if sm and sm.get("criteria_uncovered"):
        risks.append(f"{sm['criteria_uncovered']} acceptance criteria have no test case")
    lines += ["", "**Risks**", ""] + [f"- {r}" for r in risks or ["None found in the window."]]
    if site_url:
        lines += ["", f"Dashboard, traceability and the Allure report: {site_url}"]
    lines += ["", "The PDF summary is attached."]
    return "\n".join(lines)


def _existing(tracker, issue_type: str, name: str) -> str | None:
    from integrations.tracker import capability
    read = capability(tracker, "issues_for_report")
    if read is None:
        return None
    for issue in read(issue_type, open_only=False, labels=[LABEL]):
        if issue.get("summary") == name:
            return issue["key"]
    return None


def post(tracker, data: dict, pdf: Path | None, site_url: str | None,
         force: bool = False, settings: dict | None = None) -> str | None:
    """Record the sprint's summary; the issue's key, or None when nothing was
    recorded (no sprint, switched off, the tracker cannot)."""
    from integrations.tracker import capability
    try:
        if settings is None:
            from core.ops_settings import section
            settings = section("reporting")
        sprint = data.get("sprint")
        if not settings.get("sprint_summary", True) or not sprint:
            logger.info("Sprint summary: %s.", "switched off" if sprint else "no active sprint")
            return None
        create = capability(tracker, "create_issue")
        if create is None:
            logger.info("Sprint summary: the tracker cannot create an issue.")
            return None
        issue_type = settings.get("sprint_summary_issue_type") or "Task"
        name = title(sprint)
        text = summary_markdown(data, site_url)
        render = capability(tracker, "render_markdown")
        body = render(text) if render else text
        attach = capability(tracker, "add_attachment")
        key = _existing(tracker, issue_type, name)
        if key and not force:
            logger.info("Sprint summary: %s already records %s.", key, name)
            return key
        if key:
            note = body
            if attach and pdf and Path(pdf).is_file():
                note += "\n\n" + attach(key, pdf, _pdf_name(sprint))
            tracker.add_comment(key, note)
            logger.info("Sprint summary: %s updated.", key)
            return key
        key = create(issue_type, name, body, labels=[LABEL])
        if attach and pdf and Path(pdf).is_file():
            try:
                attach(key, pdf, _pdf_name(sprint))
            except Exception as e:                                 # noqa: BLE001
                logger.warning("Sprint summary: PDF not attached to %s: %s", key, e)
        status = settings.get("sprint_summary_status")
        if status:
            tracker.transition_status(key, status)
        logger.info("Sprint summary: %s recorded for %s.", key, name)
        return key
    except Exception as e:                                         # noqa: BLE001
        from core.redaction import error_text
        logger.warning("Sprint summary not recorded: %s", error_text(e))
        return None


def _pdf_name(sprint: dict) -> str:
    import re
    slug = re.sub(r"[^A-Za-z0-9]+", "-", str(sprint.get("name") or "sprint")).strip("-").lower()
    return f"test-summary-{slug}.pdf"
