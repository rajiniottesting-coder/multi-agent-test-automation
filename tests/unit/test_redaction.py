"""Nothing secret reaches a PR comment or a health alert (core/redaction.py).

Found while the agents' GitHub App (F-30) was set up: GitHub announced that App
installation tokens move to a longer, stateless `ghs_` format (about 520
characters). The token pattern of Agent 3's failure note and of the health
alerts knew `ghp_`, `gho_` and `github_pat_` only - not `ghs_` (App), `ghu_`
or `ghr_` - and stopped at a dot. The two copies also named different secrets
(the health alerts missed APP_PASSWORD; neither named JIRA_EMAIL or
APP_USER_REGISTERED), and a private key quoted in an error was caught only by
its exact value. Now one function serves both, and a test ties its list of
secrets to the workflows. Generic names only.
"""
import re
from pathlib import Path

import pytest
import yaml

from core import redaction

ROOT = Path(__file__).resolve().parents[2]
M = redaction.MARK


@pytest.mark.parametrize("token", [
    "ghp_" + "a" * 36,                          # personal (classic)
    "gho_" + "b" * 36,                          # OAuth
    "ghu_" + "c" * 36,                          # user-to-server
    "ghs_" + "d" * 36,                          # App installation, today
    "ghr_" + "e" * 76,                          # refresh
    "github_pat_" + "f" * 82,                   # fine-grained personal
    "ghs_" + "x" * 200 + "." + "y" * 150 + "." + "z" * 160,   # stateless, ~520, with dots
    "sk-" + "g" * 48,                           # a model key
])
def test_every_token_shape_is_redacted_whole(token):
    out = redaction.redact(f"HTTP 401 for token {token} at /repos", env={})
    assert token not in out and out == f"HTTP 401 for token {M} at /repos"


def test_a_longer_app_token_is_not_cut_at_a_fixed_length():
    token = "ghs_" + "A1b2_-" * 86                 # 520 characters
    assert len(token) == 520
    assert redaction.redact(token, env={}) == M


def test_ordinary_words_are_left_alone():
    text = "task_runner failed: ask-for-help, gh is a CLI, sketch_12 ok"
    assert redaction.redact(text, env={}) == text


def test_a_private_key_whole_or_cut_off():
    pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIEow" + "Q" * 300 + "\n-----END RSA PRIVATE KEY-----"
    assert redaction.redact(f"bad key: {pem} (decode)", env={}) == f"bad key: {M} (decode)"
    cut = "-----BEGIN PRIVATE KEY-----\nMIIEvQ" + "Z" * 100
    assert redaction.redact(f"error near {cut}", env={}) == f"error near {M}"


def test_every_configured_secret_value_and_emails():
    env = {"JIRA_API_TOKEN": "plain-value-123", "APP_PASSWORD": "Sup3rSecret!",
           "JIRA_EMAIL": "bot@example.org", "GH_APP_PRIVATE_KEY": "keymaterial42"}
    text = ("401 plain-value-123 / Sup3rSecret! / bot@example.org / keymaterial42 / "
            "Key=someone@x.y_123 / other@domain.io")
    out = redaction.redact(text, env=env)
    assert out == f"401 {M} / {M} / {M} / {M} / Key={M} / {M}"


def test_a_short_value_is_not_redacted_everywhere():
    """A one- or two-character secret would blank that character all over the
    message - the reason identifiers are variables (test_workflow_secrets)."""
    assert redaction.redact("build 1 of 12", env={"APP_PASSWORD": "1"}) == "build 1 of 12"


def test_every_secret_a_workflow_passes_is_on_the_list():
    """A new secret in a workflow must be named in SECRET_ENV, or its value
    could reach a PR comment or an alert unredacted."""
    missing = set()
    for wf in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        data = yaml.safe_load(wf.read_text(encoding="utf-8"))
        for job in (data.get("jobs") or {}).values():
            envs = [job.get("env") or {}] + [s.get("env") or {} for s in job.get("steps") or []]
            for env in envs:
                for name, value in env.items():
                    if re.search(r"secrets\.|steps\.identity\.outputs\.token", str(value)):
                        if name not in redaction.SECRET_ENV:
                            missing.add(f"{wf.name}: {name}")
    assert not missing, f"credentials passed but not redacted: {sorted(missing)}"


def test_agent3_and_the_health_alerts_use_the_same_rule(monkeypatch):
    from agents.agent3_reviewer import failure_note
    from core.health_checks import _redact
    token = "ghs_" + "q" * 60
    monkeypatch.setenv("APP_PASSWORD", "app-pass-9876")
    note = failure_note(RuntimeError(f"refused {token} with app-pass-9876"))
    assert token not in note and "app-pass-9876" not in note and M in note
    assert _redact(f"refused {token} with app-pass-9876") == f"refused {M} with {M}"
