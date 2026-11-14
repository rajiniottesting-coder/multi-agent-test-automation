"""A context-update rewrite quotes only what the story states (a rewrite with
an invented quote is not applied), and its pull request table shows where
each passage changed.
"""

from __future__ import annotations

from types import SimpleNamespace as NS


def test_a_quote_nobody_stated_is_found():
    from core.context_update import invented_quotes
    story = "The error explains what to do next."
    assert invented_quotes('- Error -> "Wrong input!"', '- Error -> "Wrong input. Try again later."',
                           story) == ["Wrong input. Try again later."]
    assert invented_quotes("a", 'shows "Next step" and `Save` and the user\'s name',
                           story + " Next step Save") == []


def _rw(path, old, new):
    return NS(path=path, old=old, new=new, reason="AC1")


def test_a_rewrite_with_an_invented_quote_is_not_applied():
    from core import context_update as cu
    src = {"prompts/app_context/a.md": "- Error -> \"Wrong input!\"\n"}
    rw = _rw("prompts/app_context/a.md", '- Error -> "Wrong input!"',
             '- Error -> "Wrong input. Try again later."')
    p = cu.propose(src, [], None, [rw], story_text="The error explains what to do next.")
    assert p.empty and "quotes a text the story does not state" in p.dropped[0][2]
    p = cu.propose(src, [], None, [rw], story_text='The error reads "Wrong input. Try again later."')
    assert not p.empty
    assert not cu.propose(src, [], None, [rw]).empty, "no story text: unchanged behaviour"


def test_the_table_cells_open_on_the_first_difference():
    from core import context_update as cu
    before = ("A long opening sentence that stays exactly the same in both versions of the "
              "passage, and then more of it. The ending says three.")
    after = before.replace("three", "four")
    b, a = cu.changed_part(before, after)
    assert b.startswith("…") and b.endswith("three.") and a.endswith("four.")
    assert cu.changed_part("same", "same") == ("same", "same")
    p = cu.Proposal()
    p.rewrites.append({"path": "n.md", "before": before * 3 + " x", "after": before * 3 + " y",
                       "reason": "r"})
    row = next(x for x in cu.render_body("AB-1", p).splitlines() if x.startswith("| `n.md`"))
    assert "x |" in row and "y |" in row
