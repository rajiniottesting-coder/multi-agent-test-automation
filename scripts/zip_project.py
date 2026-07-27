"""
zip_project.py — Bundle the project into a clean .zip for sharing.

What this does:
  - Creates a timestamped zip in the parent directory
  - Includes only source code, config, and docs
  - Excludes virtual envs, caches, reports, and SECRETS (.env)
  - Reports total size and file count
  - Refuses to overwrite (timestamps prevent collisions)

Why it's safe:
  - Hardcoded exclusion list for known-noisy folders
  - Explicit refusal to include .env (real secrets)
  - Dry-run mode shows what will be included BEFORE zipping

Usage:
    # Preview what would be included (no zip created)
    python scripts/zip_project.py --dry-run

    # Create the zip (default: ../<project-name>-YYYYMMDD-HHMMSS.zip)
    python scripts/zip_project.py

    # Custom output path
    python scripts/zip_project.py --output ~/Desktop/myproject.zip

    # Include hidden files (.github, .gitignore) — default is already True
    # Use --no-hidden to exclude
    python scripts/zip_project.py --no-hidden

FULL FLAG REFERENCE
-------------------
Every flag, its default and its purpose:

    python -m scripts.zip_project --help

That is the authoritative list - this docstring shows only the common
cases. --help also carries copy-pasteable examples.
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from datetime import datetime
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────
# Configuration: what to exclude
# ─────────────────────────────────────────────────────────────────────

# Folder names to skip ENTIRELY (anywhere in the tree).
EXCLUDE_DIRS: set[str] = {
    # Python virtual environments
    "venv", ".venv", "env", ".env-venv",
    # Python caches
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    # Build artifacts
    "build", "dist", "*.egg-info", ".tox", ".eggs",
    # Test reports & artifacts
    "reports", "allure-results", "allure-report",
    "playwright-report", "test-results", "htmlcov",
    # Editor / IDE
    ".vscode", ".idea", ".vs",
    # OS junk
    ".DS_Store", "__MACOSX", "Thumbs.db",
    # Node (just in case)
    "node_modules",
    # Git internals (we keep .gitignore but skip .git/)
    ".git",
}

# Specific FILENAMES to skip (exact match).
EXCLUDE_FILES: set[str] = {
    # NEVER include real secrets
    ".env", ".env.local", ".env.production",
    # OS / editor junk
    ".DS_Store", "Thumbs.db", "desktop.ini",
    # The zip script's own output (avoid recursion)
    # (handled separately via output_path check)
}

# File extensions to skip (binaries, logs, etc.)
EXCLUDE_EXTENSIONS: set[str] = {
    ".pyc", ".pyo", ".pyd",       # Compiled Python
    ".log",                        # Log files
    ".zip", ".tar", ".gz",         # Other archives
    ".sqlite", ".db",              # Databases
}


# ─────────────────────────────────────────────────────────────────────
# Core logic
# ─────────────────────────────────────────────────────────────────────

def should_exclude(path: Path, project_root: Path, include_hidden: bool) -> tuple[bool, str]:
    """
    Decide if a path should be excluded from the zip.

    Returns:
        (should_exclude, reason) — reason is a human-readable string for logs.
    """
    rel = path.relative_to(project_root)

    # Check each path part for excluded directory names
    for part in rel.parts:
        if part in EXCLUDE_DIRS:
            return True, f"in excluded dir '{part}'"

    # Hidden files/dirs (starting with .) — exclude unless explicitly allowed
    if not include_hidden:
        for part in rel.parts:
            if part.startswith(".") and part not in {".gitignore", ".env.example"}:
                return True, "hidden file/dir"

    # File-level checks (only if it's a file)
    if path.is_file():
        if path.name in EXCLUDE_FILES:
            return True, f"excluded filename '{path.name}'"
        if path.suffix in EXCLUDE_EXTENSIONS:
            return True, f"excluded extension '{path.suffix}'"

    return False, ""


def collect_files(project_root: Path, include_hidden: bool, output_path: Path) -> list[Path]:
    """Walk the project tree and return files that should be included."""
    included: list[Path] = []

    for path in sorted(project_root.rglob("*")):
        # Skip the output zip itself if it's inside the project
        try:
            if path.resolve() == output_path.resolve():
                continue
        except OSError:
            pass

        if not path.is_file():
            continue

        excluded, _reason = should_exclude(path, project_root, include_hidden)
        if not excluded:
            included.append(path)

    return included


def format_size(num_bytes: int) -> str:
    """Convert bytes to a human-readable size string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} TB"


def build_zip(files: list[Path], project_root: Path, output_path: Path) -> None:
    """Create the zip file from the list of included files."""
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for file_path in files:
            rel_path = file_path.relative_to(project_root)
            # Use project name as the top-level folder inside the zip
            arcname = Path(project_root.name) / rel_path
            zf.write(file_path, arcname=arcname)


def safety_check_secrets(files: list[Path], project_root: Path) -> list[Path]:
    """Final safety pass: warn if any file looks like it might contain secrets."""
    suspicious: list[Path] = []
    for file_path in files:
        name = file_path.name.lower()
        if name.startswith(".env") and name != ".env.example":
            suspicious.append(file_path)
        # Could add more heuristics: scan for "api_key=" patterns, etc.
    return suspicious


# ─────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bundle the project into a clean zip (excludes venv, caches, secrets, etc.)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="Output zip path (default: ../<project>-<timestamp>.zip)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be included without creating the zip",
    )
    parser.add_argument(
        "--no-hidden",
        action="store_true",
        help="Exclude hidden files/folders like .github, .gitignore",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print each included file (default: just summary)",
    )
    args = parser.parse_args()

    # Project root = parent of the scripts/ folder (where this file lives)
    project_root = Path(__file__).resolve().parent.parent
    project_name = project_root.name
    include_hidden = not args.no_hidden

    # Default output location
    if args.output:
        output_path = args.output.resolve()
    else:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_path = project_root.parent / f"{project_name}-{timestamp}.zip"

    print("=" * 70)
    print(f"📦 Project Zip Builder")
    print("=" * 70)
    print(f"Project root: {project_root}")
    print(f"Output zip:   {output_path}")
    print(f"Mode:         {'DRY RUN (no zip created)' if args.dry_run else 'CREATE ZIP'}")
    print(f"Hidden files: {'INCLUDED' if include_hidden else 'EXCLUDED'}")
    print("=" * 70)

    # Refuse to overwrite without explicit confirmation
    if output_path.exists() and not args.dry_run:
        print(f"❌ Output file already exists: {output_path}")
        print(f"   Delete it manually first, or use --output with a different name.")
        return 1

    # Collect files
    print("\n🔍 Scanning project files...")
    files = collect_files(project_root, include_hidden, output_path)

    if not files:
        print("⚠️  No files found to include. Did you run from the project root?")
        return 1

    # Compute totals
    total_size = sum(f.stat().st_size for f in files)
    print(f"   Found {len(files)} files ({format_size(total_size)})")

    # Show file list (verbose mode shows all; default shows top 20)
    if args.verbose or args.dry_run:
        print(f"\n📄 Files to include:")
        for f in files:
            rel = f.relative_to(project_root)
            size = format_size(f.stat().st_size)
            print(f"   {rel}  ({size})")
    else:
        print(f"\n📄 First 20 files (use --verbose to see all):")
        for f in files[:20]:
            rel = f.relative_to(project_root)
            print(f"   {rel}")
        if len(files) > 20:
            print(f"   ... and {len(files) - 20} more")

    # Safety check: warn about anything that looks secret-y
    suspicious = safety_check_secrets(files, project_root)
    if suspicious:
        print("\n⚠️  WARNING — potentially sensitive files would be included:")
        for f in suspicious:
            print(f"   {f.relative_to(project_root)}")
        print("   These files have been EXCLUDED automatically.")
        # Filter them out as a final safety net
        files = [f for f in files if f not in suspicious]

    # Stop here if dry-run
    if args.dry_run:
        print(f"\n✅ Dry run complete. {len(files)} files would be zipped to:")
        print(f"   {output_path}")
        print(f"\n   Run without --dry-run to create the zip.")
        return 0

    # Create the zip
    print(f"\n📦 Creating zip...")
    build_zip(files, project_root, output_path)

    # Report results
    final_size = output_path.stat().st_size
    compression_ratio = (1 - final_size / total_size) * 100 if total_size else 0

    print(f"\n✅ Done!")
    print(f"   File:          {output_path}")
    print(f"   Files zipped:  {len(files)}")
    print(f"   Original size: {format_size(total_size)}")
    print(f"   Zipped size:   {format_size(final_size)}")
    print(f"   Compression:   {compression_ratio:.1f}%")
    print()
    print(f"💡 Tip: Verify the zip contents before sharing:")
    print(f"   python -m zipfile -l \"{output_path}\"")

    return 0


if __name__ == "__main__":
    sys.exit(main())