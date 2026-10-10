"""
Unit tests for block ownership in feature files (Agent 0 design, step A2).

A scenario's tags, comments and JIRA marker sit ABOVE its keyword, and a
Scenario Outline's Examples tables sit BELOW its steps. The parser must
attach all of them to the scenario they describe, so that removing or
replacing one scenario never moves a tag onto a neighbour, drops a
neighbour's tag, leaves a dangling tag at the end of the file, or leaves
an Examples table behind.
"""

import pytest

from agents.agent2_coder import (
    append_scenario,
    classify_test_cases,
    parse_feature_file,
    remove_scenario,
    splice_scenario,
)


THREE_TAGGED = (
    "@login\n"
    "Feature: Login\n"
    "\n"
    "  Background:\n"
    "    Given the site is reachable\n"
    "\n"
    "  @smoke\n"
    "  # JIRA: AB-1 (hash: aaaaaaaa)\n"
    "  Scenario: Valid login\n"
    "    When I log in\n"
    "    Then I see the dashboard\n"
    "\n"
    "  # JIRA: AB-2 (hash: bbbbbbbb)\n"
    "  @negative\n"
    "  Scenario: Wrong password\n"
    "    When I log in with a wrong password\n"
    "    Then I see an error\n"
    "\n"
    "  @edge @slow\n"
    "  # JIRA: AB-3 (hash: cccccccc)\n"
    "  Scenario: Locked account\n"
    "    When I log in as a locked user\n"
    "    Then I see the locked message\n"
)


def _block(blocks, key):
    return next(b for b in blocks if b.jira_key == key)


def _tags_above(content, title):
    """Tag lines in the run directly above `Scenario: <title>`."""
    lines = content.splitlines()
    idx = next(i for i, l in enumerate(lines) if l.strip().endswith(title)
               and "Scenario" in l)
    tags = []
    j = idx - 1
    while j >= 0 and lines[j].strip().startswith(("@", "#")):
        if lines[j].strip().startswith("@"):
            tags.append(lines[j].strip())
        j -= 1
    return list(reversed(tags))


def _replacement(key, title, step="Then it works"):
    return (
        f"  # JIRA: {key} (hash: dddddddd)\n"
        f"  Scenario: {title}\n"
        f"    {step}\n"
    )


# ─────────────────────────────────────────────────────────────────
# Parsing
# ─────────────────────────────────────────────────────────────────
class TestParseOwnership:
    def test_each_scenario_owns_its_tags_and_marker(self):
        _h, blocks = parse_feature_file(THREE_TAGGED)
        assert [b.kind for b in blocks] == ["background", "scenario", "scenario", "scenario"]
        assert "@smoke" in _block(blocks, "AB-1").text()
        assert "@negative" in _block(blocks, "AB-2").text()
        assert "@edge @slow" in _block(blocks, "AB-3").text()
        # No scenario carries a neighbour's tag
        assert "@negative" not in _block(blocks, "AB-1").text()
        assert "@edge" not in _block(blocks, "AB-2").text()

    def test_feature_level_tags_stay_in_header(self):
        header, _blocks = parse_feature_file(THREE_TAGGED)
        assert "".join(header).startswith("@login\nFeature: Login")

    def test_marker_found_when_tag_sits_between_marker_and_keyword(self):
        _h, blocks = parse_feature_file(THREE_TAGGED)
        assert _block(blocks, "AB-2").jira_hash == "bbbbbbbb"

    def test_first_scenario_takes_its_tags_from_the_header(self):
        content = (
            "Feature: X\n"
            "\n"
            "  @smoke\n"
            "  # JIRA: AB-1 (hash: aaaaaaaa)\n"
            "  Scenario: one\n"
            "    Then a\n"
        )
        header, blocks = parse_feature_file(content)
        assert "".join(header) == "Feature: X\n\n"
        assert blocks[0].lines[0].strip() == "@smoke"
        assert blocks[0].jira_key == "AB-1"

    def test_roundtrip_is_lossless(self):
        header, blocks = parse_feature_file(THREE_TAGGED)
        assert "".join(header) + "".join(b.text() for b in blocks) == THREE_TAGGED

    def test_commented_out_step_stays_with_its_scenario(self):
        content = (
            "Feature: X\n"
            "\n"
            "  # JIRA: AB-1 (hash: aaaaaaaa)\n"
            "  Scenario: one\n"
            "    Given a\n"
            "    # Then b (disabled)\n"
            "  # JIRA: AB-2 (hash: bbbbbbbb)\n"
            "  Scenario: two\n"
            "    Then c\n"
        )
        _h, blocks = parse_feature_file(content)
        assert "# Then b (disabled)" in _block(blocks, "AB-1").text()
        assert "# Then b (disabled)" not in _block(blocks, "AB-2").text()

    def test_examples_belong_to_their_outline(self):
        content = (
            "Feature: X\n"
            "\n"
            "  @data\n"
            "  # JIRA: AB-1 (hash: aaaaaaaa)\n"
            "  Scenario Outline: many\n"
            "    When I enter <value>\n"
            "    Then I see <result>\n"
            "\n"
            "    @fast\n"
            "    Examples:\n"
            "      | value | result |\n"
            "      | 1     | one    |\n"
            "\n"
            "  # JIRA: AB-2 (hash: bbbbbbbb)\n"
            "  Scenario: single\n"
            "    Then c\n"
        )
        header, blocks = parse_feature_file(content)
        assert [b.kind for b in blocks] == ["scenario", "scenario"]
        outline = _block(blocks, "AB-1").text()
        assert "Examples:" in outline and "| 1     | one    |" in outline
        assert "@fast" in outline
        assert "".join(header) + "".join(b.text() for b in blocks) == content

    def test_existing_untagged_layout_still_parses(self):
        content = (
            "Feature: Logout\n\n"
            "  # JIRA: SCRUM-21 (hash: aaaaaaaa)\n"
            "  Scenario: a\n    Then a\n\n"
            "  # JIRA: SCRUM-22 (hash: bbbbbbbb)\n"
            "  Scenario: b\n    Then b\n"
        )
        result = classify_test_cases(
            [{"key": "SCRUM-21", "description": "x"}], content
        )
        assert result["orphan_keys"] == ["SCRUM-22"]


# ─────────────────────────────────────────────────────────────────
# Removing
# ─────────────────────────────────────────────────────────────────
class TestRemoveKeepsNeighboursIntact:
    def test_remove_first(self):
        out = remove_scenario(THREE_TAGGED, "AB-1")
        assert "Valid login" not in out and "@smoke" not in out
        assert _tags_above(out, "Wrong password") == ["@negative"]
        assert _tags_above(out, "Locked account") == ["@edge @slow"]
        assert "Background:" in out

    def test_remove_middle(self):
        out = remove_scenario(THREE_TAGGED, "AB-2")
        assert "@negative" not in out
        assert _tags_above(out, "Valid login") == ["@smoke"]
        assert _tags_above(out, "Locked account") == ["@edge @slow"]

    def test_remove_last_leaves_no_dangling_tag(self):
        out = remove_scenario(THREE_TAGGED, "AB-3")
        assert "@edge" not in out
        assert out.endswith("    Then I see an error\n")
        assert _tags_above(out, "Wrong password") == ["@negative"]

    def test_remove_outline_takes_its_examples(self):
        content = (
            "Feature: X\n\n"
            "  # JIRA: AB-1 (hash: aaaaaaaa)\n"
            "  Scenario Outline: many\n"
            "    When I enter <value>\n\n"
            "    Examples:\n"
            "      | value |\n"
            "      | 1     |\n\n"
            "  # JIRA: AB-2 (hash: bbbbbbbb)\n"
            "  Scenario: single\n"
            "    Then c\n"
        )
        out = remove_scenario(content, "AB-1")
        assert "Examples:" not in out and "| value |" not in out
        assert "Scenario: single" in out

    def test_remove_all_scenarios_keeps_header(self):
        out = remove_scenario(remove_scenario(remove_scenario(
            THREE_TAGGED, "AB-1"), "AB-2"), "AB-3")
        assert out.startswith("@login\nFeature: Login")
        assert "Scenario" not in out and "@" not in out.replace("@login", "")


# ─────────────────────────────────────────────────────────────────
# Splicing
# ─────────────────────────────────────────────────────────────────
class TestSpliceKeepsTags:
    def test_splice_middle_keeps_neighbour_tags(self):
        out = splice_scenario(
            THREE_TAGGED, "AB-2", _replacement("AB-2", "Wrong password v2"), "dddddddd"
        )
        assert _tags_above(out, "Valid login") == ["@smoke"]
        assert _tags_above(out, "Locked account") == ["@edge @slow"]
        assert "Then I see an error" not in out

    def test_splice_keeps_own_tags_when_replacement_has_none(self):
        out = splice_scenario(
            THREE_TAGGED, "AB-2", _replacement("AB-2", "Wrong password v2"), "dddddddd"
        )
        assert _tags_above(out, "Wrong password v2") == ["@negative"]
        _h, blocks = parse_feature_file(out)
        assert _block(blocks, "AB-2").jira_hash == "dddddddd"

    def test_splice_uses_replacement_tags_when_given(self):
        replacement = "  @regression\n" + _replacement("AB-2", "Wrong password v2")
        out = splice_scenario(THREE_TAGGED, "AB-2", replacement, "dddddddd")
        assert _tags_above(out, "Wrong password v2") == ["@regression"]
        assert "@negative" not in out

    def test_splice_keeps_blank_line_before_next_scenario(self):
        out = splice_scenario(
            THREE_TAGGED, "AB-2", _replacement("AB-2", "Wrong password v2"), "dddddddd"
        )
        assert "    Then it works\n\n  @edge @slow\n" in out

    def test_splice_outline_replaces_its_examples(self):
        content = (
            "Feature: X\n\n"
            "  # JIRA: AB-1 (hash: aaaaaaaa)\n"
            "  Scenario Outline: many\n"
            "    When I enter <value>\n\n"
            "    Examples:\n"
            "      | value |\n"
            "      | old   |\n"
        )
        replacement = (
            "  # JIRA: AB-1 (hash: dddddddd)\n"
            "  Scenario Outline: many\n"
            "    When I enter <value>\n\n"
            "    Examples:\n"
            "      | value |\n"
            "      | new   |\n"
        )
        out = splice_scenario(content, "AB-1", replacement, "dddddddd")
        assert out.count("Examples:") == 1
        assert "| old   |" not in out and "| new   |" in out

    def test_splice_without_trailing_newline(self):
        replacement = _replacement("AB-3", "Locked v2").rstrip("\n")
        out = splice_scenario(THREE_TAGGED, "AB-3", replacement, "dddddddd")
        assert out.endswith("    Then it works\n")
        assert _tags_above(out, "Locked v2") == ["@edge @slow"]

    def test_splice_rejects_mismatched_marker(self):
        with pytest.raises(ValueError, match="orphan"):
            splice_scenario(
                THREE_TAGGED, "AB-2", _replacement("AB-9", "liar"), "dddddddd"
            )


class TestAppendThenRemove:
    def test_appended_tagged_scenario_is_removable(self):
        new = "  @new\n" + _replacement("AB-4", "Fresh")
        out = append_scenario(THREE_TAGGED, new)
        _h, blocks = parse_feature_file(out)
        assert "@new" in _block(blocks, "AB-4").text()
        back = remove_scenario(out, "AB-4")
        assert "@new" not in back and "Fresh" not in back
        assert _tags_above(back, "Locked account") == ["@edge @slow"]


# ─────────────────────────────────────────────────────────────────
# Marker injection sees markers above tags
# ─────────────────────────────────────────────────────────────────
class TestInjectionReadsWholePreamble:
    def test_marker_above_tag_is_refreshed_not_doubled(self):
        from agents.agent2_coder import _inject_markers_into_feature, format_marker
        content = (
            "Feature: X\n\n"
            "  # JIRA: AB-1 (hash: 00000000)\n"
            "  @smoke\n"
            "  Scenario: Valid login\n"
            "    Then a\n"
        )
        out = _inject_markers_into_feature(
            content, [{"key": "AB-1", "summary": "Valid login", "description": "d"}]
        )
        assert out.count("# JIRA: AB-1") == 1
        assert format_marker("AB-1", "d") in out

    def test_marker_inserted_below_tags_when_missing(self):
        from agents.agent2_coder import _inject_markers_into_feature
        content = (
            "Feature: X\n\n"
            "  @smoke\n"
            "  Scenario: Valid login\n"
            "    Then a\n"
        )
        out = _inject_markers_into_feature(
            content, [{"key": "AB-1", "summary": "Valid login", "description": "d"}]
        )
        _h, blocks = parse_feature_file(out)
        assert blocks[0].jira_key == "AB-1"
        assert "@smoke" in blocks[0].text()


# ─────────────────────────────────────────────────────────────────
# splice_scenario checks the hash it is given (Agent 3 review of #130)
# ─────────────────────────────────────────────────────────────────
def test_splice_warns_when_the_marker_hash_is_not_the_expected_one(caplog):
    import logging
    text = _replacement("AB-2", "Wrong password v2")            # marker hash: dddddddd
    with caplog.at_level(logging.WARNING):
        ok = splice_scenario(THREE_TAGGED, "AB-2", text, "dddddddd")
    assert "was not kept as given" not in caplog.text
    with caplog.at_level(logging.WARNING):
        warned = splice_scenario(THREE_TAGGED, "AB-2", text, "12345678")
    assert "AB-2" in caplog.text and "was not kept as given" in caplog.text
    assert warned == ok                                         # behaviour unchanged
