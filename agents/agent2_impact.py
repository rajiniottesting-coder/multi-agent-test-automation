"""Agent 2's change-story work: revise and retire scenarios other stories own
(Agent 0 design, C4 and C5).

A story whose hand-over approved existing test cases carries Impacts links to
them. Its normal run then does two kinds of work in ONE branch and ONE pull
request:

  own work     the story's new test cases -> its own feature file, step
               definitions and page objects, generated exactly as today
  impact work  each approved test case's scenario, in the feature file of the
               story that OWNS it, rewritten in place by deterministic
               splicing; each retired test case's scenario removed

Owners' feature files are never generated whole - only spliced, so a scenario
nobody approved cannot be dropped or reworded. The plan sees the revisions
(so it can extend page objects), but any owner file it proposes is dropped.

Every story without Impacts links gets `([], [])` from `impacted_for_run` and
takes the normal path unchanged.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("agent2_impact")


@dataclass
class OwnerFile:
    path: str                       # features/<name>.feature
    revise: list = field(default_factory=list)     # test case dicts
    retire: list = field(default_factory=list)     # test case keys

    @property
    def step_defs_path(self) -> str:
        stem = self.path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        return f"tests/step_defs/test_{stem}.py"


def impacted_for_run(jira, story_id: str) -> tuple[list, list]:
    """(revisions, retirements) for the story; ([], []) for an ordinary story.

    A failed lookup while Agent 0 is off is logged and treated as none, so
    Agent 2's normal work never depends on the Impacts link type existing.
    """
    try:
        cases = jira.get_impacted_test_cases(story_id, include_retired=True)
    except Exception as e:                                     # noqa: BLE001
        from core.impact_settings import impact_settings
        if impact_settings()["enabled"]:
            raise
        logger.warning("Impacted lookup failed for %s (%s); Agent 0 is off - normal run.",
                       story_id, e)
        return [], []
    if not isinstance(cases, list):
        return [], []
    return ([c for c in cases if not c.get("retired")],
            [c["key"] for c in cases if c.get("retired")])


def locate(index, revisions: list, retirements: list) -> tuple[dict, list]:
    """({feature path: OwnerFile}, [keys with no marker anywhere])."""
    files: dict = {}
    unmarked: list = []
    for tc in revisions:
        entry = index.by_key.get(tc["key"])
        if entry is None:
            unmarked.append(tc["key"])
            continue
        files.setdefault(f"features/{entry.file}", OwnerFile(f"features/{entry.file}")).revise.append(tc)
    for key in retirements:
        entry = index.by_key.get(key)
        if entry is None:
            continue                     # already gone from every file: nothing to remove
        files.setdefault(f"features/{entry.file}", OwnerFile(f"features/{entry.file}")).retire.append(key)
    return dict(sorted(files.items())), unmarked


def plan_cases(owner_files: dict) -> list:
    """The revisions as the plan sees them: same keys, with a note saying the
    scenario exists and will be spliced, so the plan only extends page objects."""
    out = []
    for f in owner_files.values():
        for tc in f.revise:
            out.append(dict(tc, description=(
                f"REVISION of the existing scenario for {tc['key']} in {f.path} - that "
                "feature file and its step definitions are updated by splicing; do not "
                "plan them. Plan only page-object methods the revised steps need.\n\n"
                + tc.get("description", ""))))
    return out


def drop_owner_files(plan, owner_files: dict, own_new_cases: list) -> list:
    """Remove from the plan every file the splice owns; returns what was dropped.

    Owners' feature files and step definitions are edited only by splicing.
    With no own new test case, the story has no feature file of its own, so
    every feature file and step-definition file goes.
    """
    protected = set(owner_files) | {f.step_defs_path for f in owner_files.values()}
    keep, dropped = [], []
    for fp in plan.files_to_create:
        path = fp.file_path.replace("\\", "/").lstrip("./")
        own_test_file = fp.file_type in ("feature", "step_definitions") or \
            path.endswith(".feature") or path.startswith("tests/step_defs/")
        if path in protected or (not own_new_cases and own_test_file):
            dropped.append(fp.file_path)
        else:
            keep.append(fp)
    plan.files_to_create = keep
    if dropped:
        logger.warning("Dropped from the plan (edited by splicing only, or no own "
                       "scenarios): %s", dropped)
    return dropped


def splice_owner_files(llm, gh, story_id: str, owner_files: dict, index, ctx,
                       references: dict, page_inventory: str, tracker) -> tuple:
    """Rewrite approved scenarios and remove retired ones in the owners' files.

    Returns (generated files, report). Each owner's step definitions gain only
    the step functions the revised scenarios need (_splice_step_defs_incremental).
    """
    from agents.agent2_coder import (GeneratedFile, _generate_single_scenario,
                                     _splice_step_defs_incremental, compute_description_hash,
                                     remove_scenario, splice_scenario)
    from validators.orphan_cleanup import cleanup_orphans_after_removal

    files, report = [], {"revised": {}, "retired": {}, "owners": {}, "step_defs": {}}
    for path, of in owner_files.items():
        original = gh.get_file_content(path, branch="main")
        content = original
        for tc in of.revise:
            entry = index.by_key[tc["key"]]
            owner = entry.owner or tracker.get_parent_story_key(tc["key"])
            tc2 = dict(tc, owner=owner, impacted_by=tuple(entry.impacted_by) + (story_id,))
            text = _generate_single_scenario(llm, path, tc2, ctx, content)
            spliced = splice_scenario(content, tc["key"], text,
                                      compute_description_hash(tc.get("description", "")))
            if spliced == content:
                raise ValueError(f"{tc['key']}: splice into {path} changed nothing")
            content = spliced
            report["revised"][tc["key"]] = path
            report["owners"][tc["key"]] = owner
        for key in of.retire:
            content = remove_scenario(content, key)
            report["retired"][key] = path

        sd_path = of.step_defs_path
        sd_content, mode = _splice_step_defs_incremental(
            llm, gh, path, content, sd_path, ctx, references, page_inventory)
        report["step_defs"][sd_path] = mode
        page_updates: dict = {}
        if of.retire:
            try:
                (sd_files, page_updates, _defs, _methods) = cleanup_orphans_after_removal(
                    old_feature_content=original, new_feature_content=content,
                    removed_jira_keys=of.retire, step_def_files={sd_path: sd_content},
                    page_object_files={}, reserved_file_paths={"pages/base_page.py"})
                sd_content = sd_files.get(sd_path, sd_content)
            except Exception as e:                             # noqa: BLE001
                logger.warning("Orphan cleanup after retiring %s failed: %s", of.retire, e)
        files.append(GeneratedFile(file_path=path, content=content, is_new_file=False,
                                   purpose=f"Impact of {story_id}: revised "
                                           f"{[t['key'] for t in of.revise]}, retired {of.retire}"))
        if mode != "unchanged":
            files.append(GeneratedFile(file_path=sd_path, content=sd_content, is_new_file=False,
                                       purpose=f"Impact of {story_id}: step functions for "
                                               "revised scenarios"))
        for page_path, page_content in page_updates.items():
            files.append(GeneratedFile(file_path=page_path, content=page_content,
                                       is_new_file=False, purpose="Retired: orphan methods"))
    return files, report


def check_coverage(files: list, revisions: list, retirements: list) -> list:
    """Gate (C4): every approved key is spliced with its CURRENT hash, and no
    retired key is left in any file of the batch. Returns errors."""
    from agents.agent2_coder import compute_description_hash, parse_feature_file
    found: dict = {}
    for f in files:
        if f.file_path.endswith(".feature"):
            _h, blocks = parse_feature_file(f.content)
            for b in blocks:
                if b.jira_key:
                    found[b.jira_key] = b.jira_hash
    errors = []
    for tc in revisions:
        want = compute_description_hash(tc.get("description", ""))
        if found.get(tc["key"]) != want:
            errors.append(f"approved {tc['key']} is not revised in this batch "
                          f"(marker hash {found.get(tc['key'])}, expected {want})")
    for key in retirements:
        if key in found:
            errors.append(f"retired {key} is still in the batch")
    return errors


def pr_sections(report: dict) -> str:
    parts = []
    if report["revised"]:
        parts.append("\n\n---\n## Revised (owner)\n")
        for key, path in sorted(report["revised"].items()):
            parts.append(f"- {key} - owner {report['owners'].get(key) or '?'} - `{path}`\n")
    if report["retired"]:
        parts.append("\n## Retired\n")
        for key, path in sorted(report["retired"].items()):
            parts.append(f"- {key} - scenario removed from `{path}`\n")
    if parts:
        parts.append("\nScenarios in other stories' files were edited only by splicing: "
                     "every scenario not listed here is byte-for-byte unchanged.\n")
    return "".join(parts)
