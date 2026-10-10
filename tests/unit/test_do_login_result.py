"""do_login must judge success on the password field it actually filled.

Regression: with auto-detected fields the caller's password_selector is None.
The same-URL success check used that raw argument, page.locator(None) raised,
and the bare except reported success - so a login that never got in (password
field still present) was recorded as logged in.

Pure fake page: no browser, no network.
"""
from inventory_tools.browser import do_login


class _Loc:
    def __init__(self, page, kind):
        self._page = page
        self._kind = kind
        self.first = self

    def count(self):
        if self._kind == "password":
            # present before submit; after submit, present only if login failed
            return 0 if (self._page.submitted and not self._page.still_present) else 1
        return 1

    def fill(self, *_):
        pass

    def click(self, *_):
        if self._kind == "submit":
            self._page.submitted = True


class _FakePage:
    """A login form on the same URL. `still_present` is whether the password
    field survives submit: True = login failed, False = login worked."""

    def __init__(self, password_still_present: bool):
        self.url = "https://app.example/login"
        self.still_present = password_still_present
        self.submitted = False

    def goto(self, url, **_):
        return None

    def wait_for_selector(self, *_, **__):
        return None

    def wait_for_load_state(self, *_, **__):
        return None

    def wait_for_timeout(self, *_):
        return None

    def locator(self, selector):
        if selector is None:
            raise TypeError("locator(None)")
        if "password" in str(selector):
            return _Loc(self, "password")
        if "submit" in str(selector):
            return _Loc(self, "submit")
        return _Loc(self, "username")


def test_failed_login_on_same_url_is_reported_as_failed():
    page = _FakePage(password_still_present=True)
    assert do_login(page, "https://app.example/login", None, None, None,
                    "user", "wrong") is False


def test_successful_login_that_removes_the_password_field_is_success():
    page = _FakePage(password_still_present=False)
    assert do_login(page, "https://app.example/login", None, None, None,
                    "user", "right") is True
