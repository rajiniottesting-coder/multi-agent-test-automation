"""A repair that never RAN is not a repair that failed.

WHAT HAPPENED
    One validator error, one repair attempt, and this in the log:

        Repair attempt for 'pages/<x>.py' failed: LLM API rate limit / quota
        exhausted for model '<model>'
        Repair attempt 1 changed nothing - the same 1 error(s) came back
        verbatim. Abandoning repair

    The call was refused before it reached a model. The broad `except
    Exception` swallowed that, the loop carried on, the errors were of course
    unchanged, and the no-progress guard concluded the model was not
    converging - blaming a model that had never been asked.

    The story was reported as unbuildable when nothing about it had been
    tried, and the honest remedy - wait for the limit to reset and re-run - was
    nowhere in the output.
"""
import ast
from pathlib import Path

_AGENT2 = Path(__file__).resolve().parents[2] / "agents" / "agent2_coder.py"


def _handler_order(source: str, needle: str) -> list:
    """The except-clause names, in order, for the try that contains `needle`."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        if needle not in ast.get_source_segment(source, node) or "":
            continue
        names = []
        for h in node.handlers:
            if h.type is None:
                names.append("bare")
            elif isinstance(h.type, ast.Name):
                names.append(h.type.id)
            elif isinstance(h.type, ast.Tuple):
                names.extend(e.id for e in h.type.elts if isinstance(e, ast.Name))
        if names:
            return names
    return []


def test_quota_exhaustion_is_caught_before_the_broad_handler():
    """Ordering is the whole fix. `except Exception` first would swallow it
    again, and Python matches handlers top to bottom."""
    source = _AGENT2.read_text(encoding="utf-8")
    order = _handler_order(source, "Repair attempt for")
    assert "QuotaExhaustedError" in order, \
        "the repair loop does not distinguish a refused call from a failed one"
    assert order.index("QuotaExhaustedError") < order.index("Exception"), \
        "a broad handler placed first swallows the specific one below it"


def test_the_quota_branch_re_raises():
    """Continuing would leave the errors unchanged and hand the no-progress
    guard a verdict it has no business reaching."""
    source = _AGENT2.read_text(encoding="utf-8")
    start = source.index("except QuotaExhaustedError:")
    branch = source[start:start + 1200]
    assert "raise" in branch, \
        "swallowing this is what produced the wrong diagnosis"


def test_the_message_names_the_real_remedy():
    source = _AGENT2.read_text(encoding="utf-8")
    start = source.index("except QuotaExhaustedError:")
    branch = source[start:start + 1200].lower()
    assert "infrastructure" in branch, \
        "say plainly that the code has not been judged"
    assert "re-run" in branch, \
        "the remedy is to re-run once the limit resets, not to change the story"