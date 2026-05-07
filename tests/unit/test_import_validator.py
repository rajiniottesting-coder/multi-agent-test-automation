"""
Unit tests for agents/import_validator.py.

The validator catches the SCRUM-13 failure mode: LLM-generated step def
files that import page object classes from files that were never planned
and don't exist on disk.

These tests verify:
  - True positives (broken imports caught)
  - True negatives (valid imports accepted): stdlib, third-party, repo-internal, planned
  - Path normalization (./prefix, etc.)
  - Edge cases: malformed source, empty input, relative imports, non-Python files
  - Error messages follow the format the repair-loop grouper can parse

The tests are hermetic — no network, no real LLM, no real Jira.
"""
from pathlib import Path

import pytest

from agents.import_validator import (
    validate_imports_resolvable,
    _read_requirements,
    _extract_imports_from_source,
)


class _FakeFile:
    def __init__(self, file_path: str, content: str):
        self.file_path = file_path
        self.content = content


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """A minimal fake project structure for path-resolution tests.

    Layout:
        tmp_path/
            requirements.txt
            pages/
                login_page.py        (existing repo file)
                base_page.py         (existing repo file)
            features/
            tests/
                step_defs/
    """
    (tmp_path / "requirements.txt").write_text(
        "pytest==8.3.3\n"
        "pytest-bdd==7.3.0\n"
        "playwright==1.48.0\n"
        "PyGithub>=2.4\n"
        "jira>=3.10.5\n"
        "pydantic>=2.9\n"
        "pyyaml>=6.0\n"
    )
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "login_page.py").write_text("class LoginPage: pass\n")
    (tmp_path / "pages" / "base_page.py").write_text("class BasePage: pass\n")
    (tmp_path / "features").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "step_defs").mkdir()
    return tmp_path


# ─────────────────────────────────────────────────────────────
# True positives — broken imports get flagged
# ─────────────────────────────────────────────────────────────

class TestBrokenImportsCaught:
    def test_scrum_13_regression_missing_page_object(self, project_root):
        """The exact SCRUM-13 scenario: LLM imports page objects that
        don't exist and weren't planned."""
        broken = _FakeFile(
            "tests/step_defs/test_inventory_sorting.py",
            "from pages.login_page import LoginPage\n"
            "from pages.cart_page import CartPage\n"  # not planned, doesn't exist
            "from pages.product_detail_page import ProductDetailPage\n",  # ditto
        )
        errors = validate_imports_resolvable([broken], project_root)
        assert len(errors) == 2
        assert all("does not exist" in e for e in errors)
        assert any("pages.cart_page" in e for e in errors)
        assert any("pages.product_detail_page" in e for e in errors)

    def test_error_format_parseable_by_repair_loop(self, project_root):
        """Validator errors must follow `<type> error in '<path>':` so the
        repair loop's grouper regex can extract the file path."""
        import re
        broken = _FakeFile(
            "tests/step_defs/test_x.py",
            "from pages.nonexistent import Foo\n",
        )
        errors = validate_imports_resolvable([broken], project_root)
        assert len(errors) == 1
        # The repair loop uses pattern: `error in '([^']+)':`
        match = re.search(r"error in '([^']+)':", errors[0])
        assert match is not None
        assert match.group(1) == "tests/step_defs/test_x.py"

    def test_error_includes_line_number(self, project_root):
        broken = _FakeFile(
            "tests/test_x.py",
            "import os\n"
            "import sys\n"
            "from pages.missing import Foo\n",  # line 3
        )
        errors = validate_imports_resolvable([broken], project_root)
        assert len(errors) == 1
        assert "line 3" in errors[0]


# ─────────────────────────────────────────────────────────────
# True negatives — valid imports accepted
# ─────────────────────────────────────────────────────────────

class TestValidImportsAccepted:
    def test_stdlib_imports_pass(self, project_root):
        f = _FakeFile(
            "tests/test_x.py",
            "import os\nimport sys\nfrom pathlib import Path\nimport re\n"
            "from typing import Optional\nimport json\nimport logging\n",
        )
        assert validate_imports_resolvable([f], project_root) == []

    def test_third_party_from_requirements_pass(self, project_root):
        f = _FakeFile(
            "tests/test_x.py",
            "import pytest\n"
            "from pytest_bdd import scenarios\n"
            "from playwright.sync_api import Page\n"
            "from pydantic import BaseModel\n"
            "from jira import JIRA\n",
        )
        assert validate_imports_resolvable([f], project_root) == []

    def test_known_alias_pyyaml_accepted(self, project_root):
        """`import yaml` should be accepted because pyyaml is in requirements."""
        f = _FakeFile("tests/test_x.py", "import yaml\n")
        assert validate_imports_resolvable([f], project_root) == []

    def test_known_alias_pygithub_accepted(self, project_root):
        """`from github import Github` accepted because PyGithub in requirements."""
        f = _FakeFile("tests/test_x.py", "from github import Github\n")
        assert validate_imports_resolvable([f], project_root) == []

    def test_existing_repo_file_pass(self, project_root):
        """Imports of files that exist on disk should pass."""
        f = _FakeFile(
            "tests/test_x.py",
            "from pages.login_page import LoginPage\n"
            "from pages.base_page import BasePage\n",
        )
        assert validate_imports_resolvable([f], project_root) == []

    def test_planned_file_in_batch_passes(self, project_root):
        """Imports of files that don't exist YET but are in this generation
        batch should pass — they'll exist when the PR commits."""
        step_def = _FakeFile(
            "tests/step_defs/test_cart.py",
            "from pages.cart_page import CartPage\n",
        )
        page_object = _FakeFile("pages/cart_page.py", "class CartPage: pass\n")
        errors = validate_imports_resolvable([step_def, page_object], project_root)
        assert errors == []


# ─────────────────────────────────────────────────────────────
# Edge cases
# ─────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_input(self, project_root):
        assert validate_imports_resolvable([], project_root) == []

    def test_non_python_files_skipped(self, project_root):
        """Feature files and other non-.py shouldn't crash the parser."""
        feature = _FakeFile(
            "features/x.feature",
            "Feature: x\n  Scenario: y\n    When something\n",
        )
        assert validate_imports_resolvable([feature], project_root) == []

    def test_malformed_python_source_doesnt_crash(self, project_root):
        """Syntax errors in generated content shouldn't crash the validator —
        other validators or pytest itself will catch them."""
        broken = _FakeFile("tests/test_x.py", "from pages import (((\n")
        # Should return empty (skip) rather than raise
        errors = validate_imports_resolvable([broken], project_root)
        # Empty list — we couldn't analyze, but validator didn't crash
        assert isinstance(errors, list)

    def test_relative_imports_skipped(self, project_root):
        """`from . import x` is skipped — relative resolution depends on
        package context which is harder to determine, and these aren't a
        common LLM hallucination source."""
        f = _FakeFile(
            "tests/test_x.py",
            "from . import helper\n"
            "from .. import shared\n",
        )
        assert validate_imports_resolvable([f], project_root) == []

    def test_no_requirements_txt_graceful_degradation(self, tmp_path: Path):
        """If requirements.txt is missing, validator should still work
        (just won't recognize third-party imports)."""
        (tmp_path / "pages").mkdir()
        f = _FakeFile("tests/test_x.py", "import os\nfrom pages.x import Y\n")
        # `os` (stdlib) passes; pages.x doesn't exist so it errors
        errors = validate_imports_resolvable([f], tmp_path)
        assert len(errors) == 1
        assert "pages.x" in errors[0]

    def test_dotted_module_path_resolves(self, project_root):
        """Multi-level imports like `from pages.subdir.thing import X`
        check both `pages/subdir/thing.py` and `pages/subdir/thing/__init__.py`."""
        # Create pages/subdir/thing.py
        (project_root / "pages" / "subdir").mkdir()
        (project_root / "pages" / "subdir" / "thing.py").write_text("class X: pass\n")
        f = _FakeFile(
            "tests/test_x.py",
            "from pages.subdir.thing import X\n",
        )
        assert validate_imports_resolvable([f], project_root) == []


# ─────────────────────────────────────────────────────────────
# Helper functions
# ─────────────────────────────────────────────────────────────

class TestRequirementsParsing:
    def test_basic_pinned_version(self, tmp_path: Path):
        (tmp_path / "requirements.txt").write_text("pytest==8.3.3\n")
        pkgs = _read_requirements(tmp_path)
        assert "pytest" in pkgs

    def test_constraint_specifiers(self, tmp_path: Path):
        (tmp_path / "requirements.txt").write_text(
            "pytest>=8.0\n"
            "playwright<2.0\n"
            "pydantic~=2.9\n"
        )
        pkgs = _read_requirements(tmp_path)
        assert "pytest" in pkgs
        assert "playwright" in pkgs
        assert "pydantic" in pkgs

    def test_comments_and_blank_lines_skipped(self, tmp_path: Path):
        (tmp_path / "requirements.txt").write_text(
            "# a comment\n"
            "\n"
            "pytest==8.3.3\n"
            "  # inline comment line\n"
        )
        pkgs = _read_requirements(tmp_path)
        assert "pytest" in pkgs

    def test_pip_directives_skipped(self, tmp_path: Path):
        """Lines like `-r other.txt` shouldn't be parsed as packages."""
        (tmp_path / "requirements.txt").write_text(
            "-r constraints.txt\n"
            "--index-url https://pypi.org/simple\n"
            "pytest\n"
        )
        pkgs = _read_requirements(tmp_path)
        assert "pytest" in pkgs

    def test_dash_to_underscore_normalization(self, tmp_path: Path):
        """`langchain-google-genai` should match `langchain_google_genai` imports."""
        (tmp_path / "requirements.txt").write_text("langchain-google-genai==4.2.2\n")
        pkgs = _read_requirements(tmp_path)
        assert "langchain_google_genai" in pkgs

    def test_missing_requirements_returns_empty(self, tmp_path: Path):
        assert _read_requirements(tmp_path) == set()


class TestImportExtraction:
    def test_simple_import(self):
        imports = _extract_imports_from_source("import os\n")
        assert imports == [("os", 1)]

    def test_dotted_import(self):
        imports = _extract_imports_from_source("import os.path\n")
        assert imports == [("os.path", 1)]

    def test_from_import(self):
        imports = _extract_imports_from_source("from pathlib import Path\n")
        assert imports == [("pathlib", 1)]

    def test_from_dotted_import(self):
        imports = _extract_imports_from_source(
            "from pages.login_page import LoginPage\n"
        )
        assert imports == [("pages.login_page", 1)]

    def test_multiple_imports_correct_lines(self):
        src = (
            "import os\n"
            "\n"
            "import sys\n"
            "from pathlib import Path\n"
        )
        imports = _extract_imports_from_source(src)
        assert imports == [("os", 1), ("sys", 3), ("pathlib", 4)]

    def test_relative_imports_skipped(self):
        src = "from . import x\nfrom ..base import Y\n"
        assert _extract_imports_from_source(src) == []

    def test_malformed_source_returns_empty(self):
        """Malformed source returns empty list, doesn't raise."""
        assert _extract_imports_from_source("from import (((") == []