"""F-30: the agents write to the repository as their own identity.

N10: Agent 2's pull requests were opened with GH_PAT - a person's token - so
that person was their author. GitHub lets no author request changes on or
approve their own pull request: the reviewer had to use `/fix`, merging needed
a ruleset bypass, and a required approval could not be enforced.

Now every job that writes as the agents takes its token from one step,
`.github/actions/agent-identity`: a GitHub App's installation token when the
App is configured (APP_CLIENT_ID variable, APP_PRIVATE_KEY secret), GH_PAT
otherwise. These tests pin the wiring, the fallback, the trust boundary (the
step is never taken from a pull request's own checkout) and the health check's
view of a token created per run.
"""
import datetime as _dt
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
ACTION = ROOT / ".github" / "actions" / "agent-identity" / "action.yml"
TOKEN = "${{ steps.identity.outputs.token }}"


def _load(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _agent_jobs():
    """(workflow, job name, job) for every job that writes as the agents."""
    out = []
    for wf in WORKFLOWS:
        for name, job in (_load(wf).get("jobs") or {}).items():
            if any(TOKEN in str(s) or "agent-identity" in str(s.get("uses", ""))
                   for s in job.get("steps") or []):
                out.append((wf.name, name, job))
    return out


def test_the_agents_jobs_are_all_found():
    found = {(w, n) for w, n, _j in _agent_jobs()}
    assert found == {
        ("agent0_impact.yml", "scan"), ("agent0_impact.yml", "reconcile"),
        ("agent0_impact.yml", "code-change"), ("agent0_impact.yml", "drift"),
        ("agent2_coder.yml", "generate"), ("agent2_review_fix.yml", "fix"),
        ("sweeper.yml", "sweep"), ("pipeline_health.yml", "check"),
        ("story_done_on_merge.yml", "mark-done")}


@pytest.mark.parametrize("wf", WORKFLOWS, ids=lambda p: p.name)
def test_no_step_writes_with_gh_pat_directly(wf):
    """GH_PAT is only the identity step's fallback: a step reading it directly
    would write as a person even with the App configured."""
    for name, job in (_load(wf).get("jobs") or {}).items():
        for step in job.get("steps") or []:
            env = step.get("env") or {}
            assert "secrets.GH_PAT" not in str(env), (wf.name, name, step.get("name"))
            if "secrets.GH_PAT" in str(step):
                assert step.get("id") == "identity" and \
                    step["with"]["fallback-token"] == "${{ secrets.GH_PAT }}", (wf.name, name)


@pytest.mark.parametrize("wf,name,job", _agent_jobs(), ids=lambda x: str(x)[:30])
def test_each_agent_job_gets_its_token_from_the_identity_step(wf, name, job):
    steps = job["steps"]
    ids = [i for i, s in enumerate(steps) if s.get("id") == "identity"]
    assert len(ids) == 1, f"{wf}/{name}: one identity step"
    step = steps[ids[0]]
    assert step["with"] == {"client-id": "${{ vars.APP_CLIENT_ID }}",
                            "private-key": "${{ secrets.APP_PRIVATE_KEY }}",
                            "fallback-token": "${{ secrets.GH_PAT }}"}
    users = [i for i, s in enumerate(steps) if TOKEN in str(s.get("env") or {})]
    assert users and all(i > ids[0] for i in users), f"{wf}/{name}: token used before it exists"
    for i in users:
        assert steps[i]["env"]["GITHUB_TOKEN"] == TOKEN


@pytest.mark.parametrize("wf,name,job", _agent_jobs(), ids=lambda x: str(x)[:30])
def test_the_identity_step_comes_from_trusted_code_never_the_pull_request(wf, name, job):
    """A local action resolves from a checkout. The code-change job checks the
    pull request out too; taking the step from it would let a pull request
    rewrite the code that holds the App's private key."""
    steps = job["steps"]
    i = next(i for i, s in enumerate(steps) if s.get("id") == "identity")
    uses = steps[i]["uses"]
    checkouts = {(s.get("with") or {}).get("path", "."): s for s in steps[:i]
                 if "actions/checkout" in str(s.get("uses", ""))}
    assert uses.startswith("./") and uses.endswith(".github/actions/agent-identity"), uses
    base = uses.removeprefix("./").split(".github/")[0].rstrip("/") or "."
    assert base in checkouts, f"{wf}/{name}: no checkout at {base} before the step"
    ref = (checkouts[base].get("with") or {}).get("ref", "")
    assert ref in ("main", "${{ github.event.pull_request.base.sha }}"), \
        f"{wf}/{name}: the step comes from {ref or 'the triggering ref'} - must be main or the base"


@pytest.mark.parametrize("wf,name,job", _agent_jobs(), ids=lambda x: str(x)[:30])
def test_every_agent_job_ends_inside_the_tokens_hour(wf, name, job):
    assert int(job.get("timeout-minutes") or 360) <= 55, \
        f"{wf}/{name}: an App's token lasts one hour; a longer job loses its writes"


def test_the_identity_action():
    action = _load(ACTION)
    steps = action["runs"]["steps"]
    app = steps[0]
    assert app["id"] == "app" and app["if"] == "inputs.client-id != ''"
    assert app["uses"] == "actions/create-github-app-token@v3"
    perms = {k: v for k, v in app["with"].items() if k.startswith("permission-")}
    assert perms == {"permission-contents": "write", "permission-pull-requests": "write",
                     "permission-issues": "write", "permission-actions": "read"}, \
        "exactly what the agents do - and a token asking for more than the App has fails"
    assert action["outputs"]["token"]["value"] == \
        "${{ steps.app.outputs.token || inputs.fallback-token }}"
    assert "'app'" in action["outputs"]["kind"]["value"] and \
        "'personal'" in action["outputs"]["kind"]["value"]
    say = steps[1]["run"]
    assert "::warning" in say and "GH_PAT" in say, "writing as a person is said in the run"
    assert "::error" in say and "exit 1" in say, "no token at all fails the step"
    assert "continue-on-error" not in str(app), \
        "a configured App that cannot create a token must fail, never fall back silently"


def test_the_app_id_is_an_identifier_and_the_key_a_credential():
    from tests.unit import test_workflow_secrets as rule
    assert "APP_CLIENT_ID" in rule._MUST_NOT_BE_SECRET
    for wf, name, job in _agent_jobs():
        body = str(job)
        assert "secrets.APP_CLIENT_ID" not in body and "vars.APP_PRIVATE_KEY" not in body


def test_the_health_check_is_told_when_the_token_is_created_per_run():
    wf = _load(ROOT / ".github" / "workflows" / "pipeline_health.yml")
    step = next(s for s in wf["jobs"]["check"]["steps"] if s.get("name") == "Run the health check")
    assert step["env"]["REPO_HOST_TOKEN_PER_RUN"] == "${{ steps.identity.outputs.kind == 'app' }}"


# ── the health check ─────────────────────────────────────────────────────────

NOW = _dt.datetime(2026, 10, 28, 3, 20, tzinfo=_dt.timezone.utc)


class _Host:
    def __init__(self, expires=None, refuse=False):
        self.expires, self.refuse = expires, refuse

    def check_access(self):
        if self.refuse:
            raise RuntimeError("HTTP 401: Bad credentials")
        return {"ok": True, "expires": self.expires}


def test_a_token_created_per_run_has_no_expiry_to_warn_about():
    from core import health_checks as hc
    soon = "2026-10-28 04:20:00 UTC"                       # an App token: one hour
    found = hc.repo_host_findings(lambda: _Host(soon), NOW, 14, per_run=True)
    assert {f.alert_id: f.problem for f in found} == {
        "credential:repo-host": False, "credential-expiry:repo-host": False}, \
        "and an earlier expiry alert (from GH_PAT) closes"
    same_as_pat = hc.repo_host_findings(lambda: _Host(soon), NOW, 14)
    assert {f.alert_id: f.problem for f in same_as_pat}["credential-expiry:repo-host"] is True, \
        "a personal token that expires that soon is still an alert"


def test_a_refused_token_is_an_alert_whichever_kind():
    from core import health_checks as hc
    for per_run in (False, True):
        (f,) = hc.repo_host_findings(lambda: _Host(refuse=True), NOW, 14, per_run=per_run)
        assert f.alert_id == "credential:repo-host" and f.problem


def test_the_health_check_reads_the_workflows_word(monkeypatch):
    import scripts.pipeline_health_check as phc
    from core import health_checks as hc
    seen = {}
    monkeypatch.setattr(hc, "workflow_findings", lambda *a, **k: [])
    monkeypatch.setattr(hc, "check_model", lambda mode: None)
    monkeypatch.setattr(hc, "repo_host_findings",
                        lambda factory, now, days, per_run=False: seen.update(per_run=per_run) or [])
    for value, expected in (("true", True), ("false", False), ("", False)):
        monkeypatch.setenv("REPO_HOST_TOKEN_PER_RUN", value)
        phc.findings(None, lambda: _Host(), ROOT, NOW)
        assert seen["per_run"] is expected, value


# ── the review fix, once a person can request changes ───────────────────────

def test_a_request_for_changes_from_a_person_starts_the_review_fix_and_a_bot_never():
    wf = _load(ROOT / ".github" / "workflows" / "agent2_review_fix.yml")
    cond = re.sub(r"\s+", " ", wf["jobs"]["fix"]["if"])
    assert "github.event.review.state == 'changes_requested'" in cond
    assert "github.event.review.user.type != 'Bot'" in cond, \
        "the App's own review replies arrive as reviews: they must never start it"
    assert "github.event.comment.user.type != 'Bot'" in cond
    assert "OWNER" in cond and "MEMBER" in cond and "COLLABORATOR" in cond


def test_the_apps_own_replies_are_not_taken_as_review_comments():
    from agents.agent2_review_fix import collect_items

    class Host:
        def get_review_comments(self, pr, review_id):
            return [{"id": 1, "body": "Rename this step", "author": "reviewer", "path": "a.py",
                     "line": 3},
                    {"id": 2, "body": "Fixed in abc123", "author": "test-agents[bot]",
                     "path": "a.py", "line": 3}]
    items = collect_items(Host(), 7, None, "", set())
    assert [i.body for i in items] == ["Rename this step"]
