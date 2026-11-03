"""Remove the fingerprint labels (`<defects.label>-<10 hex>`) from raised defects.

    python -m scripts.tidy_defect_labels            # lists what it would remove
    python -m scripts.tidy_defect_labels --apply    # removes it

Defects were raised with a code label per test and cause, which filled the
tracker's label suggestions with meaningless codes - kept by closed defects
too. The triage now identifies a defect from its own triage data
(core/defects.fingerprint_of) and removes the label when it next updates one;
this one-off pass clears the rest, so the tracker stops suggesting them.

A label is removed when the defect no longer needs it:
  - its triage data names the test and the cause (the fingerprint is computed
    from them), or
  - it is closed (a status outside defects.open_statuses): the triage never
    updates a closed defect - a new failure raises a new one.
An OPEN defect whose triage data cannot be read keeps its label - it is still
how the triage finds it - and is listed for a person.

Exit code 0, also when a removal is refused (listed). Generic: the label,
issue type and statuses come from the `defects` settings.
"""
from __future__ import annotations

import argparse
import logging
import sys


def plan(issues: list, s: dict) -> tuple:
    """([(key, [labels to remove], why)], [(key, [labels kept], why)])."""
    from core import defects
    remove, keep = [], []
    open_statuses = set(s["open_statuses"])
    for issue in issues:
        old = defects.legacy_labels(issue.get("labels"), s)
        if not old:
            continue
        state = defects.state_of(issue.get("description", "")) or {}
        if state.get("test") and state.get("cause"):
            remove.append((issue["key"], old, "its triage data identifies it"))
        elif issue.get("status") not in open_statuses:
            remove.append((issue["key"], old, f"closed ({issue.get('status')})"))
        else:
            keep.append((issue["key"], old, "open, and its triage data cannot be read - "
                                            "the label is how the triage finds it"))
    return remove, keep


def run(tracker, s: dict, apply: bool) -> dict:
    issues = tracker.find_stories_to_process(
        {"issue_type": s["issue_type"], "required_labels": [s["label"]]}, max_results=1000)
    remove, keep = plan(issues or [], s)
    refused = []
    for key, labels, why in remove:
        print(f"{'Removing' if apply else 'Would remove'} {', '.join(labels)} from {key} ({why})")
        if not apply:
            continue
        for label in labels:
            try:
                tracker.remove_label(key, label)
            except Exception as e:                                 # noqa: BLE001
                refused.append((key, label, f"{type(e).__name__}: {e}"))
                print(f"  refused: {label} on {key}: {type(e).__name__}: {e}")
    for key, labels, why in keep:
        print(f"Keeping {', '.join(labels)} on {key} ({why})")
    print(f"{len(issues or [])} defect(s) read; {sum(len(x[1]) for x in remove)} label(s) "
          f"{'removed' if apply else 'to remove'} on {len(remove)}; {len(keep)} kept; "
          f"{len(refused)} refused." + ("" if apply else " Run with --apply to remove them."))
    return {"remove": remove, "keep": keep, "refused": refused}


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="remove them (default: list only)")
    args = ap.parse_args(argv)
    from core.defects import settings
    from integrations.tracker import get_tracker
    run(get_tracker(), settings(), args.apply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
