"""Agent 1, impact-aware mode (Agent 0 design, C3).

Runs instead of the normal draft when the story has APPROVED impacted test
cases - its Impacts links, created by the hand-over. Agent 1's normal mode is
untouched: a story with no impacted cases never reaches this module.

What it does, in order:
  1. Input    the story, each approved case (key, current text, the reason it
              was chosen), the retired keys, and every existing scenario title.
  2. Draft    one structured call returning ImpactAwareDraft: a revision per
              approved key, plus new cases only for uncovered criteria.
  3. Validate every approved key revised exactly once, no unknown key, and no
              new case repeating a revised case or an existing scenario (by
              normalised title). A failing draft is sent back once with the
              problems listed; a second failure stops the run before any write.
              Near matches are flagged in the gate comment, not rejected.
  4. Snapshot before each revision, a comment on the test case holding its old
              text and the old and new hashes - the undo source for C7.
  5. Write    update_test_case per revision, create_test_case per new case.
  6. Labels   ai-processed and impact-applied on; ai-ready off.
  7. Gate     one comment on the story: each revision before and after, then
              the new cases - what the human-approved reviewer must read.

Re-running is safe: a test case this change already revised (its current
hash equals the new hash in this change's snapshot) is left as it is, and its
original snapshot is never overwritten.
"""
from __future__ import annotations

import logging

from agents.agent2_coder import (build_marker_index, compute_description_hash,
                                 plain_test_case_title, _title_similarity)
from core import impact_review, impact_trace
from core.impact_settings import impact_settings
from core.schemas import ImpactAwareDraft
from validators.gherkin_analyzer import normalize_scenario_name

logger = logging.getLogger("agent1_impact")

GATE = "[agent1:impact-draft]"
NEAR_MATCH = 0.6


def _norm(title: str) -> str:
    return normalize_scenario_name(plain_test_case_title(title))


def validate_draft(draft: ImpactAwareDraft, approved_keys: set, existing_titles: set) -> tuple:
    """(errors, near_matches). Errors reject the draft; near matches are shown."""
    errors, near = [], []
    seen: dict = {}
    for rev in draft.revisions:
        seen[rev.key] = seen.get(rev.key, 0) + 1
    for key in sorted(approved_keys - set(seen)):
        errors.append(f"approved test case {key} was not revised")
    for key in sorted(set(seen) - approved_keys):
        errors.append(f"{key} is not an approved test case; do not revise it")
    for key, n in sorted(seen.items()):
        if n > 1:
            errors.append(f"{key} was revised {n} times; revise it exactly once")

    taken = {_norm(r.revised.title): f"revised {r.key}" for r in draft.revisions}
    taken.update({t: "an existing scenario" for t in existing_titles if t not in taken})
    for tc in draft.new_test_cases:
        n = _norm(tc.title)
        if n in taken:
            errors.append(f"new test case '{tc.title}' repeats {taken[n]}")
            continue
        for other, what in taken.items():
            if _title_similarity(n, other) >= NEAR_MATCH:
                near.append(f"'{tc.title}' is close to {what} ('{other}')")
        taken[n] = "another new test case"
    return errors, near


def _block(cases: list, reasons: dict) -> str:
    if not cases:
        return "(none)"
    parts = []
    for c in cases:
        reason = reasons.get(c["key"], {}).get("evidence") or "-"
        parts.append(f"## {c['key']} - {c['summary']}\nWhy it is affected: {reason}\n"
                     f"Current text:\n{c['description']}")
    return "\n\n".join(parts)


def _review_rows(tracker, story_id: str, settings: dict) -> dict:
    prefix = settings["review"]["summary_prefix"]
    reviews = [s for s in tracker.get_subtasks(story_id) if s["summary"].startswith(prefix)]
    return impact_review.parse_rows(reviews[-1]["description"]) if reviews else {}


def _draft(llm, prompt: str, approved_keys: set, existing_titles: set) -> tuple:
    system = "You are a meticulous, expert QA test analyst."
    draft = llm.invoke_structured(system_prompt=system, user_prompt=prompt,
                                  output_schema=ImpactAwareDraft)
    errors, near = validate_draft(draft, approved_keys, existing_titles)
    if not errors:
        return draft, near
    logger.warning("Impact-aware draft rejected, asking once more: %s", errors)
    retry = (prompt + "\n\n# Your previous answer was rejected\n"
             + "\n".join(f"- {e}" for e in errors) + "\nReturn a corrected answer.")
    draft = llm.invoke_structured(system_prompt=system, user_prompt=retry,
                                  output_schema=ImpactAwareDraft)
    errors, near = validate_draft(draft, approved_keys, existing_titles)
    if errors:
        raise ValueError("impact-aware draft rejected twice; nothing was written: "
                         + "; ".join(errors))
    return draft, near


def _steps_text(description: str) -> str:
    return "\n".join(f"  {line}" for line in (description or "").splitlines()) or "  (empty)"


def run_impact_aware(tracker, story_id: str, story: dict, prompt_header: dict,
                     llm, dry_run: bool, agent_config: dict) -> dict:
    """prompt_header: {"app_name", "app_base_url", "app_context", "story_text"}."""
    from config.paths import FEATURES_DIR, PROMPTS_DIR
    settings = impact_settings()

    approved = {c["key"]: c for c in tracker.get_impacted_test_cases(story_id)}
    retired = [c for c in tracker.get_impacted_test_cases(story_id, include_retired=True)
               if c.get("retired")]
    reasons = _review_rows(tracker, story_id, settings)
    index = build_marker_index(FEATURES_DIR)
    existing_titles = {normalize_scenario_name(e.title) for e in index.by_key.values()}
    existing_titles |= {normalize_scenario_name(t) for _f, t in index.unmarked}

    prompt = (PROMPTS_DIR / "agent1_impact_aware.md").read_text(encoding="utf-8")
    for name, value in prompt_header.items():
        prompt = prompt.replace("{" + name + "}", value)
    prompt = (prompt
              .replace("{approved_block}", _block(list(approved.values()), reasons))
              .replace("{retired_block}", "\n".join(f"- {c['key']} - {c['summary']}"
                                                    for c in retired) or "(none)")
              .replace("{existing_titles_block}", "\n".join(f"- {t}" for t in
                                                            sorted(existing_titles)) or "(none)"))

    draft, near = _draft(llm, prompt, set(approved), existing_titles)
    logger.info("Impact-aware draft for %s: %d revision(s), %d new test case(s)",
                story_id, len(draft.revisions), len(draft.new_test_cases))

    revised, skipped, created, gate = [], [], [], []
    for rev in draft.revisions:
        current = approved[rev.key]
        rendered = tracker.render_test_case(rev.revised)
        old_hash = compute_description_hash(current["description"])
        new_hash = compute_description_hash(rendered["description"])
        comments = [] if dry_run else tracker.get_comments(rev.key)
        snap = impact_trace.latest_snapshot(comments, story_id)
        if old_hash == new_hash or (snap and snap["new_hash"] == old_hash):
            skipped.append(rev.key)          # already revised by this change
            continue
        gate.append(f"*{rev.key}* (owner {reasons.get(rev.key, {}).get('owner') or '-'}): "
                    f"{rev.change_note}\nBefore - {current['summary']}\n"
                    f"{_steps_text(current['description'])}\n"
                    f"After - {rendered['summary']}\n{_steps_text(rendered['description'])}")
        if dry_run:
            revised.append(rev.key)
            continue
        if not (snap and snap["new_hash"] == new_hash):
            tracker.add_comment(rev.key, impact_trace.snapshot(
                story_id, current["summary"], current["description"], old_hash, new_hash))
        tracker.update_test_case(rev.key, rev.revised)
        revised.append(rev.key)

    for tc in draft.new_test_cases:
        if dry_run:
            created.append("(dry run)")
            continue
        created.append(tracker.create_test_case(tc, parent_story_key=story_id).key)

    if not dry_run:
        body = [f"{GATE} Impact-aware draft for {story_id}",
                f"Revised {len(revised)}, skipped {len(skipped)} (already revised), "
                f"new {len(created)}. Review these before adding human-approved."]
        body += ["", "*Revised test cases*"] + (gate or ["(none)"])
        body += ["", "*New test cases*"] + ([f"{k} - {tc.title}" for k, tc in
                                            zip(created, draft.new_test_cases)] or ["(none)"])
        if near:
            body += ["", "*Close to an existing test - check these*"] + [f"- {n}" for n in near]
        if retired:
            body += ["", "*Retired (scenarios removed by Agent 2)*: "
                     + ", ".join(c["key"] for c in retired)]
        tracker.add_comment(story_id, "\n".join(body))

        from core.board_status import move_card_for_label
        completion = agent_config.get("completion_label", "ai-processed")
        tracker.add_label(story_id, completion)
        tracker.add_label(story_id, settings["labels"]["applied"])
        move_card_for_label(tracker, story_id, completion)
        for label in agent_config.get("trigger_labels_to_remove",
                                      agent_config.get("selection", {}).get("required_labels", [])):
            try:
                tracker.remove_label(story_id, label)
            except Exception as e:                              # noqa: BLE001
                logger.warning("Could not remove trigger label %s: %s", label, e)

    return {"story_id": story_id, "story_summary": story["summary"],
            "mode": "impact-aware", "revised": revised, "skipped_revisions": skipped,
            "retired": [c["key"] for c in retired], "near_matches": near,
            "test_cases_generated": len(draft.new_test_cases), "test_case_keys": created,
            "status": "tests_revised" if not dry_run else "tests_revised_dry_run"}
