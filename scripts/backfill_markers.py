"""Marker backfill: give unmarked scenarios their `# JIRA:` marker (Agent 0, B1).

WHY
---
A scenario without a `# JIRA: <key> (hash: <h>)` marker can be found by the
impact analysis, but it has no test case to revise and no owner to trace.
This script proposes a test case for each unmarked scenario and, once a
person has confirmed the proposals, writes the markers.

NOTHING IS WRITTEN WITHOUT CONFIRMATION
---------------------------------------
1. propose   reads the feature files and the tracker, and writes a proposals
             file (default reports/marker_backfill.json). No file is changed.

                 python scripts/backfill_markers.py propose
                 python scripts/backfill_markers.py propose --story SCRUM-187

             --story (repeatable) limits the candidates to test cases owned by
             those stories. Use it when the project holds test cases from
             other applications or old runs: titles alike across apps pair
             convincingly and wrongly.

2. review    open the proposals file. Each row has `"apply": true` only when
             its title score reaches the floor. Set `apply` on the rows you
             accept, change `test_case` where the proposal is wrong, and leave
             `apply: false` on everything else.

3. apply     writes the markers for rows with `"apply": true`:

                 python scripts/backfill_markers.py apply reports/marker_backfill.json
                 python scripts/backfill_markers.py apply reports/marker_backfill.json --open-pr

             Without --open-pr the local feature files are changed and you
             commit them. With --open-pr the markers are applied to the files
             on `main` and a pull request is opened; nothing local changes.
             Every row is re-checked first: the scenario must still be
             unmarked, the key must not be marked anywhere else, and the hash
             is computed from the test case's CURRENT description.

A scenario with no acceptable match stays unmarked. Either create a test case
for it in the tracker, link it to its owning story, and run `propose` again;
or leave it report-only - the impact analysis still finds it, it just cannot
be revised automatically.

Reserved reference files (app_under_test.reserved_paths) are refused unless
--allow-reserved is given: a marker there makes the file a target for
`ai-update`, which would then rewrite the style baseline Agent 2 learns from.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEFAULT_FLOOR = 0.3                 # the same floor marker injection uses
DEFAULT_OUT = "reports/marker_backfill.json"


# ─────────────────────────────────────────────────────────────
# propose (pure)
# ─────────────────────────────────────────────────────────────

def build_proposals(unmarked: list, test_cases: list, marked_keys: set,
                    reserved_files: set, floor: float = DEFAULT_FLOOR) -> list:
    """One proposal per unmarked scenario.

    unmarked:       [(feature filename, scenario title)]
    test_cases:     [{"key", "summary", "description", "owner"}]
    marked_keys:    test case keys already marked somewhere - never proposed
    reserved_files: feature filenames that are reserved reference files
    """
    from agents.agent2_coder import greedy_title_pairing, plain_test_case_title

    candidates = [dict(tc, summary=plain_test_case_title(tc.get("summary", "")))
                  for tc in test_cases if tc["key"] not in marked_keys]
    # Scenarios that can be marked pair first. Reserved-file scenarios are
    # only shown for information, so they pair last, from what is left -
    # otherwise an identical title in the reference file takes the test case
    # the story's own scenario needs.
    markable = {i: t for i, (f, t) in enumerate(unmarked) if f not in reserved_files}
    reserved = {i: t for i, (f, t) in enumerate(unmarked) if f in reserved_files}
    chosen, claimed = greedy_title_pairing(markable, candidates)
    left = [c for n, c in enumerate(candidates) if n not in claimed]
    chosen.update(greedy_title_pairing(reserved, left)[0])

    rows = []
    for i, (filename, title) in enumerate(unmarked):
        score, tc = chosen.get(i, (0.0, None))
        reserved = filename in reserved_files
        notes = []
        if tc is None:
            notes.append("no candidate test case left")
        elif score < floor:
            notes.append(f"best score {score:.2f} is below the floor {floor}")
        if reserved:
            notes.append("reserved reference file - needs --allow-reserved")
        rows.append({
            "file": filename,
            "scenario": title,
            "test_case": tc["key"] if tc else None,
            "summary": next((c["summary"] for c in test_cases if c["key"] == tc["key"]),
                            None) if tc else None,
            "owner": tc.get("owner") if tc else None,
            "score": round(score, 2),
            "apply": bool(tc) and score >= floor and not reserved,
            "note": "; ".join(notes),
        })
    return rows


# ─────────────────────────────────────────────────────────────
# apply (pure)
# ─────────────────────────────────────────────────────────────

def insert_markers(content: str, markers: dict, owners: dict | None = None) -> tuple[str, dict]:
    """Insert a marker above each named, still-unmarked scenario.

    markers: {scenario title: (test case key, description)}
    owners:  {scenario title: owning story key}, written on the marker (C6)
    Returns (new content, {title: "applied" | reason it was skipped}).
    The marker goes directly above the `Scenario:` line, below any tags -
    where marker injection puts it.
    """
    from agents.agent2_coder import format_marker, parse_feature_file
    from agents.agent2_coder import _keyword_index, _indent_of, _scenario_title

    owners = owners or {}
    header, blocks = parse_feature_file(content)
    by_title: dict = {}
    for block in blocks:
        if block.kind == "scenario":
            by_title.setdefault(_scenario_title(block), []).append(block)

    result: dict = {}
    for title, (key, description) in markers.items():
        found = by_title.get(title, [])
        if not found:
            result[title] = "scenario not found"
            continue
        if len(found) > 1:
            result[title] = "scenario title is not unique in the file"
            continue
        block = found[0]
        if block.jira_key:
            result[title] = f"already marked {block.jira_key}"
            continue
        k = _keyword_index(block.lines)
        indent = block.lines[k][:_indent_of(block.lines[k])]
        block.lines.insert(k, f"{indent}{format_marker(key, description, owner=owners.get(title))}\n")
        result[title] = "applied"

    new_content = "".join(header) + "".join(b.text() for b in blocks)
    # Prove every applied marker parses back onto its scenario.
    _h, check = parse_feature_file(new_content)
    for title, status in result.items():
        if status == "applied":
            key = markers[title][0]
            if not any(b.jira_key == key and _scenario_title(b) == title for b in check):
                raise RuntimeError(f"marker for {key} did not attach to {title!r}")
    return new_content, result


def validate_rows(rows: list, marked_keys: set, live: dict, reserved_files: set,
                  allow_reserved: bool) -> tuple[list, list]:
    """Split confirmed rows into (accepted, rejected-with-reason).

    live: {key: test case dict} from the tracker NOW.
    """
    accepted, rejected, seen = [], [], set()
    for row in rows:
        if not row.get("apply"):
            continue
        key = row.get("test_case")
        reason = None
        if not key:
            reason = "no test case given"
        elif key in seen:
            reason = f"{key} is confirmed for more than one scenario"
        elif key in marked_keys:
            reason = f"{key} is already marked in a feature file"
        elif key not in live:
            reason = f"{key} is not a (non-retired) test case in the tracker"
        elif row["file"] in reserved_files and not allow_reserved:
            reason = "reserved reference file (pass --allow-reserved to override)"
        if reason:
            rejected.append((row, reason))
        else:
            seen.add(key)
            accepted.append(row)
    return accepted, rejected


# ─────────────────────────────────────────────────────────────
# command line
# ─────────────────────────────────────────────────────────────

def _reserved_feature_files() -> set:
    from core.app_context import AppContext
    return {Path(p).name for p in AppContext.load().reserved_paths if p.endswith(".feature")}


def _print_table(rows: list) -> None:
    print(f"{'apply':5}  {'score':5}  {'test case':11} {'owner':11} scenario")
    for r in rows:
        print(f"{'yes' if r['apply'] else 'no':5}  {r['score']:<5}  {r['test_case'] or '-':11} "
              f"{r['owner'] or '-':11} {r['file']} :: {r['scenario']}")
        if r["summary"]:
            print(f"{'':37}-> {r['summary']}")
        if r["note"]:
            print(f"{'':37}({r['note']})")


def cmd_propose(args) -> int:
    from agents.agent2_coder import build_marker_index
    from config.paths import FEATURES_DIR, PROJECT_ROOT
    from integrations.tracker import get_tracker

    index = build_marker_index(FEATURES_DIR)
    if not index.unmarked:
        print("Every scenario already carries a marker. Nothing to propose.")
        return 0
    test_cases = get_tracker().get_all_test_cases()
    if args.story:
        wanted = {s.upper() for s in args.story}
        test_cases = [tc for tc in test_cases if (tc.get("owner") or "").upper() in wanted]
    rows = build_proposals(index.unmarked, test_cases, set(index.by_key),
                           _reserved_feature_files(), args.floor)

    out = PROJECT_ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "floor": args.floor,
        "candidate_stories": sorted(args.story or []),
        "candidates": len(test_cases),
        "proposals": rows,
    }, indent=2), encoding="utf-8")
    _print_table(rows)
    print(f"\n{len(rows)} unmarked scenario(s), {len(test_cases)} candidate test case(s).")
    print(f"Proposals written to {args.out}. Review them, then run:\n"
          f"  python scripts/backfill_markers.py apply {args.out}")
    return 0


def cmd_apply(args) -> int:
    from agents.agent2_coder import build_marker_index
    from config.paths import FEATURES_DIR
    from integrations.tracker import get_tracker

    data = json.loads(Path(args.proposals).read_text(encoding="utf-8"))
    index = build_marker_index(FEATURES_DIR)
    live = {tc["key"]: tc for tc in get_tracker().get_all_test_cases()}
    accepted, rejected = validate_rows(data.get("proposals", []), set(index.by_key), live,
                                       _reserved_feature_files(), args.allow_reserved)
    for row, reason in rejected:
        print(f"SKIP  {row['file']} :: {row['scenario']} -> {row.get('test_case')}: {reason}")
    if not accepted:
        print("No confirmed rows to apply.")
        return 1 if rejected else 0

    by_file: dict = {}
    for row in accepted:
        by_file.setdefault(row["file"], {})[row["scenario"]] = (
            row["test_case"], live[row["test_case"]].get("description", ""))
    print("\nWill mark:")
    for filename, markers in by_file.items():
        for title, (key, _d) in markers.items():
            print(f"  {filename} :: {title} -> {key}")
    if not args.yes and input("\nType 'yes' to write these markers: ").strip().lower() != "yes":
        print("Nothing written.")
        return 1

    gh = None
    branch = None
    if args.open_pr:
        from integrations.repo_host import get_repo_host
        gh = get_repo_host()
        branch = "chore/marker-backfill-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        gh.create_branch(branch, from_branch="main")

    applied = 0
    for filename, markers in by_file.items():
        rel = f"features/{filename}"
        content = (gh.get_file_content(rel, branch="main") if gh
                   else (FEATURES_DIR / filename).read_text(encoding="utf-8"))
        new_content, status = insert_markers(content, markers, {
            title: live[key].get("owner") for title, (key, _d) in markers.items()})
        for title, s in status.items():
            print(f"{'OK  ' if s == 'applied' else 'SKIP'}  {filename} :: {title}: {s}")
        n = sum(1 for s in status.values() if s == "applied")
        if not n:
            continue
        applied += n
        if gh:
            gh.create_or_update_file(rel, new_content,
                                     f"chore(features): backfill {n} JIRA marker(s) in {filename}",
                                     branch)
        else:
            (FEATURES_DIR / filename).write_text(new_content, encoding="utf-8")

    if gh and applied:
        url = gh.open_pull_request(
            title=f"chore(features): backfill {applied} JIRA marker(s)",
            body=("Markers written by `scripts/backfill_markers.py apply` from a reviewed "
                  f"proposals file ({args.proposals}). Each marker's hash is computed from "
                  "the test case's current description."),
            head_branch=branch)
        print(f"\nPull request: {url}")
    elif gh:
        gh.delete_branch(branch)
    print(f"\n{applied} marker(s) written.")
    return 0


def main(argv=None) -> int:
    from dotenv import load_dotenv
    load_dotenv()
    ap = argparse.ArgumentParser(description="Backfill # JIRA: markers on unmarked scenarios.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("propose", help="write a proposals file; changes nothing")
    p.add_argument("--story", action="append",
                   help="only consider test cases owned by this story (repeatable)")
    p.add_argument("--floor", type=float, default=DEFAULT_FLOOR,
                   help=f"minimum title score for apply=true (default {DEFAULT_FLOOR})")
    p.add_argument("--out", default=DEFAULT_OUT, help=f"proposals file (default {DEFAULT_OUT})")
    a = sub.add_parser("apply", help="write markers for confirmed rows")
    a.add_argument("proposals", help="the reviewed proposals file")
    a.add_argument("--open-pr", action="store_true",
                   help="apply to main through the repo host and open a pull request")
    a.add_argument("--allow-reserved", action="store_true",
                   help="also mark scenarios in reserved reference files")
    a.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    args = ap.parse_args(argv)
    return cmd_propose(args) if args.cmd == "propose" else cmd_apply(args)


if __name__ == "__main__":
    sys.exit(main())
