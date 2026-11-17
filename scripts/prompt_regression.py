#!/usr/bin/env python3
"""Replay a fixed set when Agent 1-3 prompts change (C3).

    python -m scripts.prompt_regression --plan --changed-files changed.txt
    python -m scripts.prompt_regression --agents agent1 --report reports/pr-agent1.md

WHY
    A change to a prompt of Agents 1-3 (or to the code that builds it) was
    proven only by the unit suite, which pins the validators but never calls
    the model: a reworded rule that made Agent 1 drop a criterion, Agent 2
    fail its own gate or Agent 3 wave a defect through showed up on the next
    real story - after the merge (L12).

WHAT
    `prompt_regression` in config.yaml names a fixed set, replayed WITHOUT
    writing anything to the tracker or the repository (each agent's dry run),
    and holds each to what it must keep doing:

      agent1   each story drafted again (replay: its own scenarios are not
               counted as existing ones): the draft passes its rules and maps
               every criterion (Agent 1 raises otherwise), with between
               `agent1_min_cases` and `agent1_max_cases` test cases;
      agent2   each story coded again (regenerate, dry run): the generated
               files pass the whole gate, with no test case left out;
      agent3   each pull request reviewed again: `approve` - the review must
               not request changes; `request_changes` - it must.

    `--plan` reads the changed files and prints which agents replay
    (`triggers`: path prefixes per agent). Replays cost model spend, so the
    workflow runs only the agents whose prompts changed.

    Exit 0 when every replay holds (or nothing replays), 1 when one does not,
    2 on a usage error. `--report` writes the table the workflow posts.

Generic: the stories, pull requests and limits come from config.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("prompt_regression")

AGENTS = ("agent1", "agent2", "agent3")


def settings() -> dict:
    from core.ops_settings import section
    return section("prompt_regression")


def agents_for(changed, triggers: dict) -> list:
    """The agents a change replays: one of its files starts with a prefix the
    agent's `triggers` list."""
    paths = [str(p).strip().lstrip("./") for p in changed or () if str(p).strip()]
    return [a for a in AGENTS
            if any(p.startswith(tuple(triggers.get(a) or ())) for p in paths)]


def _row(agent: str, item: str, ok: bool, detail: str) -> dict:
    return {"agent": agent, "item": item, "ok": ok, "detail": detail}


def replay_agent1(key: str, s: dict, run=None) -> dict:
    if run is None:
        from agents.agent1_analyst import run
    try:
        result = run(key, dry_run=True, replay=True)
    except Exception as e:                                         # noqa: BLE001
        return _row("agent1", key, False, f"draft refused: {type(e).__name__}: {e}"[:400])
    status = result.get("status")
    n = int(result.get("test_cases_generated") or 0)
    lo, hi = int(s.get("agent1_min_cases") or 1), int(s.get("agent1_max_cases") or 7)
    if status != "tests_drafted_dry_run":
        return _row("agent1", key, False, f"status {status!r}, not a draft "
                    f"({result.get('readiness') or 'see the log'})")
    if not lo <= n <= hi:
        return _row("agent1", key, False, f"{n} test case(s), outside {lo}-{hi}")
    refs = result.get("criteria") or []
    return _row("agent1", key, True, f"{n} test case(s); criteria {', '.join(refs) or 'none'} "
                "all mapped")


def replay_agent2(key: str, s: dict, run=None) -> dict:
    if run is None:
        from agents.agent2_coder import run
    try:
        result = run(key, dry_run=True, is_regenerate=True)
    except Exception as e:                                         # noqa: BLE001
        errors = getattr(e, "errors", None) or []
        more = f" - {errors[0]}" if errors else ""
        return _row("agent2", key, False, f"gate refused: {type(e).__name__}: {e}{more}"[:400])
    status = result.get("status")
    left_out = result.get("not_automated") or []
    if status != "code_generated_dry_run":
        return _row("agent2", key, False, f"status {status!r}, no code generated")
    if left_out:
        return _row("agent2", key, False, f"test case(s) left out: {', '.join(left_out)}")
    return _row("agent2", key, True, f"{result.get('files_generated', 0)} file(s) pass the gate")


def replay_agent3(pr: str, expected: str, s: dict, run=None) -> dict:
    if run is None:
        from agents.agent3_reviewer import run
    expected = str(expected or "approve").strip().lower()
    try:
        result = run(int(pr), dry_run=True)
    except Exception as e:                                         # noqa: BLE001
        return _row("agent3", f"#{pr}", False, f"review failed: {type(e).__name__}: {e}"[:400])
    verdict = result.get("verdict")
    blocked = verdict == "request_changes"
    ok = blocked if expected == "request_changes" else not blocked
    return _row("agent3", f"#{pr}", ok,
                f"verdict {verdict!r} ({result.get('blocking_count', 0)} blocking), "
                f"expected {'request_changes' if expected == 'request_changes' else 'no request_changes'}")


def replay(agents, s: dict, runners: dict | None = None) -> list:
    """Every replay of `agents`, each on its own: one failing never stops the
    others. `runners` replaces an agent's run() (tests)."""
    runners = runners or {}
    rows = []
    from core.llm_client import reset_usage
    for agent in agents:
        if agent == "agent1":
            for key in s.get("agent1_stories") or []:
                rows.append(replay_agent1(key, s, runners.get("agent1")))
                reset_usage()
        elif agent == "agent2":
            for key in s.get("agent2_stories") or []:
                rows.append(replay_agent2(key, s, runners.get("agent2")))
                reset_usage()
        elif agent == "agent3":
            for pr, expected in (s.get("agent3_reviews") or {}).items():
                rows.append(replay_agent3(pr, expected, s, runners.get("agent3")))
                reset_usage()
    return rows


HEADING = "## Prompt regression (C3)"


def report(rows: list, agents) -> str:
    """The markdown for these replays: one `###` section (the workflow puts
    the sections of each agent's step under one HEADING)."""
    lines = [f"### {', '.join(agents) or 'no agent'}", ""]
    if not rows:
        lines.append(f"Nothing replayed for {', '.join(agents) or 'no agent'} - no story or "
                     "pull request is configured for it (`prompt_regression` in config.yaml).")
        return "\n".join(lines) + "\n"
    failed = [r for r in rows if not r["ok"]]
    lines.append(f"{len(rows) - len(failed)} of {len(rows)} replay(s) hold."
                 + (" **The prompts changed what the agents do - see the failures.**"
                    if failed else ""))
    lines += ["", "| Agent | Replayed | Result | Detail |", "|---|---|---|---|"]
    for r in rows:
        detail = str(r["detail"]).replace("|", "/").replace("\n", " ")
        lines.append(f"| {r['agent']} | {r['item']} | {'✅' if r['ok'] else '❌'} | {detail} |")
    lines += ["", "_Replayed as dry runs: nothing was written to the tracker or the "
              "repository._"]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plan", action="store_true",
                    help="print the agents the changed files replay (no model call)")
    ap.add_argument("--changed-files", help="file listing the changed paths, one per line")
    ap.add_argument("--agents", default="",
                    help="comma-separated agents to replay: agent1,agent2,agent3")
    ap.add_argument("--report", help="write the markdown report here")
    args = ap.parse_args(argv)
    s = settings()
    if not s.get("enabled"):
        print("prompt_regression.enabled is false - nothing replayed.")
        if args.plan:
            _output("agents", "")
        return 0
    if args.plan:
        if not args.changed_files:
            ap.print_usage()
            return 2
        changed = Path(args.changed_files).read_text(encoding="utf-8").splitlines()
        agents = agents_for(changed, s.get("triggers") or {})
        print(f"replay: {', '.join(agents) or 'nothing'}")
        _output("agents", ",".join(agents))
        return 0
    agents = [a.strip() for a in args.agents.split(",") if a.strip()]
    unknown = [a for a in agents if a not in AGENTS]
    if not agents or unknown:
        print(f"--agents takes {', '.join(AGENTS)}; got {args.agents!r}", file=sys.stderr)
        return 2
    rows = replay(agents, s)
    text = report(rows, agents)
    print(f"{HEADING}\n\n{text}")
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(text, encoding="utf-8")
    return 1 if any(not r["ok"] for r in rows) else 0


def _output(name: str, value: str) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"{name}={value}\n")


if __name__ == "__main__":
    sys.exit(main())
