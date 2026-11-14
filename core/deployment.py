"""A deployment signal for change stories (Group B, X4).

WHY
    A change story's tests are written before the application changes. Its
    absence test, and every revised test, fail until the change is deployed -
    the correct red (L20). With nothing to say so, those failures looked real:
    the story's report said "failed", the nightly run on main raised defects,
    and nobody was told to merge the story's context-update pull request (the
    inventory and notes it brings must land when the change is live, not
    before).

WHAT
    With `deployment.enabled` on:

    pending   Agent 0's hand-over labels a change story `pending_label`. A
              person may add it to any story whose change is not live yet.
    expected  While a story is pending, its failing tests are EXPECTED:
              Agent 5's report says so above its summary, and the triage on
              main raises no defect for them (it lists them instead).
    deployed  The signal: `deployed_label` on the story - added by a person,
              a tracker automation, or the `Deployment signal` workflow (a
              webhook: repository_dispatch `deployed` with the story keys, or
              by hand). The watcher (core/tracker_watch.py) then removes the
              pending label and says once, on the story and on its open
              context-update pull request: merge it now; failures from the next
              run on main on are real.

    Off by default: a project without a deployment step to wait for keeps
    today's behaviour.

Generic: the labels and the context-update branch prefix come from config.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

MARKER = "[deployment]"


def settings() -> dict:
    from core.ops_settings import section
    return section("deployment")


def enabled(s: dict | None = None) -> bool:
    return bool((s or settings()).get("enabled"))


def is_pending(labels, s: dict | None = None) -> bool:
    """A story with these labels waits for its deployment."""
    s = s or settings()
    labels = set(labels or ())
    return enabled(s) and s["pending_label"] in labels and s["deployed_label"] not in labels


class PendingStories:
    """Which failures are expected? Read once per run: the pending stories,
    and the test cases they revise (their `impacts` links - a change story's
    revised tests are owned by other stories, and fail until it is live too).
    An unreadable tracker answers "not pending": a failure then counts as real."""

    def __init__(self, tracker, s: dict | None = None):
        self.tracker, self.s = tracker, s or settings()
        self._stories: set | None = None
        self._cases: dict = {}

    def _load(self) -> None:
        self._stories = set()
        if not enabled(self.s) or self.tracker is None:
            return
        try:
            found = self.tracker.find_stories_to_process(
                {"issue_type": self.s["story_type"],
                 "required_labels": [self.s["pending_label"]],
                 "excluded_labels": [self.s["deployed_label"]]}, max_results=100) or []
        except Exception as e:                                     # noqa: BLE001
            logger.warning("Stories awaiting deployment not read (%s) - every failure "
                           "counts as real.", e)
            return
        impacted = getattr(self.tracker, "get_impacted_test_cases", None)
        for story in found:
            self._stories.add(story["key"])
            try:
                for tc in (impacted(story["key"]) if impacted else []) or []:
                    self._cases[tc["key"]] = story["key"]
            except Exception as e:                                 # noqa: BLE001
                logger.warning("%s: revised test cases not read (%s).", story["key"], e)

    def story_of(self, owner: str | None, test_case: str | None = None) -> str | None:
        """The pending story a test waits for: its owner, or the change story
        revising its test case; None when it waits for nothing."""
        if self._stories is None:
            self._load()
        if owner and owner in self._stories:
            return owner
        return self._cases.get(test_case) if test_case else None

    def __bool__(self) -> bool:
        if self._stories is None:
            self._load()
        return bool(self._stories)


def mark_pending(tracker, story_key: str, s: dict | None = None) -> bool:
    """At hand-over: the change story waits for its deployment."""
    s = s or settings()
    if not enabled(s):
        return False
    tracker.add_label(story_key, s["pending_label"])
    from integrations.tracker import add_markdown_comment
    add_markdown_comment(
        tracker, story_key,
        f"{MARKER} This change story waits for its deployment (`{s['pending_label']}`): "
        f"its failing tests are expected until then, and no defect is raised for them. "
        f"When the change is live, add `{s['deployed_label']}` (or send the deployment "
        f"signal); you will then be reminded to merge its context-update pull request.")
    return True


def expected_note(s: dict | None = None) -> str:
    """Agent 5's line above the summary of a pending story's report."""
    s = s or settings()
    return (f"> ⏳ **Awaiting deployment** (`{s['pending_label']}`): this story's failing "
            f"tests are expected until the change is deployed - no defect is raised for "
            f"them. Add `{s['deployed_label']}` when it is live.")


def _context_prs(host, story_key: str) -> list:
    """The story's open context-update pull requests (core/context_update.py
    names their branch from the story, never with an issue key in it)."""
    from core.context_update import branch_for
    from core.impact_settings import impact_settings
    prefix = (impact_settings().get("context_update") or {}).get("branch_prefix") or ""
    if not prefix or host is None:
        return []
    branch = branch_for(story_key, prefix)
    out = []
    for pr in host.list_open_prs(prefix) or []:
        head = pr.get("head_ref") or ""
        if head == branch or head.startswith(branch + "-"):
            out.append(pr)
    return out


def deployed(tracker, host, result: dict, dry_run: bool = False, s: dict | None = None) -> None:
    """The watcher's step: every pending story the signal says is live."""
    s = s or settings()
    if not enabled(s):
        return
    stories = tracker.find_stories_to_process(
        {"issue_type": s["story_type"],
         "required_labels": [s["pending_label"], s["deployed_label"]]}, max_results=100) or []
    for story in stories:
        key = story["key"]
        prs = []
        try:
            prs = _context_prs(host, key)
        except Exception as e:                                     # noqa: BLE001
            logger.warning("%s: open context-update pull requests not read: %s", key, e)
        result["deployed"].append(key)
        if dry_run:
            continue
        if prs:
            listed = ", ".join(f"#{p['number']}" for p in prs)
            ask = (f"Merge its context-update pull request {listed} now, so the inventory "
                   f"and the notes describe the live application.")
        else:
            ask = "It has no open context-update pull request."
        try:
            tracker.remove_label(key, s["pending_label"])
            from integrations.tracker import add_markdown_comment
            add_markdown_comment(
                tracker, key,
                f"{MARKER} Deployed (`{s['deployed_label']}`). {ask} From the next run on "
                f"main, this story's failing tests are real again and raise defects.")
            for pr in prs:
                host.post_pr_comment(
                    pr["number"],
                    f"{MARKER} {key} is deployed: merge this pull request now, so the "
                    f"agents read what the live application shows.")
                result["reminded"].append(pr["number"])
        except Exception as e:                                     # noqa: BLE001
            logger.warning("%s: deployment not recorded: %s", key, e)
            result["errors"].append((f"{key} deployed", str(e)[:300]))
            result["write_errors"].append((f"{key} deployed", str(e)[:300]))


def signal(tracker, keys, s: dict | None = None) -> list:
    """The webhook: label each pending story deployed. Returns the keys
    labelled; a story not pending is left as it is (and named in the log)."""
    s = s or settings()
    done = []
    for key in [k.strip() for k in keys if k and k.strip()]:
        story = tracker.get_story(key) or {}
        if s["pending_label"] not in (story.get("labels") or []):
            logger.warning("%s is not waiting for a deployment - left as it is.", key)
            continue
        tracker.add_label(key, s["deployed_label"])
        done.append(key)
    return done
