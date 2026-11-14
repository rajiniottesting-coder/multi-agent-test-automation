"""Which tests a pull request runs (Group B, X1).

WHY
    Agent 4 ran the whole suite on every pull request. A story's pull request
    changes one feature file, its step definitions and perhaps a page object;
    the other scenarios cannot change result because of it, and each one
    costs browser time on every push - while the nightly run on main already
    runs everything.

WHAT
    With `agents.agent4_runner.pr_selection.enabled`, a pull request runs:

      - every scenario of a feature file it changes;
      - every scenario using a step definition from a step module it changes;
      - every scenario calling a page-object method defined in a page file it
        changes (Agent 0's impact graph, core/impact_graph.py - the same code
        reading the same links);
      - every scenario tagged `smoke_tag` (a quick check of the rest).

    Anything else read while tests run - the inventory, config, conftest, the
    base page, requirements, a framework module, a workflow - is read by every
    test, so it runs the whole suite. So does the label `full_label` on the
    pull request (re-run the job after adding it), a pull request whose
    changed files cannot be listed, and any error here: over-running costs
    minutes; under-running ships an untested change behind a green tick.
    The nightly run and every run by hand stay the whole suite.

    The choice is written to a file Agent 4's pytest reads
    (tests/conftest.py, AGENT4_SELECTION) and to the run's report, so Agent 3
    knows a green run did not run a scenario it predicted would fail.

Generic: paths are the framework's layout (features/, tests/step_defs/,
pages/); the tag and the label come from config.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

ENV = "AGENT4_SELECTION"
FILE = "selection.json"

_NOT_READ = re.compile(r"^(prompts/|docs/)|\.md$")
_FEATURE = re.compile(r"^features/[^/]+\.feature$")
_STEPS = re.compile(r"^tests/step_defs/test_[^/]+\.py$")
_PAGE = re.compile(r"^pages/[^/]+\.py$")

DEFAULTS = {"enabled": False, "smoke_tag": "smoke", "full_label": "full-suite",
            "shared_pages": ["pages/base_page.py", "pages/__init__.py"]}


def settings(agent_config: dict | None = None) -> dict:
    if agent_config is None:
        try:
            import yaml
            from config.paths import CONFIG_YAML
            data = yaml.safe_load(CONFIG_YAML.read_text(encoding="utf-8")) or {}
            agent_config = ((data.get("agents") or {}).get("agent4_runner") or {})
        except Exception as e:                                     # noqa: BLE001
            logger.warning("config not read (%s) - the whole suite runs.", e)
            agent_config = {}
    return {**DEFAULTS, **((agent_config or {}).get("pr_selection") or {})}


def full(why: str) -> dict:
    return {"mode": "full", "why": why, "scenarios": [], "smoke_tag": None}


def _defining_file(graph, cls: str, method: str) -> str | None:
    for c in graph._mro(cls):
        found = graph.page_methods.get((c, method))
        if found is not None:
            return found.file
    return None


def select(changed, root: Path, s: dict | None = None, labels=(), graph=None) -> dict:
    """{"mode": "full" | "selected", "why", "scenarios": [[feature, title]...],
    "smoke_tag"} for a pull request changing `changed` (project-relative)."""
    s = s or settings()
    if not s.get("enabled"):
        return full("pull-request selection is off")
    if s.get("full_label") and s["full_label"] in set(labels or ()):
        return full(f"the pull request is labelled {s['full_label']}")
    paths = [p.strip() for p in changed or () if p and p.strip()]
    if not paths:
        return full("the changed files could not be listed")
    read = [p for p in paths if not _NOT_READ.search(p)]
    shared = set(s.get("shared_pages") or ())
    for p in read:
        if not (_FEATURE.match(p) or _STEPS.match(p) or (_PAGE.match(p) and p not in shared)):
            return full(f"{p} is read by every test")
    try:
        if graph is None:
            from core.impact_graph import build_impact_graph
            graph = build_impact_graph(root)
        chosen: dict = {}
        reasons = []
        for p in read:
            if _FEATURE.match(p):
                hits = [n for n in graph.scenarios if n.file == p]
            elif _STEPS.match(p):
                hits = [n for n in graph.scenarios
                        if any(d.file == p for d in n.step_definitions)]
            else:
                hits = [n for n in graph.scenarios
                        if any(_defining_file(graph, c, m) == p
                               for c, m in n.methods | n.shared_methods)]
            reasons.append(f"{p}: {len(hits)}")
            for n in hits:
                chosen[(n.file, n.title)] = True
    except Exception as e:                                         # noqa: BLE001
        logger.warning("Selection not computed (%s) - the whole suite runs.", e)
        return full(f"the selection could not be computed ({type(e).__name__})")
    if not chosen:
        # Nothing traced (a deleted feature file, a page no scenario uses):
        # the whole suite, not a run that may collect nothing.
        return full("no scenario traces to the change (" + "; ".join(reasons) + ")")
    return {"mode": "selected", "smoke_tag": s.get("smoke_tag") or None,
            "why": "; ".join(reasons),
            "scenarios": [list(k) for k in sorted(chosen)]}


def write(selection: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(selection, indent=1), encoding="utf-8")
    return path


def load(path) -> dict | None:
    """The selection a run reads, or None (the whole suite)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:                                              # noqa: BLE001
        return None
    return data if isinstance(data, dict) and data.get("mode") == "selected" else None


def keeps(selection: dict, feature_file: str, title: str, tags) -> bool:
    """Does the selection keep this scenario? `feature_file` project-relative."""
    if selection.get("smoke_tag") and selection["smoke_tag"] in set(tags or ()):
        return True
    return [feature_file, title] in selection.get("scenarios", [])
