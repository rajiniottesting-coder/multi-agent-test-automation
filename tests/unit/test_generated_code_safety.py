"""Generated test code reaches the application only through the page objects (S1).

A story's text is untrusted, and Agent 2 turns it into Python that Agent 4
runs on the pull request - before a person reviews it - with the
application's login in the environment. These tests pin each layer:

  - the static check (validators/code_safety.py): every denied form, every
    detour round it, and the ordinary test code it must leave alone;
  - Agent 2: the repair loop is told, the final gate refuses, the plan may not
    put Python outside the test-code directories;
  - Agent 4: scripts/check_code_safety.py runs before the browser run, and the
    browser run and its retry wait for it;
  - BasePage: navigate() opens only the application's host, an upload attaches
    only a project file.
"""
from __future__ import annotations

import io
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from validators.code_safety import (CODE_DIRS, code_path_problem, settings, unsafe_calls,
                                    validate_code_safety)

ROOT = Path(__file__).resolve().parents[2]


def _found(source: str, allow=()) -> list:
    return [what for _line, what in unsafe_calls(source, allow)]


# ── what is refused ───────────────────────────────────────────────────────────

UNSAFE = {
    # the environment
    "os.environ": "import os\nx = os.environ['APP_PASSWORD']\n",
    "os.getenv": "import os\nx = os.getenv('APP_PASSWORD')\n",
    "from os import environ": "from os import environ\n",
    "os as alias": "import os as o\nx = o.environ\n",
    "import os.path then os": "import os.path\nos.system('id')\n",
    "star import from os": "from os import *\n",
    "os reached through os.path": "import os\nx = os.path.os.environ\n",
    "os reached through another module": "import logging\nx = logging.os.environ\n",
    # processes
    "subprocess": "import subprocess\nsubprocess.run(['id'])\n",
    "os.system": "import os\nos.system('id')\n",
    "os.popen": "import os\nos.popen('id')\n",
    "sys through a module": "import logging\nlogging.sys.exit(1)\n",
    # the network
    "socket": "import socket\n",
    "requests": "import requests\nrequests.get('https://example.org')\n",
    "urllib.request": "from urllib.request import urlopen\n",
    "urllib.request as module": "import urllib.request\n",
    "http.client": "import http.client\n",
    # running or loading code
    "eval": "eval('1')\n",
    "exec": "exec('x = 1')\n",
    "compile": "compile('1', 'f', 'eval')\n",
    "__import__": "__import__('os')\n",
    "importlib": "import importlib\n",
    "pickle": "import pickle\n",
    "inspect": "import inspect\n",
    "getattr computed": "def f(x, n):\n    return getattr(x, n)\n",
    "getattr literal environ": "import os\nx = getattr(os, 'environ')\n",
    "getattr literal evaluate": "def f(p):\n    return getattr(p, 'evaluate')('1')\n",
    "attrgetter": "from operator import attrgetter\n",
    "operator.methodcaller": "import operator\nf = operator.methodcaller('x')\n",
    # restriction escapes
    "__builtins__": "x = __builtins__\n",
    "__subclasses__": "x = ().__class__.__base__.__subclasses__()\n",
    "__globals__": "def f():\n    pass\nx = f.__globals__\n",
    "frames": "def f(e):\n    return e.__traceback__.tb_frame.f_globals\n",
    "globals()": "x = globals()\n",
    "vars()": "x = vars()\n",
    # files
    "open()": "open('.git/config').read()\n",
    "read_text": "from pathlib import Path\nPath('.env').read_text()\n",
    "write_text": "from pathlib import Path\nPath('x').write_text('y')\n",
    "path.open": "from pathlib import Path\nPath('.git/config').open().read()\n",
    "a name a path was assigned to": "from pathlib import Path\nf = Path('x')\nf.open()\n",
    "a self attribute a path was assigned to":
        "from pathlib import Path\nclass P:\n    def __init__(self):\n"
        "        self.cfg = Path('x')\n    def r(self):\n        return self.cfg.open()\n",
    "a parameter annotated as a path": "from pathlib import Path\ndef f(p: Path):\n    return p.open()\n",
    "io": "import io\n",
    "codecs": "import codecs\n",
    "shutil": "import shutil\n",
    "os.remove": "import os\nos.remove('x')\n",
    "save_as": "def f(d):\n    d.save_as('tests/conftest.py')\n",
    # the browser past the page objects
    "evaluate": "def f(page):\n    page.evaluate('fetch(1)')\n",
    "locator evaluate": "def f(page):\n    page.locator('x').evaluate('e => e')\n",
    "add_init_script": "def f(page):\n    page.add_init_script('x')\n",
    "route": "def f(page):\n    page.route('**', lambda r: r)\n",
    "request": "def f(page):\n    page.request.get('https://example.org')\n",
    "context request": "def f(page):\n    page.context.request.post('https://example.org')\n",
    "cookies": "def f(page):\n    page.context.cookies()\n",
    "storage_state": "def f(page):\n    page.context.storage_state()\n",
    "goto": "def f(start_page):\n    start_page.page.goto('https://example.org')\n",
    "new_context": "def f(browser):\n    browser.new_context()\n",
    "expose_function": "def f(page):\n    page.expose_function('x', print)\n",
}


@pytest.mark.parametrize("source", UNSAFE.values(), ids=list(UNSAFE))
def test_every_way_out_is_refused(source):
    assert _found(source), source


SAFE = {
    "a step through page objects":
        "from pytest_bdd import given, when, then, parsers\n"
        "@given('the start page is open')\n"
        "def open_start(start_page, base_url):\n    start_page.open(base_url)\n",
    "a page object's own open()":
        "from pages.base_page import BasePage\nclass P(BasePage):\n"
        "    def open(self, base_url):\n        self.navigate(base_url + self.page_url())\n"
        "    def again(self, base_url):\n        self.open(base_url)\n",
    "os.path": "import os\nx = os.path.join('a', 'b')\n",
    "urllib.parse": "from urllib.parse import urlsplit\nx = urlsplit('https://a/b').path\n",
    "re, time, datetime": "import re\nimport time\nimport datetime\nx = re.sub('a', 'b', 'c')\n",
    "a literal getattr": "def f(x):\n    return getattr(x, 'name', None)\n",
    "the page's url": "def f(start_page):\n    assert start_page.page.url.endswith('/')\n",
    "a test-data path for an upload":
        "from pathlib import Path\nDATA = Path(__file__).parent / 'data' / 'a.png'\n"
        "def f(form_page):\n    form_page.upload_file('upload_field', DATA)\n"
        "    form_page.open('x')\n",
    "str.replace": "x = 'a'.replace('a', 'b')\n",
    "expect": "from playwright.sync_api import expect\ndef f(p):\n    expect(p.page).to_have_title('x')\n",
    "a relative import": "from .helpers import thing\n",
}


@pytest.mark.parametrize("source", SAFE.values(), ids=list(SAFE))
def test_ordinary_test_code_is_left_alone(source):
    assert _found(source) == []


def test_a_file_that_does_not_parse_is_left_to_the_other_validators():
    assert unsafe_calls("def (:\n") == []


def test_the_line_is_reported():
    assert unsafe_calls("x = 1\nimport os\ny = os.environ\n") == [(3, "uses `os.environ`")]


# ── the project's reviewed exceptions ─────────────────────────────────────────

def test_a_name_allowed_in_config_is_not_refused():
    source = "from pathlib import Path\nPath('reports/x.txt').write_text('y')\n"
    assert _found(source)
    assert _found(source, allow=["write_text"]) == []


def test_a_module_allowed_in_config_is_not_refused():
    assert _found("import shutil\n", allow=["shutil"]) == []


def test_the_settings_are_read_over_the_defaults():
    assert settings({}) == {"enabled": True, "allow": [], "code_dirs": list(CODE_DIRS)}
    got = settings({"enabled": False, "allow": ["write_text"], "code_dirs": ["src/tests/"]})
    assert got == {"enabled": False, "allow": ["write_text"], "code_dirs": ["src/tests/"]}
    # a wrong type keeps the default rather than switching the check off
    assert settings({"enabled": "no", "allow": "x", "code_dirs": []})["enabled"] is True


def test_the_shipped_config_turns_it_on():
    cfg = yaml.safe_load((ROOT / "config" / "config.yaml").read_text(encoding="utf-8"))
    block = cfg["agents"]["agent2_coder"]["code_safety"]
    assert block["enabled"] is True
    assert block["allow"] == []
    assert block["code_dirs"] == list(CODE_DIRS)


# ── Agent 2: repair, gate, plan ───────────────────────────────────────────────

def _gf(path, content):
    return SimpleNamespace(file_path=path, content=content)


def test_the_error_is_in_the_shape_the_repair_loop_reads():
    errors = validate_code_safety([_gf("tests/step_defs/test_x.py", "import os\nos.environ\n"),
                                   _gf("features/x.feature", "import os\n")],
                                  allow=[], enabled=True)
    assert len(errors) == 1
    assert errors[0].startswith("Unsafe code error in 'tests/step_defs/test_x.py': line 2 ")
    assert "page-object method" in errors[0]


def test_the_framework_s_own_files_in_a_batch_are_not_read():
    """A reserved base page or a conftest.py reads the environment on purpose;
    the path policy keeps generated code out of them, so the check does not
    read them when a batch carries one as context."""
    files = [_gf("pages/ref_page.py", "import os\nos.environ\n"),
             _gf("tests/step_defs/conftest.py", "import os\nos.getenv('X')\n"),
             _gf("pages/x_page.py", "import os\nos.environ\n")]
    errors = validate_code_safety(files, allow=[], enabled=True, trusted={"pages/ref_page.py"})
    assert [e.split("'")[1] for e in errors] == ["pages/x_page.py"]


def test_switched_off_it_reports_nothing():
    assert validate_code_safety([_gf("pages/x_page.py", "import os\nos.environ\n")],
                                allow=[], enabled=False) == []


def test_the_repair_loop_is_told_and_given_its_own_hint():
    import agents.agent2_coder as a2
    err = validate_code_safety([_gf("pages/x_page.py", "eval('1')\n")], allow=[], enabled=True)[0]
    assert a2._classify_error(err) == "unsafe_code"
    assert "UNSAFE CODE" in a2._build_error_type_guidance([err])
    gf = [a2.GeneratedFile(file_path="pages/x_page.py", content="eval('1')\n",
                           file_type="page_object")]
    assert any(e.startswith("Unsafe code error") for e in a2._collect_repairable_errors(gf))


def test_the_final_gate_refuses_what_the_repair_left(monkeypatch):
    import agents.agent2_coder as a2
    gf = [a2.GeneratedFile(file_path="tests/step_defs/test_x.py",
                           content="import subprocess\n", file_type="step_definitions")]
    with pytest.raises(a2.GateFailure, match="Code safety validation failed") as raised:
        a2._validate_generated_files(gf, "AB-1")
    assert any("imports `subprocess`" in e for e in raised.value.errors)


@pytest.mark.parametrize("path, refused", [
    ("pages/widget_page.py", False),
    ("tests/step_defs/test_widget.py", False),
    ("features/widget.feature", False),
    ("tests/step_defs/conftest.py", True),
    ("tests/conftest.py", True),
    ("pages/__init__.py", True),
    ("conftest.py", True),
    ("scripts/helper.py", True),
    ("agents/agent2_coder.py", True),
    ("tests/unit/test_x.py", True),
    ("./pages/widget_page.py", False),
])
def test_generated_python_lives_only_in_page_objects_and_step_definitions(path, refused):
    assert bool(code_path_problem(path)) is refused


def test_a_plan_that_writes_python_elsewhere_is_refused():
    import agents.agent2_coder as a2
    from core.app_context import AppContext
    from core.schemas import CodePlan, FilePlan
    plan = CodePlan(feature_name="x", branch_name="auto/X-1-x", pr_title="t", pr_body="b",
                    files_to_create=[FilePlan(file_path="tests/step_defs/conftest.py",
                                              file_type="step_definitions", purpose="p")])
    with pytest.raises(ValueError, match="where generated code may not live"):
        a2.validate_paths_against_policy(plan, AppContext.load())


# ── Agent 4: before the browser run ───────────────────────────────────────────

def test_only_the_pull_request_s_test_code_is_read():
    from scripts.check_code_safety import to_check
    got = to_check(["pages/a_page.py", "./tests/step_defs/test_a.py", "pages/base_page.py",
                    "tests/step_defs/conftest.py", "tests/unit/test_x.py", "features/a.feature",
                    "scripts/x.py", "pages/a_page.py"],
                   trusted={"pages/base_page.py"}, code_dirs=CODE_DIRS)
    assert got == ["pages/a_page.py", "tests/step_defs/test_a.py"]


def test_the_trusted_files_are_the_reserved_paths():
    from scripts.check_code_safety import trusted_paths
    assert trusted_paths({"app_under_test": {"reserved_paths": ["./pages/base_page.py"]}}) \
        == {"pages/base_page.py"}
    assert trusted_paths({}) == set()


def test_a_finding_is_listed_with_its_line(tmp_path):
    from scripts.check_code_safety import check
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "a_page.py").write_text("x = 1\nimport socket\n", encoding="utf-8")
    assert check(["pages/a_page.py", "pages/removed_page.py"], tmp_path) \
        == [("pages/a_page.py", 2, "imports `socket`")]


def test_a_file_that_cannot_be_read_is_a_finding_not_a_traceback(tmp_path, monkeypatch):
    from scripts.check_code_safety import check
    (tmp_path / "pages").mkdir()
    target = tmp_path / "pages" / "a_page.py"
    target.write_text("x = 1\n", encoding="utf-8")
    real = Path.read_text

    def unreadable(self, *a, **k):
        if self == target:
            raise PermissionError("denied")
        return real(self, *a, **k)
    monkeypatch.setattr(Path, "read_text", unreadable)
    assert check(["pages/a_page.py"], tmp_path) == [
        ("pages/a_page.py", 0, "could not be read (PermissionError) - not checked")]


def test_the_script_exits_1_on_a_finding_and_2_on_no_input(monkeypatch, capsys):
    import scripts.check_code_safety as script
    monkeypatch.setattr(script, "check", lambda paths, root, allow=(): [
        ("pages/a_page.py", 2, "imports `socket`")])
    assert script.main(["pages/a_page.py"]) == 1
    out = capsys.readouterr().out
    assert "::error file=pages/a_page.py,line=2::Unsafe code: imports `socket`" in out
    assert "browser run is not started" in out
    assert script.main([]) == 2


def test_the_script_reads_paths_from_stdin(monkeypatch, capsys):
    import scripts.check_code_safety as script
    seen = []
    monkeypatch.setattr(script, "check", lambda paths, root, allow=(): seen.extend(paths) or [])
    monkeypatch.setattr("sys.stdin", io.StringIO("pages/a_page.py\n\nREADME.md\n"))
    assert script.main(["--stdin"]) == 0
    assert seen == ["pages/a_page.py"]


def test_the_committed_test_code_passes():
    """Every page object and step definition the project has passes - the
    check refuses nothing the framework already runs."""
    import scripts.check_code_safety as script
    if not list((ROOT / "pages").glob("*_page.py")):
        pytest.skip("no page objects committed yet")
    assert script.main(["--all"]) == 0


def _job_with_the_check() -> tuple:
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "agent4_runner.yml")
                        .read_text(encoding="utf-8"))
    for name, job in wf["jobs"].items():
        if any(s.get("id") == "safety" for s in job.get("steps", [])):
            return name, job["steps"]
    raise AssertionError("no Agent 4 job runs the code safety check")


def test_agent4_checks_before_any_step_that_has_the_login():
    _job, steps = _job_with_the_check()
    ids = [s.get("id") for s in steps]
    at = ids.index("safety")
    check = steps[at]
    assert "scripts.check_code_safety --stdin" in check["run"]
    assert "scripts.check_code_safety --all" in check["run"]      # files not listable
    assert "pull_request" in check["if"]
    assert "APP_PASSWORD" not in str(check.get("env", {}))
    with_login = [i for i, s in enumerate(steps) if "secrets.APP_PASSWORD" in str(s.get("env", {}))]
    assert with_login and all(i > at for i in with_login)
    for i in with_login:
        assert "steps.safety.outcome != 'failure'" in steps[i]["if"], steps[i].get("name")


def test_a_refusal_is_explained_in_the_run_summary():
    """Found live (E258, run 44033374696): the check refused the code, the
    unit gate and the browser run were skipped, and the summary said only
    'Framework Unit Tests: no report' - a red job that did not say why."""
    _job, steps = _job_with_the_check()
    summary = next(s for s in steps if s.get("name", "").startswith("Write test summary"))
    assert summary["env"]["E2E_SAFETY"] == "${{ steps.safety.outcome }}"
    assert summary["if"] == "always()"
    assert 'os.environ.get("E2E_SAFETY")' in summary["run"]
    assert "Unsafe test code refused (S1)" in summary["run"]


# ── BasePage: the two doors the static check leaves open ──────────────────────

class _Page:
    def __init__(self, url="about:blank"):
        self.url = url
        self.went = []

    def goto(self, url, **_kw):
        self.went.append(url)
        return SimpleNamespace(ok=True, status=200, status_text="OK")

    def wait_for_timeout(self, _ms):
        pass


@pytest.fixture
def app_host(monkeypatch):
    from pages.base_page import BasePage
    monkeypatch.setattr(BasePage, "_NAV_HOSTS_CACHE", ("app.example", "docs.example"))
    monkeypatch.setattr(BasePage, "_NAV_RETRY_CACHE", ())
    monkeypatch.setattr(BasePage, "_wait_for_page_scripts", lambda self: None)
    return BasePage


@pytest.mark.parametrize("url", [
    "https://app.example/account", "https://www.app.example/", "https://shop.app.example/x",
    "https://docs.example/a", "about:blank", "/relative/path"])
def test_navigate_opens_the_application_s_hosts(app_host, url):
    page = _Page()
    app_host(page).navigate(url)
    assert page.went == [url]


@pytest.mark.parametrize("url", [
    "https://collector.example/?p=secret", "https://app.example.attacker.example/",
    "http://notapp.example/"])
def test_navigate_refuses_another_host(app_host, url):
    page = _Page()
    with pytest.raises(AssertionError, match="refused: that host is not the application's"):
        app_host(page).navigate(url)
    assert page.went == []


def test_the_host_the_browser_is_already_on_stays_reachable(app_host):
    """require_own_page()/confirm_arrival() re-open a path on the host the
    browser is on - reached by the application's own links."""
    page = _Page(url="https://partner.example/start")
    app_host(page).navigate("https://partner.example/catalogue")
    assert page.went == ["https://partner.example/catalogue"]


def test_without_a_base_url_nothing_is_refused(monkeypatch):
    from pages.base_page import BasePage
    monkeypatch.setattr(BasePage, "_NAV_HOSTS_CACHE", ())
    BasePage(_Page())._refuse_other_hosts("https://anywhere.example/")


def test_the_hosts_come_from_the_base_url_and_the_config(monkeypatch):
    from pages.base_page import BasePage
    monkeypatch.setattr(BasePage, "_NAV_HOSTS_CACHE", None)
    monkeypatch.setenv("BASE_URL", "https://staging.app.example/")
    hosts = BasePage._navigation_hosts()
    assert hosts[0] == "staging.app.example"
    monkeypatch.setattr(BasePage, "_NAV_HOSTS_CACHE", None)


def test_an_upload_attaches_only_a_project_file(tmp_path):
    from pages.base_page import BasePage
    from config.paths import PROJECT_ROOT
    inside = Path(PROJECT_ROOT) / "config" / "config.yaml"
    assert BasePage._uploadable(inside) == str(inside.resolve())
    assert BasePage._uploadable("config/config.yaml") == str(inside.resolve())
    outside = tmp_path / "x.txt"
    outside.write_text("x", encoding="utf-8")
    for refused in (outside, "/proc/self/environ", ".git/config", ".env",
                    "pages/../../outside.txt"):
        with pytest.raises(AssertionError, match="Upload of .* refused"):
            BasePage._uploadable(refused)


def test_an_upload_is_checked_before_it_is_attached(monkeypatch):
    from pages.base_page import BasePage
    attached = []
    obj = BasePage(_Page())
    monkeypatch.setattr(BasePage, "_wait_for_page_scripts", lambda self: None)
    monkeypatch.setattr(BasePage, "_locator", lambda self, loc: SimpleNamespace(
        set_input_files=attached.append))
    with pytest.raises(AssertionError):
        obj.upload_file("upload_field", "/etc/passwd")
    with pytest.raises(AssertionError):
        obj.upload_files("upload_field", ["config/config.yaml", ".git/config"])
    assert attached == []
    obj.upload_file("upload_field", "config/config.yaml")
    assert len(attached) == 1


# ── the model is told ─────────────────────────────────────────────────────────

def test_the_prompt_says_test_code_drives_the_application_and_nothing_else():
    text = (ROOT / "prompts" / "agent2_coder_generate.md").read_text(encoding="utf-8")
    section = text.split("## Test code drives the application, and nothing else", 1)[1]
    section = section.split("\n## ", 1)[0]
    for word in ("os.environ", "subprocess", "evaluate", "fixtures", "page-object"):
        assert word in section
    assert re.search(r"renamed or\s+not", section)
