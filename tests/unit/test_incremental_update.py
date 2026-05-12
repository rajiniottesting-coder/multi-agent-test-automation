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
    """Tests for `_inject_markers_into_feature` and `_ensure_jira_markers_on_feature_files`.

    These cover the post-v12b-bug-fix behavior:
      - Order-based positional pairing (robust to LLM paraphrasing)
      - Token-similarity safety check (≥ 0.3) for new injections
      - Existing markers refreshed by their existing key (reorder-safe)
    """

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
        out = _inject_markers_into_feature(self.SCENARIOS_WITHOUT_MARKERS, self.TEST_CASES)
        assert "# JIRA: SCRUM-1" in out
        assert "# JIRA: SCRUM-2" in out

    def test_marker_appears_above_scenario_with_same_indent(self):
        from agents.agent2_coder import _inject_markers_into_feature
        out = _inject_markers_into_feature(self.SCENARIOS_WITHOUT_MARKERS, self.TEST_CASES)
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
        """Existing markers get hash refreshed, never duplicated."""
        from agents.agent2_coder import (
            _inject_markers_into_feature, format_marker, compute_description_hash,
        )
        content = (
            "Feature: T\n\n"
            f"  {format_marker('SCRUM-1', 'OLD description')}\n"
            "  Scenario: first scenario title\n    Then x\n"
        )
        test_cases = [
            {"key": "SCRUM-1", "summary": "first scenario title", "description": "NEW description"}
        ]
        out = _inject_markers_into_feature(content, test_cases)
        # Marker refreshed, not duplicated
        assert out.count("# JIRA: SCRUM-1") == 1
        old_h = compute_description_hash("OLD description")
        new_h = compute_description_hash("NEW description")
        assert new_h in out
        assert old_h not in out

    def test_unmatched_scenario_left_unmarkered_when_multiple_pairs(self):
        """With multiple scenarios, low title-similarity skips that pair safely."""
        from agents.agent2_coder import _inject_markers_into_feature
        content = (
            "Feature: T\n\n"
            "  Scenario: complete nonsense xyz qrt\n    Then x\n"
            "\n"
            "  Scenario: totally unrelated foo bar baz\n    Then y\n"
        )
        # Test cases whose summaries don't match scenario titles at all
        test_cases = [
            {"key": "SCRUM-99", "summary": "user logs into the system", "description": "z"},
            {"key": "SCRUM-100", "summary": "checkout flow completes successfully", "description": "z"},
        ]
        out = _inject_markers_into_feature(content, test_cases)
        # With 2 pairs of low similarity, both skip rather than mislabel
        assert "# JIRA:" not in out

    def test_pro_paraphrasing_still_matches_via_token_overlap(self):
        """REGRESSION: Pro adds 'Verify' prefix and reorders words. Old code
        used exact-string match and silently failed. New code uses token
        overlap and succeeds."""
        from agents.agent2_coder import _inject_markers_into_feature
        # Pro's scenarios (with "Verify" prefix, reworded)
        content = (
            "Feature: T\n\n"
            "  Scenario: Verify successful logout from inventory page\n    Then x\n"
            "\n"
            "  Scenario: User cannot access inventory page once logged out\n    Then y\n"
        )
        # Jira summaries (the originals)
        test_cases = [
            {"key": "SCRUM-21", "summary": "Successful logout from the inventory page", "description": "a"},
            {"key": "SCRUM-22", "summary": "User cannot access inventory page after logging out", "description": "b"},
        ]
        out = _inject_markers_into_feature(content, test_cases)
        assert "# JIRA: SCRUM-21" in out, "Paraphrased title should still match SCRUM-21 positionally"
        assert "# JIRA: SCRUM-22" in out, "Paraphrased title should still match SCRUM-22 positionally"

    def test_single_pair_always_accepted_no_similarity_gate(self):
        """If there's only one scenario and one test case, accept the pairing
        unconditionally — there's no ambiguity to guard against."""
        from agents.agent2_coder import _inject_markers_into_feature
        content = "Feature: T\n\n  Scenario: complete nonsense\n    Then x\n"
        test_cases = [
            {"key": "SCRUM-1", "summary": "completely different summary", "description": "z"}
        ]
        out = _inject_markers_into_feature(content, test_cases)
        assert "# JIRA: SCRUM-1" in out

    def test_count_mismatch_uses_min_with_warning(self):
        """If scenario count != test case count, pair the first min(N, M)."""
        from agents.agent2_coder import _inject_markers_into_feature
        # 3 scenarios but only 2 test cases
        content = (
            "Feature: T\n\n"
            "  Scenario: logout flow\n    Then x\n\n"
            "  Scenario: session cleared\n    Then y\n\n"
            "  Scenario: extra scenario the llm invented\n    Then z\n"
        )
        test_cases = [
            {"key": "SCRUM-1", "summary": "logout flow", "description": "a"},
            {"key": "SCRUM-2", "summary": "session cleared", "description": "b"},
        ]
        out = _inject_markers_into_feature(content, test_cases)
        assert "# JIRA: SCRUM-1" in out
        assert "# JIRA: SCRUM-2" in out
        # Third scenario must stay unmarkered (no test case for it)
        scenario_3_line = "Scenario: extra scenario"
        before_s3 = out[: out.find(scenario_3_line)]
        # The JIRA line immediately preceding "Scenario: extra" should NOT be a marker for it
        assert out.count("# JIRA:") == 2

    def test_existing_marker_preserves_its_key_not_position(self):
        """REGRESSION-PREP: If a scenario already carries marker SCRUM-22,
        and test_cases are provided in order [SCRUM-21, SCRUM-22, SCRUM-23],
        the marker should stay SCRUM-22 (refresh hash) even if the scenario
        appears at position 0. Protects against ai-update reorders relabelling."""
        from agents.agent2_coder import _inject_markers_into_feature, format_marker
        content = (
            "Feature: T\n\n"
            f"  {format_marker('SCRUM-22', 'old desc')}\n"
            "  Scenario: session cleared\n    Then x\n\n"
            "  Scenario: logout flow\n    Then y\n"
        )
        test_cases = [
            # Note: SCRUM-21 listed FIRST positionally, but the scenario
            # already says SCRUM-22 via its marker. We expect SCRUM-22 to
            # stick.
            {"key": "SCRUM-21", "summary": "logout flow", "description": "a"},
            {"key": "SCRUM-22", "summary": "session cleared", "description": "new desc"},
        ]
        out = _inject_markers_into_feature(content, test_cases)
        # SCRUM-22 still attached to "session cleared", hash refreshed
        idx_s22 = out.find("Scenario: session cleared")
        marker_region = out[:idx_s22]
        assert "# JIRA: SCRUM-22" in marker_region
        assert "# JIRA: SCRUM-21" not in marker_region

    def test_orphan_marker_left_alone(self):
        """If a scenario carries marker SCRUM-999 but SCRUM-999 isn't in
        test_cases (deleted from Jira), the orphan marker stays — let
        ai-update's remove_scenario handle cleanup."""
        from agents.agent2_coder import _inject_markers_into_feature, format_marker
        content = (
            "Feature: T\n\n"
            f"  {format_marker('SCRUM-999', 'orphan')}\n"
            "  Scenario: orphan scenario\n    Then x\n"
        )
        test_cases = [
            {"key": "SCRUM-1", "summary": "different one", "description": "a"}
        ]
        out = _inject_markers_into_feature(content, test_cases)
        # Orphan stays — ai-update flow handles orphan cleanup, not injection
        assert "# JIRA: SCRUM-999" in out

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

    def test_title_similarity_token_overlap(self):
        """Direct unit test for the similarity helper."""
        from agents.agent2_coder import _title_similarity
        # Identical content → high similarity
        assert _title_similarity("logout from inventory", "logout from inventory") > 0.9
        # Paraphrased but same content words → still good
        assert _title_similarity(
            "Verify successful logout from inventory page",
            "Successful logout from the inventory page"
        ) > 0.5
        # Completely different → low
        assert _title_similarity("user login flow", "checkout payment") < 0.2
        # Empty input → 0
        assert _title_similarity("", "anything") == 0.0
        assert _title_similarity("anything", "") == 0.0


# ─────────────────────────────────────────────────────────────────
# Markdown fence extraction (v12e — Pro over-escapes backticks)
# ─────────────────────────────────────────────────────────────────
class TestExtractCodeFromResponse:
    """Regression coverage for extract_code_from_response.

    v12e bug: Pro occasionally emits 4+ backticks at fence boundaries
    instead of the canonical 3. The old regex matched the first 3
    backticks against the immediately-adjacent next 3, captured an
    empty body, and returned 1 char. Fix: collapse runs of 4+ backticks
    to exactly 3 before extraction.

    This class doubles as a contract for the extractor — any future
    change to it must keep all these cases passing.
    """

    def test_canonical_three_backtick_fence(self):
        from agents.agent2_coder import extract_code_from_response
        assert extract_code_from_response("```python\nprint('hi')\n```").strip() == "print('hi')"

    def test_six_backtick_fence_normalized(self):
        """REGRESSION (v12e): Pro's six-backtick variant must extract content."""
        from agents.agent2_coder import extract_code_from_response
        result = extract_code_from_response("``````python\nprint('hi')\n``````")
        assert result.strip() == "print('hi')"

    def test_exact_failing_response_from_may12_cron(self):
        """Verbatim Pro response from the production cron failure that
        motivated this fix. The diagnostic captured this; the regression
        test prevents it from ever silently breaking again."""
        from agents.agent2_coder import extract_code_from_response
        response = (
            '``````gherkin\nFeature: User Logout Functionality\n'
            '  Scenario: Successful logout\n    When I log out\n'
            '    Then I should be on the login page\n``````'
        )
        result = extract_code_from_response(response)
        assert "Feature: User Logout Functionality" in result
        assert "Scenario: Successful logout" in result
        assert "```" not in result, "No stray backticks in extracted output"
        assert len(result) > 100, f"Should extract real content, got {len(result)} chars"

    def test_eight_backticks_also_normalized(self):
        """Defensive: even more extreme over-escaping should still work."""
        from agents.agent2_coder import extract_code_from_response
        assert extract_code_from_response("````````py\nx=1\n````````").strip() == "x=1"

    def test_no_fence_returns_bare_text(self):
        """Plain text with no fence is returned trimmed (existing behavior)."""
        from agents.agent2_coder import extract_code_from_response
        result = extract_code_from_response("Feature: T\n  Scenario: S\n    Then x\n")
        assert "Feature: T" in result and "Scenario: S" in result

    def test_no_language_tag(self):
        """Fence without a language tag still works."""
        from agents.agent2_coder import extract_code_from_response
        assert extract_code_from_response("```\nplain\n```").strip() == "plain"

    def test_six_backticks_no_language_tag(self):
        """Combination: over-escaped fence + no language tag."""
        from agents.agent2_coder import extract_code_from_response
        assert extract_code_from_response("``````\ncontent\n``````").strip() == "content"