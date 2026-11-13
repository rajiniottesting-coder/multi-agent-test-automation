"""The defect history kept on the results store (D7, D8, D9).

WHY
    The reports read the tracker's OPEN defects only, live, on each build. A
    closed defect dropped out of every page, and a deleted one out of the
    tracker too: on 13 Nov 2026 24 closed defects the nightly run had raised
    were deleted, and nothing anywhere still knew when they were opened or
    closed. A defect trend, a time to fix or a density per module needs that
    history, so the reports keep their own copy.

WHAT
    `defects.json` on the store: every defect's last known state, keyed by
    its tracker key - opened and closed (UTC), status, resolution, priority,
    module, close category, where it came from (raised by the pipeline or by
    a person), and the test, test case and story it is traced to. Each build
    (scripts/build_site.py) reads the defects changed since the last sync
    (all of them the first time) and the open ones:
      - a closed defect that opens again counts one reopening;
      - a defect the history holds as open that the tracker no longer has is
        recorded as deleted on that day - its history stays;
      - an issue labelled `cleanup.delete_label` (throw-away) is left out;
      - a closed defect leaves the history `reporting.defect_keep_days`
        after it closed (0: never);
      - a key in `reporting.defect_history_forget` leaves it at once (a
        throw-away issue deleted before it was labelled as one).
    A tracker that cannot be read leaves the history as it is.

    `sprints/<id>-<name>.json`: the active sprint's figures, rewritten on
    every build while it is active - so the last one written stays as the
    sprint's record after it closes, whatever is later deleted or pruned.

    Module (D8): the defect's tracker component when it has one; else the
    module of the feature file its test (or a linked test case) is in -
    `reporting.modules` maps module names to feature file patterns - else
    the feature file's own name; else "unassigned".

    Close category (D9): what a closed defect was - `defects.close_categories`
    (a label a person adds when closing) first, else
    `defects.resolution_categories` (the tracker's resolution). Categories:
    app, test, environment, duplicate, not-a-bug. The density counts app
    defects and the ones nobody categorised (counted, never dropped: an
    uncategorised defect may be a product bug); the rest are listed apart.

Generic: no application, tracker or project name lives here.
"""
from __future__ import annotations

import datetime as _dt
import fnmatch
import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

LEDGER_FILE = "defects.json"
SPRINTS_DIR = "sprints"
CATEGORIES = ("app", "test", "environment", "duplicate", "not-a-bug")
NOT_PRODUCT = {"test", "environment", "duplicate", "not-a-bug"}
UNASSIGNED = "unassigned"
# How far before the last sync the next one reads again: a defect changed
# while the last build ran, or a tracker clock in another time zone, is
# read twice rather than missed.
_OVERLAP = _dt.timedelta(days=2)


# ── time ────────────────────────────────────────────────────────────────

def utc(value) -> str | None:
    """An ISO time in UTC (seconds), or None."""
    if not value:
        return None
    try:
        t = _dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=_dt.timezone.utc)
    return t.astimezone(_dt.timezone.utc).isoformat(timespec="seconds")


def _day(value) -> str | None:
    t = utc(value)
    return t[:10] if t else None


# ── the store files ─────────────────────────────────────────────────────

def read(store: Path) -> dict:
    """{"synced": iso or None, "defects": {key: record}}."""
    try:
        data = json.loads((Path(store) / LEDGER_FILE).read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("defects"), dict):
            return data
    except (OSError, ValueError):
        pass
    return {"synced": None, "defects": {}}


def write(store: Path, ledger: dict) -> None:
    Path(store).mkdir(parents=True, exist_ok=True)
    (Path(store) / LEDGER_FILE).write_text(
        json.dumps(ledger, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def records(store: Path) -> list[dict]:
    return sorted(read(store)["defects"].values(), key=lambda r: (r.get("opened") or "", r["key"]))


# ── module (D8) and close category (D9) ─────────────────────────────────

def module_of_file(feature_file: str | None, patterns: dict | None) -> str | None:
    """The module a feature file belongs to: the first module whose pattern
    matches its name, else the file's own name without `.feature`."""
    if not feature_file:
        return None
    name = Path(feature_file).name
    for module, globs in (patterns or {}).items():
        for g in [globs] if isinstance(globs, str) else globs or []:
            if fnmatch.fnmatch(name, Path(str(g)).name):
                return str(module)
    return name[:-len(".feature")] if name.endswith(".feature") else name


def feature_file_of_test(test_id: str | None) -> str | None:
    """`tests.step_defs.test_<name>::...` -> `<name>.feature`."""
    if not test_id:
        return None
    module = test_id.partition("::")[0].rsplit(".", 1)[-1]
    return (module[len("test_"):] if module.startswith("test_") else module) + ".feature"


def module_of(components, test_id, keys, files_by_key: dict, patterns: dict) -> str:
    """D8: tracker component, else the feature file of the test or of the
    first linked key that is a test case of the suite, else unassigned."""
    if components:
        return str(components[0])
    file = feature_file_of_test(test_id)
    if not file:
        file = next((files_by_key[k] for k in keys or [] if k in files_by_key), None)
    return module_of_file(file, patterns) or UNASSIGNED


def category_of(labels, resolution, s_defects: dict) -> str | None:
    """D9: the close category from a label, else from the resolution."""
    by_label = s_defects.get("close_categories") or {}
    for label in labels or []:
        if label in by_label and by_label[label] in CATEGORIES:
            return by_label[label]
    by_res = s_defects.get("resolution_categories") or {}
    cat = by_res.get(resolution) if resolution else None
    return cat if cat in CATEGORIES else None


def close_hint(s_defects: dict) -> str:
    """One line for a person closing a defect: which label says what it was."""
    labels = s_defects.get("close_categories") or {}
    if not labels:
        return ""
    names = {"app": "a bug in the application", "test": "the test was wrong",
             "environment": "the application or the runner was down or slow",
             "duplicate": "a duplicate", "not-a-bug": "not a bug"}
    return ("When you close it, add the label that says what it was: "
            + "; ".join(f"`{lb}` ({names.get(c, c)})" for lb, c in labels.items())
            + " - the reports' defect density counts application bugs only.")


# ── the sync ────────────────────────────────────────────────────────────

def _record(issue: dict, prev: dict | None, today: str, files_by_key: dict,
            patterns: dict, s_defects: dict) -> dict:
    from core.defects import state_of
    state = state_of(issue.get("description") or "") or {}
    labels = issue.get("labels") or []
    links = issue.get("links") or []
    test_case = state.get("test_case") or next((k for k in links if k in files_by_key), None)
    rec = {
        "key": issue["key"], "summary": issue.get("summary"),
        "status": issue.get("status"), "open": bool(issue.get("open")),
        "opened": utc(issue.get("created")),
        # A tracker without a resolution date: the last change of a closed
        # defect is the nearest to its closing.
        "closed": None if issue.get("open") else (utc(issue.get("resolved"))
                                                  or (prev or {}).get("closed")
                                                  or utc(issue.get("updated")) or today),
        "resolution": issue.get("resolution"), "priority": issue.get("priority"),
        "category": None if issue.get("open") else category_of(labels, issue.get("resolution"),
                                                               s_defects),
        "module": module_of(issue.get("components"), state.get("test"),
                            [test_case] + list(links), files_by_key, patterns),
        "source": "pipeline" if s_defects.get("label") in labels else "person",
        "test": state.get("test"), "test_case": test_case,
        "story": state.get("owner"), "cause": state.get("cause"),
        "reopened": int((prev or {}).get("reopened") or 0),
        "first_recorded": (prev or {}).get("first_recorded") or today,
        "deleted": None,
    }
    if prev and not prev.get("open") and rec["open"]:
        rec["reopened"] += 1
    return rec


def sync(store: Path, tracker, features_dir: Path, now: _dt.datetime) -> dict | None:
    """Bring the history up to date from the tracker. The counts, or None
    when switched off or the tracker cannot be read (nothing changed)."""
    from core.ops_settings import section
    from integrations.tracker import capability
    s_rep, s_def = section("reporting"), section("defects")
    if not s_rep.get("defect_history", True):
        return None
    fetch = capability(tracker, "defects_for_history")
    if fetch is None:
        return None
    ledger = read(store)
    since = None
    if ledger["defects"] and ledger.get("synced"):
        t = _dt.datetime.fromisoformat(ledger["synced"]) - _OVERLAP
        since = t.strftime("%Y-%m-%d %H:%M")
    changed = fetch(s_def["issue_type"], updated_since=since)
    still_open = fetch(s_def["issue_type"], open_only=True) if since else None
    if changed is None or (since and still_open is None):
        return None
    throwaway = (section("cleanup").get("delete_label") or "").strip()
    files_by_key = _files_by_key(features_dir)
    patterns = s_rep.get("modules") or {}
    today = now.astimezone(_dt.timezone.utc).isoformat(timespec="seconds")
    counts = {"read": len(changed), "new": 0, "updated": 0, "reopened": 0, "deleted": 0,
              "left_out": 0, "dropped": 0, "forgotten": 0}
    defects = ledger["defects"]
    seen = set()
    for issue in changed + (still_open or []):
        if issue["key"] in seen:
            continue
        seen.add(issue["key"])
        if throwaway and throwaway in (issue.get("labels") or []):
            defects.pop(issue["key"], None)
            counts["left_out"] += 1
            continue
        prev = defects.get(issue["key"])
        rec = _record(issue, prev, today, files_by_key, patterns, s_def)
        counts["new" if prev is None else "updated"] += 1
        counts["reopened"] += rec["reopened"] - int((prev or {}).get("reopened") or 0)
        defects[issue["key"]] = rec
    # Open in the history, gone from the tracker: deleted (a full read lists
    # every defect, an incremental one every open defect).
    for key, rec in defects.items():
        if rec.get("open") and key not in seen:
            rec.update(open=False, deleted=today, status="deleted from the tracker",
                       closed=rec.get("closed") or today)
            counts["deleted"] += 1
    # Keys a person listed to forget: a throw-away issue deleted before it
    # carried the throw-away label stays as 'deleted' otherwise.
    for key in s_rep.get("defect_history_forget") or []:
        if defects.pop(str(key).strip().upper(), None) is not None:
            counts["forgotten"] += 1
    keep = int(s_rep.get("defect_keep_days") or 0)
    if keep > 0:
        cutoff = (now - _dt.timedelta(days=keep)).astimezone(_dt.timezone.utc).isoformat()
        for key in [k for k, r in defects.items() if not r.get("open")
                    and (r.get("closed") or "9") < cutoff]:
            del defects[key]
            counts["dropped"] += 1
    ledger["synced"] = today
    write(store, ledger)
    logger.info("Defect history: %(read)d read, %(new)d new, %(updated)d updated, "
                "%(reopened)d reopened, %(deleted)d deleted from the tracker, "
                "%(left_out)d throw-away left out, %(dropped)d past keep_days dropped, "
                "%(forgotten)d forgotten", counts)
    return counts


def _files_by_key(features_dir: Path) -> dict:
    """{test case key: feature file name} from the scenarios' markers."""
    try:
        from agents.agent2_coder import build_marker_index
        return {k: e.file for k, e in build_marker_index(Path(features_dir)).by_key.items()}
    except Exception as e:                                         # noqa: BLE001
        logger.warning("Feature files not read for the defect modules: %s", e)
        return {}


def scenarios_per_module(features_dir: Path, patterns: dict) -> dict:
    """{module: number of scenarios} - the density's denominator."""
    out: dict = {}
    try:
        from agents.agent2_coder import build_marker_index
        index = build_marker_index(Path(features_dir))
        files = [e.file for e in index.by_key.values()] + [f for f, _ in index.unmarked]
    except Exception as e:                                         # noqa: BLE001
        logger.warning("Feature files not read for the density: %s", e)
        return out
    for f in files:
        m = module_of_file(f, patterns)
        out[m] = out.get(m, 0) + 1
    return out


# ── the figures (RP12) ──────────────────────────────────────────────────

def _in(value, start: str, end: str) -> bool:
    return bool(value) and start <= value[:len(start)] <= end


def is_product(rec: dict) -> bool:
    return rec.get("category") not in NOT_PRODUCT


def trend(recs: list[dict], start: _dt.date, end: _dt.date) -> dict:
    """Per day: defects opened, closed, and open at the end of the day."""
    days, opened, closed, still = [], [], [], []
    d = start
    while d <= end:
        day = d.isoformat()
        days.append(day)
        opened.append(sum(1 for r in recs if (r.get("opened") or "")[:10] == day))
        closed.append(sum(1 for r in recs if (r.get("closed") or "")[:10] == day))
        still.append(sum(1 for r in recs if (r.get("opened") or "9")[:10] <= day
                         and not ((r.get("closed") or "9")[:10] <= day)))
        d += _dt.timedelta(days=1)
    return {"days": days, "opened": opened, "closed": closed, "open": still}


def summary(recs: list[dict], start: str, end: str) -> dict:
    """Totals between two ISO days (inclusive)."""
    opened = [r for r in recs if _in(r.get("opened"), start, end)]
    closed = [r for r in recs if _in(r.get("closed"), start, end)]
    fix_days = []
    for r in closed:
        try:
            a = _dt.datetime.fromisoformat(r["opened"])
            b = _dt.datetime.fromisoformat(r["closed"])
            fix_days.append(max(0.0, (b - a).total_seconds() / 86400))
        except (KeyError, TypeError, ValueError):
            pass
    cats: dict = {}
    for r in closed:
        c = r.get("category") or "not categorised"
        cats[c] = cats.get(c, 0) + 1
    return {"opened": len(opened), "closed": len(closed),
            "open": sum(1 for r in recs if r.get("open")),
            "by_pipeline": sum(1 for r in opened if r.get("source") == "pipeline"),
            "by_person": sum(1 for r in opened if r.get("source") != "pipeline"),
            "mean_days_to_close": round(sum(fix_days) / len(fix_days), 1) if fix_days else None,
            "reopened": sum(int(r.get("reopened") or 0) for r in recs
                            if _in(r.get("opened"), start, end) or r.get("open")),
            "deleted": sum(1 for r in recs if _in(r.get("deleted"), start, end)),
            "closed_by_category": sorted(cats.items(), key=lambda kv: (-kv[1], kv[0]))}


def by_module(recs: list[dict], start: str, end: str, scenarios: dict, per: int) -> list[dict]:
    """Per module: scenarios, defects opened, product defects among them,
    closed, open now, and the density (product defects per `per` scenarios)."""
    names = set(scenarios) | {r.get("module") or UNASSIGNED for r in recs
                              if _in(r.get("opened"), start, end) or r.get("open")}
    rows = []
    for m in names:
        mine = [r for r in recs if (r.get("module") or UNASSIGNED) == m]
        opened = [r for r in mine if _in(r.get("opened"), start, end)]
        product = [r for r in opened if is_product(r)]
        n = scenarios.get(m) or 0
        rows.append({"module": m, "scenarios": n, "opened": len(opened),
                     "product": len(product),
                     "closed": sum(1 for r in mine if _in(r.get("closed"), start, end)),
                     "open": sum(1 for r in mine if r.get("open")),
                     "density": round(len(product) * per / n, 2) if n else None})
    return sorted(rows, key=lambda r: (-(r["density"] or 0), -r["opened"], r["module"]))


# ── sprints ─────────────────────────────────────────────────────────────

def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", str(text)).strip("-").lower() or "sprint"


def sprint_snapshot(store: Path, sprint: dict | None, recs: list[dict], scenarios: dict,
                    per: int, now: _dt.datetime) -> dict | None:
    """Write the active sprint's figures to sprints/; the snapshot or None."""
    if not sprint or not sprint.get("name") or not sprint.get("start"):
        return None
    start = _day(sprint.get("start"))
    end = _day(sprint.get("end")) or now.date().isoformat()
    snap = {"id": sprint.get("id"), "name": sprint["name"], "start": start, "end": end,
            "written": now.astimezone(_dt.timezone.utc).isoformat(timespec="seconds"),
            **summary(recs, start, end),
            "modules": by_module(recs, start, end, scenarios, per)}
    folder = Path(store) / SPRINTS_DIR
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{sprint.get('id') or ''}-{_slug(sprint['name'])}".strip("-") + ".json"
    (folder / name).write_text(json.dumps(snap, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return snap


def read_sprints(store: Path) -> list[dict]:
    out = []
    for p in sorted((Path(store) / SPRINTS_DIR).glob("*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            logger.warning("Sprint record %s unreadable; left out.", p.name)
    return sorted(out, key=lambda s: (s.get("start") or "", s.get("name") or ""))
