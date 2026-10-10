"""Trace and snapshot comments: fixed formats with fixed prefixes.

The pipeline writes these comments and later reads its own back, so every
format starts with a prefix it can find and carries the fields it needs. A
comment is never posted twice: `already_posted` checks the same kind, change
story and reference first.

    [agent0:trace] will-revise   on each OWNING story, at hand-over (C2)
    [agent0:trace] result        on each owning story, after the run (Agent 5)
    [agent0:trace] merged        on each owning story, at reconcile (C7)
    [agent0:trace] restored      on each owning story, at reconcile (C7)
    [agent0:snapshot]            on each REVISED test case, before Agent 1
                                 rewrites it (C3); the undo source for C7

Trace comments are the owner's only view of a change made by another story,
so they name the change story, the tests and where to look.
"""
from __future__ import annotations

import json
import re
from typing import Iterable, Optional

TRACE = "[agent0:trace]"
SNAPSHOT = "[agent0:snapshot]"
KINDS = ("will-revise", "result", "merged", "restored")

_HEAD = re.compile(r"^\[agent0:trace\] (?P<kind>[a-z-]+) \| change: (?P<change>\S+)"
                   r"(?: \| ref: (?P<ref>\S+))?", re.M)


def _head(kind: str, change: str, ref: Optional[str]) -> str:
    if kind not in KINDS:                 # not an assert: it must survive python -O
        raise ValueError(f"unknown trace kind {kind!r}; expected one of {KINDS}")
    return f"{TRACE} {kind} | change: {change}" + (f" | ref: {ref}" if ref else "")


def will_revise(change: str, change_summary: str, revised: list, retired: list,
                review: Optional[str] = None) -> str:
    lines = [_head("will-revise", change, review),
             f"{change} ({change_summary}) changes test cases this story owns. "
             f"The work runs on {change}; this story is not reopened."]
    if revised:
        lines.append("Will revise: " + ", ".join(revised))
    if retired:
        lines.append("Will retire: " + ", ".join(retired))
    if review:
        lines.append(f"Decided in Impact Review {review}.")
    return "\n".join(lines)


def result(change: str, pr_url: str, outcomes: dict) -> str:
    """outcomes: {test case key: 'passed' | 'failed' | 'not run'}"""
    parts = ", ".join(f"{k} {v}" for k, v in sorted(outcomes.items()))
    return "\n".join([_head("result", change, pr_url),
                      f"Run on {change}'s pull request {pr_url}: {parts}."])


def merged(change: str, pr_url: str, tests: Iterable[str]) -> str:
    return "\n".join([_head("merged", change, pr_url),
                      f"{change}'s pull request was merged: the revised tests "
                      f"({', '.join(sorted(tests))}) are now on main."])


def restored(change: str, pr_url: Optional[str], tests: Iterable[str],
             left_for_a_person: Iterable[str] = ()) -> str:
    lines = [_head("restored", change, pr_url),
             f"{change}'s pull request was closed without merging. Restored to "
             f"their earlier text: {', '.join(sorted(tests)) or 'none'}."]
    left = sorted(left_for_a_person)
    if left:
        lines.append("Edited since the revision, so NOT restored - a person must "
                     "decide: " + ", ".join(left))
    return "\n".join(lines)


def parse(body: str) -> Optional[dict]:
    m = _HEAD.search(body or "")
    return m.groupdict() if m else None


def already_posted(comments: Iterable[str], kind: str, change: str,
                   ref: Optional[str] = None) -> bool:
    for body in comments:
        p = parse(body)
        if p and p["kind"] == kind and p["change"] == change and (ref is None or p["ref"] == ref):
            return True
    return False


# ── snapshots ──────────────────────────────────────────────────

def snapshot(change: str, old_summary: str, old_description: str,
             old_hash: str, new_hash: str) -> str:
    payload = {"change": change, "old_summary": old_summary,
               "old_description": old_description, "old_hash": old_hash,
               "new_hash": new_hash}
    return (f"{SNAPSHOT} change: {change} | old hash: {old_hash} | new hash: {new_hash}\n"
            f"Text before {change} revised this test case (used to undo it):\n"
            "{code:json}\n" + json.dumps(payload, indent=1) + "\n{code}")


def parse_snapshot(body: str) -> Optional[dict]:
    if not (body or "").startswith(SNAPSHOT):
        return None
    m = re.search(r"\{code:json\}\n(.*)\n\{code\}", body, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError:
        return None


def latest_snapshot(comments: Iterable[str], change: str) -> Optional[dict]:
    found = None
    for body in comments:
        snap = parse_snapshot(body)
        if snap and snap.get("change") == change:
            found = snap
    return found
