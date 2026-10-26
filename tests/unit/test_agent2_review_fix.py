"""Agent 2's review fix: a person's review comments become a checked fix on the
same pull request - or a clear answer why not.

Before it, no agent read a review comment: the reviewer fixed the code by hand
or regenerated the whole story. Every safeguard below is one way an automatic
fix could do harm: change a file another story owns, change what the approved
test cases verify, push code the gate refuses, loop on its own comments, or
act twice on one review.

Fake host, tracker and model; no network, no application names.
"""
from pathlib import Path

import pytest
import yaml

import agents.agent2_coder as a2
import agents.agent2_review_fix as rf
from core.schemas import ReviewFixDecision, ReviewFixPlan

ROOT = Path(__file__).resolve().parents[2]
HEAD = "auto/S-7-checkout"

FEATURE = """Feature: Checkout
  As a returning customer
  I want to pay with what I saved
  So that checking out takes one step

  # JIRA: S-8 (hash: aaaaaaaa)
  Scenario: Pay with a saved card
    Given I am on the checkout page
    When I pay with my saved card
    Then the order should be confirmed
    And the confirmation should show the order number

  # JIRA: S-9 (hash: cccccccc)
  Scenario: A declined card keeps the order open
    Given I am on the checkout page
    When I pay with a card the bank declines
    Then the order should still be open
    And the payment error should be shown
"""
STEPS = '''from pytest_bdd import given, when, then


@given("I am on the checkout page")
def open_checkout(checkout_page):
    checkout_page.open()


@when("I pay with my saved card")
def pay_saved(checkout_page):
    checkout_page.pay_with_saved_card()


@then("the order should be confirmed")
def order_confirmed(checkout_page):
    assert checkout_page.is_confirmed(), "the order was not confirmed"


@then("the confirmation should show the order number")
def order_number_shown(checkout_page):
    assert checkout_page.order_number(), "no order number was shown"
'''
PAGE = '''from pages.base_page import BasePage


class CheckoutPage(BasePage):
    \"\"\"The checkout page: pay, then read the outcome.\"\"\"

    def open(self) -> None:
        self.navigate("/checkout")

    def pay_with_saved_card(self) -> None:
        self.click(self.sel("pay_saved_card"))

    def is_confirmed(self) -> bool:
        return self.is_showing(self.sel("confirmation"))

    def order_number(self) -> str:
        return self.get_text(self.sel("order_number"))
'''
OWNER_FEATURE = "Feature: Cart\n\n  # JIRA: S-2 (hash: bbbbbbbb)\n  Scenario: Empty cart\n    Given x\n"


class FakeHost:
    def __init__(self, state="open", head=HEAD, comments=(), inline=()):
        self.meta = {"number": 5, "title": "S-7 checkout", "body": "", "head_branch": head,
                     "base_branch": "main", "state": state, "author": "bot", "url": "u"}
        self.comments = list(comments)
        self.inline = list(inline)
        self.files = {"features/checkout.feature": FEATURE,
                      "tests/step_defs/test_checkout.py": STEPS,
                      "pages/checkout_page.py": PAGE,
                      "features/cart.feature": OWNER_FEATURE}
        self.changed = [{"filename": "features/checkout.feature", "status": "added"},
                        {"filename": "tests/step_defs/test_checkout.py", "status": "added"},
                        {"filename": "pages/checkout_page.py", "status": "modified"},
                        {"filename": "features/cart.feature", "status": "modified"},
                        {"filename": "docs/notes.md", "status": "modified"}]
        self.pushed, self.replies, self.inline_reads = {}, [], []

    def get_pr_metadata(self, n): return self.meta
    def get_pr_comments(self, n): return list(self.comments)
    def get_review_comments(self, n, review_id=None):
        self.inline_reads.append(review_id)
        return [c for c in self.inline if review_id is None or c["review_id"] == review_id]
    def get_pr_changed_files(self, n): return self.changed
    def get_file_content(self, path, branch="main"):
        assert branch == HEAD
        return self.files[path]
    def create_or_update_file(self, path, content, commit_message, branch):
        assert branch == HEAD
        self.pushed[path] = content
    def post_pr_comment(self, n, body): self.comments.append(body)
    def reply_to_review_comment(self, n, comment_id, body): self.replies.append((comment_id, body))


class FakeTracker:
    def __init__(self): self.added = []
    def get_story(self, key): return {"key": key, "summary": "Checkout", "description": "Pay",
                                      "components": []}
    def get_linked_test_cases(self, key): return [{"key": "S-8", "summary": "[Positive] Pay with a saved card",
                                                    "description": "Steps"}]
    def add_comment(self, key, body): self.added.append((key, body))


class FakeLLM:
    def __init__(self, decisions):
        self.decisions, self.calls = decisions, 0
    def invoke_structured(self, system_prompt, user_prompt, output_schema):
        self.calls += 1
        self.prompt = user_prompt
        return ReviewFixPlan(decisions=[ReviewFixDecision(**d) for d in self.decisions])


class FakeCtx:
    def reserved_paths_normalized(self): return {"features/reference.feature"}
    def load_reference_files(self): return {}
    def load_page_inventory_json(self, components=None): return "{}"


def _inline(cid=11, path="pages/checkout_page.py", body="Wait for the pay button before clicking it.",
            review_id=99, author="person"):
    return {"id": cid, "path": path, "line": 6, "body": body, "author": author, "review_id": review_id}


@pytest.fixture
def wired(monkeypatch):
    """generate / repair / gate replaced by recorders the tests steer."""
    state = {"generated": [], "gate_error": None, "new": {}, "repair": None}

    def generate(llm, fp, plan, test_cases, references, page_inventory, ctx, **kw):
        state["generated"].append((fp.file_path, kw.get("review_feedback")))
        assert kw.get("previous_attempt") is not None
        return state["new"].get(fp.file_path, kw["previous_attempt"] + "\n# changed\n")

    def repair(batch, *args, **kwargs):
        return state["repair"](batch) if state["repair"] else batch

    def gate(batch, story_id, test_cases=None):
        if state["gate_error"]:
            raise ValueError(state["gate_error"])

    monkeypatch.setattr(a2, "generate_file_content", generate)
    monkeypatch.setattr(a2, "_attempt_step_coverage_repair", repair)
    monkeypatch.setattr(a2, "_validate_generated_files", gate)
    monkeypatch.setattr(rf, "settings", lambda: {"enabled": True, "command": "/fix",
                                                 "branch_prefix": "auto/", "max_files": 6})
    return state


def _run(host, llm, **kw):
    return rf.run(5, kw.pop("review_id", 99), kw.pop("comment_id", None), kw.pop("text", ""),
                  host=host, tracker=FakeTracker(), llm=llm, ctx=FakeCtx(), **kw)


# ── which files may change ──────────────────────────────────────────────

def test_editable_files_are_the_storys_own_and_the_page_objects_it_extends():
    editable, protected = rf.classify_files(FakeHost().changed + [
        {"filename": "features/reference.feature", "status": "modified"},
        {"filename": "pages/base_page.py", "status": "modified"},
        {"filename": "pages/gone_page.py", "status": "removed"}], {"features/reference.feature"})
    assert set(editable) == {"features/checkout.feature", "tests/step_defs/test_checkout.py",
                             "pages/checkout_page.py"}
    assert "another story" in protected["features/cart.feature"]
    assert "reserved" in protected["features/reference.feature"]
    assert "framework" in protected["pages/base_page.py"]
    assert "docs/notes.md" not in editable and "docs/notes.md" not in protected


# ── the fix itself ──────────────────────────────────────────────────────

def test_a_requested_fix_is_pushed_to_the_same_branch_and_answered(wired):
    host = FakeHost(inline=[_inline()])
    llm = FakeLLM([{"comment": 1, "action": "fix", "files": ["pages/checkout_page.py"],
                    "reason": "open() now waits for the pay button."}])
    out = _run(host, llm)
    assert out["status"] == "fixed"
    assert list(host.pushed) == ["pages/checkout_page.py"]
    assert wired["generated"] == [("pages/checkout_page.py",
                                   ["On pages/checkout_page.py:6: Wait for the pay button before clicking it."])]
    assert host.replies[0][0] == 11 and "changed pages/checkout_page.py" in host.replies[0][1]
    summary = host.comments[-1]
    assert summary.startswith(f"{rf.MARKER} review 99 comments: 11")
    assert "Agents 3, 4 and 5 run again" in summary


def test_a_comment_on_a_file_another_story_owns_is_declined(wired):
    host = FakeHost(inline=[_inline(path="features/cart.feature", body="Rename this step")])
    llm = FakeLLM([{"comment": 1, "action": "fix", "files": ["features/cart.feature"], "reason": "rename"}])
    out = _run(host, llm)
    assert out["status"] == "nothing_to_fix" and not host.pushed and not wired["generated"]
    assert "not changed" in host.replies[0][1] and "another story" in host.replies[0][1]


def test_a_request_to_test_something_else_is_declined_with_the_way_to_get_it(wired):
    host = FakeHost(inline=[_inline(body="Also check the order total")])
    llm = FakeLLM([{"comment": 1, "action": "decline", "files": [],
                    "reason": "The test case does not state a total; update it, then add ai-regenerate."}])
    _run(host, llm)
    assert not wired["generated"] and not host.pushed
    assert "ai-regenerate" in host.replies[0][1]


def test_the_model_cannot_name_a_file_that_is_not_editable(wired):
    host = FakeHost()
    llm = FakeLLM([{"comment": 1, "action": "fix", "files": ["features/cart.feature", "agents/agent2_coder.py"],
                    "reason": "x"}])
    _run(host, llm, review_id=None, comment_id=3, text="/fix make the wait shorter")
    assert not wired["generated"] and not host.pushed


def test_nothing_is_pushed_when_the_gate_refuses(wired):
    wired["gate_error"] = "validate_page_object_methods: bad"
    host = FakeHost(inline=[_inline()])
    llm = FakeLLM([{"comment": 1, "action": "fix", "files": ["pages/checkout_page.py"], "reason": "x"}])
    out = _run(host, llm)
    assert out["status"] == "refused" and not host.pushed
    assert "Nothing was pushed" in host.comments[-1] and "validate_page_object_methods" in host.comments[-1]
    assert "did not pass the checks" in host.replies[0][1]


def test_a_gate_refusal_names_each_rule_still_broken(wired, monkeypatch):
    """The gate's own exception says "see logs"; the reviewer gets the list."""
    errors = [f"pages/checkout_page.py: rule {i} broken" for i in range(12)]

    def gate(batch, story_id, test_cases=None):
        raise a2.GateFailure("Validation failed. See logs for each error.", errors=errors)

    monkeypatch.setattr(a2, "_validate_generated_files", gate)
    host = FakeHost(inline=[_inline()])
    llm = FakeLLM([{"comment": 1, "action": "fix", "files": ["pages/checkout_page.py"], "reason": "x"}])
    out = _run(host, llm)
    assert out["status"] == "refused" and not host.pushed
    summary = host.comments[-1]
    assert "- pages/checkout_page.py: rule 0 broken" in summary
    assert "- pages/checkout_page.py: rule 9 broken" in summary
    assert "rule 10 broken" not in summary and "... and 2 more" in summary


def test_a_repair_that_reaches_a_protected_file_is_refused(wired):
    def reach(batch):
        return [f.model_copy(update={"content": f.content + "x"}) if f.file_path == "features/cart.feature"
                else f for f in batch]
    wired["repair"] = reach
    host = FakeHost(inline=[_inline()])
    llm = FakeLLM([{"comment": 1, "action": "fix", "files": ["pages/checkout_page.py"], "reason": "x"}])
    assert _run(host, llm)["status"] == "refused" and not host.pushed


def test_a_feature_fix_must_keep_its_scenarios_titles_and_markers(wired):
    wired["new"]["features/checkout.feature"] = FEATURE.replace("Pay with a saved card", "Pay quickly")
    host = FakeHost(inline=[_inline(path="features/checkout.feature", body="Reword the title")])
    llm = FakeLLM([{"comment": 1, "action": "fix", "files": ["features/checkout.feature"], "reason": "x"}])
    _run(host, llm)
    assert not host.pushed and "approved test cases" in host.replies[0][1]


def test_a_feature_step_can_be_reworded(wired):
    wired["new"]["features/checkout.feature"] = FEATURE.replace("my saved card", "the saved card")
    host = FakeHost(inline=[_inline(path="features/checkout.feature", body="'the' not 'my'")])
    llm = FakeLLM([{"comment": 1, "action": "fix", "files": ["features/checkout.feature"], "reason": "x"}])
    assert _run(host, llm)["status"] == "fixed"
    assert "the saved card" in host.pushed["features/checkout.feature"]


def test_a_degraded_regeneration_is_discarded(wired):
    wired["new"]["pages/checkout_page.py"] = "x"
    host = FakeHost(inline=[_inline()])
    llm = FakeLLM([{"comment": 1, "action": "fix", "files": ["pages/checkout_page.py"], "reason": "x"}])
    _run(host, llm)
    assert not host.pushed and "degraded" in host.replies[0][1]


def test_a_short_file_is_judged_against_itself_not_the_stub_floor():
    short = "class P:\n    def a(self):\n        return 1\n"
    assert not rf.degraded(short + "    def b(self):\n        return 2\n", short, "pages/p.py")
    assert rf.degraded("def broken(:\n", short, "pages/p.py")
    assert rf.degraded("x = 1\n" * 3, PAGE * 3, "pages/p.py")


def test_an_unchanged_answer_is_reported_as_no_change(wired):
    wired["new"]["pages/checkout_page.py"] = PAGE
    host = FakeHost(inline=[_inline()])
    llm = FakeLLM([{"comment": 1, "action": "fix", "files": ["pages/checkout_page.py"], "reason": "x"}])
    out = _run(host, llm)
    assert out["status"] == "nothing_to_fix" and "unchanged" in host.replies[0][1]


def test_too_many_files_in_one_review_are_not_attempted(wired, monkeypatch):
    monkeypatch.setattr(rf, "settings", lambda: {"enabled": True, "command": "/fix",
                                                 "branch_prefix": "auto/", "max_files": 1})
    host = FakeHost(inline=[_inline()])
    llm = FakeLLM([{"comment": 1, "action": "fix",
                    "files": ["pages/checkout_page.py", "tests/step_defs/test_checkout.py"], "reason": "x"}])
    _run(host, llm)
    assert not wired["generated"] and "Split the review" in host.comments[-1]
    assert "did not pass the checks" not in host.replies[0][1] and "Not attempted" in host.replies[0][1]


def test_when_one_file_of_a_change_is_refused_the_others_are_put_back(wired):
    wired["new"]["features/checkout.feature"] = FEATURE.replace("Pay with a saved card", "Pay quickly")
    host = FakeHost(inline=[_inline(path="features/checkout.feature", body="Rename the step and its body")])
    llm = FakeLLM([{"comment": 1, "action": "fix",
                    "files": ["features/checkout.feature", "tests/step_defs/test_checkout.py"], "reason": "x"}])
    out = _run(host, llm)
    assert not host.pushed and out["status"] == "nothing_to_fix"


# ── when it does nothing at all ─────────────────────────────────────────

def test_a_review_handled_before_is_not_handled_again(wired):
    host = FakeHost(comments=[f"{rf.MARKER} review 99 comments: 11\n..."], inline=[_inline()])
    llm = FakeLLM([])
    out = _run(host, llm)
    assert out["status"] == "skipped" and llm.calls == 0 and not host.replies


def test_review_ids_do_not_collide_by_prefix():
    assert not rf.handled([f"{rf.MARKER} review 991 comments: 1"], "review 99")
    assert rf.handled([f"{rf.MARKER} review 99 comments: -"], "review 99")


@pytest.mark.parametrize("host,why", [(FakeHost(head="feature/S-7-x"), "not one Agent 2 opened"),
                                      (FakeHost(state="closed"), "not open")])
def test_only_open_pull_requests_agent2_opened_are_touched(wired, host, why):
    llm = FakeLLM([])
    out = _run(host, llm)
    assert out["status"] == "skipped" and why in out["reason"] and llm.calls == 0


def test_the_feature_can_be_switched_off(wired, monkeypatch):
    monkeypatch.setattr(rf, "settings", lambda: {"enabled": False, "command": "/fix",
                                                 "branch_prefix": "auto/", "max_files": 6})
    assert _run(FakeHost(), FakeLLM([]))["status"] == "disabled"


def test_comments_from_bots_are_ignored(wired):
    host = FakeHost(inline=[_inline(author="github-actions[bot]")])
    llm = FakeLLM([])
    assert _run(host, llm)["status"] == "skipped" and llm.calls == 0


# ── what a /fix comment means ───────────────────────────────────────────

def test_fix_with_text_acts_on_the_text_alone():
    host = FakeHost(inline=[_inline()])
    items = rf.collect_items(host, 5, None, rf.strip_command("/fix shorten the wait", "/fix"), set())
    assert [(i.body, i.path) for i in items] == [("shorten the wait", None)] and host.inline_reads == []


def test_bare_fix_takes_every_inline_comment_not_handled_before():
    host = FakeHost(inline=[_inline(cid=11), _inline(cid=12, review_id=100)])
    handled = rf.handled_comment_ids([f"{rf.MARKER} review 99 comments: 11\n"])
    items = rf.collect_items(host, 5, None, rf.strip_command("/fix", "/fix"), handled)
    assert [i.comment_id for i in items] == [12]


# ── dry run, ledger ─────────────────────────────────────────────────────

def test_a_dry_run_writes_nothing(wired, capsys):
    host = FakeHost(inline=[_inline()])
    llm = FakeLLM([{"comment": 1, "action": "fix", "files": ["pages/checkout_page.py"], "reason": "x"}])
    _run(host, llm, dry_run=True)
    assert not host.pushed and not host.replies and not host.comments
    assert "create_or_update_file" in capsys.readouterr().out


def test_the_cost_lands_on_the_storys_ledger(wired, monkeypatch):
    posted = []
    monkeypatch.setattr("core.usage_ledger.post_usage_to_story",
                        lambda key, agent, usage, jira=None: posted.append((key, agent)))
    host = FakeHost(inline=[_inline()])
    _run(host, FakeLLM([{"comment": 1, "action": "no_change", "files": [], "reason": "ok"}]))
    assert posted == [("S-7", rf.AGENT_NAME)]


# ── the generator's review mode ─────────────────────────────────────────

def test_review_mode_shows_the_current_file_whole_whatever_its_format(monkeypatch):
    from core.app_context import AppContext
    from core.schemas import CodePlan, FilePlan
    seen = {}

    class LLM:
        def invoke_text(self, system_prompt, user_prompt, **kw):
            seen["prompt"] = user_prompt
            return "```gherkin\n" + FEATURE + "```"

    fp = FilePlan(file_path="features/checkout.feature", file_type="feature", is_new_file=True,
                  purpose="p", related_test_cases=["S-8"])
    plan = CodePlan(feature_name="f", branch_name=HEAD, pr_title="t", pr_body="", files_to_create=[fp])
    ctx = AppContext.load()
    a2.generate_file_content(LLM(), fp, plan, [{"key": "S-8", "summary": "s", "description": "d"}],
                             ctx.load_reference_files(), "{}", ctx, previous_attempt=FEATURE,
                             review_feedback=["On features/checkout.feature:6: reword the step"])
    assert "Apply the reviewer's requested changes" in seen["prompt"]
    assert "reword the step" in seen["prompt"] and "When I pay with my saved card" in seen["prompt"]


# ── the workflow's guards ───────────────────────────────────────────────

def test_the_workflow_admits_only_people_with_write_access_and_never_a_bot():
    wf = yaml.safe_load((ROOT / ".github/workflows/agent2_review_fix.yml").read_text(encoding="utf-8"))
    on = wf.get(True, wf.get("on"))
    assert on["pull_request_review"]["types"] == ["submitted"]
    assert on["issue_comment"]["types"] == ["created"]
    job = wf["jobs"]["fix"]
    cond = job["if"]
    assert "changes_requested" in cond and "startsWith(github.event.pull_request.head.ref, 'auto/')" in cond
    assert cond.count('["OWNER","MEMBER","COLLABORATOR"]') == 2 and cond.count("!= 'Bot'") == 2
    assert "startsWith(github.event.comment.body, '/fix')" in cond
    checkout = next(s for s in job["steps"] if s.get("uses", "").startswith("actions/checkout"))
    assert checkout["with"]["ref"] == "main"


def test_the_reviewers_text_never_reaches_the_shell_as_code():
    wf = yaml.safe_load((ROOT / ".github/workflows/agent2_review_fix.yml").read_text(encoding="utf-8"))
    step = next(s for s in wf["jobs"]["fix"]["steps"] if "agent2_review_fix" in (s.get("run") or ""))
    assert "${{" not in step["run"]
    assert "github.event.review.body" in step["env"]["REVIEW_FIX_TEXT"]
