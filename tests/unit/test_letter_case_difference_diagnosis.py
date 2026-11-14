"""A text that differs only in letter case is diagnosed as such, and the
generation rules say to compare displayed text case-insensitively.
"""

from __future__ import annotations


def test_a_case_only_difference_is_diagnosed():
    from core.failure_diagnosis import diagnose
    d = diagnose("AssertionError: Expected heading 'Order History' in 'ORDER HISTORY'")
    assert d.label == "letter case" and "casefold" in d.remedy
    assert diagnose("AssertionError: Expected heading 'Order History' in 'Settings'").label != "letter case"
    assert diagnose("assert 2 == 1").label == "count assertion", "other readings unchanged"


def test_the_generation_rules_say_to_compare_displayed_text_case_insensitively():
    import agents.agent2_coder as a2
    text = (a2.PROMPTS_DIR / "agent2_coder_generate.md").read_text(encoding="utf-8")
    assert "letter case" in text and "casefold" in text
