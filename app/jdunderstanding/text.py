"""Text acquisition for JD analysis — standard library only.

``html_to_document`` uses ``html.parser.HTMLParser`` (stdlib) to convert
untrusted JD HTML into a block-structured document:

- script/style contents are dropped;
- h1..h6 become heading blocks (level preserved);
- <li> becomes list-item blocks;
- other block containers close a paragraph run.

No third-party parser is used. Content size is hard-capped; truncation is
reported, never silent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

_BLOCK_TAGS = frozenset(
    {"p", "div", "section", "article", "ul", "ol", "table", "tr", "hr", "br", "main", "header", "footer"}
)
_HEADING_TAGS = {f"h{i}" for i in range(1, 7)}
_SKIP_TAGS = frozenset({"script", "style"})


@dataclass
class TextBlock:
    kind: str  # "heading" | "li" | "para"
    text: str
    level: int | None = None  # heading level 1..6
    line: int | None = None


@dataclass
class TextDocument:
    blocks: list[TextBlock] = field(default_factory=list)
    plain_text: str = ""
    truncated: bool = False
    total_source_chars: int = 0


class _DocumentBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[TextBlock] = []
        self._skip_depth = 0
        self._heading_level: int | None = None
        self._in_li = False
        self._buffer: list[str] = []

    # -- context helpers ---------------------------------------------------
    def _flush(self, *, kind: str = "para", level: int | None = None) -> None:
        text = "".join(self._buffer).strip()
        self._buffer = []
        if text:
            self.blocks.append(TextBlock(kind=kind, text=text, level=level))

    # -- HTMLParser API ------------------------------------------------------
    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[no-untyped-def]
        tag = tag.lower()
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag in _HEADING_TAGS:
            self._flush()
            self._heading_level = int(tag[1])
            return
        if tag == "li":
            self._flush()
            self._in_li = True
            return
        if tag in _BLOCK_TAGS:
            self._flush()

    def handle_startendtag(self, tag: str, attrs) -> None:  # type: ignore[no-untyped-def]
        if tag.lower() == "br":
            self._flush()

    def handle_endtag(self, tag: str) -> None:  # type: ignore[no-untyped-def]
        tag = tag.lower()
        if tag in _SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
            return
        if tag in _HEADING_TAGS and self._heading_level is not None:
            self._flush(kind="heading", level=self._heading_level)
            self._heading_level = None
            return
        if tag == "li" and self._in_li:
            self._flush(kind="li")
            self._in_li = False
            return
        if tag in _BLOCK_TAGS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        self._buffer.append(data)

    def close(self) -> None:  # noqa: D102
        self._flush()
        super().close()


def _collapse_ws(text: str) -> str:
    return " ".join(text.split())


def extract_text_document(
    raw: str,
    *,
    max_chars: int,
) -> TextDocument:
    """Build a block-structured document from HTML or plain text."""
    builder = _DocumentBuilder()
    try:
        builder.feed(raw)
        builder.close()
    except Exception:  # malformed HTML must never crash analysis
        builder.blocks = [TextBlock(kind="para", text=_collapse_ws(raw))]

    truncated = False
    total = sum(len(block.text) + 1 for block in builder.blocks)

    blocks: list[TextBlock] = []
    used = 0
    for block in builder.blocks:
        text = _collapse_ws(block.text)
        if not text:
            continue
        if used + len(text) > max_chars:
            remaining = max_chars - used
            if remaining > 0:
                blocks.append(
                    TextBlock(kind=block.kind, text=text[:remaining], level=block.level)
                )
            truncated = True
            break
        blocks.append(TextBlock(kind=block.kind, text=text, level=block.level))
        used += len(text) + 1

    plain_text = "\n".join(block.text for block in blocks)
    return TextDocument(
        blocks=blocks,
        plain_text=plain_text,
        truncated=truncated or total > max_chars,
        total_source_chars=total,
    )


def bullet_items(text: str) -> list[str]:
    """Split a section's text into bullet-ish items when present."""
    items: list[str] = []
    current: list[str] = []

    def push(line: str) -> None:
        stripped = line.strip()
        if not stripped:
            return
        cleaned = stripped.lstrip("-•*·–—").strip()
        cleaned = _strip_numbering(cleaned)
        if cleaned:
            items.append(cleaned)

    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if line.startswith(("-", "•", "*", "·")) or _NUMBERED.match(line):
            if current:
                push(" ".join(current))
                current = []
            current.append(line)
        elif line:
            current.append(line)
    if current:
        push(" ".join(current))
    return [item for item in items if len(item) >= 3]


_NUMBERED = re.compile(r"^\d{1,2}[.)]\s")


def _strip_numbering(text: str) -> str:
    return _NUMBERED.sub("", text).strip()


__all__ = ["TextBlock", "TextDocument", "bullet_items", "extract_text_document"]
