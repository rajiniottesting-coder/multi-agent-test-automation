"""Allure severity, behaviours and links for every scenario (RP8).

The Allure report groups a run by what the scenarios ARE, not only by file:

  severity   from the scenario's and feature's tags
             (`reporting.severity_by_tag`; the most severe match), else
             `reporting.default_severity`
  feature    the feature's name; `story` the owning story's key
  links      the test case and the owning story in the tracker, from the
             scenario's `# JIRA:` marker (`integrations.tracker.issue_url`)

Read from the feature files and the environment only: a test run has no
tracker credentials, and a label must never fail a test - every error is
logged and ignored.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_SEVERITIES = ("blocker", "critical", "normal", "minor", "trivial")


@lru_cache(maxsize=1)
def _markers(features_dir: str) -> dict:
    """{(feature file name, scenario title): (test case key, owner key)}."""
    from agents.agent2_coder import build_marker_index
    index = build_marker_index(Path(features_dir))
    return {(e.file, e.title): (e.key, getattr(e, "owner", None))
            for e in index.by_key.values()}


def severity_for(tags, settings: dict) -> str:
    """The most severe level a scenario's tags give it (case and @ ignored)."""
    by_tag = {str(k).lower().lstrip("@"): str(v).lower()
              for k, v in (settings.get("severity_by_tag") or {}).items()}
    found = [by_tag.get(str(t).lower().lstrip("@")) for t in tags or ()]
    found = [sev for sev in found if sev in _SEVERITIES]
    if found:                       # the most severe of the scenario's tags
        return min(found, key=_SEVERITIES.index)
    default = str(settings.get("default_severity") or "normal").lower()
    return default if default in _SEVERITIES else "normal"


def labels_for(feature_file: str, feature_name: str, scenario_name: str,
               tags, settings: dict, features_dir: str) -> dict:
    """What Allure is told about one scenario: {"severity", "feature",
    "story", "links": [(url, name, type)]}. Pure, for the tests."""
    test_case, owner = _markers(features_dir).get(
        (Path(feature_file).name, scenario_name), (None, None))
    from integrations.tracker import issue_url
    links = []
    for key, kind in ((test_case, "tms"), (owner, "issue")):
        url = issue_url(key) if key else None
        if url:
            links.append((url, key, kind))
    return {"severity": severity_for(tags, settings), "feature": feature_name,
            "story": owner, "links": links}


def apply(feature, scenario, features_dir: str = "features") -> None:
    """Label the running scenario in Allure. Never raises."""
    try:
        import allure
        from core.ops_settings import section
        s = section("reporting")
        if not s.get("enabled", True):
            return
        info = labels_for(getattr(feature, "filename", "") or "",
                          getattr(feature, "name", "") or "",
                          getattr(scenario, "name", "") or "",
                          sorted(set(getattr(scenario, "tags", set()) or ())
                                 | set(getattr(feature, "tags", set()) or ())),
                          s, features_dir)
        allure.dynamic.severity(getattr(allure.severity_level, info["severity"].upper()))
        if info["feature"]:
            allure.dynamic.feature(info["feature"])
        if info["story"]:
            allure.dynamic.story(info["story"])
        for url, name, kind in info["links"]:
            allure.dynamic.link(url, link_type=kind, name=name)
    except Exception as e:                                         # noqa: BLE001
        logger.debug("Allure labels not set: %s", e)
