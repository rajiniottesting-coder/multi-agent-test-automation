"""Every validator error reaches the repair loop, however its rule is worded.

The loop routed only messages of the form `<rule> error in '<path>':`. Two
rules are worded without the word "error" - `Row index used as a cell index
in '<path>' line N:` and `Drifted step wording in '<path>':` - so they were
dropped silently: the file never got a repair attempt, and SCRUM-111 failed at
the final gate on a page-object defect the loop was never shown.
"""
import os
import textwrap
from types import SimpleNamespace

for v in ("OPENAI_API_KEY", "JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN",
          "JIRA_PROJECT_KEY", "GITHUB_TOKEN", "GITHUB_REPO"):
    os.environ.setdefault(v, "stub")

from agents.agent2_coder import (
    _group_validator_errors_by_file,
    _rules_persisting,
)
from validators.method_resolution_validator import (
    validate_row_index_is_not_a_cell_index,
)

ROW = "Row index used as a cell index in 'pages/widget_page.py' line 9: `i` is passed"
DRIFT = ("Drifted step wording in 'tests/step_defs/test_w.py': the feature step "
         "`Given a` (in 'features/w.feature') and the decorator")
CONVENTIONAL = "Persistent state error in 'features/w.feature': the step `x`"


def test_rules_worded_without_error_are_routed_to_their_file():
    grouped = _group_validator_errors_by_file([ROW, DRIFT, CONVENTIONAL])
    assert grouped == {"pages/widget_page.py": [ROW],
                       "tests/step_defs/test_w.py": [DRIFT],
                       "features/w.feature": [CONVENTIONAL]}


def test_the_first_quoted_path_wins_over_a_later_mention():
    assert list(_group_validator_errors_by_file([DRIFT])) == ["tests/step_defs/test_w.py"]


def test_an_unroutable_error_is_logged_not_dropped_silently(caplog):
    assert _group_validator_errors_by_file(["Something odd happened"]) == {}
    assert "no repair can be targeted" in caplog.text


def test_the_real_row_index_message_is_routed():
    """End to end with the validator's own output, so a reworded message
    cannot slip out of the loop again unnoticed."""
    source = textwrap.dedent('''
        class WidgetPage:
            def quantity_of(self, index):
                values = self.get_column_values(self.sel("rows"), self.sel("qty"), index)
                return values[index]
    ''')
    errors = validate_row_index_is_not_a_cell_index(
        [SimpleNamespace(file_path="pages/widget_page.py", content=source)])
    assert errors
    assert list(_group_validator_errors_by_file(errors)) == ["pages/widget_page.py"]


def test_thrash_detection_names_rules_worded_either_way():
    assert _rules_persisting([ROW, CONVENTIONAL], [ROW, CONVENTIONAL]) == [
        "Persistent state", "Row index used as a cell index"]
