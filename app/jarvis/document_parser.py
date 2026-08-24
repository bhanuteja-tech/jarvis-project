"""Document-extraction integration layer (PDF/DOCX/TXT/MD -> text).

Thin, deliberately boring boundary between uploaded FILES and the frozen
Phase-3 text-based resume parser:

    PDF/DOCX/TXT/MD -> document_parser.extract() -> normalized text
                    -> ResumeAnalyzer.build_profile({"text": ...})

Responsibilities (and nothing more):
- extension + size validation (MIME is untrusted; never authoritative)
- per-format text extraction via pypdf / python-docx / plain decoding
- whitespace + line-ending normalization
- typed error results (no exceptions cross this boundary)
- extraction METADATA only — never content echoes in errors

Security posture: uploads are UNTRUSTED BYTES. Filenames are inspected for
extension only (never used as paths); nothing is executed; no OCR exists and
scanned documents fail with ``no_extractable_text`` rather than pretending.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PdfReadError

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".docx", ".txt", ".md"})

_FORMAT_LABELS: dict[str, str] = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".txt": "txt",
    ".md": "md",
}


class DocumentParseError(Exception):
    """Typed failure carrying a SAFE machine code + user-facing message.

    Messages never contain exception details, paths, or resume content.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ExtractionResult:
    """Normalized text plus non-sensitive metadata for the UI."""

    text: str
    source_format: str  # pdf|docx|txt|md
    character_count: int
    page_count: int | None  # pdf only
    paragraph_count: int | None  # docx only
    extraction_status: str = "success"
    warnings: list[str] = field(default_factory=list)


def safe_extension(filename: str | None) -> str:
    """Extension of an untrusted filename, lowercase with dot; '' if none.

    The filename is NEVER used to construct paths — inspection only.
    """
    if not filename or not isinstance(filename, str):
        return ""
    name = filename.strip().replace("\\", "/").rsplit("/", 1)[-1]
    if "/" in name or "\x00" in name:
        return ""  # traversal-ish garbage: refuse to classify
    dot = name.rfind(".")
    if dot <= 0 or dot == len(name) - 1:
        return ""
    return name[dot:].lower()


def extract(
    *,
    data: bytes,
    filename: str | None,
    max_bytes: int,
) -> ExtractionResult:
    """Validate and extract normalized text from one uploaded resume file."""
    ext = safe_extension(filename)
    if ext not in SUPPORTED_EXTENSIONS:
        raise DocumentParseError(
            "unsupported_format",
            "This file type isn't supported. Use PDF, DOCX, TXT or MD.",
        )
    if not isinstance(data, bytes) or len(data) == 0:
        raise DocumentParseError("empty_file", "The uploaded file is empty.")
    if len(data) > max_bytes:
        raise DocumentParseError(
            "file_too_large",
            "This file is too large. Please upload a smaller resume.",
        )

    # Content sniffing guards the extension claim (magic numbers only).
    if ext == ".pdf" and not data.startswith(b"%PDF-"):
        raise DocumentParseError(
            "invalid_document",
            "We couldn't read this PDF. It may be corrupted.",
        )
    if ext == ".docx" and not data.startswith(b"PK"):
        raise DocumentParseError(
            "invalid_document",
            "We couldn't read this Word document. Please try exporting it again.",
        )

    if ext == ".pdf":
        text, page_count, warnings = _extract_pdf(data)
    elif ext == ".docx":
        text, _para_count, warnings = _extract_docx(data)
        page_count = None
    else:
        text = _decode_text(data)
        warnings = []
        page_count = None

    normalized = normalize_text(text)
    if not normalized:
        raise DocumentParseError(
            "no_extractable_text",
            "No selectable text could be extracted from this document. "
            "Please upload a text-based PDF or DOCX.",
        )
    if len(normalized) > max_bytes * 4:  # absurd expansion guard
        raise DocumentParseError(
            "invalid_document",
            "This document could not be processed safely.",
        )

    return ExtractionResult(
        text=normalized,
        source_format=_FORMAT_LABELS[ext],
        character_count=len(normalized),
        page_count=page_count,
        paragraph_count=None,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------


def _extract_pdf(data: bytes) -> tuple[str, int | None, list[str]]:
    warnings: list[str] = []
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:  # noqa: BLE001 - typed failure below
                raise DocumentParseError(
                    "invalid_document",
                    "This PDF is password-protected. Remove the password "
                    "and try again.",
                ) from exc
        pages = len(reader.pages)
    except PdfReadError as exc:
        raise DocumentParseError(
            "invalid_document",
            "We couldn't read this PDF. It may be corrupted.",
        ) from exc
    except Exception as exc:  # noqa: BLE001 - any parser blow-up is typed
        raise DocumentParseError(
            "invalid_document",
            "We couldn't read this PDF. It may be corrupted.",
        ) from exc

    chunks: list[str] = []
    for index, page in enumerate(reader.pages):
        try:
            chunks.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001 - skip a broken page, keep the rest
            warnings.append(f"page_{index + 1}_skipped")

    return "\n".join(chunks), pages, warnings


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------


def _extract_docx(data: bytes) -> tuple[str, int | None, list[str]]:
    try:
        import docx  # local import keeps module import cost off the hot path

        document = docx.Document(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001 - malformed OOXML is typed
        raise DocumentParseError(
            "invalid_document",
            "We couldn't read this Word document. Please try exporting it again.",
        ) from exc

    parts: list[str] = []

    def _walk(parent: Any) -> None:
        from docx.document import Document as _Document
        from docx.table import Table, _Cell
        from docx.text.paragraph import Paragraph

        for child in parent.iter_inner_content():
            if isinstance(child, Paragraph):
                style = getattr(getattr(child, "style", None), "name", "") or ""
                text_value = child.text or ""
                if style.startswith("Heading") and text_value.strip():
                    parts.append(text_value.strip())
                elif text_value.strip():
                    parts.append(text_value.strip())
            elif isinstance(child, Table):
                for row in child.rows:
                    cells = [cell.text.strip() for cell in row.cells]
                    if any(cells):
                        parts.append(" | ".join(cells))
            elif isinstance(child, _Cell):
                _walk(child)
            elif isinstance(child, _Document):
                _walk(child)

    _walk(document)
    return "\n".join(parts), len(parts), []


# ---------------------------------------------------------------------------
# TXT / MD + normalization
# ---------------------------------------------------------------------------

_TEXT_ENCODINGS: tuple[str, ...] = ("utf-8", "utf-8-sig", "cp1252", "latin-1")


def _decode_text(data: bytes) -> str:
    for encoding in _TEXT_ENCODINGS:
        try:
            decoded = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        if "\x00" not in decoded and _printable_ratio(decoded) >= 0.7:
            return decoded
    return ""


def _printable_ratio(text: str) -> float:
    if not text:
        return 0.0
    printable = sum(
        1
        for ch in text
        if ch.isprintable() or ch in "\n\r\t"
    )
    return printable / len(text)


_WS_RUN_RE = re.compile(r"[ \t]{2,}")
_BLANK_RUN_RE = re.compile(r"\n{3,}")


def normalize_text(text: str) -> str:
    """Line-ending + whitespace normalization; content itself untouched."""
    if not isinstance(text, str):
        return ""
    unified = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    unified = _WS_RUN_RE.sub(" ", unified)
    unified = _BLANK_RUN_RE.sub("\n\n", unified)
    return unified.strip()


def metadata(result: ExtractionResult) -> dict[str, Any]:
    """Safe, PII-free projection for API responses."""
    meta: dict[str, Any] = {
        "source_format": result.source_format,
        "character_count": result.character_count,
        "extraction_status": result.extraction_status,
    }
    if result.page_count is not None:
        meta["page_count"] = result.page_count
    if result.warnings:
        meta["warnings"] = list(result.warnings)
    return meta


__all__ = [
    "DocumentParseError",
    "ExtractionResult",
    "SUPPORTED_EXTENSIONS",
    "extract",
    "metadata",
    "normalize_text",
    "safe_extension",
]
