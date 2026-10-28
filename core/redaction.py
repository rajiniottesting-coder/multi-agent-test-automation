"""Nothing secret leaves the pipeline in text it writes for people.

Agent 3's failure note on a pull request and the pipeline health alerts carry
an error's message, and an error can quote what it was given. Before either is
posted, `redact()` removes:

  - the value of every credential the workflows pass (SECRET_ENV - a unit test
    fails when a workflow passes a secret this list does not name);
  - anything shaped like a token, whatever the value: model keys (`sk-`),
    every GitHub token kind (`ghp_` personal, `gho_` OAuth, `ghu_` user,
    `ghs_` App installation, `ghr_` refresh, `github_pat_` fine-grained) at
    any length and with dots - GitHub's App installation tokens are moving to
    a longer, stateless `ghs_` format (about 520 characters);
  - a private key block (`-----BEGIN ... PRIVATE KEY-----`), whole or cut off;
  - a gateway's key alias (`Key=<owner>_<id>`) and any email address.

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
_KEY_ALIAS = re.compile(r"\bKey=\S+")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")

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
    return _EMAIL.sub(MARK, text)
