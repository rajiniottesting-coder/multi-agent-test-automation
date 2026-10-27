"""G5 / F-13: no approved test case is dropped without a word.

Before: when Agent 2 could not automate an approved test case - an element
missing from the inventory, a step the page cannot show, a title it could not
pair with a marker - the model left it out and said so in `notes`, which were
printed only in a dry run. Marker injection only logged a warning. The story
still got `ai-coded`. The duplicate check's "title clash" and ai-update's
"unmarked scenario" skips were logged the same way.

Now every approved test case is covered (a markered scenario), or named - in the
pull request and in one story comment - with its reason; a story with an
uncovered one gets `ai-incomplete` beside `ai-coded`, and the run that fills the
gap removes it. A run that would automate none of them opens no pull request.

End to end in the sandbox (fake Jira, fake repository host); the model-facing
functions return fixed content. Generic names only.
"""
from unittest.mock import MagicMock, patch

import pytest

from agents import agent2_coverage as cov
from agents.agent2_coder import format_marker
from core.schemas import CodePlan, FilePlan, GeneratedFile
from tests.sandbox.fake_jira import FakeRepoHost, jira_client_over
from tests.sandbox.seed import build_repo, repo_files, seed_jira

STORY = "SBX-50"
FEATURE = "features/wish_list.feature"
STEPS = "tests/step_defs/test_wish_list.py"
CASES = {"SBX-51": "[Positive] Add a product to the wish list",
         "SBX-52": "[Positive] Remove a product from the wish list",
         "SBX-53": "[Negative] Wish list refuses a sold-out product"}
LABELS = {"update_label": "ai-update", "incomplete_label": "ai-incomplete"}


def _gf(path, content):
    return GeneratedFile(file_path=path, content=content, is_new_file=True, purpose="p")


def _scenario(key, title, marker=True, description="d"):
    head = f"  {format_marker(key, description, owner=STORY)}\n" if marker else ""
    return f"{head}  Scenario: {title}\n    Given I am on the wish list page\n"


# ── the rule, on files ──────────────────────────────────────────────────

def test_markered_and_unmarked_scenarios_are_read_from_the_files():
    files = [_gf(FEATURE, "Feature: W\n\n" + _scenario("SBX-51", "Add a product")
                 + "\n" + _scenario("SBX-52", "Stray", marker=False)),
             _gf(STEPS, "# JIRA: SBX-53 (hash: 0123abcd)\n")]       # not a feature file
    assert cov.markered_keys(files) == {"SBX-51"}
    assert cov.unmarked_scenarios(files) == [(FEATURE, "Stray")]


def test_notes_about_picks_the_sentences_naming_the_key_and_no_longer_key():
    notes = ("Skipped: SBX-5 -- covered by the reference file. Grouped the rest.\n"
             "SBX-53 needs the sold-out badge, which is not in the inventory; SBX-530 is fine.")
    assert cov.notes_about(notes, "SBX-5") == "covered by the reference file."
    assert cov.notes_about("- SBX-7: no badge.", "SBX-7") == "no badge."
    assert cov.notes_about("Keep SBX-7 for later.", "SBX-7") == "Keep SBX-7 for later."
    assert cov.notes_about(notes, "SBX-53") == ("SBX-53 needs the sold-out badge, which is "
                                                "not in the inventory;")
    assert cov.notes_about(notes, "SBX-9") == ""
    assert len(cov.notes_about("SBX-1 " + "x" * 900, "SBX-1")) == 300


def test_each_missing_case_carries_the_reason_the_notes_give_or_says_none():
    files = [_gf(FEATURE, "Feature: W\n\n" + _scenario("SBX-51", "Add"))]
    cases = [{"key": k, "summary": s} for k, s in CASES.items()]
    gaps = cov.missing_from_batch(files, cases, "SBX-53: the badge is not in the inventory.")
    assert [g.key for g in gaps] == ["SBX-52", "SBX-53"] and all(g.blocking for g in gaps)
    assert "no scenario of its own" in gaps[0].reason
    assert "the model gave no reason" in gaps[0].reason
    assert "the badge is not in the inventory" in gaps[1].reason


def test_a_key_no_marker_can_hold_is_named_as_the_cause():
    gap, = cov.missing_from_batch([], [{"key": "ACME-T1", "summary": "x"}])
    assert "cannot be carried by a scenario marker" in gap.reason


def test_the_duplicate_checks_skips_are_classified():
    tc = lambda k: {"key": k, "summary": CASES.get(k, k)}
    gaps = cov.skipped_gaps([
        {"test_case": tc("SBX-51"), "reason": "unchanged", "matched_file": FEATURE},
        {"test_case": tc("SBX-52"), "reason": "title_clash", "matched_file": FEATURE,
         "matched_scenario": "Remove a product", "other_key": "SBX-11"},
        {"test_case": tc("SBX-53"), "reason": "modified", "matched_file": FEATURE},
        {"test_case": tc("SBX-54"), "reason": "legacy", "matched_file": FEATURE},
    ], LABELS)
    by = {g.key: g for g in gaps}
    assert "SBX-51" not in by, "unchanged is covered and says nothing"
    assert by["SBX-52"].blocking and "belongs to SBX-11" in by["SBX-52"].reason
    assert not by["SBX-53"].blocking and "add `ai-update`" in by["SBX-53"].reason
    assert not by["SBX-54"].blocking and "backfill_markers" in by["SBX-54"].reason


def test_the_pull_request_section_and_the_comment():
    gaps = [cov.Gap("SBX-53", "Sold out", "no scenario - x", True),
            cov.Gap("SBX-54", "Old", "outdated", False)]
    section = cov.pr_section(gaps, [(FEATURE, "Stray")], LABELS)
    assert "Approved test cases not automated (1)" in section
    assert "**SBX-53** Sold out" in section and "Covered, but needing a person" in section
    assert '`features/wish_list.feature`: "Stray"' in section and "`ai-update`" in section
    body = cov.comment(STORY, gaps, [], "pull request https://x/1", LABELS)
    assert body.startswith(f"{cov.INCOMPLETE_MARKER} Agent 2 automated {STORY} only in part: 1 ")
    assert "(pull request https://x/1)" in body and "ai-incomplete" in body
    only_needs = cov.pr_section(gaps[1:], [], LABELS)
    assert "Approved test cases to check" in only_needs and "ai-update`" not in only_needs
    assert cov.pr_section([], [], LABELS) == ""


def test_record_comments_and_labels_and_never_raises():
    tracker = MagicMock()
    cov.record(tracker, STORY, [cov.Gap("SBX-53", "s", "r", True)], [], "pr", LABELS, [])
    tracker.add_comment.assert_called_once()
    tracker.add_label.assert_called_once_with(STORY, "ai-incomplete")

    tracker = MagicMock()
    cov.record(tracker, STORY, [], [], "pr", LABELS, ["ai-coded"])
    tracker.add_comment.assert_not_called()
    tracker.remove_label.assert_not_called(), "no label to clear: no tracker call"
    cov.record(tracker, STORY, [], [], "pr", LABELS, ["ai-incomplete"])
    tracker.remove_label.assert_called_once_with(STORY, "ai-incomplete")

    tracker = MagicMock()
    tracker.add_comment.side_effect = RuntimeError("down")
    cov.record(tracker, STORY, [cov.Gap("SBX-53", "s", "r", True)], [], "pr", LABELS)
    tracker.add_label.assert_called_once_with(STORY, "ai-incomplete"), "a failed comment keeps the label"
    tracker.add_label.side_effect = RuntimeError("down")
    cov.record(tracker, STORY, [cov.Gap("SBX-53", "s", "r", True)], [], "pr", LABELS)


def test_a_comment_listing_only_scenarios_does_not_call_them_test_cases():
    body = cov.comment(STORY, [], [(FEATURE, "Stray")], "pull request u", LABELS)
    assert "the items below need a person" in body and "test case(s) have" not in body
    assert "retired instead" not in body, "no remedy without a missing test case"
    assert "retired instead" in cov.comment(STORY, [cov.Gap("K-1", "s", "r", True)], [], "", LABELS)


# ── end to end ──────────────────────────────────────────────────────────

@pytest.fixture
def world(tmp_path, monkeypatch):
    fake = seed_jira()
    fake.add("Story", "A shopper keeps a wish list", key=STORY,
             labels=["ai-processed", "human-approved"], components=["Products"])
    for key, summary in CASES.items():
        fake.add("Test Case", summary, key=key, description=f"steps of {key}")
        fake.link("Relates", key, STORY)
    jira = jira_client_over(fake, monkeypatch)
    root = build_repo(tmp_path / "repo")
    import config.paths as paths
    import agents.agent2_coder as a2
    monkeypatch.setattr(paths, "FEATURES_DIR", root / "features")
    monkeypatch.setattr(a2, "FEATURES_DIR", root / "features")
    return fake, jira, root, FakeRepoHost(repo_files(root))


def _feature(*titles):
    return "Feature: Wish list\n\n" + "\n".join(
        f"  Scenario: {t}\n    Given I am on the wish list page\n" for t in titles)


def _run(jira, gh, scenarios, notes="", **kw):
    import agents.agent2_coder as a2
    plan = CodePlan(feature_name="wish-list", branch_name=f"auto/{STORY}-wish-list",
                    pr_title="Wish list", pr_body="Body", notes=notes,
                    files_to_create=[FilePlan(file_path=FEATURE, file_type="feature", purpose="f"),
                                     FilePlan(file_path=STEPS, file_type="step_definitions",
                                              purpose="s")])

    def gen(llm, file_plan, *a, **k):
        return _feature(*scenarios) if file_plan.file_path == FEATURE else "# steps\n"

    with patch.object(a2, "get_tracker", return_value=jira), \
         patch.object(a2, "get_repo_host", return_value=gh), \
         patch.object(a2, "LLMClient"), \
         patch.object(a2, "build_plan", return_value=plan), \
         patch.object(a2, "generate_file_content", side_effect=gen), \
         patch.object(a2, "_attempt_step_coverage_repair", side_effect=lambda g, *a, **k: g), \
         patch.object(a2, "_validate_generated_files"):
        return a2.run(STORY, **kw)


def _comments(fake):
    return [c for c in fake.comments.get(STORY, []) if c.startswith(cov.INCOMPLETE_MARKER)]


def test_a_partial_run_opens_its_pr_and_names_what_it_left_out(world):
    fake, jira, root, gh = world
    result = _run(jira, gh, ["Add a product to the wish list",
                             "Remove a product from the wish list"],
                  notes="Skipped: SBX-53 -- the sold-out badge is not in the inventory.")
    assert result["status"] == "pr_opened" and result["not_automated"] == ["SBX-53"]
    body = gh.prs[0]["body"]
    assert "Approved test cases not automated (1)" in body
    assert "**SBX-53** [Negative] Wish list refuses a sold-out product" in body
    assert "the sold-out badge is not in the inventory" in body
    note, = _comments(fake)
    assert "SBX-53" in note and "(pull request " in note
    labels = fake.issues[STORY]["labels"]
    assert "ai-coded" in labels and "ai-incomplete" in labels
    assert labels.index("ai-incomplete") < labels.index("ai-coded"), "said before ai-coded"


def test_a_complete_run_says_nothing_new(world):
    fake, jira, root, gh = world
    result = _run(jira, gh, ["Add a product to the wish list",
                             "Remove a product from the wish list",
                             "Wish list refuses a sold-out product"])
    assert result["not_automated"] == []
    assert "not automated" not in gh.prs[0]["body"] and not _comments(fake)
    assert "ai-incomplete" not in fake.issues[STORY]["labels"]


def test_a_complete_run_makes_no_label_call_when_there_is_none_to_clear(world):
    fake, jira, root, gh = world
    jira.remove_label = MagicMock(wraps=jira.remove_label)
    _run(jira, gh, ["Add a product to the wish list", "Remove a product from the wish list",
                    "Wish list refuses a sold-out product"])
    assert not any(c.args[1] == "ai-incomplete" for c in jira.remove_label.call_args_list)


def test_a_run_that_automates_nothing_opens_no_pull_request(world):
    fake, jira, root, gh = world
    from agents.agent2_coder import GateFailure
    with pytest.raises(GateFailure, match="none of its 3 new approved test case"):
        _run(jira, gh, [])                       # the model wrote no scenario at all
    assert gh.prs == [] and "ai-coded" not in fake.issues[STORY]["labels"]
    blocked, = [c for c in fake.comments[STORY] if c.startswith("[agent2:blocked]")]
    assert "SBX-51" in blocked and "no approved test case automated" in blocked


def test_a_regeneration_that_fills_the_gap_removes_the_label(world):
    fake, jira, root, gh = world
    fake.issues[STORY]["labels"] += ["ai-coded", "ai-incomplete", "ai-regenerate"]
    result = _run(jira, gh, ["Add a product to the wish list",
                             "Remove a product from the wish list",
                             "Wish list refuses a sold-out product"], is_regenerate=True)
    assert result["status"] == "pr_opened" and result["not_automated"] == []
    assert "ai-incomplete" not in fake.issues[STORY]["labels"]


def test_an_unpaired_scenario_is_listed_too(world):
    fake, jira, root, gh = world
    _run(jira, gh, ["Add a product to the wish list", "Remove a product from the wish list",
                    "Wish list refuses a sold-out product", "Totally unrelated check"])
    body = gh.prs[0]["body"]
    assert '"Totally unrelated check"' in body and "Approved test cases to check" in body


def test_a_dry_run_prints_the_gaps_and_writes_nothing(world, capsys):
    fake, jira, root, gh = world
    result = _run(jira, gh, ["Add a product to the wish list"], dry_run=True)
    assert result["not_automated"] == ["SBX-52", "SBX-53"]
    assert "Approved test cases not automated (2)" in capsys.readouterr().out
    assert gh.prs == [] and not _comments(fake)
    assert "ai-incomplete" not in fake.issues[STORY]["labels"]


CLASH = "Wish list shows a sold-out product as unavailable"


def _clash_on_main(root, gh):
    """Another story's MARKED scenario on main, with a title one of ours repeats."""
    text = "Feature: Other\n\n" + _scenario("SBX-21", CLASH).replace(STORY, "SBX-2")
    (root / "features" / "other.feature").write_text(text, encoding="utf-8")
    gh.branches["main"]["features/other.feature"] = text


def test_a_title_clash_is_not_counted_as_covered(world):
    """SBX-53's summary matches the title of SBX-21's scenario on main: the
    duplicate check skipped it, logged it and called the story coded."""
    fake, jira, root, gh = world
    _clash_on_main(root, gh)
    fake.issues["SBX-53"]["summary"] = f"[Negative] {CLASH}"
    result = _run(jira, gh, ["Add a product to the wish list",
                             "Remove a product from the wish list"])
    assert result["not_automated"] == ["SBX-53"]
    assert "belongs to SBX-21" in gh.prs[0]["body"]
    assert "ai-incomplete" in fake.issues[STORY]["labels"]


def test_a_legacy_match_is_covered_but_listed(world):
    """A title matching an UNMARKED scenario (the reference file's) is covered;
    it needs its marker, and the story is not incomplete for it."""
    fake, jira, root, gh = world
    fake.issues["SBX-53"]["summary"] = "[Negative] Login fails with an incorrect password"
    result = _run(jira, gh, ["Add a product to the wish list",
                             "Remove a product from the wish list"])
    assert result["not_automated"] == []
    assert "backfill_markers" in gh.prs[0]["body"]
    assert "ai-incomplete" not in fake.issues[STORY]["labels"]


def test_every_case_skipped_still_says_why_on_the_story(world):
    """The no-work path: no pull request, but the clash is still on the story."""
    fake, jira, root, gh = world
    _clash_on_main(root, gh)
    for key in CASES:
        fake.links = {k: v for k, v in fake.links.items() if v[1] != key}
    fake.add("Test Case", f"[Negative] {CLASH}", key="SBX-59", description="steps")
    fake.link("Relates", "SBX-59", STORY)
    result = _run(jira, gh, [])
    assert result["status"] == "skipped_all_duplicates" and result["not_automated"] == ["SBX-59"]
    note, = _comments(fake)
    assert "no pull request opened" in note and "belongs to SBX-21" in note
    assert {"ai-coded", "ai-incomplete"} <= set(fake.issues[STORY]["labels"])


def test_the_scan_summary_names_the_cases_left_out():
    from agents.agent2_coder import _scan_summary_lines
    lines = _scan_summary_lines([{"story_id": STORY, "status": "pr_opened",
                                  "pr_url": "u", "not_automated": ["SBX-53"]}])
    assert any("not automated: SBX-53" in line for line in lines)


# ── ai-update fills the gap after the cause is fixed ─────────────────────

def _merge_partial(fake, jira, root, gh):
    _run(jira, gh, ["Add a product to the wish list", "Remove a product from the wish list"])
    branch = gh.prs[0]["head_ref"]
    gh.merge(1)
    # A person's hand-written scenario, unmarked, already in the file.
    gh.branches[branch][FEATURE] += "\n" + _scenario("", "Hand-written check", marker=False)
    for path in (FEATURE, STEPS):
        gh.branches["main"][path] = gh.branches[branch][path]
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(gh.branches[branch][path], encoding="utf-8")
    fake.issues[STORY]["labels"].append("ai-update")


def _update(jira, gh, with_marker=True):
    import agents.agent2_coder as a2

    def one(llm, path, tc, ctx, existing):
        return _scenario(tc["key"], "Wish list refuses a sold-out product", marker=with_marker,
                         description=tc.get("description", ""))

    with patch.object(a2, "get_tracker", return_value=jira), \
         patch.object(a2, "get_repo_host", return_value=gh), \
         patch.object(a2, "LLMClient"), \
         patch.object(a2, "_generate_single_scenario", side_effect=one), \
         patch.object(a2, "_splice_step_defs_incremental",
                      side_effect=lambda llm, gh_, p, c, sd, *a, **k: ("# steps\n", "spliced")), \
         patch.object(a2, "_validate_generated_files"):
        return a2.run_update(STORY)


def test_ai_update_generates_only_the_missing_case_and_clears_the_label(world):
    fake, jira, root, gh = world
    _merge_partial(fake, jira, root, gh)
    assert "ai-incomplete" in fake.issues[STORY]["labels"]
    result = _update(jira, gh)
    assert result["status"] == "update_pr_opened" and result["scenarios_added"] == 1
    assert result["not_automated"] == []
    assert "not automated" not in gh.prs[1]["body"]
    assert "Hand-written check" not in gh.prs[1]["body"], "only scenarios this update added"
    assert "ai-incomplete" not in fake.issues[STORY]["labels"]


def test_ai_update_whose_scenario_lost_its_marker_stays_incomplete(world):
    fake, jira, root, gh = world
    _merge_partial(fake, jira, root, gh)
    result = _update(jira, gh, with_marker=False)
    assert result["not_automated"] == ["SBX-53"]
    body = gh.prs[1]["body"]
    assert "**SBX-53**" in body and '"Wish list refuses a sold-out product"' in body
    assert "ai-incomplete" in fake.issues[STORY]["labels"]


def test_ai_update_with_nothing_to_do_clears_a_stale_label(world):
    fake, jira, root, gh = world
    _merge_partial(fake, jira, root, gh)
    _update(jira, gh)                                       # fills it; label off
    fake.issues[STORY]["labels"] += ["ai-incomplete", "ai-update"]   # stale, by hand
    gh.merge(2)
    branch = gh.prs[1]["head_ref"]
    gh.branches["main"][FEATURE] = gh.branches[branch][FEATURE]
    (root / FEATURE).write_text(gh.branches[branch][FEATURE], encoding="utf-8")
    result = _update(jira, gh)
    assert result["status"] == "noop_all_unchanged"
    assert "ai-incomplete" not in fake.issues[STORY]["labels"]


def test_the_label_is_configured_and_reset_on_a_reverted_change():
    import yaml
    from core.impact_settings import DEFAULTS
    cfg = yaml.safe_load(open("config/config.yaml", encoding="utf-8"))
    assert cfg["agents"]["agent2_coder"]["incomplete_label"] == "ai-incomplete"
    assert "ai-incomplete" in DEFAULTS["reconcile"]["reset_labels"]


def test_ai_update_lists_an_unmarked_match_without_calling_the_story_incomplete(world):
    """A test case whose scenario already sits UNMARKED in the file is covered:
    ai-update does not append it twice, says it needs its marker, and does not
    count it as missing."""
    fake, jira, root, gh = world
    _merge_partial(fake, jira, root, gh)
    fake.add("Test Case", "[Positive] Hand-written check", key="SBX-54", description="steps")
    fake.link("Relates", "SBX-54", STORY)
    result = _update(jira, gh)
    assert result["not_automated"] == []
    body = gh.prs[1]["body"]
    assert "**SBX-54**" in body and "backfill_markers" in body
    assert "ai-incomplete" not in fake.issues[STORY]["labels"]
    note = _comments(fake)[-1]
    assert "SBX-54" in note and "needing a person" in note
