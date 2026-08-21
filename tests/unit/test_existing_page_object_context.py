"""Agent 2 sees page objects that ALREADY EXIST on main.

WHY THIS EXISTS
    `_build_sibling_page_object_context` only ever saw files generated in the
    SAME run. A story that reused a page object from an earlier story got no
    ground truth about its methods, so the model invented names — the gap that
    `key_methods` was filling by hand: a specification written before the code
    existed, which then had to be kept in step with it.

    The page object on disk IS the contract. Reading it removes the duplicate
    source of truth: fix the code and the constraint follows.

SAFETY CONTRACT
    This may only ever ADD prompt context. Every failure — missing file,
    unreachable repo, unparseable module — must yield nothing rather than
    raise, because a thinner prompt is a far better outcome than a failed
    story. `key_methods` stays honoured for pages whose object does not exist
    yet.
"""
import pytest

from agents.agent2_coder import (
    _existing_page_objects_on_main,
    _build_sibling_page_object_context,
)

PAGE_OBJECT = (
    "from pages.base_page import BasePage\n\n\n"
    "class ListingPage(BasePage):\n"
    '    INVENTORY_PAGE = "products"\n\n'
    "    def search(self, term: str) -> None:\n"
    '        """Search the catalogue."""\n'
    "        pass\n\n"
    "    def has_product(self, name: str) -> bool:\n"
    "        return True\n"
)


class FakeRepo:
    """Minimal RepoHost stand-in. No Jira, no GitHub, no network."""

    def __init__(self, files=None, listing_raises=False, read_raises=False):
        self.files = files or {}
        self.listing_raises = listing_raises
        self.read_raises = read_raises

    def list_files_in_directory(self, directory, branch="main"):
        if self.listing_raises:
            raise RuntimeError("repo unreachable")
        return list(self.files)

    def get_file_content(self, path, branch="main"):
        if self.read_raises:
            raise RuntimeError("404 not found")
        return self.files[path]


# ── the flows ───────────────────────────────────────────────────────────

def test_first_story_has_no_existing_pages_and_no_context():
    """Nothing on main yet — identical to the behaviour before this change."""
    assert _existing_page_objects_on_main(FakeRepo({}), set()) == []


def test_a_later_story_sees_the_earlier_page_object():
    got = _existing_page_objects_on_main(
        FakeRepo({"pages/products_page.py": PAGE_OBJECT}), set())
    assert [f.file_path for f in got] == ["pages/products_page.py"]
    block = _build_sibling_page_object_context(got)
    assert "search" in block and "has_product" in block


def test_a_file_being_written_this_run_is_not_fetched():
    """The batch copy is newer than main's. Injecting both would give the model
    two versions of the same class to choose between."""
    got = _existing_page_objects_on_main(
        FakeRepo({"pages/products_page.py": PAGE_OBJECT}),
        {"pages/products_page.py"})
    assert got == []


def test_base_page_is_never_included():
    """Its 75 helpers already reach the prompt through their own block; adding
    them again would duplicate a large payload."""
    assert _existing_page_objects_on_main(
        FakeRepo({"pages/base_page.py": PAGE_OBJECT}), set()) == []


@pytest.mark.parametrize("path", ["pages/__init__.py", "pages/helpers.py", "pages/README.md"])
def test_only_page_object_files_are_read(path):
    assert _existing_page_objects_on_main(FakeRepo({path: PAGE_OBJECT}), set()) == []


# ── the negative paths: every one must degrade, never raise ─────────────

def test_an_unreachable_repo_yields_no_context():
    assert _existing_page_objects_on_main(FakeRepo({}, listing_raises=True), set()) == []


def test_a_failed_file_read_is_skipped():
    assert _existing_page_objects_on_main(
        FakeRepo({"pages/products_page.py": PAGE_OBJECT}, read_raises=True), set()) == []


def test_an_empty_file_is_skipped():
    assert _existing_page_objects_on_main(FakeRepo({"pages/x_page.py": ""}), set()) == []


def test_an_unparseable_file_produces_no_block_but_does_not_raise():
    """A half-written page object must not take the whole story down with it."""
    got = _existing_page_objects_on_main(FakeRepo({"pages/x_page.py": "def ((("}), set())
    assert _build_sibling_page_object_context(got).strip() == ""


def test_a_listing_of_none_is_handled():
    class NoneRepo(FakeRepo):
        def list_files_in_directory(self, directory, branch="main"):
            return None
    assert _existing_page_objects_on_main(NoneRepo(), set()) == []


# ── the contract ────────────────────────────────────────────────────────

def test_generate_file_content_defaults_to_the_old_behaviour():
    """The parameter is optional, so every existing caller and every test that
    does not pass it behaves exactly as before."""
    import inspect
    from agents.agent2_coder import generate_file_content
    p = inspect.signature(generate_file_content).parameters["existing_page_objects"]
    assert p.default is None


def test_the_ai_update_path_accepts_it_too():
    """ai-update regenerates against page objects that already exist, which is
    where invented method names hurt most."""
    import inspect
    from agents.agent2_coder import _regenerate_step_defs_whole
    p = inspect.signature(_regenerate_step_defs_whole).parameters["existing_page_objects"]
    assert p.default is None


# ─────────────────────────────────────────────────────────────────────────
# End-to-end: the signatures actually REACH the prompt
#
# The two guards above prove the fetcher and the block builder work. Neither
# would catch the failure that matters most: a correct block built and then
# never substituted into the template, because the placeholder was missing or
# the file_type check excluded it. That fails silently — the story still runs,
# the model still invents names, and nothing looks wrong.
# ─────────────────────────────────────────────────────────────────────────

class _CapturingLLM:
    """Records the prompt instead of calling anything."""

    def __init__(self):
        self.prompt = ""

    def invoke_text(self, system_prompt=None, user_prompt=None, **kwargs):
        self.prompt = f"{system_prompt}\n{user_prompt}"
        return "# stub"


def _run_generation(file_type):
    from types import SimpleNamespace
    from agents.agent2_coder import generate_file_content
    from core.app_context import AppContext

    existing = [SimpleNamespace(file_path="pages/products_page.py",
                                content=PAGE_OBJECT)]
    file_plan = SimpleNamespace(file_path="pages/cart_page.py",
                                file_type=file_type, purpose="p",
                                is_new_file=True)
    plan = SimpleNamespace(feature_name="f", branch_name="b", pr_title="t",
                           pr_body="b", files_to_create=[file_plan], notes="")
    llm = _CapturingLLM()
    try:
        generate_file_content(
            llm, file_plan, plan, [],
            {"feature": "", "step_def": "", "page_object": ""},
            "{}", AppContext.load(), existing_page_objects=existing)
    except Exception:
        # The stub response fails content validation — irrelevant here. The
        # prompt was already built and captured by that point.
        pass
    return llm.prompt


@pytest.mark.parametrize("file_type", ["page_object", "step_definitions"])
def test_existing_signatures_reach_the_prompt(file_type):
    """`page_object` is the half that was missing: the block was built only for
    step-def files, so a page object being extended never saw the API it was
    meant to stay consistent with."""
    # A DISTINCTIVE token. "search" alone also appears in the prompt template
    # and in the inventory, so asserting on it passes even when the block is
    # missing entirely - which is exactly how the first version of this test
    # failed to catch a deliberately broken condition.
    assert "has_product" in _run_generation(file_type), (
        f"{file_type} prompt does not carry the existing page object's methods"
    )


def test_a_feature_file_gets_no_method_signatures():
    """Gherkin describes behaviour and calls nothing. Injecting Python method
    names there would be tokens spent on noise."""
    assert "has_product" not in _run_generation("feature")


# ─────────────────────────────────────────────────────────────────────────
# The read prefers the story's OWN branch
#
# A re-run — a fix pushed onto an open PR, or ai-update on a story already
# coded — must see the methods that run wrote, not the older ones on main, or
# it renames its own work.
# ─────────────────────────────────────────────────────────────────────────

class _BranchRepo:
    """Different content per branch, as a real repo has."""

    def __init__(self, per_branch, missing_branches=()):
        self.per_branch = per_branch
        self.missing = set(missing_branches)

    def list_files_in_directory(self, directory, branch="main"):
        if branch in self.missing:
            raise RuntimeError(f"no such branch: {branch}")
        return list(self.per_branch.get(branch, {}))

    def get_file_content(self, path, branch="main"):
        return self.per_branch[branch][path]


_ON_MAIN = "class ListingPage:\n    def old_name(self): pass\n"
_ON_BRANCH = "class ListingPage:\n    def new_name(self): pass\n"


def test_the_story_branch_wins_over_main():
    repo = _BranchRepo({"main": {"pages/products_page.py": _ON_MAIN},
                        "auto/S-1-x": {"pages/products_page.py": _ON_BRANCH}})
    got = _existing_page_objects_on_main(repo, set(), branch="auto/S-1-x")
    assert "new_name" in got[0].content, "a re-run must see its own earlier work"


def test_main_is_used_when_the_branch_does_not_exist_yet():
    """The first generation for a story runs before its branch is pushed."""
    repo = _BranchRepo({"main": {"pages/products_page.py": _ON_MAIN}},
                       missing_branches={"auto/S-2-y"})
    got = _existing_page_objects_on_main(repo, set(), branch="auto/S-2-y")
    assert "old_name" in got[0].content


def test_no_branch_argument_behaves_exactly_as_before():
    repo = _BranchRepo({"main": {"pages/products_page.py": _ON_MAIN}})
    assert "old_name" in _existing_page_objects_on_main(repo, set())[0].content


def test_both_branches_unreachable_yields_nothing():
    repo = _BranchRepo({}, missing_branches={"main", "auto/S-3-z"})
    assert _existing_page_objects_on_main(repo, set(), branch="auto/S-3-z") == []


@pytest.mark.parametrize("label,per_branch,list_raises,read_raises,branch,expected", [
    ("branch empty falls back to main",
     {"main": {"pages/a_page.py": "class P:\n    def go(self): pass\n"}, "br": {}}, (), (), "br", 1),
    ("branch lists but its files are unreadable -> main",
     {"main": {"pages/a_page.py": "class P:\n    def go(self): pass\n"},
      "br": {"pages/a_page.py": "class P:\n    def go(self): pass\n"}}, (), ("br",), "br", 1),
    ("empty branch string behaves as no branch",
     {"main": {"pages/a_page.py": "class P:\n    def go(self): pass\n"}}, (), (), "", 1),
    ("branch is literally 'main'",
     {"main": {"pages/a_page.py": "class P:\n    def go(self): pass\n"}}, (), (), "main", 1),
])
def test_branch_fallback_edge_cases(label, per_branch, list_raises, read_raises,
                                    branch, expected):
    """Every one of these must degrade to fewer files, never to an exception:
    a story is not worth failing over missing prompt context."""
    class Repo:
        def list_files_in_directory(self, directory, branch="main"):
            if branch in list_raises:
                raise RuntimeError("unreachable")
            return list(per_branch.get(branch, {}))

        def get_file_content(self, path, branch="main"):
            if branch in read_raises:
                raise RuntimeError("unreadable")
            return per_branch[branch][path]

    assert len(_existing_page_objects_on_main(Repo(), set(), branch=branch)) == expected