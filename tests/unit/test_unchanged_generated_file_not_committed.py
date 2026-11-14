"""A planned file Agent 2 generates exactly as it is on main is not committed
(and not claimed as the story's change).
"""

from __future__ import annotations

from types import SimpleNamespace as NS


def test_a_file_generated_exactly_as_on_main_is_not_committed():
    from agents.agent2_coder import unchanged_files_dropped, unchanged_section
    main = {"pages/a_page.py": "same\n"}

    class Host:
        def get_file_content(self, path, branch="main"):
            return main[path]
    files = [NS(file_path="pages/a_page.py", content="same\n", is_new_file=False),
             NS(file_path="pages/b_page.py", content="new\n", is_new_file=False),
             NS(file_path="features/x.feature", content="F\n", is_new_file=True)]
    keep, unchanged = unchanged_files_dropped(Host(), files)
    assert [f.file_path for f in keep] == ["pages/b_page.py", "features/x.feature"]
    assert unchanged == ["pages/a_page.py"]
    assert "`pages/a_page.py`" in unchanged_section(unchanged) and unchanged_section([]) == ""
