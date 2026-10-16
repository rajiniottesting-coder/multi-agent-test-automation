"""Delete old GitHub Actions artifacts so the repository stays inside its
Actions storage quota.

Every Agent 4 run uploads a test report (junit, HTML and Allure reports, and on
failure screenshots, videos and traces). Agent 5 reads it within minutes, in
the same workflow run; after that it is only for a person who wants to look.
Kept for 14 days, ~140 of them filled the plan's storage.

Safe by default:
  - prints what it WOULD delete unless --yes is given
  - never touches an artifact of a run that is still queued or in progress
    (Agent 5 may not have read it yet)
  - keeps anything newer than --older-than-days

Usage:
    python -m scripts.cleanup_artifacts                       # dry run, older than 2 days
    python -m scripts.cleanup_artifacts --older-than-days 0 --yes
    python -m scripts.cleanup_artifacts --name-prefix pytest-report- --yes

Needs GITHUB_TOKEN (with actions: write) and GITHUB_REPO=owner/name, the same
variables the agents use. Nothing here names an application.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

API = "https://api.github.com"


def _session(token: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}",
                      "Accept": "application/vnd.github+json",
                      "X-GitHub-Api-Version": "2022-11-28"})
    return s


def list_artifacts(s: requests.Session, repo: str) -> list[dict]:
    out, page = [], 1
    while True:
        r = s.get(f"{API}/repos/{repo}/actions/artifacts",
                  params={"per_page": 100, "page": page}, timeout=30)
        r.raise_for_status()
        batch = r.json().get("artifacts", [])
        out += batch
        if len(batch) < 100:
            return out
        page += 1


def active_run_ids(s: requests.Session, repo: str) -> set[int]:
    """Runs still queued or in progress: their artifacts may not be read yet."""
    ids: set[int] = set()
    for status in ("queued", "in_progress"):
        r = s.get(f"{API}/repos/{repo}/actions/runs",
                  params={"status": status, "per_page": 100}, timeout=30)
        r.raise_for_status()
        ids |= {run["id"] for run in r.json().get("workflow_runs", [])}
    return ids


def select(artifacts: list[dict], older_than: timedelta, prefix: str,
           active: set[int], now: datetime) -> list[dict]:
    """The artifacts to delete. Pure: no network, so it is unit-tested."""
    chosen = []
    for a in artifacts:
        if a.get("expired"):
            continue                                   # already gone from storage
        if prefix and not a.get("name", "").startswith(prefix):
            continue
        if (a.get("workflow_run") or {}).get("id") in active:
            continue
        created = datetime.fromisoformat(a["created_at"].replace("Z", "+00:00"))
        if now - created >= older_than:
            chosen.append(a)
    return chosen


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--older-than-days", type=float, default=2.0,
                    help="delete artifacts at least this old (default 2)")
    ap.add_argument("--name-prefix", default="",
                    help="only artifacts whose name starts with this")
    ap.add_argument("--yes", action="store_true", help="really delete (default: dry run)")
    args = ap.parse_args(argv)

    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPO")
    if not token or not repo:
        print("GITHUB_TOKEN and GITHUB_REPO must be set.", file=sys.stderr)
        return 2
    s = _session(token)
    artifacts = list_artifacts(s, repo)
    live = [a for a in artifacts if not a.get("expired")]
    chosen = select(artifacts, timedelta(days=args.older_than_days), args.name_prefix,
                    active_run_ids(s, repo), datetime.now(timezone.utc))

    mb = lambda items: sum(a.get("size_in_bytes", 0) for a in items) / 1048576  # noqa: E731
    print(f"Artifacts in storage: {len(live)} ({mb(live):.1f} MB)")
    print(f"{'Deleting' if args.yes else 'Would delete'}: {len(chosen)} ({mb(chosen):.1f} MB)"
          f" - older than {args.older_than_days:g} day(s)"
          + (f", name starting '{args.name_prefix}'" if args.name_prefix else ""))
    failed = 0
    for a in sorted(chosen, key=lambda a: a["created_at"]):
        line = f"  {a['created_at'][:16]}  {a.get('size_in_bytes', 0) / 1048576:7.1f} MB  {a['name']}"
        if not args.yes:
            print(line)
            continue
        r = s.delete(f"{API}/repos/{repo}/actions/artifacts/{a['id']}", timeout=30)
        if r.status_code == 204:
            print(line + "  deleted")
        else:
            failed += 1
            print(line + f"  FAILED ({r.status_code}: {r.text[:120]})")
    if not args.yes and chosen:
        print("Dry run - nothing deleted. Add --yes to delete.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
