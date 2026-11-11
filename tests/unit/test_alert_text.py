"""A health alert carries a person-readable error, and nothing secret.

11 Nov 2026 (validation E31h): the triage's `defects-not-written` alert quoted
the tracker client's error whole - its response headers included - and
`raise_alert` posted it unredacted (only some callers redacted). A header dump
can carry a session cookie. Now every alert body is redacted where it is
posted, credential-carrying header values are redacted, and the defect
triage records `error_text()`: the status and the server's own message.
"""
from core import pipeline_health as ph
from core.redaction import MARK, error_text, redact
from tests.sandbox.fake_jira import FakeJira, jira_client_over


class _HttpError(Exception):
    status_code = 400
    text = "Specify a valid issue type"

    def __str__(self):
        return ("HttpError HTTP 400 url: https://tracker.example/rest/api/2/issue\n\ttext: "
                "Specify a valid issue type\n\nresponse headers = {'Content-Type': 'json', "
                "'Set-Cookie': 'session=abcdef0123456789; Path=/'}")


def test_an_http_error_is_its_status_and_the_servers_message():
    assert error_text(_HttpError()) == "_HttpError: HTTP 400: Specify a valid issue type"


def test_a_header_dump_is_dropped_and_a_long_text_cut():
    e = RuntimeError("refused response headers = {'Set-Cookie': 'session=zzzzzzzzzz'} after")
    assert error_text(e) == "RuntimeError: refused after"
    assert error_text(RuntimeError("x" * 500), limit=40).endswith("...")
    assert len(error_text(RuntimeError("x" * 500), limit=40)) == 40


def test_credential_headers_are_redacted_wherever_they_appear():
    text = redact("{'Authorization': 'Bearer abcdefghij', 'Set-Cookie': 'a=1', "
                  "'Content-Type': 'json'} Cookie: s=2 X-Api-Token: t123")
    assert "abcdefghij" not in text and "a=1" not in text and "s=2" not in text
    assert "t123" not in text and "'Content-Type': 'json'" in text
    # An unquoted value runs to the end of the line: over-redacting is safe.
    assert text.endswith(f"Cookie: {MARK}")


def test_every_alert_is_redacted_where_it_is_posted(monkeypatch):
    fake = FakeJira()
    jira = jira_client_over(fake, monkeypatch)
    monkeypatch.setenv("JIRA_API_TOKEN", "tok-123456789")
    ph.raise_alert(jira, "x-alert", "Title", "error: tok-123456789 Set-Cookie: s=abc; Path=/")
    body = fake.comments[ph.issue_key(jira)][-1]
    assert "tok-123456789" not in body and "s=abc" not in body and MARK in body
    ph.resolve_alert(jira, "x-alert", "closed: tok-123456789")
    assert "tok-123456789" not in fake.comments[ph.issue_key(jira)][-1]
