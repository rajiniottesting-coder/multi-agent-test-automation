"""Nothing secret leaves the pipeline in text it writes for people.

Agent 3's failure note on a pull request, the pipeline health alerts and the
agents' notices on a story (integrations.tracker.add_markdown_comment - a
refused story's reasons, say) carry an error's message, and an error can quote
what it was given. Before any of them is posted, `redact()` removes:

  - the value of every credential the workflows pass (SECRET_ENV - a unit test
    fails when a workflow passes a secret this list does not name);
  - anything shaped like a token, whatever the value: model keys (`sk-`),
    every GitHub token kind (`ghp_` personal, `gho_` OAuth, `ghu_` user,
    `ghs_` App installation, `ghr_` refresh, `github_pat_` fine-grained) at
    any length and with dots - GitHub's App installation tokens are moving to
    a longer, stateless `ghs_` format (about 520 characters);
  - a private key block (`-----BEGIN ... PRIVATE KEY-----`), whole or cut off;
  - a gateway's key alias (`Key=<owner>_<id>`) and any email address;
  - the value of a credential-carrying HTTP header an error quotes
    (`Authorization`, `Cookie`, `Set-Cookie`, a `...-Token` header): an HTTP
    client's error can print the response's headers, session cookie included;
  - the signature or token of a signed URL (`sig=`, `signature=`,
    `X-Amz-Signature=`, `X-Goog-Signature=`, `token=`, `access_token=`): a
    failed download prints the URL it was redirected to, and a storage
    host's signed link lets anyone holding it read the file until it expires.

`error_text()` is the readable form of such an error for a person: its status
and the server's own message, without the request/response header dump.

One function for every caller, so the places that post text never disagree
about what is secret. Generic: no application or provider names a value.
"""
from __future__ import annotations

import os
import re

# Environment variables holding credentials in any workflow step - the
# agents' and the application under test's.
SECRET_ENV = (
    "OPENAI_API_KEY",
    "GITHUB_TOKEN",
    "GH_PAT",
    "GH_APP_PRIVATE_KEY",
    "JIRA_API_TOKEN",
    "JIRA_EMAIL",
    "APP_USER_REGISTERED",
    "APP_PASSWORD",
)

_TOKEN = re.compile(r"\b(?:sk|gh[pousr]|github_pat)[-_][A-Za-z0-9_.\-]{8,}")
_PEM = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)",
                  re.S)
# The alias runs to the next space or closing punctuation; a sentence's
# comma, bracket or full stop after it stays.
_KEY_ALIAS = re.compile(r"\bKey=[^\s,;)\]'\"]*[^\s,;)\]'\".]")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")

# A credential-carrying header's value, quoted or not, as an error prints it
# (`'Set-Cookie': 'session=...'`, `Authorization: Bearer ...`).
_HEADER = re.compile(r"(?i)(\b(?:proxy-)?authorization|\bset-cookie|\bcookie|\b[\w-]*-token)"
                     r"(['\"]?\s*[:=]\s*)(['\"]?)([^'\"\n]*)")
# The secret part of a signed URL's query string.
_SIGNED_QUERY = re.compile(r"(?i)([?&](?:sig|signature|x-amz-signature|x-amz-security-token|"
                           r"x-goog-signature|token|access_token)=)[^&\s'\"]+")
# An HTTP client's dump of the headers it sent or received.
_HEADER_DUMP = re.compile(r"(?is)\s*(?:request|response)\s+headers\s*=\s*\{.*?(?:\}|\Z)")
MARK = "[redacted]"


def redact(text: str, env=None) -> str:
    """`text` with every secret value and secret-shaped string replaced."""
    env = os.environ if env is None else env
    text = str(text or "")
    values = sorted({(env.get(name) or "").strip() for name in SECRET_ENV}, key=len, reverse=True)
    for value in values:
        if len(value) >= 8:
            text = text.replace(value, MARK)
    text = _PEM.sub(MARK, text)
    text = _TOKEN.sub(MARK, text)
    text = _KEY_ALIAS.sub(f"Key={MARK}", text)
    text = _HEADER.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}{MARK}", text)
    text = _SIGNED_QUERY.sub(lambda m: m.group(1) + MARK, text)
    return _EMAIL.sub(MARK, text)


def error_text(error, limit: int = 300) -> str:
    """`<Type>: <message>` for a person, redacted: an HTTP error's status and
    the server's own text when the error carries them (`status_code`, `text`),
    never the header dump some clients append; whitespace collapsed; at most
    `limit` characters."""
    status = getattr(error, "status_code", None)
    server = getattr(error, "text", None)
    if status and isinstance(server, str) and server.strip():
        message = f"HTTP {status}: {server.strip()}"
    else:
        message = _HEADER_DUMP.sub("", str(error))
    message = " ".join(redact(message).split())
    text = f"{type(error).__name__}: {message}"
    return text if len(text) <= limit else text[:limit - 3].rstrip() + "..."
