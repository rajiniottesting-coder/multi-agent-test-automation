"""A spliced or appended scenario's `# JIRA:` marker sits where every
generated marker sits: below the scenario's tags, indented like the scenario.
"""


ORIGINAL = ("Feature: F\n\n  @smoke @x\n  # JIRA: AB-1 (hash: 11111111) owner: AB-9\n"
            "  Scenario: old\n    Given a\n\n"
            "  # JIRA: AB-2 (hash: 22222222) owner: AB-9\n  Scenario: two\n    Given b\n")
MODEL = ("# JIRA: AB-1 (hash: 33333333) owner: AB-9 impacted-by: AB-5\n"
         "  Scenario: new\n    Given c\n")


def test_a_spliced_marker_sits_below_the_tags_indented_like_the_scenario():
    from agents.agent2_coder import parse_feature_file, splice_scenario
    out = splice_scenario(ORIGINAL, "AB-1", MODEL, "33333333")
    assert ("  @smoke @x\n  # JIRA: AB-1 (hash: 33333333) owner: AB-9 impacted-by: AB-5\n"
            "  Scenario: new\n") in out
    _h, blocks = parse_feature_file(out)
    assert [b.jira_key for b in blocks if b.kind == "scenario"] == ["AB-1", "AB-2"]


def test_an_appended_marker_is_indented_like_the_scenario():
    from agents.agent2_coder import append_scenario
    out = append_scenario(ORIGINAL, "# JIRA: AB-3 (hash: 44444444) owner: AB-5\n"
                                    "  Scenario: three\n    Given d\n")
    assert out.endswith("\n  # JIRA: AB-3 (hash: 44444444) owner: AB-5\n"
                        "  Scenario: three\n    Given d\n")
