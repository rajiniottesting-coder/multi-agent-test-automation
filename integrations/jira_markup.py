"""Markdown -> Jira wiki markup, for comments posted through the REST v2 API.

The python `jira` client posts comment bodies to REST v2, which renders Jira
WIKI markup, not Markdown. Agent 5 writes Markdown, so on Jira its comments
showed a table separator as a row of dashes, **bold** with its stars intact
and [links](url) as literal brackets.

Covers the Markdown the agents actually write: headings, bold, inline code,
links, bullet lists, block quotes, horizontal rules, pipe tables and fenced
code. Anything else passes through unchanged, so plain text - including the
bracketed machine markers other comments carry, such as "[LLM-USAGE]" - is
never altered. Text inside fenced code is left exactly as written.
"""
from __future__ import annotations

import re

_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)")
_BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
_CODE = re.compile(r"`([^`\n]+)`")


# Characters wiki markup reads as formatting even inside {{monospace}}: bold,
# italics, strike, links, images, macros, tables. A code span is literal text -
# a step pattern, a selector, a label - so each one is escaped. 11 Nov 2026:
# a refused story's comment quoted the step `... "(?P<expected_message>[^"]*)"`
# and Jira drew a broken image and bold text out of it.
_WIKI_SPECIAL = re.compile(r"([*_?+^~!\[\]{}|#-])")


def _literal(code: str) -> str:
    """`code` as wiki monospace that shows exactly these characters. A
    backslash is written as its character reference: in wiki markup a
    backslash escapes the next character, and two of them break the line."""
    escaped = _WIKI_SPECIAL.sub(r"\\\1", code.replace("\\", "\x01"))
    return "{{" + escaped.replace("\x01", "&#92;") + "}}"


def _inline(text: str) -> str:
    # Code spans first, and protected, so nothing inside them is rewritten.
    spans: list[str] = []

    def keep(match):
        spans.append(_literal(match.group(1)))
        return f"\x00{len(spans) - 1}\x00"

    text = _CODE.sub(keep, text)
    text = _LINK.sub(lambda m: f"[{m.group(1)}|{m.group(2)}]", text)
    text = _BOLD.sub(lambda m: f"*{m.group(1)}*", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: spans[int(m.group(1))], text)


def _cells(row: str) -> list[str]:
    row = row.strip()
    row = row.removeprefix("|")
    row = row.removesuffix("|")
    return [_inline(c.strip()) for c in row.split("|")]


def markdown_to_jira_wiki(markdown: str) -> str:
    lines = (markdown or "").split("\n")
    out: list[str] = []
    in_code = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("```"):
            out.append("{code}")
            in_code = not in_code
            i += 1
            continue
        if in_code:
            out.append(line)
            i += 1
            continue

        # A pipe table: a header row followed by a separator row.
        if ("|" in line and i + 1 < len(lines)
                and _TABLE_SEPARATOR.match(lines[i + 1]) and "-" in lines[i + 1]):
            out.append("||" + "||".join(_cells(line)) + "||")
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                out.append("|" + "|".join(_cells(lines[i])) + "|")
                i += 1
            continue

        if re.fullmatch(r"\s*(-{3,}|\*{3,}|_{3,})\s*", line):
            out.append("----")
        elif (m := _HEADING.match(line)):
            out.append(f"h{len(m.group(1))}. {_inline(m.group(2))}")
        elif line.lstrip().startswith(">"):
            out.append("bq. " + _inline(line.lstrip()[1:].strip()))
        elif (m := _BULLET.match(line)):
            depth = len(m.group(1).replace("\t", "  ")) // 2 + 1
            out.append("*" * depth + " " + _inline(m.group(2)))
        else:
            out.append(_inline(line))
        i += 1
    return "\n".join(out)
