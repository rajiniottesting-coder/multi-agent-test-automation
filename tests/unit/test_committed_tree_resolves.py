"""Every method a COMMITTED step definition calls must still exist.

THE CASE THIS CATCHES
    Agent 2 opens a pull request whose step definitions call search_for().
    Someone renames that method to search_catalogue() on their own branch and
    merges first. Agent 2's branch is now stale in a way nothing notices:
    validate_method_resolution ran at generation time and does not run again,
    the diff still looks correct in isolation, and Agent 3 reviews the diff
    rather than the merged tree.

    It surfaces as an AttributeError when Agent 4 executes the suite - after
    Playwright has installed, launched a browser and signed in. Three minutes
    of CI to discover a rename.

WHY A UNIT TEST RATHER THAN A GATE
    The generation gate cannot help: it runs before the branch exists, and the
    breakage is introduced by a DIFFERENT branch afterwards. But GitHub checks
    out the merge result for a pull_request event, so this test sees exactly
    the tree Agent 4 would execute - and it sees it in seconds, with no
    browser, naming the method rather than reporting an AttributeError from
    somewhere inside a page object.

    Third time this shape has earned its keep: one rule, applied both at the
    gate and to what is committed.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from validators.method_resolution_validator import validate_method_resolution

_PROJECT = Path(__file__).resolve().parents[2]


def _committed_files() -> list:
    """Step definitions and page objects, as the validator expects them."""
    paths = sorted(_PROJECT.joinpath("tests", "step_defs").glob("test_*.py"))
    paths += sorted(_PROJECT.joinpath("pages").glob("*_page.py"))
    return [
        SimpleNamespace(
            file_path=str(p.relative_to(_PROJECT)).replace("\\", "/"),
            content=p.read_text(encoding="utf-8"),
        )
        for p in paths
    ]


def test_every_committed_step_def_calls_a_method_that_exists():
    files = _committed_files()
    if not any(f.file_path.startswith("tests/step_defs/") for f in files):
        pytest.skip("no step definitions committed yet")

    errors = validate_method_resolution(files, _PROJECT)
    assert not errors, (
        "a committed step definition calls a page-object method that does not "
        "exist. The usual cause is a rename landing on main while another "
        "branch was open: the diff looked correct in isolation, and nothing "
        "re-checked the two together. Rename the call, or restore the "
        "method.\n  " + "\n  ".join(errors))


def test_the_check_sees_both_halves():
    """A guard on the guard: if the file collection ever stopped picking up
    step definitions, the test above would pass by looking at nothing.

    Skips rather than fails when a half is genuinely absent. A freshly
    onboarded application has page objects and no step definitions yet, and a
    FRAMEWORK test must not fail simply because Agent 2 has not run - that
    turns "nothing generated yet" into a red suite on day one.
    """
    kinds = {f.file_path.split("/")[0] for f in _committed_files()}
    if "tests" not in kinds:
        pytest.skip("no step definitions committed yet - nothing to resolve")
    assert "pages" in kinds, \
        "step definitions exist but no page objects - the check is vacuous"


# =========================================================================
# THE SAME RULE, ONE STAGE EARLIER
#
# The check above reads what is COMMITTED, and it works - it is what caught
# the failure this section exists for. But it caught it on the branch, after
# Agent 2 had spent its budget and opened a pull request. The unit gate went
# red, then three reference E2E tests died on AttributeError.
#
# What happened: a story regenerated the shared navigation page object. Agent 2
# emits a whole file, not a patch, so the replacement kept the two methods that
# story needed and dropped eight it did not - three of which the reference
# login suite calls.
#
# Every check in the batch passed, correctly. The generated step definitions
# resolved perfectly against the generated page object. The callers that
# noticed were already on main and were never in the batch to speak for
# themselves.
#
# validate_method_resolution now reads the current file from disk as well, so
# the same rule applies while the file can still be repaired.
# =========================================================================

def _snake(name: str) -> str:
    import re
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _page_object(class_name: str, rel: str, methods: list):
    """A generated replacement for `rel`, defining only `methods`."""
    from types import SimpleNamespace
    body = "\n".join(f"    def {m}(self) -> None:\n        pass\n" for m in methods)
    return SimpleNamespace(
        file_path=rel,
        content=("from pages.base_page import BasePage\n\n\n"
                 f"class {class_name}(BasePage):\n"
                 f'    INVENTORY_PAGE = "a_page"\n\n' + body),
    )


def _a_page_object_with_committed_callers():
    """(class_name, relative path, its public methods) - discovered, not named.

    Which page object is this application's business. The check is about the
    SHAPE - a regeneration that drops a method somebody else still calls - so
    the test finds a page object that has callers rather than hardcoding one,
    and works unchanged when the framework is pointed at a different
    application.
    """
    import ast
    import re

    step_defs = {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(_PROJECT.joinpath("tests", "step_defs").glob("test_*.py"))
    }
    for path in sorted(_PROJECT.joinpath("pages").glob("*_page.py")):
        if path.name == "base_page.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for cls in tree.body:
            if not isinstance(cls, ast.ClassDef):
                continue
            methods = [n.name for n in cls.body
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                       and not n.name.startswith("_")]
            fixture = _snake(cls.name)
            called = [m for m in methods
                      if any(re.search(rf"\b{fixture}\.{m}\s*\(", src)
                             for src in step_defs.values())]
            if len(called) >= 1 and len(methods) > len(called):
                return cls.name, f"pages/{path.name}", methods, called
    return None


def test_dropping_a_method_a_committed_step_def_calls_is_rejected():
    """The exact regeneration that broke the build, in shape."""
    from validators.method_resolution_validator import validate_method_resolution

    found = _a_page_object_with_committed_callers()
    if not found:
        pytest.skip("no committed page object has callers outside its own batch")
    class_name, rel, methods, called = found

    # Keep everything EXCEPT the methods somebody still calls.
    kept = [m for m in methods if m not in called]
    errors = [e for e in validate_method_resolution(
        [_page_object(class_name, rel, kept)], _PROJECT)
        if "no longer defines" in e]

    assert errors, (
        "a regeneration that drops methods the committed step definitions call "
        "must be rejected at the generation gate, not discovered on the branch"
    )
    assert any("tests/step_defs/" in e for e in errors), "name who still calls it"


def test_keeping_every_method_is_accepted():
    """Break the thing the guard guards. A story that ADDS a method to a shared
    page object is the normal case and must not be blocked."""
    from validators.method_resolution_validator import validate_method_resolution

    found = _a_page_object_with_committed_callers()
    if not found:
        pytest.skip("no committed page object has callers outside its own batch")
    class_name, rel, methods, _ = found

    errors = [e for e in validate_method_resolution(
        [_page_object(class_name, rel, methods + ["do_something_new"])], _PROJECT)
        if "no longer defines" in e]

    assert not errors, "adding a method must be allowed:\n  " + "\n  ".join(errors)


def test_a_brand_new_page_object_is_not_judged():
    """Nothing on disk to compare against, so nothing was removed."""
    from validators.method_resolution_validator import validate_method_resolution

    errors = [e for e in validate_method_resolution(
        [_page_object("NoSuchPage", "pages/no_such_page.py", ["do_a_thing"])],
        _PROJECT)
        if "no longer defines" in e]
    assert not errors


# =========================================================================
# NO APPLICATION VOCABULARY IN A FRAMEWORK FILE
#
# The golden rule's acceptance test - swap the application, run the suite -
# passes even with app names scattered through comments and fixtures, because
# those are synthetic strings rather than lookups. So it never caught them,
# and forty-one accumulated: page-object class names in a validator docstring,
# inventory element keys quoted in a test, a CSS id in a ranking fixture.
#
# Hand-written token lists did not catch them either. Every sweep in this
# project was a list of words somebody thought of, and it missed whatever
# nobody thought of.
#
# So the vocabulary is HARVESTED from the application's own permitted homes -
# its inventory and its page objects - and every framework file is scanned for
# it. A token this application coins cannot be in a framework file, whoever
# adds it and whatever they call it.
#
# Only COINED tokens count: element keys, page-object class and method names,
# and structural selector fragments. Ordinary English that happens to appear
# in the application's UI text is not its property - a comment may say
# "address" without meaning the app's address field.
# =========================================================================

# Names that are POM convention everywhere, not this application's property.
_CONVENTIONAL = frozenset({
    "LoginPage", "NavPage", "HomePage", "BasePage",
    "login_page", "nav_page", "home_page", "base_page",
    "login_as", "is_loaded", "page_url", "open_login_page", "clear_credentials",
    "data-qa", "data-test", "data-testid", "data-cy",
    # The framework's own vocabulary: an application may name a page after it
    # (4 Nov 2026: a "test_cases" page), which does not make the framework's
    # TestCaseList.test_cases the application's. "Test Cases" likewise is
    # the framework's Jira issue type, whatever page an application has.
    "test_cases", "Test Cases",
})

_FRAMEWORK_PATHS = (
    "agents", "core", "validators", "integrations", "inventory_tools",
    "scripts", "pages/base_page.py", "tests/unit", "tests/conftest.py",
    "tests/step_defs/conftest.py",
)
# Every agent prompt is framework, whichever agent it belongs to. A glob, not
# a list: a list missed agent0_*.md and agent1_impact_aware.md when they were
# added, and would miss the next prompt the same way. prompts/app_context/ is
# the application's own notes and is deliberately not matched.
_FRAMEWORK_PROMPT_GLOB = "agent*.md"


def _coined_by_the_application() -> dict:
    """{token: where it was coined} from the inventory and the page objects."""
    import ast as _ast
    import json
    import re

    import yaml

    coined: dict = {}

    def add(token, kind):
        text = str(token).strip()
        distinctive = (len(text) >= 5 and re.search(r"[_\-.#\[]", text)) or (
            len(text) >= 6 and text[:1].isupper()) or (
            len(text) >= 6 and " " in text and text[:1].isupper())
        if distinctive and text not in _CONVENTIONAL:
            coined.setdefault(text, kind)

    config = yaml.safe_load(
        (_PROJECT / "config" / "config.yaml").read_text(encoding="utf-8"))
    app = config.get("app_under_test") or {}

    inventory_path = _PROJECT / app.get("inventory_file", "")
    if inventory_path.is_file():
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        for entry in (inventory.get("pages") or {}).values():
            if not isinstance(entry, dict):
                continue
            add(entry.get("page_object_class", ""), "page-object class")
            for key, selector in (entry.get("elements") or {}).items():
                add(key, "inventory element key")
                for fragment in re.findall(r"[#.\[][\w\-\[\]='\"]{4,}", str(selector)):
                    add(fragment.strip("'\"[]"), "selector fragment")

    # Page-object CLASS names only. Method names are deliberately NOT
    # harvested: they are shared vocabulary, not coined. Two unrelated
    # applications both have sign_in(), is_empty(), submit() - flagging those
    # would report a framework file for using ordinary POM verbs, and a check
    # that cries wolf gets deleted.
    #
    # Nothing is lost by the omission: every one of the forty-one leaks this
    # scan first found was an element key, a class name or a selector
    # fragment. Not one was a method name.
    for path in sorted((_PROJECT / "pages").glob("*_page.py")):
        if path.name == "base_page.py":
            continue
        for cls in _ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(cls, _ast.ClassDef):
                add(cls.name, "page-object class")

    # The same application also names things through its FILES and PAGES.
    # A framework test quoted `features/<story>.feature` and
    # `pages/<app>_page.py` verbatim and passed, because only class names,
    # element keys and selector fragments were harvested.
    reserved = {str(p).replace("\\", "/") for p in (app.get("reserved_paths") or [])}
    if inventory_path.is_file():
        for page_key, entry in (inventory.get("pages") or {}).items():
            add(page_key, "inventory page key")
            if not isinstance(entry, dict):
                continue
            add(Path(str(entry.get("page_object_file", ""))).stem, "page-object file")
            for segment in re.split(r"[/?#]", str(entry.get("url", ""))):
                if "{" not in segment:
                    add(segment, "page URL path")
    for folder, pattern, kind in (("features", "*.feature", "feature file"),
                                  ("tests/step_defs", "test_*.py", "step-definition file"),
                                  ("pages", "*_page.py", "page-object file")):
        for path in sorted((_PROJECT / folder).glob(pattern)):
            if f"{folder}/{path.name}" in reserved or path.name == "base_page.py":
                continue
            add(path.stem, kind)
            add(path.stem.removeprefix("test_"), kind)

    # ...and through its DATA. The app's own context modules quote the values
    # its scenarios use - record names, UI labels - in backticks. A multi-word
    # value made only of words is data, not code: harvested. Paths, code and
    # single words are not, so ordinary vocabulary is never flagged.
    for md in sorted((_PROJECT / "prompts" / "app_context").glob("*.md")):
        for value in re.findall(r"`([A-Z][A-Za-z0-9]*(?: [A-Za-z0-9]+)+)`",
                                md.read_text(encoding="utf-8")):
            add(value, "application data value")

    # ...and through its UI TEXT, its NAME and its TRACKER (9 Nov 2026: framework
    # comments and tests quoted a page heading, a link's email address and the
    # project's issue keys, none of which the harvest above sees).
    # UI text a selector quotes (an ARIA name, a has-text value): only several
    # words or an address - a single word ("Submit") is ordinary vocabulary.
    if inventory_path.is_file():
        for entry in (inventory.get("pages") or {}).values():
            for selector in ((entry or {}).get("elements") or {}).values():
                for text in re.findall(r"""['"]([^'"]{3,})['"]""", str(selector)):
                    if " " in text.strip() or "@" in text:
                        add(text.strip(), "UI text in a selector")
    # The application's own name and host.
    add(str(app.get("name", "")), "application name")
    host = re.sub(r"^\w+://(www\.)?", "", str(app.get("base_url", ""))).split("/")[0]
    if host:
        coined.setdefault(host.split(".")[0], "application host")
    # Its tracker's issue keys: the project key on the markers of its own
    # feature files. Framework fixtures use invented keys (AB-1, PROJ-7).
    for path in sorted((_PROJECT / "features").glob("*.feature")):
        for prefix in re.findall(r"#\s*JIRA:\s*([A-Z][A-Z0-9]+)-\d+",
                                 path.read_text(encoding="utf-8")):
            coined.setdefault(f"{prefix}-", "issue key of the application's project")
    return coined


def _framework_files() -> list:
    files = []
    for entry in _FRAMEWORK_PATHS:
        path = _PROJECT / entry
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files += [f for f in path.rglob("*")
                      if f.suffix in (".py", ".md") and "__pycache__" not in f.parts]
    files += sorted((_PROJECT / "prompts").glob(_FRAMEWORK_PROMPT_GLOB))
    return files


def test_every_agent_prompt_is_scanned_by_the_golden_rule():
    """The scan covers each prompt an agent loads, and no application notes."""
    scanned = {f.relative_to(_PROJECT).as_posix() for f in _framework_files()}
    prompts = {f"prompts/{p.name}" for p in (_PROJECT / "prompts").glob("*.md")
               if p.name.startswith("agent")}
    assert prompts and prompts <= scanned, sorted(prompts - scanned)
    assert {"prompts/agent0_seeds.md", "prompts/agent1_impact_aware.md"} <= scanned
    assert not any(s.startswith("prompts/app_context/") for s in scanned)


def _leak_pattern(token: str):
    """Where `token` names the application in a line of a framework file.

    A class or id fragment (`.banner`, `#total`) after `)` or `]` is a Python
    attribute (`checks["size"].banner`), not a selector: an inventory page
    added on 3 Nov 2026 used a CSS class that is also a common attribute name,
    and every such attribute in the framework's tests read as a leak. In a
    string, after a space, quote or paren-open it is still one."""
    import re
    if token.endswith("-"):                     # an issue-key prefix: KEY-<number>
        return re.compile(r"(?<![\w\-])" + re.escape(token) + r"\d+")
    before = r"(?<![\w\-)\]])" if token[:1] in ".#" else r"(?<![\w\-])"
    return re.compile(before + re.escape(token) + r"(?![\w\-])")


def test_no_framework_file_names_anything_the_application_coins():
    import re

    coined = _coined_by_the_application()
    if not coined:
        pytest.skip("no inventory or page objects to harvest a vocabulary from")

    files = _framework_files()
    assert files, "no framework files found - the scan would be vacuous"

    offences = []
    for token, kind in coined.items():
        pattern = _leak_pattern(token)
        for path in files:
            text = path.read_text(encoding="utf-8", errors="replace")
            for number, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    rel = path.relative_to(_PROJECT)
                    offences.append(f"{rel}:{number}  {token}  ({kind})")

    assert not offences, (
        f"{len(offences)} application-specific name(s) in framework files. "
        f"These come from the inventory and the page objects, which are where "
        f"app knowledge belongs - a framework file naming one cannot be "
        f"pointed at a different application without reading as a lie:\n  "
        + "\n  ".join(sorted(offences)[:25])
        + ("\n  ..." if len(offences) > 25 else "")
    )


def test_the_scan_would_notice_a_leak():
    """Break the thing the guard guards.

    A harvester that returns nothing, or a pattern that matches nothing, would
    make the test above pass by doing nothing at all.
    """
    import re

    coined = _coined_by_the_application()
    assert len(coined) >= 10, (
        f"only {len(coined)} coined token(s) harvested - the scan is too thin "
        f"to be protecting anything"
    )

    kinds = set(coined.values())
    for kind in ("issue key of the application's project", "application name",
                 "application host"):
        assert kind in kinds, f"the harvest no longer sees the application's {kind}"
    key = next(t for t, k in coined.items() if k.startswith("issue key"))
    assert _leak_pattern(key).search(f"# seen on {key}293's pull request")
    assert not _leak_pattern(key).search(f"x = '{key}'"), "a bare prefix is not a key"

    sample = sorted(coined)[0]
    pattern = _leak_pattern(sample)
    assert pattern.search(f"    self.click(self.sel(\"{sample}\"))"), (
        "the pattern does not match its own token in a realistic line"
    )

@pytest.mark.parametrize("line, leak", [
    ('    self.click(self.sel(".banner"))', True),
    ("    page.locator('.banner').click()", True),
    ("    css = .banner", True),
    ('    assert checks["size"].banner == WARN', False),       # attribute access
    ("    assert result().banner == OK", False),
    ("    assert obj.banner", False),
])
def test_a_dotted_fragment_is_a_selector_not_an_attribute(line, leak):
    assert bool(_leak_pattern(".banner").search(line)) is leak
    assert _leak_pattern("banner_key").search("x = banner_key") is not None
