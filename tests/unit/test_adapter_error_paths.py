"""Unknown-adapter errors must name the file that really holds the registry.

The messages pointed at agents/tracker.py and agents/repo_host.py; both
modules live under integrations/. A reader adding an adapter would look in the
wrong place.
"""
import pytest

from integrations import repo_host, tracker


def test_unknown_tracker_message_names_the_real_file():
    with pytest.raises(ValueError) as exc:
        tracker.get_tracker("no-such-tracker", fresh=True)
    assert "integrations/tracker.py" in str(exc.value)
    assert "agents/tracker.py" not in str(exc.value)


def test_unknown_repo_host_message_names_the_real_file():
    with pytest.raises(ValueError) as exc:
        repo_host.get_repo_host("no-such-host", fresh=True)
    assert "integrations/repo_host.py" in str(exc.value)
    assert "agents/repo_host.py" not in str(exc.value)
