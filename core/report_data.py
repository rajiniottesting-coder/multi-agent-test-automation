"""The numbers every report shows, from the results store (RP3, RP4, RP6).

Pure functions over the store's records (core/results_store.py) and issue
dicts from the tracker, so the dashboard, the traceability matrix and the PDF
summary cannot disagree, and every number is unit-tested.

Reading of a verdict, used everywhere:
  counted   passed, flaky, failed - the tests that ran against a working
            application (outage: the application was down, nothing tested;
            skipped: not run)
  pass rate (passed + flaky) / counted - a flake passed on its retry
"""
from __future__ import annotations

import datetime as _dt
import re
import statistics
from collections import Counter, defaultdict

PASSING = ("passed", "flaky")
COUNTED = ("passed", "flaky", "failed")


def pass_rate(records) -> float | None:
    """Share of counted tests that passed, 0..1; None when none counted."""
    counted = [r for r in records if r.get("verdict") in COUNTED]
    if not counted:
        return None
    return sum(r["verdict"] in PASSING for r in counted) / len(counted)


def kpis(runs: list[dict], results: list[dict]) -> dict:
    """The headline: the latest run, and the window's runs and flakes."""
    latest = runs[-1] if runs else None
    latest_results = [r for r in results if latest and r.get("run_id") == latest["run_id"]]
    return {
        "runs": len(runs),
        "latest_run": latest,
        "latest_pass_rate": pass_rate(latest_results),
        "window_pass_rate": pass_rate(results),
        "flaky": sum(r.get("verdict") == "flaky" for r in results),
        "outage_runs": sum(1 for run in runs if run.get("outage")),
        "tests": len({r["test"] for r in results}),
    }


_ATTENTION = ("failed", "outage", "flaky", "skipped")


def latest_run(runs: list[dict], results: list[dict]) -> dict | None:
    """The newest run and what in it needs a look: every test not plainly
    passed, failed first, then outage, flaky, skipped. None without a run."""
    if not runs:
        return None
    run = runs[-1]
    mine = [r for r in results if r.get("run_id") == run["run_id"]]
    rows = sorted((r for r in mine if r.get("verdict") in _ATTENTION),
                  key=lambda r: (_ATTENTION.index(r["verdict"]), r.get("test") or ""))
    return {"run": run, "rows": rows, "pass_rate": pass_rate(mine),
            "passed": sum(r.get("verdict") == "passed" for r in mine)}


def trend(runs: list[dict]) -> dict:
    """Per run, oldest first: verdict counts and suite duration."""
    keys = ("passed", "flaky", "failed", "outage", "skipped")
    return {"run": [r["run_id"] for r in runs],
            "started": [(r.get("started") or "")[:16].replace("T", " ") for r in runs],
            "url": [r.get("url") for r in runs],
            **{k: [r.get(k, 0) for r in runs] for k in keys},
            "duration_min": [round((r.get("duration_s") or 0) / 60, 2) for r in runs]}


def slowest(results: list[dict], top: int = 10) -> list[dict]:
    """Tests by median duration over the window, slowest first."""
    by = defaultdict(list)
    for r in results:
        if r.get("verdict") in COUNTED:
            by[r["test"]].append(r.get("duration_s") or 0)
    rows = [{"test": t, "median_s": round(statistics.median(d), 1),
             "max_s": round(max(d), 1), "runs": len(d)} for t, d in by.items()]
    return sorted(rows, key=lambda x: -x["median_s"])[:top]


def flaky_ranking(results: list[dict]) -> list[dict]:
    """Tests that flaked in the window, most often first, with their share."""
    runs = Counter(r["test"] for r in results if r.get("verdict") in COUNTED)
    flakes = Counter(r["test"] for r in results if r.get("verdict") == "flaky")
    last = {}
    for r in results:
        if r.get("verdict") == "flaky":
            last[r["test"]] = (r.get("started") or "")[:10]
    return [{"test": t, "flaky": n, "runs": runs[t], "last": last.get(t, "")}
            for t, n in flakes.most_common()]


def breakdown(results: list[dict], key: str, current: set | None = None) -> list[dict]:
    """Latest result per test, grouped by `key` ("file" or "story"). With
    `current` (the tests of the newest run), a test no longer in the suite - a
    removed scenario - is left out instead of showing its last result for ever."""
    from core.results_store import latest_by_test
    groups = defaultdict(list)
    for r in latest_by_test(results).values():
        if current is not None and r["test"] not in current:
            continue
        groups[r.get(key) or "(not traced)"].append(r)
    rows = []
    for name, recs in groups.items():
        c = Counter(r["verdict"] for r in recs)
        rows.append({"name": name, "tests": len(recs), "passed": c["passed"] + c["flaky"],
                     "failed": c["failed"], "other": c["outage"] + c["skipped"],
                     "pass_rate": pass_rate(recs)})
    return sorted(rows, key=lambda x: (x["pass_rate"] is None, x["pass_rate"] or 0, x["name"]))


def age_days(created: str | None, now: _dt.datetime) -> int | None:
    if not created:
        return None
    try:
        t = _dt.datetime.fromisoformat(created.replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=_dt.timezone.utc)
    return max(0, (now - t).days)


AGE_BUCKETS = ((0, 2, "0-2 days"), (3, 7, "3-7 days"), (8, 30, "8-30 days"),
               (31, 10 ** 6, "over 30 days"))


def defects_summary(defects: list[dict], now: _dt.datetime) -> dict:
    """Open defects by age bucket and by component (a defect without one is
    counted under "(no component)")."""
    by_age = Counter()
    by_component = Counter()
    for d in defects:
        a = age_days(d.get("created"), now)
        label = next((name for lo, hi, name in AGE_BUCKETS if a is not None and lo <= a <= hi),
                     "unknown age")
        by_age[label] += 1
        for comp in d.get("components") or ["(no component)"]:
            by_component[comp] += 1
    order = [name for _, _, name in AGE_BUCKETS] + ["unknown age"]
    return {"total": len(defects),
            "by_age": [(k, by_age[k]) for k in order if by_age[k]],
            "by_component": by_component.most_common()}


# ── traceability (RP4) ──────────────────────────────────────────────────

_TYPE_PREFIX = re.compile(r"^\s*\[[^\]]+\]\s*")


def _norm(title: str) -> str:
    plain = (title or "").replace("\\", "")          # wiki markup escapes [ ] { }
    return re.sub(r"\s+", " ", _TYPE_PREFIX.sub("", plain)).strip().lower()


def coverage_map(comment_body: str, criteria_refs, test_cases: list[dict]) -> dict:
    """{criterion ref: [test case keys]} from Agent 1's `[agent1:coverage]`
    comment: each line `- AC1 <wording> -> <titles> | <how>` names the test
    cases by title. A test case is matched when its title appears in the
    line's cited part (titles may contain commas, so the part is searched,
    not split)."""
    out = {ref: [] for ref in criteria_refs}
    for line in (comment_body or "").splitlines():
        m = re.match(r"^\s*[-*]\s*(AC\d+|TITLE)\b(.*?)->(.*)$", line.strip())
        if not m:
            continue
        ref, cited = m.group(1), m.group(3).split(" | ", 1)[0]
        cited_n = _norm(cited)
        for tc in test_cases:
            t = _norm(tc.get("summary", ""))
            if t and t in cited_n and tc["key"] not in out.setdefault(ref, []):
                out[ref].append(tc["key"])
    return out


def unmatched_citations(comment_body: str, criteria_refs, test_cases: list[dict]) -> set:
    """Criteria whose coverage line cites a test case by a title no test case
    has now (a title revised after the map was written). Shown as such, not
    as a criterion nobody covered."""
    found = coverage_map(comment_body, criteria_refs, test_cases)
    out = set()
    for line in (comment_body or "").splitlines():
        m = re.match(r"^\s*[-*]\s*(AC\d+|TITLE)\b(.*?)->(.*)$", line.strip())
        if not m:
            continue
        cited = _norm(m.group(3).split(" | ", 1)[0])
        if cited and cited not in ("(none)", "none", "-") and not found.get(m.group(1)):
            out.add(m.group(1))
    return out


def traceability_rows(stories: list[dict], latest: dict, defects_by_key: dict) -> list[dict]:
    """One row per (story, criterion, test case, scenario).

    `stories`: [{"key","summary","status","criteria":[(ref, text)],
    "coverage":{ref:[tc keys]}, "test_cases":[{"key","summary"}],
    "scenarios":{tc key: [test ids]}, "has_coverage_map", "unmatched"}];
    `latest`: {test id: store record}; `defects_by_key`: {test case or story
    key: [defect keys]}.

    A story with no coverage map (Agent 1 wrote none - stories older than
    it) cannot say which test case covers which criterion: its rows are its
    test cases, and one cell names its criteria as not mapped. 13 Nov 2026:
    a row per criterion with test case 'none' read as gaps on stories whose
    every test case passed."""
    rows = []
    for s in stories:
        tcs = {tc["key"]: tc for tc in s.get("test_cases") or []}
        crit = list(s.get("criteria") or [])
        if not s.get("has_coverage_map", True):
            refs = ", ".join(ref for ref, _ in crit) or "none found"
            text = (f"Acceptance criteria {refs}: not mapped to test cases (the story "
                    "has no coverage map)" if crit else "(no acceptance criteria found)")
            first = True
            for k, tc in tcs.items():
                for test in (s.get("scenarios") or {}).get(k) or [None]:
                    rows.append(_row(s, "-", text, tc, test, latest.get(test) if test else None,
                                     defects_by_key, unmapped=len(crit) if first else 0))
                    first = False
            if first:                                # no test case at all
                rows.append(_row(s, "-", text, None, None, None, defects_by_key,
                                 "no test case", unmapped=len(crit)))
            continue
        covered = set()
        for ref, text in crit or [("-", "(no acceptance criteria found)")]:
            keys = (s.get("coverage") or {}).get(ref) or []
            covered.update(keys)
            if not keys:
                why = ("cited test case not found" if ref in (s.get("unmatched") or ())
                       else "no test case")
                rows.append(_row(s, ref, text, None, None, None, defects_by_key, why))
            for k in keys:
                for test in (s.get("scenarios") or {}).get(k) or [None]:
                    rows.append(_row(s, ref, text, tcs.get(k, {"key": k}), test,
                                     latest.get(test) if test else None, defects_by_key))
        for k, tc in tcs.items():                   # test cases no criterion cites
            if k in covered:
                continue
            for test in (s.get("scenarios") or {}).get(k) or [None]:
                rows.append(_row(s, "-", "(not mapped to a criterion)", tc, test,
                                 latest.get(test) if test else None, defects_by_key))
    return rows


def _row(story, ref, text, tc, test, record, defects_by_key, why: str = "",
         unmapped: int = 0) -> dict:
    keys = [story["key"]] + ([tc["key"]] if tc else [])
    defects = sorted({d for k in keys for d in defects_by_key.get(k, [])})
    return {"story": story["key"], "story_summary": story.get("summary", ""),
            "story_status": story.get("status", ""), "criterion": ref,
            "criterion_text": text, "test_case": tc["key"] if tc else "",
            "test_case_summary": (tc or {}).get("summary", ""),
            "scenario": test or "",
            "result": why or (record or {}).get("verdict", "not run" if test else "no scenario"),
            "result_date": ((record or {}).get("started") or "")[:10],
            "defects": defects, "unmapped_criteria": unmapped}


def unlinked_defects(defects: list[dict] | None, rows: list[dict]) -> list[dict]:
    """Open defects linked to no story or test case of the matrix - a person
    may raise one without a link; the matrix cannot place it, so it is
    listed apart instead of dropped."""
    keys = {r["story"] for r in rows} | {r["test_case"] for r in rows if r["test_case"]}
    return [d for d in defects or [] if not keys & set(d.get("links") or [])]


def traceability_summary(rows: list[dict]) -> dict:
    """Criteria with no test case, test cases with no scenario, and results."""
    crit = {(r["story"], r["criterion"]) for r in rows if r["criterion"] != "-"}
    uncovered = {(r["story"], r["criterion"]) for r in rows
                 if r["criterion"] != "-" and not r["test_case"]}
    unmapped = sum(r.get("unmapped_criteria") or 0 for r in rows)
    tcs = {r["test_case"] for r in rows if r["test_case"]}
    no_scenario = {r["test_case"] for r in rows if r["test_case"] and not r["scenario"]}
    results = Counter(r["result"] for r in rows if r["scenario"])
    return {"stories": len({r["story"] for r in rows}), "criteria": len(crit) + unmapped,
            "criteria_uncovered": len(uncovered), "criteria_unmapped": unmapped,
            "test_cases": len(tcs),
            "test_cases_without_scenario": len(no_scenario), "results": dict(results)}
