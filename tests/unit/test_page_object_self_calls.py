"""A page object may only call methods its class hierarchy defines.

Method resolution checked step definitions' calls INTO page objects, never a
page object's calls on itself. A generated page object called
`self.require_own_page_on()` and `self.sel_on()` - defined nowhere - passed
every gate and failed every scenario at runtime with AttributeError.
Generic names only; no network, no model.
"""
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

from validators.method_resolution_validator import validate_method_resolution

BASE = '''
class BasePage:
    def __init__(self, page):
        self.page = page
        self._timeout = 5
    def sel(self, key):
        return key
    def require_own_page(self):
        pass
'''


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "base_page.py").write_text(textwrap.dedent(BASE), encoding="utf-8")
    return tmp_path


def _check(root, body, path="pages/widget_page.py"):
    return validate_method_resolution(
        [SimpleNamespace(file_path=path, content=textwrap.dedent(body))], root)


def test_inherited_and_own_methods_resolve(root):
    assert _check(root, '''
        from pages.base_page import BasePage
        class WidgetPage(BasePage):
            def open_widget(self):
                self.require_own_page()
                self._helper(self.sel("x"))
            def _helper(self, s):
                return s
    ''') == []


def test_an_undefined_self_call_is_refused_with_a_suggestion(root):
    errors = _check(root, '''
        from pages.base_page import BasePage
        class WidgetPage(BasePage):
            def open_widget(self):
                self.require_own_page_on("other")
                self.require_own_page_on("again")
    ''')
    assert len(errors) == 1, "one error per missing name, not per call"
    assert errors[0].startswith("Method resolution error in 'pages/widget_page.py' line 5:")
    assert "`self.require_own_page_on()`" in errors[0]
    assert "`require_own_page()`" in errors[0]


def test_a_callable_attribute_resolves(root):
    assert _check(root, '''
        from pages.base_page import BasePage
        class WidgetPage(BasePage):
            reader = staticmethod(len)
            def __init__(self, page):
                super().__init__(page)
                self.probe = lambda: True
            def check_widget(self):
                return self.probe() and self.reader("x")
    ''') == []


def test_an_unknown_base_is_not_guessed_at(root):
    assert _check(root, '''
        class WidgetPage(SomethingExternal):
            def open_widget(self):
                self.anything_at_all()
    ''') == []


def test_getattr_is_respected(root):
    assert _check(root, '''
        from pages.base_page import BasePage
        class WidgetPage(BasePage):
            def __getattr__(self, name):
                return lambda *a: None
            def open_widget(self):
                self.dynamic()
    ''') == []


def test_a_sibling_in_the_batch_is_a_valid_base(root):
    files = [
        SimpleNamespace(file_path="pages/gadget_page.py", content=textwrap.dedent('''
            from pages.base_page import BasePage
            class GadgetPage(BasePage):
                def shared_step(self):
                    pass
        ''')),
        SimpleNamespace(file_path="pages/widget_page.py", content=textwrap.dedent('''
            from pages.gadget_page import GadgetPage
            class WidgetPage(GadgetPage):
                def open_widget(self):
                    self.shared_step()
        ''')),
    ]
    assert validate_method_resolution(files, root) == []


def test_the_committed_page_objects_pass():
    root = Path(__file__).resolve().parents[2]
    files = [SimpleNamespace(file_path=f"pages/{p.name}", content=p.read_text(encoding="utf-8"))
             for p in (root / "pages").glob("*_page.py")]
    assert files
    assert validate_method_resolution(files, root) == []
