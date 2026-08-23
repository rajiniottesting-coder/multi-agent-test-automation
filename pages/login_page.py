"""
LoginPage — the Signup / Login screen.

RESERVED reference file. Agent 2 copies this style when generating new page
objects, so it is the single worked example of the conventions:

  - SELECTORS COME FROM THE APP INVENTORY, never from a literal in this file.
    Declare INVENTORY_PAGE, then use self.sel("<element_key>"). The keys are
    the `elements` keys on that page in app_inventory/<app>.json.
  - methods are business verbs (login_as), not UI mechanics (type_then_click)
  - every method uses a BasePage helper; no raw self.page.* calls
  - no assertions here — those belong in step definitions

App: https://automationexercise.com
"""
from typing import Optional

import logging
from urllib.parse import urlsplit

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class LoginPage(BasePage):
    """Signup / Login. Selectors: see `pages.login` in the app inventory.

    ONE PAGE, TWO FORMS. "Login to your account" and "New User Signup!" sit
    side by side and both have an email field, so every method here names the
    form-specific inventory key. A selector loose enough to match "the email
    input" matches both and raises a strict-mode violation.
    """

    INVENTORY_PAGE = "login"

    # ── actions ──────────────────────────────────────────────
    def open_login_page(self, base_url: str) -> None:
        """Navigate to the Signup / Login screen.

        Args:
            base_url: application base URL, supplied by the `base_url` fixture
                      from BASE_URL or config.yaml. The path comes from the
                      inventory, so it is never duplicated here.
        """
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def login_as(self, email: str, password: str) -> None:
        """Fill both credentials on the LOGIN form and submit.

        Takes the values rather than a role name: resolving a role to real
        credentials is the `credentials` fixture's job, so this page object
        stays usable with any user, including deliberately invalid ones.

        Confirms it is ON this page first. Filling a field that is not there
        does not fail fast - Playwright waits the full timeout and then
        reports a locator that "timed out", which reads like a selector
        problem and is not one. A scenario that reached this method from
        somewhere else lost thirty seconds and then blamed the field.

        It RAISES rather than navigating. Being on the wrong page here is a
        scenario that forgot its opening step, and silently correcting that
        would hide the mistake and make the scenario pass for a reason it
        never stated. confirm_arrival() is the tool for a click that should
        have landed; this is a precondition.
        """
        self._require_login_page()
        self.fill(self.sel("login_email_input"), email)
        self.fill(self.sel("login_password_input"), password)
        self.click(self.sel("login_button"))

    def _require_login_page(self) -> None:
        """Make sure the browser is on the login page, navigating if it is not.

        Filling a field that is not on screen does not fail fast: Playwright
        waits the full timeout and then reports the LOCATOR as having timed
        out. That reads like a broken selector, and the selector is fine - the
        page is wrong. Thirty seconds spent, and the reader sent to the one
        place the fault is not.

        It NAVIGATES rather than raising, which reverses an earlier decision.

        Raising was meant to stop a scenario passing for a reason it never
        stated. In practice the scenario that hit it was doing something
        reasonable - clearing an account-scoped collection in a Given, which
        left the browser on that collection's page - and every route to the
        login form was legitimate. Refusing to go there turned a recoverable
        situation into two failed tests and a regeneration.

        This method needs the login page; being elsewhere has exactly one
        sensible recovery, and taking it is what confirm_arrival() does
        everywhere else in this framework. The scenario-level mistake - a
        precondition placed before the login it depends on - is caught by the
        persistent-state rule and by review, which is where it belongs.

        The warning stays loud, because arriving here from somewhere else is
        still worth knowing about.
        """
        expected = self.page_url()
        current = urlsplit(self.page.url)
        if current.path.rstrip("/") == expected.rstrip("/"):
            return

        if not current.scheme or not current.netloc:
            raise AssertionError(
                f"login_as() was called with the browser at "
                f"{self.page.url!r}, which is not an address this page object "
                f"can navigate from. Open the login page first - the scenario "
                f"needs a Given that navigates here before the step that "
                f"signs in."
            )

        target = f"{current.scheme}://{current.netloc}{expected}"
        logger.warning(
            "LoginPage.login_as() was called from %s, not %s. Navigating to "
            "the login page so the credential fields are actually present - "
            "filling them from another page would wait the full timeout and "
            "then blame the field. If the scenario meant to be here already, "
            "it is missing a step that opens the login page; if a preceding "
            "Given navigated away, note that an account-scoped precondition "
            "has to run AFTER signing in, not before.",
            self.page.url, expected,
        )
        self.navigate(target)

    def start_signup(self, name: str, email: str) -> None:
        """Submit the SIGNUP form — the first of registration's two steps.

        This does NOT create the account. It navigates to a fuller form asking
        for password, address and contact details; the account exists only
        after that second form is submitted. Do not assert a logged-in state
        straight after calling this.

        Same precondition as login_as(): the signup fields share this page, so
        being elsewhere costs the full timeout and then blames the field.
        """
        self._require_login_page()
        self.fill(self.sel("signup_name_input"), name)
        self.fill(self.sel("signup_email_input"), email)
        self.click(self.sel("signup_button"))

    def clear_credentials(self) -> None:
        """Empty both login fields without submitting."""
        self.clear(self.sel("login_email_input"))
        self.clear(self.sel("login_password_input"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the login form is on screen. WAITS for it.

        Delegates to BasePage.is_showing() rather than swallowing the error in
        a bare `except`: a failed readiness check logs the selector, the wait
        it used and the current URL, so a CI log says more than `assert False`.
        """
        return self.is_showing(self.sel("login_heading"), timeout_ms=timeout_ms)

    def get_login_error(self) -> str:
        """The 'incorrect credentials' message. WAITS for it to appear.

        Only call this when an error IS expected. To assert that NO error is
        shown, use has_login_error(), which does not wait.
        """
        self.wait_visible(self.sel("login_error"))
        return self.get_text(self.sel("login_error"))

    def has_login_error(self) -> bool:
        """True if an error is showing right now. Never waits, never raises.

        The non-waiting counterpart to get_login_error(), for asserting that a
        valid login produced NO error. Using the waiting reader for that would
        time out instead of returning False.
        """
        return bool(self.get_all_texts(self.sel("login_error")))