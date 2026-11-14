"""A Gherkin tag on a scenario (@smoke, @cart) is a free pytest marker: it
needs no registration in pytest.ini.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_a_gherkin_tag_is_a_free_marker():
    ini = (ROOT / "pytest.ini").read_text(encoding="utf-8")
    assert "ignore::pytest.PytestUnknownMarkWarning" in ini
    assert "--strict-markers" not in ini.split("addopts", 1)[-1].split("\n", 3)[0]
