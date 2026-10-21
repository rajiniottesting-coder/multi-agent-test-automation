"""
C6 (Agent 0 design): owner and impacted-by on the marker line, and what
ai-update does with them.
"""
from unittest.mock import patch

import pytest

from agents.agent2_coder import (_inject_markers_into_feature, build_marker_index,
                                 compute_description_hash, format_marker,
                                 parse_feature_file, parse_marker, parse_marker_fields,
                                 splice_scenario)
from tests.sandbox.fake_jira import FakeRepoHost, jira_client_over
from tests.sandbox.seed import build_repo, repo_files, seed_jira

H = compute_description_hash("d")


class TestMarkerFormat:
    def test_old_format_parses_unchanged(self):
        assert parse_marker(f"  # JIRA: AB-3 (hash: {H})") == ("AB-3", H)
        assert parse_marker_fields(f"# JIRA: AB-3 (hash: {H})") == \
            {"key": "AB-3", "hash": H, "owner": None, "impacted_by": ()}

    def test_new_format_round_trip(self):
        line = format_marker("AB-3", "d", owner="ab-1", impacted_by=["AB-9", "AB-12", "AB-9"])
        assert line == f"# JIRA: AB-3 (hash: {H}) owner: AB-1 impacted-by: AB-9,AB-12"
        assert parse_marker(line) == ("AB-3", H)            # every old caller still works
        assert parse_marker_fields(line)["impacted_by"] == ("AB-9", "AB-12")

    def test_owner_only_and_no_extras(self):
        assert format_marker("AB-3", "d") == f"# JIRA: AB-3 (hash: {H})"
        assert format_marker("AB-3", "d", owner="AB-1").endswith("owner: AB-1")
        assert "impacted-by" not in format_marker("AB-3", "d", owner="AB-1", impacted_by=["AB-1"])

    def test_garbage_after_the_marker_is_not_a_marker(self):
        assert parse_marker(f"# JIRA: AB-3 (hash: {H}) whatever") is None

    def test_blocks_and_index_carry_the_fields(self, tmp_path):
        text = ("Feature: x\n\n  @t\n  " + format_marker("AB-3", "d", "AB-1", ["AB-9"])
                + "\n  Scenario: s\n    Then x\n")
        _h, blocks = parse_feature_file(text)
        assert (blocks[0].owner, blocks[0].impacted_by) == ("AB-1", ("AB-9",))
        (tmp_path / "x.feature").write_text(text)
        entry = build_marker_index(tmp_path).by_key["AB-3"]
        assert (entry.owner, entry.impacted_by) == ("AB-1", ("AB-9",))

    def test_splice_round_trip_with_extended_markers(self):
        old = "Feature: x\n\n  " + format_marker("AB-3", "d", "AB-1") + "\n  Scenario: s\n    Then a\n"
        new = "  " + format_marker("AB-3", "v2", "AB-1", ["AB-9"]) + "\n  Scenario: s\n    Then b\n"
        out = splice_scenario(old, "AB-3", new, compute_description_hash("v2"))
        _h, blocks = parse_feature_file(out)
        assert blocks[0].impacted_by == ("AB-9",) and "Then b" in out

    def test_a_hash_refresh_keeps_the_trace(self):
        content = ("Feature: x\n\n  " + format_marker("AB-3", "old", "AB-1", ["AB-9"])
                   + "\n  Scenario: Login works\n    Then a\n")
        out = _inject_markers_into_feature(content, [{"key": "AB-3", "summary": "Login works",
                                                      "description": "new"}])
        f = parse_marker_fields(next(l for l in out.splitlines() if "JIRA" in l))
        assert f["hash"] == compute_description_hash("new")
        assert (f["owner"], f["impacted_by"]) == ("AB-1", ("AB-9",))

    def test_new_markers_name_their_owner(self):
        out = _inject_markers_into_feature(
            "Feature: x\n\n  Scenario: Login works\n    Then a\n",
            [{"key": "AB-3", "summary": "Login works", "description": "d", "owner": "AB-1"}])
        assert "owner: AB-1" in out


# ─────────────────────────────────────────────────────────────────
# ai-update with owners recorded, in the sandbox
# ─────────────────────────────────────────────────────────────────
@pytest.fixture
def world(tmp_path, monkeypatch):
    fake = seed_jira()
    jira = jira_client_over(fake, monkeypatch)
    root = build_repo(tmp_path / "repo")
    import config.paths as paths
    import agents.agent2_coder as a2
    monkeypatch.setattr(paths, "FEATURES_DIR", root / "features")
    monkeypatch.setattr(a2, "FEATURES_DIR", root / "features")
    return fake, jira, root


def _update(jira, root, story="SBX-1"):
    import agents.agent2_coder as a2
    gh = FakeRepoHost(repo_files(root))

    def one(llm, path, tc, ctx, existing):
        return ("  " + format_marker(tc["key"], tc.get("description", ""), tc.get("owner"),
                                     tc.get("impacted_by", ()))
                + f"\n  Scenario: {tc['summary'].split('] ')[-1]} (revised)\n    Then revised\n")

    with patch.object(a2, "get_tracker", return_value=jira), \
         patch.object(a2, "get_repo_host", return_value=gh), \
         patch.object(a2, "LLMClient"), \
         patch.object(a2, "_generate_single_scenario", side_effect=one), \
         patch.object(a2, "_splice_step_defs_incremental",
                      side_effect=lambda *a, **k: ("# step defs", "spliced")), \
         patch.object(a2, "_validate_generated_files"):
        result = a2.run_update(story)
    return result, gh


def _add_scenario(root, marker, title):
    path = root / "features" / "sandbox_login.feature"
    path.write_text(path.read_text() + f"\n  {marker}\n  Scenario: {title}\n"
                    "    When I log in as a \"registered\" user\n    Then I should be logged in\n")


class TestUpdateWithOwners:
    def test_another_storys_scenario_in_the_file_is_not_an_orphan(self, world):
        fake, jira, root = world
        _add_scenario(root, format_marker("SBX-21", "x", owner="SBX-2"), "Shopper session")
        fake.issues["SBX-12"]["description"] = "changed"
        _result, gh = _update(jira, root)
        new = gh.branches[gh.prs[0]["head_ref"]]["features/sandbox_login.feature"]
        assert "Shopper session" in new

    def test_an_unowned_stale_marker_is_still_an_orphan(self, world):
        """Unchanged behaviour for markers written before owners existed."""
        fake, jira, root = world
        _add_scenario(root, format_marker("SBX-77", "x"), "Stale scenario")
        fake.issues["SBX-12"]["description"] = "changed"
        _result, gh = _update(jira, root)
        new = gh.branches[gh.prs[0]["head_ref"]]["features/sandbox_login.feature"]
        assert "Stale scenario" not in new

    def test_spliced_markers_keep_and_write_the_owner(self, world):
        fake, jira, root = world
        fake.issues["SBX-12"]["description"] = "changed"
        _result, gh = _update(jira, root)
        new = gh.branches[gh.prs[0]["head_ref"]]["features/sandbox_login.feature"]
        _h, blocks = parse_feature_file(new)
        assert {b.jira_key: b.owner for b in blocks if b.jira_key}["SBX-12"] == "SBX-1"

    def test_a_reserved_reference_file_is_never_updated(self, world, monkeypatch):
        fake, jira, root = world
        ref = root / "features" / "login.feature"
        text = ref.read_text().replace(
            "  Scenario: Successful login with valid credentials",
            "  " + format_marker("SBX-11", "x", owner="SBX-1")
            + "\n  Scenario: Successful login with valid credentials", 1)
        ref.write_text(text)
        sbx = root / "features" / "sandbox_login.feature"
        sbx.write_text("\n".join(l for l in sbx.read_text().splitlines()
                                 if "JIRA: SBX-1" not in l) + "\n")
        result, gh = _update(jira, root)
        assert result["status"] == "reserved_target" and gh.prs == []


def test_repeated_refreshes_never_grow_the_marker():
    """Agent 3 review on #130: the refresh concatenates the recorded and the
    new impacted-by before format_marker de-duplicates; pin that the line is
    stable across any number of refreshes."""
    content = ("Feature: x\n\n  " + format_marker("AB-3", "old", "AB-1", ["AB-9"])
               + "\n  Scenario: Login works\n    Then a\n")
    tc = {"key": "AB-3", "summary": "Login works", "description": "new",
          "impacted_by": ("AB-9", "AB-9", "AB-1")}
    once = _inject_markers_into_feature(content, [tc])
    assert _inject_markers_into_feature(_inject_markers_into_feature(once, [tc]), [tc]) == once
    line = next(l for l in once.splitlines() if "JIRA" in l)
    assert line.strip() == format_marker("AB-3", "new", "AB-1", ["AB-9"])


class TestUpdateLeavesNoUnusedStepDefinitions:
    """ai-update removing (or revising) a scenario can take the last use of a
    step with it. The step-def splice keeps existing functions, so run_update
    must comment those out - otherwise the final unused-step check rejects a
    run on code no model wrote."""

    def _update_keeping_step_defs(self, jira, root):
        import agents.agent2_coder as a2
        gh = FakeRepoHost(repo_files(root))
        sd = (root / "tests" / "step_defs" / "test_sandbox_login.py").read_text()
        with patch.object(a2, "get_tracker", return_value=jira), \
             patch.object(a2, "get_repo_host", return_value=gh), \
             patch.object(a2, "LLMClient"), \
             patch.object(a2, "_splice_step_defs_incremental",
                          side_effect=lambda *a, **k: (sd, "unchanged")), \
             patch.object(a2, "_validate_generated_files"):
            a2.run_update("SBX-1")
        return gh

    def test_a_removed_scenarios_only_step_is_commented_out(self, world):
        from validators.gherkin_analyzer import validate_no_unused_step_definitions
        from types import SimpleNamespace
        fake, jira, root = world
        feature = root / "features" / "sandbox_login.feature"
        feature.write_text(feature.read_text() + "\n  " + format_marker("SBX-77", "x")
                           + "\n  Scenario: Retired panel\n    When I open the retired panel\n")
        sd_path = root / "tests" / "step_defs" / "test_sandbox_login.py"
        sd_path.write_text(sd_path.read_text()
                           + '\n\n@when("I open the retired panel")\ndef open_retired_panel():\n    pass\n')

        gh = self._update_keeping_step_defs(jira, root)

        pr = gh.prs[0]
        files = gh.branches[pr["head_ref"]]
        new_sd = files["tests/step_defs/test_sandbox_login.py"]
        assert '# @when("I open the retired panel")' in new_sd
        assert "AI-ORPHAN" in new_sd and "SBX-77" in new_sd
        assert "`open_retired_panel`" in pr["body"]
        assert "removed by regeneration" not in pr["body"]
        errors = validate_no_unused_step_definitions([
            SimpleNamespace(file_path="features/sandbox_login.feature",
                            content=files["features/sandbox_login.feature"]),
            SimpleNamespace(file_path="tests/step_defs/test_sandbox_login.py", content=new_sd)])
        assert not any("retired panel" in e for e in errors), errors

    def test_steps_other_scenarios_still_use_are_kept(self, world):
        fake, jira, root = world
        feature = root / "features" / "sandbox_login.feature"
        feature.write_text(feature.read_text() + "\n  " + format_marker("SBX-77", "x")
                           + "\n  Scenario: Retired copy\n"
                           "    When I log in as a \"registered\" user\n")
        gh = self._update_keeping_step_defs(jira, root)
        files = gh.branches[gh.prs[0]["head_ref"]]
        assert files["tests/step_defs/test_sandbox_login.py"] == \
            (root / "tests" / "step_defs" / "test_sandbox_login.py").read_text()
