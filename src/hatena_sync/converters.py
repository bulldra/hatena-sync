"""Utility converters for Hatena Blog content."""
from __future__ import annotations

import re


def hatena_to_markdown(text: str) -> str:
    """Convert Hatena notation to Markdown.

    This is a best-effort converter that supports a small subset of Hatena
    syntax including headings, bold/italic, and simple links.
    """
    lines = text.splitlines()
    converted_lines = []
    for line in lines:
        # headings using '*' characters
        m = re.match(r"^(\*{1,6})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            converted_lines.append(f"{'#' * level} {m.group(2)}")
            continue
        converted_lines.append(line)
    converted = "\n".join(converted_lines)

    # bold '''text''' -> **text**
    converted = re.sub(r"'''(.*?)'''", r"**\1**", converted)
    # italic ''text'' -> *text*
    converted = re.sub(r"''(.*?)''", r"*\1*", converted)
    # links [url:title=Title] -> [Title](url)
    def _link(m: re.Match) -> str:
        url = m.group("url")
        title = m.group("title") or url
        return f"[{title}]({url})"

    pattern_title = re.compile(
        r"\[(?P<url>https?://[^\s\]:]+):title=(?P<title>[^\]]+)\]"
    )
    pattern_simple = re.compile(r"\[(?P<url>https?://[^\s\]]+)\]")
    converted = pattern_title.sub(_link, converted)
    converted = pattern_simple.sub(_link, converted)

    return converted
