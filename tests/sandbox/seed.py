"""Dummy data for sandbox flow tests: a Jira project and a repository copy.

Shaped like the real project, under the made-up key SBX so nothing can be
mistaken for live data:

  Stories
    SBX-1  User can log in                     Done       Login, Account
    SBX-2  Shopping session                    In Review  Login, Products, Cart
    SBX-3  Clearer error for a wrong password  To Do      Login   <- change story
    SBX-4  Old app: login (another application) Done

  Test cases (owner = Relates link, laid out exactly as Agent 1 creates it)
    SBX-11 owned by SBX-1  marked in features/sandbox_login.feature
    SBX-12 owned by SBX-1  marked;  SBX-3 IMPACTS it
    SBX-13 owned by SBX-1  its scenario is UNMARKED  (backfill target)
    SBX-21 owned by SBX-2  no scenario yet
    SBX-31 owned by SBX-4  old-application look-alike title
    SBX-32 owned by SBX-4  old-application look-alike title
    SBX-33 owned by SBX-4  labelled ai-retired

  Trace: SBX-3 impacts SBX-1 (story to story).
"""
from __future__ import annotations

import shutil
from pathlib import Path

from tests.sandbox.fake_jira import FakeJira

ROOT = Path(__file__).resolve().parents[2]

DESCRIPTIONS = {
    "SBX-11": "Log in with the registered role and see the account name.",
    "SBX-12": "Log in with a wrong password and see the error message.",
    "SBX-13": "Log in with an unknown email and see the error message.",
    "SBX-21": "Log in, search, add to cart, remove, log out.",
    "SBX-31": "Old app: log in as standard_user and land on the inventory page.",
    "SBX-32": "Old app: invalid username/password shows an error banner.",
    "SBX-33": "Old app: retired case.",
}


def seed_jira() -> FakeJira:
    j = FakeJira("SBX")
    j._n = iter(range(100, 10_000))           # created issues start at SBX-100
    j.add("Story", "User can log in", key="SBX-1", status="Done",
          components=["Login", "Account"], labels=["ai-processed", "human-approved",
                                                   "ai-coded", "tests-run"])
    j.add("Story", "Shopping session from login to logout", key="SBX-2",
          status="In Review", components=["Login", "Products", "Cart"])
    j.add("Story", "Show a clearer error for a wrong password", key="SBX-3",
          components=["Login"])
    j.add("Story", "Old app: login", key="SBX-4", status="Done")
    cases = [
        ("SBX-11", "[Positive] Successful login with valid credentials", "SBX-1", ()),
        ("SBX-12", "[Negative] Login fails with an incorrect password", "SBX-1", ()),
        ("SBX-13", "[Negative] Login fails with an unknown email address", "SBX-1", ()),
        ("SBX-21", "[Positive] Registered shopper completes a full session", "SBX-2", ()),
        ("SBX-31", "[Positive] [Positive] Successful login with valid standard_user credentials",
         "SBX-4", ()),
        ("SBX-32", "[Negative] Login fails with invalid username/password combination",
         "SBX-4", ()),
        ("SBX-33", "[Edge] Login with an expired session cookie", "SBX-4", ("ai-retired",)),
    ]
    for key, summary, owner, labels in cases:
        j.add("Test Case", summary, key=key, description=DESCRIPTIONS[key], labels=labels)
        j.link("Relates", key, owner)                 # Agent 1's layout: test inward
    j.link("Impacts", "SBX-3", "SBX-12")              # story impacts test
    j.link("Impacts", "SBX-3", "SBX-1")               # story-to-story trace
    return j


SANDBOX_FEATURE = """Feature: Sandbox login
  Scenarios owned by SBX-1, used only by the sandbox flow tests.

  Background:
    Given I am on the signup and login page

  @smoke
  {m11}
  Scenario: Successful login with valid credentials
    When I log in as a "registered" user
    Then I should be logged in
    And I should see my account name in the navigation

  @negative
  {m12}
  Scenario: Login fails with an incorrect password
    When I log in as a "registered" user with an incorrect password
    Then I should see the error message "Your email or password is incorrect!"
    And I should remain on the login page

  @negative
  Scenario: Login fails with an unknown email address
    When I log in with email "nobody@example.invalid" and password "whatever"
    Then I should see the error message "Your email or password is incorrect!"
"""


def build_repo(dest: Path) -> Path:
    """The framework's own baseline test surface, plus one sandbox feature
    owned by SBX-1. The real reference file login.feature is kept as is.

    Only the RESERVED files (the reference feature, step definitions and page
    objects, and the framework's base page) are copied - never whatever stories
    have merged since. Copying the whole features/ and pages/ folders coupled
    every sandbox test to the pipeline's own output: the first story merged
    (SCRUM-111) arrived without its step definitions, which are not copied here,
    and failed the framework's unit tests on its
    own PR with "no step definition" gaps and a changed scenario count.
    """
    from agents.agent2_coder import format_marker
    from core.app_context import AppContext
    for rel in ("app_inventory", "config"):
        shutil.copytree(ROOT / rel, dest / rel,
                        ignore=shutil.ignore_patterns("__pycache__"))
    baseline = {p for p in AppContext.load().reserved_paths_normalized()
                if p.startswith(("pages/", "features/"))} | {"pages/__init__.py"}
    for rel in sorted(baseline):
        if (ROOT / rel).is_file():
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / rel, dest / rel)
    (dest / "tests" / "step_defs").mkdir(parents=True)
    for name in ("__init__.py", "conftest.py", "test_login.py"):
        shutil.copy(ROOT / "tests" / "step_defs" / name, dest / "tests" / "step_defs" / name)
    (dest / "features" / "sandbox_login.feature").write_text(SANDBOX_FEATURE.format(
        m11=format_marker("SBX-11", DESCRIPTIONS["SBX-11"]),
        m12=format_marker("SBX-12", DESCRIPTIONS["SBX-12"]),
    ), encoding="utf-8")
    steps = (ROOT / "tests" / "step_defs" / "test_login.py").read_text(encoding="utf-8")
    (dest / "tests" / "step_defs" / "test_sandbox_login.py").write_text(
        steps.replace('feature_path("login")', 'feature_path("sandbox_login")'),
        encoding="utf-8")
    return dest


def repo_files(root: Path) -> dict:
    """{project-relative path: content} for a FakeRepoHost's main branch."""
    return {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
            for p in root.rglob("*") if p.is_file() and p.suffix in (".feature", ".py", ".json", ".yaml")}
