"""Copy the published reports into a folder on your machine (RP9).

    python -m scripts.pull_reports --to D:\\TestReports

Downloads the results store branch (`reporting.store_branch`) as one archive
and replaces the folder's contents with its `latest/` pages - Latest run
(index.html), History, Traceability, the PDF summary and data.json. One copy,
no git history, so the folder never grows: run it on a schedule (GUIDE ->
Reports in a folder on your machine).

The repository is read from GITHUB_REPO, else from this checkout's `origin`.
A public repository needs no credentials; for a private one set GITHUB_TOKEN
(read access). Exit 1 when nothing could be downloaded - the folder is then
left as it was.
"""
from __future__ import annotations

import argparse
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

PAGES = "latest/"


def repo_name() -> str:
    name = (os.getenv("GITHUB_REPO") or "").strip()
    if name:
        return name
    url = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True,
                         text=True, timeout=10).stdout.strip()
    m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", url)
    if not m:
        raise ValueError("set GITHUB_REPO (owner/name): origin is not a GitHub repository")
    return m.group(1)


def download(repo: str, branch: str) -> bytes:
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/zipball/{branch}",
                                 headers={"Accept": "application/vnd.github+json",
                                          "User-Agent": "pull-reports"})
    token = (os.getenv("GITHUB_TOKEN") or "").strip()
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def extract_pages(archive: bytes, target: Path) -> int:
    """Replace `target`'s contents with the archive's latest/ files; how many.
    Written beside the target first, so a broken archive leaves it intact."""
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        members = []
        for name in zf.namelist():
            inner = name.split("/", 1)[1] if "/" in name else ""   # drop <repo>-<sha>/
            if inner.startswith(PAGES) and not name.endswith("/"):
                rel = inner[len(PAGES):]
                if rel and ".." not in Path(rel).parts:
                    members.append((name, rel))
        if not members:
            return 0
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".reports-", dir=target.parent))
        for name, rel in members:
            dest = staging / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(name))
    if target.exists():
        shutil.rmtree(target)
    staging.chmod(0o755)
    staging.rename(target)
    return len(members)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--to", required=True, type=Path, help="the folder to keep the reports in")
    ap.add_argument("--repo", default=None, help="owner/name (default: GITHUB_REPO or origin)")
    ap.add_argument("--branch", default=None, help="default: reporting.store_branch")
    args = ap.parse_args(argv)
    try:
        if args.branch:
            branch = args.branch
        else:
            from core.ops_settings import section
            branch = section("reporting")["store_branch"]
        count = extract_pages(download(args.repo or repo_name(), branch), args.to)
    except Exception as e:                                         # noqa: BLE001
        from core.redaction import error_text
        print(f"Reports not copied: {error_text(e)}")
        return 1
    if not count:
        print("The store has no pages yet: nothing copied.")
        return 1
    print(f"{count} report file(s) in {args.to.resolve()}; open index.html.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
