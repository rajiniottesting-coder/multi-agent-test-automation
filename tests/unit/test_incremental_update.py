"""
Unit tests for the ai-update (incremental scenario splice) feature.

All functions under test live inside agents.agent2_coder (inlined v12b).

Covers:
  - JIRA marker hashing, formatting, parsing
  - Feature file parsing, classification, splice/append/remove
  - Marker injection on LLM-generated feature files (idempotent, refresh,
    fail-quiet on unmatched scenarios)
"""

import pytest


# ─────────────────────────────────────────────────────────────────
# JIRA marker helpers
# ─────────────────────────────────────────────────────────────────
class TestJiraMarker:
    def test_hash_is_deterministic(self):
        from agents.agent2_coder import compute_description_hash
        a = compute_description_hash("Some test case description")
        b = compute_description_hash("Some test case description")
        assert a == b
        assert len(a) == 8

    def test_hash_ignores_whitespace_differences(self):
        from agents.agent2_coder import compute_description_hash
        a = compute_description_hash("step one\nstep two")
        b = compute_description_hash("step one     step two")
        c = compute_description_hash("  step one\n\n\nstep two  ")
        assert a == b == c

    def test_hash_differs_for_different_content(self):
        from agents.agent2_coder import compute_description_hash
        assert compute_description_hash("a") != compute_description_hash("b")

    def test_format_and_parse_roundtrip(self):
        from agents.agent2_coder import format_marker, parse_marker
        m = format_marker("SCRUM-42", "Verify thing works correctly")
        parsed = parse_marker(m)
        assert parsed is not None
        key, h = parsed
        assert key == "SCRUM-42"
        assert len(h) == 8

    def test_parse_rejects_non_marker(self):
        from agents.agent2_coder import parse_marker
        assert parse_marker("Scenario: foo") is None
        assert parse_marker("# random comment") is None
        assert parse_marker("# JIRA: SCRUM-1") is None  # no hash → reject
        assert parse_marker("") is None
        assert parse_marker(None) is None

    def test_parse_tolerates_leading_whitespace(self):
        from agents.agent2_coder import parse_marker
        result = parse_marker("    # JIRA: SCRUM-7 (hash: abcd1234)")
        assert result == ("SCRUM-7", "abcd1234")


# ─────────────────────────────────────────────────────────────────
# Feature file surgeon
# ─────────────────────────────────────────────────────────────────
class TestFeatureFileSurgeon:
    SAMPLE_FILE = (
        "Feature: Logout\n"
        "\n"
        "  Background:\n"
        "    Given the site is reachable\n"
        "\n"
        "  # JIRA: SCRUM-21 (hash: aaaaaaaa)\n"
        "  Scenario: Successful logout\n"
        "    When I click logout\n"
        "    Then I am redirected\n"
        "\n"
        "  # JIRA: SCRUM-22 (hash: bbbbbbbb)\n"
        "  Scenario: Logout clears session\n"
        "    When I logout\n"
        "    Then session is empty\n"
    )

    def test_parse_extracts_blocks(self):
        from agents.agent2_coder import parse_feature_file
        _header, blocks = parse_feature_file(self.SAMPLE_FILE)
        kinds = [b.kind for b in blocks]
        assert kinds == ["background", "scenario", "scenario"]
        assert blocks[1].jira_key == "SCRUM-21"
        assert blocks[2].jira_key == "SCRUM-22"

    def test_parse_roundtrip_is_lossless(self):
        from agents.agent2_coder import parse_feature_file
        header, blocks = parse_feature_file(self.SAMPLE_FILE)
        reassembled = "".join(header) + "".join(b.text() for b in blocks)
        assert reassembled == self.SAMPLE_FILE

    def test_classify_detects_unchanged_modified_new_orphan(self):
        from agents.agent2_coder import classify_test_cases, format_marker

        desc_21 = "the SCRUM-21 description"
        desc_22_old = "the OLD SCRUM-22 description"
        desc_22_new = "the NEW SCRUM-22 description"

        file_content = (
            "Feature: x\n\n"
            f"  {format_marker('SCRUM-21', desc_21)}\n"
            "  Scenario: a\n    Then a\n\n"
            f"  {format_marker('SCRUM-22', desc_22_old)}\n"
            "  Scenario: b\n    Then b\n\n"
            f"  {format_marker('SCRUM-99', 'old orphan')}\n"
            "  Scenario: c\n    Then c\n"
        )
        current_jira = [
            {"key": "SCRUM-21", "summary": "a", "description": desc_21},
            {"key": "SCRUM-22", "summary": "b", "description": desc_22_new},
            {"key": "SCRUM-50", "summary": "new", "description": "brand new"},
        ]
        result = classify_test_cases(current_jira, file_content)
        assert [tc["key"] for tc in result["unchanged"]] == ["SCRUM-21"]
        assert [tc["key"] for tc in result["modified"]] == ["SCRUM-22"]
        assert [tc["key"] for tc in result["new"]] == ["SCRUM-50"]
        assert result["orphan_keys"] == ["SCRUM-99"]

    def test_classify_on_empty_file_marks_all_new(self):
        from agents.agent2_coder import classify_test_cases
        result = classify_test_cases(
            [{"key": "SCRUM-1", "summary": "x", "description": "y"}],
            "",
        )
        assert [tc["key"] for tc in result["new"]] == ["SCRUM-1"]
        assert result["unchanged"] == []
        assert result["modified"] == []
        assert result["orphan_keys"] == []

    def test_splice_replaces_only_target(self):
        from agents.agent2_coder import (
            splice_scenario, format_marker, compute_description_hash
        )
        new_desc = "rewritten description"
        replacement = (
            f"  {format_marker('SCRUM-22', new_desc)}\n"
            "  Scenario: Logout clears session (NEW)\n"
            "    When I sign out\n"
            "    Then session is destroyed\n"
        )
        out = splice_scenario(
            self.SAMPLE_FILE, "SCRUM-22", replacement,
            compute_description_hash(new_desc),
        )
        assert "Logout clears session (NEW)" in out
        assert "Then session is empty" not in out  # old scenario gone
        assert "Successful logout" in out          # untouched scenario preserved
        assert "When I click logout" in out

    def test_splice_refuses_mismatched_marker(self):
        from agents.agent2_coder import splice_scenario, format_marker
        bogus = (
            f"  {format_marker('SCRUM-77', 'whatever')}\n"
            "  Scenario: liar\n    Then x\n"
        )
        with pytest.raises(ValueError, match="orphan"):
            splice_scenario(self.SAMPLE_FILE, "SCRUM-22", bogus, "deadbeef")

    def test_splice_with_missing_target_returns_original(self):
        from agents.agent2_coder import (
            splice_scenario, format_marker, compute_description_hash
        )
        replacement = (
            f"  {format_marker('SCRUM-999', 'x')}\n"
            "  Scenario: nope\n    Then x\n"
        )
        out = splice_scenario(
            self.SAMPLE_FILE, "SCRUM-999", replacement,
            compute_description_hash("x"),
        )
        assert out == self.SAMPLE_FILE

    def test_remove_takes_out_only_target(self):
        from agents.agent2_coder import remove_scenario
        out = remove_scenario(self.SAMPLE_FILE, "SCRUM-22")
        assert "Logout clears session" not in out
        assert "Successful logout" in out

    def test_remove_missing_key_is_noop(self):
        from agents.agent2_coder import remove_scenario
        out = remove_scenario(self.SAMPLE_FILE, "SCRUM-999")
        assert out == self.SAMPLE_FILE

    def test_append_adds_to_end(self):
        from agents.agent2_coder import append_scenario, format_marker
        new_block = (
            f"  {format_marker('SCRUM-50', 'new test')}\n"
            "  Scenario: Brand new\n    Then it works\n"
        )
        out = append_scenario(self.SAMPLE_FILE, new_block)
        assert "Brand new" in out
        assert "Successful logout" in out
        assert "Logout clears session" in out


# ─────────────────────────────────────────────────────────────────
# Marker injection helper
# ─────────────────────────────────────────────────────────────────
class TestMarkerInjection:
    SCENARIOS_WITHOUT_MARKERS = (
        "Feature: Test\n"
        "\n"
        "  Scenario: First scenario title\n"
        "    Given x\n"
        "    Then y\n"
        "\n"
        "  Scenario: Second scenario title\n"
        "    Given a\n"
        "    Then b\n"
    )

    TEST_CASES = [
        {"key": "SCRUM-1", "summary": "first scenario title", "description": "first desc"},
        {"key": "SCRUM-2", "summary": "second scenario title", "description": "second desc"},
    ]

    def test_injects_markers_on_unmarkered_file(self):
        from agents.agent2_coder import _inject_markers_into_feature
        title_to_tc = {tc["summary"].lower(): tc for tc in self.TEST_CASES}
        out = _inject_markers_into_feature(self.SCENARIOS_WITHOUT_MARKERS, title_to_tc)
        assert "# JIRA: SCRUM-1" in out
        assert "# JIRA: SCRUM-2" in out

    def test_marker_appears_above_scenario_with_same_indent(self):
        from agents.agent2_coder import _inject_markers_into_feature
        title_to_tc = {tc["summary"].lower(): tc for tc in self.TEST_CASES}
        out = _inject_markers_into_feature(self.SCENARIOS_WITHOUT_MARKERS, title_to_tc)
        lines = out.splitlines()
        for i, line in enumerate(lines):
            if "Scenario: First" in line:
                indent = line[: len(line) - len(line.lstrip())]
                assert lines[i - 1].startswith(f"{indent}# JIRA: SCRUM-1"), \
                    f"Expected marker before scenario; got: {lines[i-1]!r}"
                break
        else:
            pytest.fail("First scenario not found in output")

    def test_idempotent_existing_markers_refreshed_not_duplicated(self):
        from agents.agent2_coder import (
            _inject_markers_into_feature, format_marker, compute_description_hash,
        )
        content = (
            "Feature: T\n\n"
            f"  {format_marker('SCRUM-1', 'OLD description')}\n"
            "  Scenario: first scenario title\n    Then x\n"
        )
        title_to_tc = {"first scenario title": {
            "key": "SCRUM-1", "summary": "first scenario title",
            "description": "NEW description"
        }}
        out = _inject_markers_into_feature(content, title_to_tc)
        # Marker refreshed, not duplicated
        assert out.count("# JIRA: SCRUM-1") == 1
        old_h = compute_description_hash("OLD description")
        new_h = compute_description_hash("NEW description")
        assert new_h in out
        assert old_h not in out

    def test_unmatched_scenario_left_unmarkered(self):
        from agents.agent2_coder import _inject_markers_into_feature
        content = (
            "Feature: T\n\n"
            "  Scenario: A scenario the LLM invented\n    Then x\n"
        )
        title_to_tc = {"completely different title": {
            "key": "SCRUM-99", "summary": "completely different title", "description": "z"
        }}
        out = _inject_markers_into_feature(content, title_to_tc)
        assert "# JIRA:" not in out

    def test_non_feature_files_passed_through(self):
        from agents.agent2_coder import _ensure_jira_markers_on_feature_files
        from agents.schemas import GeneratedFile
        gf = GeneratedFile(
            file_path="pages/inventory_page.py",
            content="class Foo: pass",
            is_new_file=True,
            purpose="x",
        )
        out = _ensure_jira_markers_on_feature_files([gf], self.TEST_CASES)
        assert out[0].content == "class Foo: pass"
        assert out[0].file_path == "pages/inventory_page.py"