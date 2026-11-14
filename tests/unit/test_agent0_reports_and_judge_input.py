"""What Agent 0 writes and reads: a code-change report reads as Markdown on
the pull request, a report with nothing affected has no empty table, and the
judge sees each element's selector.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_the_pull_request_copy_is_markdown():
    from agents.agent0_impact import for_pull_request
    body = ("[agent0:report] Impact of PR #1 | hash: h | graph: g\n\n||Tier||Test||\n|review|AB-1|\n\n"
            "note\n{code:json}\n{\"a\": \"{code}\"}\n{code}")
    out = for_pull_request(body)
    assert out.splitlines()[0] == body.splitlines()[0]
    assert "| Tier | Test |\n|---|---|\n|review|AB-1|" in out
    assert "```json" in out and '{"a": "{code}"}' in out and "{code:json}" not in out
    assert out.rstrip().endswith("</details>")


def test_a_report_with_nothing_affected_has_no_empty_table():
    """PR #287 (4 Nov): "Affected: 0" was followed by a table header with no rows."""
    from agents.agent0_impact import _render_report
    report = {"content_hash": "h", "graph_sha": "g", "no_component": False, "ranked": [],
              "unaffected": [], "not_judged": [], "by_owner": {},
              "seeds": {"elements": [], "methods": [], "pages": [], "dropped": []}}
    empty = _render_report(report, "Impact of PR #1 (code change)")
    assert "Affected: 0" in empty and "||Tier||" not in empty
    report["ranked"] = [{"tier": "review", "score": 0.4, "key": "AB-1", "owner": "AB-2",
                         "title": "t", "evidence": "e"}]
    assert "||Tier||Score||Test||Owner||Scenario||Evidence||" in _render_report(report, "x")


def test_an_element_path_carries_its_selector():
    from core import impact_analysis as ia
    from core.impact_graph import ImpactGraph, ScenarioNode
    s = ScenarioNode(file="features/f.feature", title="t", jira_key="AB-2", steps=(),
                     step_definitions=(), methods=frozenset(), shared_methods=frozenset(),
                     elements=frozenset({("p", "go_button")}), pages=frozenset({"p"}),
                     components=frozenset())
    g = ImpactGraph(scenarios=[s], selectors={("p", "go_button"): "button.go"})
    (c,) = ia.structural_candidates(g, ia.Seeds(elements={("p", "go_button")}))
    assert c.paths[0]["text"].startswith("element p:go_button (selector `button.go`) <- ")
    prompt = (ROOT / "prompts" / "agent0_adjudicate.md").read_text(encoding="utf-8")
    assert "Finding an element is not reading its text" in prompt
