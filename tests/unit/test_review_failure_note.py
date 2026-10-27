"""Agent 3 says why it could not review.

Found on PR #225: the review job failed and posted nothing - a red check and
no comment, so the reviewer could not tell a failed review from a finding.
Now a failure posts one short note with the error, every configured secret
value redacted, and the job still fails.
"""
import sys

import pytest

from agents import agent3_reviewer as a3


def test_the_note_names_the_error_and_says_nothing_was_reviewed():
    note = a3.failure_note(ValueError("prompt is too long: 210000 tokens > 200000 maximum"))
    assert "Could not review this pull request" in note
    assert "ValueError: prompt is too long" in note and "Nothing was reviewed" in note


def test_secrets_never_reach_the_note(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "key-value-12345678")
    monkeypatch.setenv("GITHUB_TOKEN", "tok-value-abcdefgh")
    note = a3.failure_note(RuntimeError(
        "401 for key-value-12345678 and tok-value-abcdefgh, also sk-abcdefghijk and ghp_abcdefghijk"))
    for secret in ("key-value-12345678", "tok-value-abcdefgh", "sk-abcdefghijk", "ghp_abcdefghijk"):
        assert secret not in note
    assert note.count("[redacted]") == 4


def test_a_long_error_is_cut():
    assert len(a3.failure_note(RuntimeError("x" * 5000))) < 1000


def _run_main(monkeypatch, argv, posted, fail_post=False):
    monkeypatch.setattr(sys, "argv", ["agent3", *argv])
    monkeypatch.setattr(a3, "validate_required_env", lambda *a, **k: None)
    monkeypatch.setattr(a3, "run", lambda n, dry_run=False: (_ for _ in ()).throw(
        RuntimeError("gateway refused")))

    class Host:
        def post_pr_comment(self, n, body):
            if fail_post:
                raise RuntimeError("cannot post")
            posted.append((n, body))
    monkeypatch.setattr(a3, "get_repo_host", lambda: Host())
    with pytest.raises(SystemExit) as e:
        a3.main()
    return e.value.code


def test_a_failed_review_posts_the_note_and_still_fails_the_job(monkeypatch):
    posted = []
    assert _run_main(monkeypatch, ["--pr", "7"], posted) == 1
    assert posted and posted[0][0] == 7 and "RuntimeError: gateway refused" in posted[0][1]


def test_a_dry_run_posts_nothing_and_a_failed_post_hides_nothing(monkeypatch):
    posted = []
    assert _run_main(monkeypatch, ["--pr", "7", "--dry-run"], posted) == 1 and not posted
    assert _run_main(monkeypatch, ["--pr", "7"], posted, fail_post=True) == 1


def test_a_gateway_error_never_carries_an_owner_or_a_key_alias():
    """Seen live on PR #225: the gateway's 429 named the key's owner."""
    note = a3.failure_note(RuntimeError(
        "Error code: 429 - Budget has been exceeded! Key=someone.name@example.org_123456 "
        "(sk-...AbCd) Current cost: 30.7, Max budget: 30.0; contact admin@example.com"))
    assert "@" not in note and "someone.name" not in note
    assert "Budget has been exceeded" in note and "Max budget: 30.0" in note
