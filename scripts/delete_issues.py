"""Delete closed tracker issues for good, by key - throw-away validation
issues, or defects the pipeline raised and closed.

    python -m scripts.delete_issues --keys PRJ-1,PRJ-2 --confirm DELETE

Run by hand only (.github/workflows/delete_issues.yml, or locally with the
tracker's credentials in .env). Guards, each one on every issue:
  - nothing happens without `--confirm DELETE`;
  - an issue not in the done category is never deleted (close it first);
  - an issue with sub-tasks is never deleted;
  - at most `--max` keys (default 50) in one run.
Each key is reported (deleted, or why not). Exit 1 when any key was not
deleted, so a refused key is never mistaken for done. Deletion cannot be
undone.
"""
from __future__ import annotations

import argparse
import re
import sys

KEY = re.compile(r"^[A-Z][A-Z0-9_]+-\d+$")


def parse_keys(text: str) -> list[str]:
    keys = [k.strip().upper() for k in re.split(r"[,\s]+", text or "") if k.strip()]
    bad = [k for k in keys if not KEY.match(k)]
    if bad:
        raise ValueError(f"not issue keys: {', '.join(bad)}")
    return list(dict.fromkeys(keys))                    # once each, in order


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--keys", required=True, help="comma- or space-separated issue keys")
    ap.add_argument("--confirm", default="", help="must be DELETE")
    ap.add_argument("--max", type=int, default=50)
    args = ap.parse_args(argv)
    try:
        keys = parse_keys(args.keys)
    except ValueError as e:
        print(f"Nothing deleted: {e}")
        return 1
    if args.confirm != "DELETE":
        print("Nothing deleted: pass --confirm DELETE (deletion cannot be undone).")
        return 1
    if not keys or len(keys) > args.max:
        print(f"Nothing deleted: give 1 to {args.max} keys (got {len(keys)}).")
        return 1
    from config import _ensure_env_file_loaded
    _ensure_env_file_loaded()
    from integrations.tracker import capability, get_tracker
    delete = capability(get_tracker(), "delete_closed_issue")
    if delete is None:
        print("Nothing deleted: this tracker has no delete_closed_issue capability.")
        return 1
    failed = 0
    for key in keys:
        try:
            r = delete(key)
        except Exception as e:                                     # noqa: BLE001
            from core.redaction import error_text
            r = {"key": key, "summary": "", "deleted": False, "reason": error_text(e)}
        if r["deleted"]:
            print(f"deleted  {r['key']}  {r.get('type', '')}: {r['summary']}")
        else:
            failed += 1
            print(f"KEPT     {r['key']}  - {r['reason']}")
    print(f"{len(keys) - failed} deleted, {failed} kept.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
