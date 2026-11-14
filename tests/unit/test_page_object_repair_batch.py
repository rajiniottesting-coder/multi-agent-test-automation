"""Which page objects Agent 2's repair loop repairs, and in what order: a
committed page object the steps need a method on joins the batch, page objects
are repaired before the files that call them, a step file is not repaired on
feedback a page repair just answered, and a reserved page object's missing
method is kept for a person.
"""

from __future__ import annotations


def test_a_committed_page_object_missing_a_called_method_joins_the_batch(tmp_path, monkeypatch):
    """4 Nov 2026: the steps called a method missing from a committed page
    object; the plan had not named that page object, so only the step definitions were
    repaired, and the story was refused after every attempt."""
    import agents.agent2_coder as a2
    import validators.method_resolution_validator as v
    from core.schemas import CodePlan, GeneratedFile
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "front_page.py").write_text("class FrontPage: ...\n")
    (tmp_path / "pages" / "menu_page.py").write_text("class MenuPage: ...\n")
    monkeypatch.setattr(v, "_reserved_page_files", lambda: {"pages/menu_page.py"})
    steps = GeneratedFile(file_path="tests/step_defs/test_x.py", content="# steps")
    from core.schemas import FilePlan
    own = FilePlan(file_path="tests/step_defs/test_x.py", file_type="step_definitions",
                   purpose="steps")
    plan = CodePlan(feature_name="x", branch_name="auto/AB-1-x", pr_title="t", pr_body="b",
                    notes="", files_to_create=[own])
    err = ("Method resolution error in 'tests/step_defs/test_x.py': line {n} calls "
           "`front.{m}()`, but `FrontPage` does not define `{m}`. Did you mean ...")
    errors = [err.format(n=3, m="go_to_reports"), err.format(n=9, m="has_reports_link"),
              ("Method resolution error in 'tests/step_defs/test_x.py': line 5 calls "
               "`menu.open_reports()`, but `MenuPage` does not define `open_reports`. ...")]
    batch = [steps]
    feedback = a2._bring_in_page_objects(batch, plan, errors, root=tmp_path)
    assert [f.file_path for f in batch] == ["pages/front_page.py", "tests/step_defs/test_x.py"]
    assert batch[0].content == "class FrontPage: ...\n" and batch[0].is_new_file is False
    assert [fp.file_path for fp in plan.files_to_create] == ["pages/front_page.py",
                                                             "tests/step_defs/test_x.py"]
    (fb,) = feedback
    assert fb.startswith("Page object error in 'pages/front_page.py':")
    assert "`go_to_reports()`, `has_reports_link()`" in fb and "keep every existing method" in fb
    assert list(a2._group_validator_errors_by_file(feedback)) == ["pages/front_page.py"]
    # next attempt: still missing -> the feedback again, the file not added twice
    again = a2._bring_in_page_objects(batch, plan, errors[:1], root=tmp_path)
    assert len(again) == 1 and len(batch) == 2 and len(plan.files_to_create) == 2


def test_a_page_object_the_model_planned_is_not_given_extra_feedback(tmp_path, monkeypatch):
    import agents.agent2_coder as a2
    import validators.method_resolution_validator as v
    from core.schemas import CodePlan, GeneratedFile
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "front_page.py").write_text("class FrontPage: ...\n")
    monkeypatch.setattr(v, "_reserved_page_files", lambda: set())
    batch = [GeneratedFile(file_path="pages/front_page.py", content="planned", is_new_file=False,
                           purpose="the plan's own extension")]
    from core.schemas import FilePlan
    plan = CodePlan(feature_name="x", branch_name="b", pr_title="t", pr_body="b", notes="",
                    files_to_create=[FilePlan(file_path="pages/front_page.py",
                                              file_type="page_object", purpose="p")])
    err = ("Method resolution error in 'tests/step_defs/test_x.py': line 3 calls "
           "`front.go()`, but `FrontPage` does not define `go`.")
    assert a2._bring_in_page_objects(batch, plan, [err], root=tmp_path) == []
    assert len(batch) == 1


def test_the_repair_loop_extends_the_page_object_and_the_error_goes(tmp_path, monkeypatch):
    import agents.agent2_coder as a2
    import validators.method_resolution_validator as v
    from core.schemas import CodePlan, FilePlan, GeneratedFile
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "front_page.py").write_text("class FrontPage:\n    pass\n")
    monkeypatch.setattr(a2, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(v, "_reserved_page_files", lambda: set())
    err = ("Method resolution error in 'tests/step_defs/test_x.py': line 3 calls "
           "`front.go_to_reports()`, but `FrontPage` does not define `go_to_reports`.")

    def errors(files):
        page = next((f for f in files if f.file_path == "pages/front_page.py"), None)
        return [] if page and "def go_to_reports" in page.content else [err]
    monkeypatch.setattr(a2, "_collect_repairable_errors", errors)
    monkeypatch.setattr(a2, "_absence_claim_errors", lambda *a: [])
    repaired = []

    def generate(llm, fp, plan, *a, previous_attempt="", **k):
        repaired.append(fp.file_path)
        if fp.file_path == "pages/front_page.py":
            return previous_attempt + "\n    def go_to_reports(self):\n        pass\n"
        return previous_attempt
    monkeypatch.setattr(a2, "generate_file_content", generate)
    monkeypatch.setattr(a2, "_is_degraded_regeneration", lambda *a: False)
    steps = GeneratedFile(file_path="tests/step_defs/test_x.py", content="# steps")
    plan = CodePlan(feature_name="x", branch_name="b", pr_title="t", pr_body="b", notes="",
                    files_to_create=[FilePlan(file_path="tests/step_defs/test_x.py",
                                              file_type="step_definitions", purpose="s")])
    out = a2._attempt_step_coverage_repair([steps], None, plan, [], {}, "", None)
    assert repaired[0] == "pages/front_page.py", "the page object is repaired first"
    page = next(f for f in out if f.file_path == "pages/front_page.py")
    assert "def go_to_reports" in page.content and errors(out) == []


def test_a_step_file_is_not_repaired_on_feedback_a_page_repair_just_answered(tmp_path, monkeypatch):
    """10 Nov 2026 (validation item E90, Agent 2 run 42825326200): the joined page
    object was repaired first and gained the six methods the steps call, but
    the steps' feedback - computed before - still said the class did not
    define them. The steps' repair believed it and moved the calls to a
    reserved page object; the story was refused. Stale items are dropped."""
    import agents.agent2_coder as a2
    import validators.method_resolution_validator as v
    from core.schemas import CodePlan, FilePlan, GeneratedFile
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "front_page.py").write_text("class FrontPage:\n    pass\n")
    monkeypatch.setattr(v, "_reserved_page_files", lambda: set())
    monkeypatch.setattr(a2, "PROJECT_ROOT", tmp_path)
    err = ("Method resolution error in 'tests/step_defs/test_x.py': line 3 calls "
           "`front_page.go_to_reports()`, but `FrontPage` does not define `go_to_reports`. "
           "Did you mean one of: go_to_help?")

    def errors(files):
        page = next((f.content for f in files if f.file_path == "pages/front_page.py"), "")
        return [] if "def go_to_reports" in page else [err]
    monkeypatch.setattr(a2, "_collect_repairable_errors", errors)
    monkeypatch.setattr(a2, "_absence_claim_errors", lambda files, tcs: [])
    repaired = []

    def regenerate(llm, target_plan, plan, *a, **k):
        repaired.append((target_plan.file_path, list(k["validator_feedback"])))
        if target_plan.file_path == "pages/front_page.py":
            return ('"""The front page."""\n\n\nclass FrontPage:\n'
                    '    """Reads and acts on the front page through its inventory keys."""\n\n'
                    "    def go_to_reports(self):\n"
                    '        """Open the reports page from the front page\'s link."""\n'
                    "        return self.click(self.sel('reports_link'))\n" + "\n" * 0
                    + "".join(f"\n    def keep_{i}(self):\n        \"\"\"An existing method kept "
                              f"as it was.\"\"\"\n        return {i}\n" for i in range(8)))
        return "# steps rewritten on stale feedback"
    monkeypatch.setattr(a2, "generate_file_content", regenerate)
    steps = GeneratedFile(file_path="tests/step_defs/test_x.py", content="# steps")
    plan = CodePlan(feature_name="x", branch_name="b", pr_title="t", pr_body="b", notes="",
                    files_to_create=[FilePlan(file_path="tests/step_defs/test_x.py",
                                              file_type="step_definitions", purpose="steps")])
    out = a2._attempt_step_coverage_repair([steps], None, plan, [], {}, "", None)
    assert [path for path, _fb in repaired] == ["pages/front_page.py"], \
        "the steps are not rewritten on feedback the page repair answered"
    assert next(f.content for f in out if f.file_path.endswith("test_x.py")) == "# steps"
    assert errors(out) == []


def test_page_objects_are_repaired_before_the_files_that_call_them():
    import agents.agent2_coder as a2
    order = a2._page_objects_first({"tests/step_defs/test_x.py": ["a"],
                                    "features/x.feature": ["b"], "pages/x_page.py": ["c"]})
    assert list(order)[0] == "pages/x_page.py"
    defined = a2._methods_defined("class XPage:\n    def go(self):\n        pass\n")
    assert ("XPage", "go") in defined
    other = ("Method resolution error in 'tests/step_defs/test_x.py': line 3 calls "
             "`x_page.stay()`, but `XPage` does not define `stay`.")
    assert a2._still_missing([other], defined) == [other]


def test_a_reserved_page_objects_missing_method_seen_in_the_repair_is_kept(monkeypatch):
    """11 Nov 2026 (validation Run L): the steps needed two methods a RESERVED page
    object lacks; the repair stood the login error in for the signup error, and
    the refusal named only that stand-in - advising an inventory element the
    inventory already had. The reserved need is kept for the refusal."""
    import agents.agent2_coder as a2
    from core import blocked
    from core.schemas import CodePlan, FilePlan, GeneratedFile
    reserved = ("Method resolution error in 'tests/step_defs/test_x.py': line 50 calls "
                "`login_page.get_signup_error()`, but `LoginPage` does not define "
                "`get_signup_error`. `pages/login_page.py` is a RESERVED file - Agent 2 must "
                "not modify it")
    rounds = iter([[reserved], []])
    monkeypatch.setattr(a2, "_collect_repairable_errors", lambda files: next(rounds, []))
    monkeypatch.setattr(a2, "_absence_claim_errors", lambda files, tcs: [])
    monkeypatch.setattr(a2, "generate_file_content", lambda *a, **k: "x = 1\n" * 200)
    steps = GeneratedFile(file_path="tests/step_defs/test_x.py", content="x = 0\n" * 200)
    plan = CodePlan(feature_name="x", branch_name="b", pr_title="t", pr_body="b", notes="",
                    files_to_create=[FilePlan(file_path="tests/step_defs/test_x.py",
                                              file_type="step_definitions", purpose="s")])
    needs: dict = {}
    a2._attempt_step_coverage_repair([steps], None, plan, [], {}, "", None,
                                     reserved_needs=needs)
    assert list(needs) == ["`LoginPage.get_signup_error` (pages/login_page.py)"]
    text = blocked.blocked_comment("AB-1", "fp", list(needs.values()) + ["Step fidelity error x"])
    assert "reserved page object does not offer" in text and "LoginPage.get_signup_error" in text
