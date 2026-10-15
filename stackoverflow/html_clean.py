"""Convert Stack Overflow HTML bodies to plain text (keep code blocks)."""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser


class _ToText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._in_pre = False
        self._in_code = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("pre",):
            self._in_pre = True
            self.parts.append("\n```\n")
        elif tag in ("code", "kbd"):
            if not self._in_pre:
                self._in_code = True
                self.parts.append("`")
        elif tag in ("p", "div", "br", "li"):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "pre":
            self._in_pre = False
            self.parts.append("\n```\n")
        elif tag in ("code", "kbd") and not self._in_pre:
            self._in_code = False
            self.parts.append("`")
        elif tag in ("p", "div", "li"):
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        raw = html.unescape("".join(self.parts))
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        raw = re.sub(r"[ \t]+\n", "\n", raw)
        return raw.strip()


def html_to_text(body_html: str) -> str:
    parser = _ToText()
    parser.feed(body_html or "")
    parser.close()
    return parser.text()
