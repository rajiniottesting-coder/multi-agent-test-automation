"""Read back the JSON an agent stored in a tracker code block.

Agents keep machine data in issue descriptions and comments as a code block:

    {code:json}
    {...}
    {code}

A person who edits the issue in Jira's editor makes Jira store the block
again, and it comes back WITHOUT the line breaks round the JSON:

    {code:json}{...}{code}

Every reader used to require the line breaks, so after a person decided an
Impact Review (an edit by design) Agent 0's report could no longer be read
from it - the outcome measurement, the repeat check and the delta all saw
"no report" without a word. This is the one reader for such blocks; it
accepts both forms and any `{code...}` opener.
"""
from __future__ import annotations

import json
import re
from typing import Any

_OPEN = re.compile(r"\{code(?::[^}]*)?\}")
_CLOSE = "{code}"


def read_json_block(text: str) -> Any | None:
    """The JSON value of the first code block that holds valid JSON, else None.

    The stored JSON may itself contain the text "{code}" (a test case quoting
    Jira markup), so each closing tag after an opener is tried in turn, and
    the first span that parses wins.
    """
    text = text or ""
    for opener in _OPEN.finditer(text):
        start = opener.end()
        end = text.find(_CLOSE, start)
        while end != -1:
            try:
                return json.loads(text[start:end].strip())
            except ValueError:
                end = text.find(_CLOSE, end + 1)
    return None
