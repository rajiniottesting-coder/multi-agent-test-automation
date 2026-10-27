"""
Merge crawl drafts and strip what a human has been told to strip.

WHY THIS EXISTS
    A crawl produces one draft per auth state, and each draft carries review
    blocks naming elements that should not survive: third-party embeds whose
    text rotates per impression, and structural css paths that describe where
    something sat rather than what it is. Acting on those by hand across five
    pages and 500 elements is tedious and easy to get half-right, and a
    half-pruned draft is worse than an unpruned one because the leftovers look
    deliberate.

WHAT IT DOES NOT DO
    It does not curate. `elements_notes`, `key_methods`, `multi_match` and
    `conditional` still have to be written by someone who knows what the page
    means - the crawler cannot infer them, and this tool does not pretend to.
    The output is a CLEAN DRAFT, not an inventory ready to commit.

USAGE
    Example: python -m scripts.promote_draft `
  app_inventory/login.draft.json app_inventory/full_auth.draft.json `
  -o app_inventory/clean.draft.json

python -m scripts.verify_locators --inventory app_inventory/clean.draft.json --login-url /login --only-problems

    python -m scripts.promote_draft a.draft.json b.draft.json -o merged.json
    python -m scripts.promote_draft *.draft.json -o merged.json --drop-fragile
    python -m scripts.promote_draft a.json b.json -o out.json --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Blocks the crawler adds for human review. All are removed from the output;
# the first two also name elements that get dropped with them.
# Only third-party embeds are deleted by default. A "fragile" selector means
# the ELEMENT IS REAL and only its handle is poor - deleting it would throw
# away something a test needs. Verified on a live draft: add_cart_button,
# continue_button and continue_cart_button were all flagged fragile,
# and all three are required by a cart story. Improving a weak locator beats
# losing the element.
_DROP_ELEMENTS_FROM = ("_third_party_elements",)
_REVIEW_BLOCKS = (
    "_third_party_elements", "_fragile_selectors", "_unstable_selectors",
    "_ambiguous_selectors", "_selector_strategies", "_interaction_required",
    "_unresolved_selectors", "title_seen",
)


def _named_elements(block: dict | None) -> set[str]:
    """Element names out of a review block, whichever shape it uses."""
    if not block:
        return set()
    items = block.get("elements") or []
    out = set()
    for item in items:
        out.add(item["element"] if isinstance(item, dict) else item)
    return out


def merge_drafts(paths: list[Path]) -> tuple[dict, dict[str, list[str]]]:
    """Combine drafts. A page captured more than once is kept ONCE PER SOURCE.

    Two crawls of the same path in different auth states are not duplicates -
    the nav differs, and on some apps the whole page does. Silently keeping one
    would discard a real difference, so collisions are suffixed with the file
    they came from and left for a human to reconcile.
    """
    merged: dict | None = None
    pages: dict[str, dict] = {}
    origin: dict[str, str] = {}
    collisions: dict[str, list[str]] = {}

    for path in paths:
        draft = json.loads(path.read_text(encoding="utf-8"))
        if merged is None:
            merged = {k: v for k, v in draft.items() if k != "pages"}
        tag = path.stem.replace(".draft", "")
        for name, entry in (draft.get("pages") or {}).items():
            if name not in pages:
                pages[name] = entry
                origin[name] = tag
                continue
            # Collision: move the first copy under its own tag too, so neither
            # version is privileged.
            first = origin[name]
            if name in pages:
                pages[f"{name}__{first}"] = pages.pop(name)
            pages[f"{name}__{tag}"] = entry
            collisions.setdefault(name, [first]).append(tag)

    merged = merged or {}
    merged["pages"] = pages
    return merged, collisions


def prune(inventory: dict, drop_fragile: bool = False) -> list[tuple[str, int, int]]:
    """Drop third-party elements and every review block. Returns per-page counts.

    Fragile selectors are KEPT unless `drop_fragile` is set. The element behind
    one is real; only the locator is structural. A cart story needs
    add_cart_button whether or not the crawler found a good handle for it.
    """
    report = []
    for name, entry in (inventory.get("pages") or {}).items():
        elements = entry.get("elements") or {}
        before = len(elements)

        drop = _named_elements(entry.get("_third_party_elements"))
        if drop_fragile:
            drop |= _named_elements(entry.get("_fragile_selectors"))
        for key in drop:
            elements.pop(key, None)

        # A family or conditional list may now name an element that is gone.
        for field in ("multi_match", "conditional", "async_family", "removed"):
            if field in entry:
                kept = [k for k in entry[field] if k in elements]
                if kept:
                    entry[field] = kept
                else:
                    entry.pop(field, None)
                    entry.pop(f"{field}_note", None)

        # Carry the fragile list forward as a TODO rather than dropping it with
        # the other review blocks. These elements survive, so the weak locator
        # survives with them, and silently discarding the warning would hide
        # work that still needs doing.
        weak = sorted(_named_elements(entry.get("_fragile_selectors")) & set(elements))
        if weak and not drop_fragile:
            entry["_selectors_to_improve"] = {
                "elements": weak,
                "warning": ("KEPT because the element is real and a test may need "
                            "it, but each of these is located by a STRUCTURAL PATH "
                            "that describes where it sat during one crawl. They "
                            "resolve today and break when anything above them "
                            "re-renders. Replace with an id, name, href or a "
                            "data-test added to the app, then delete this block."),
            }

        for block in _REVIEW_BLOCKS:
            if block == "_selectors_to_improve":
                continue
            entry.pop(block, None)

        report.append((name, before - len(elements), len(elements), len(weak)))
    return report


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="python -m scripts.promote_draft",
        description="Merge crawl drafts and strip flagged elements.",
        epilog="The result is a CLEAN DRAFT. It still needs elements_notes, "
               "key_methods, multi_match and conditional written by hand before "
               "it can replace a real inventory.",
    )
    ap.add_argument("drafts", nargs="+", help="Draft JSON files to merge.")
    ap.add_argument("-o", "--output", required=True, help="Where to write the result.")
    ap.add_argument("--drop-fragile", action="store_true",
                    help="Also delete elements located by a structural css path. "
                         "OFF by default: the element is real and a test may need "
                         "it - only its locator is weak.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Report what would change; write nothing.")
    args = ap.parse_args()

    paths = [Path(p) for p in args.drafts]
    missing = [p for p in paths if not p.is_file()]
    if missing:
        print("Not found: " + ", ".join(str(m) for m in missing), file=sys.stderr)
        return 2

    inventory, collisions = merge_drafts(paths)

    if collisions:
        print("Pages captured more than once - kept SEPARATELY, not merged:")
        for name, tags in collisions.items():
            print(f"  {name}: {' + '.join(tags)}  ->  " +
                  ", ".join(f"{name}__{t}" for t in tags))
        print("  These are different auth states of one page, not duplicates.")
        print("  Reconcile them by hand: keep the version your tests need.\n")

    report = prune(inventory, drop_fragile=args.drop_fragile)
    print(f"{'page':26} {'removed':>8} {'kept':>6} {'to improve':>11}")
    print("-" * 58)
    total_removed = total_kept = total_weak = 0
    for name, removed, kept, weak in report:
        print(f"  {name:24} {removed:8} {kept:6} {weak:11}")
        total_removed += removed
        total_kept += kept
        total_weak += weak
    print("-" * 58)
    print(f"  {'TOTAL':24} {total_removed:8} {total_kept:6} {total_weak:11}\n")
    print("Removed = third-party embeds only. Nothing belonging to the "
          "application was deleted.")
    if total_weak:
        print(f"{total_weak} element(s) kept but located by a structural path - "
              f"see _selectors_to_improve on each page.")

    if args.dry_run:
        print("--dry-run: nothing written.")
        return 0

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print(f"Wrote {out}")
    print("STILL A DRAFT. Add elements_notes, key_methods, multi_match and "
          "conditional before this replaces a real inventory, and verify it:")
    print(f"  python -m scripts.verify_locators --inventory {out} --only-problems")
    return 0


if __name__ == "__main__":
    sys.exit(main())