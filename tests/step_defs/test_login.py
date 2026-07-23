"""
Step definitions for features/login.feature.

REFERENCE FILE — this is the gold-standard example Agent 2 copies when it
generates new step-def modules. Follow the pattern shown here.

1. BIND the module to its feature file with `scenarios(...)`.

2. REUSE shared steps — do NOT redefine them. Steps and page-object fixtures
   that more than one feature needs live in `tests/step_defs/conftest.py`.
   That is the ONLY place pytest-bdd shares them from: step definitions are
   pytest fixtures, and fixtures are module-scoped everywhere else. A step
   defined in a sibling step-def module is invisible to this one and fails at
   collection with StepDefinitionNotFoundError.

   Shared steps available from conftest.py:
     Given I am on the SauceDemo login page
     When  I log in with username "..." and password "..."
     Then  I should be redirected to the inventory page
     Then  I should see the page title "..."
     Then  I should see the error message "..."

3. DEFINE LOCALLY only the steps specific to THIS feature — like the two
   below, which exercise error dismissal and are not used by any other
   feature. If a step you are about to write is needed by more than one
   feature, put it in conftest.py instead.

CONVENTIONS THESE STEPS DEMONSTRATE
-----------------------------------
- Step functions call PAGE OBJECT methods only. Never use a selector or read
  a selector constant here — that breaks the POM boundary.
- Keep each decorator's pattern on ONE single-quoted line. The step-coverage
  validator reads from the first quote to the last quote, so splitting a
  pattern across lines corrupts it and every step using it stops matching.
- Use parsers.re with [^"]* for any quoted placeholder whose value could
  legitimately be empty; parsers.parse cannot match "".
- Assertions carry a message showing expected vs actual, so a CI failure is
  readable without re-running locally.
"""
from pytest_bdd import scenarios, when, then

from config.paths import feature_path


# Bind this test module to the feature file.
scenarios(str(feature_path("login")))


# === Feature-specific WHEN steps ===

@when("I dismiss the error message")
def dismiss_error_banner(login_page):
    login_page.dismiss_error()


# === Feature-specific THEN steps ===

@then("no error message should be displayed")
def verify_no_error_message(login_page):
    actual = login_page.get_error_message()
    assert actual == "", \
        f"Expected no error message, but got '{actual}'"