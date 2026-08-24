"""Document-extraction layer: format support, typed errors, normalization."""

from __future__ import annotations

import pytest

from app.jarvis.document_parser import (
    DocumentParseError,
    extract,
    normalize_text,
    safe_extension,
)
from tests.jarvis.doc_fixtures import (
    SAMPLE_RESUME_LINES,
    make_docx,
    make_docx_with_table,
    make_empty_pdf,
    make_pdf,
)

MAX_BYTES = 10 * 1024 * 1024


def run(data: bytes, name: str):
    return extract(data=data, filename=name, max_bytes=MAX_BYTES)


class TestTxtMd:
    def test_txt_extraction(self) -> None:
        result = run(b"Python engineer.\nSkills: python\n", "resume.txt")
        assert "Python engineer" in result.text
        assert result.source_format == "txt"
        assert result.page_count is None

    def test_md_extraction(self) -> None:
        result = run(b"# Head\n\n- python\n- sql\n", "resume.md")
        assert "python" in result.text and "sql" in result.text
        assert result.source_format == "md"

    def test_cp1252_decoding(self) -> None:
        raw = "Caf\u00e9 manager.\n".encode("cp1252")
        result = run(raw, "r.txt")
        assert "Caf" in result.text

    def test_binary_txt_rejected_as_no_text(self) -> None:
        payload = bytes(range(256)) * 64
        with pytest.raises(DocumentParseError) as excinfo:
            run(payload, "blob.txt")
        assert excinfo.value.code in {"no_extractable_text", "invalid_document"}


class TestPdf:
    def test_pdf_extraction(self) -> None:
        result = run(make_pdf(SAMPLE_RESUME_LINES), "resume.pdf")
        assert "Senior Python Engineer" in result.text
        assert "docker" in result.text
        assert result.source_format == "pdf"
        assert result.page_count == 1

    def test_scanned_pdf_no_extractable_text(self) -> None:
        with pytest.raises(DocumentParseError) as excinfo:
            run(make_empty_pdf(), "scanned.pdf")
        assert excinfo.value.code == "no_extractable_text"

    def test_wrong_magic_invalid_document(self) -> None:
        with pytest.raises(DocumentParseError) as excinfo:
            run(b"%PDF-1.4 but total garbage", "fake.pdf")
        assert excinfo.value.code == "invalid_document"

    def test_malformed_pdf_body(self) -> None:
        data = bytearray(make_pdf(SAMPLE_RESUME_LINES))
        data[40:120] = b"\x00" * 80  # corrupt an object body
        with pytest.raises(DocumentParseError) as excinfo:
            run(bytes(data), "broken.pdf")
        assert excinfo.value.code == "invalid_document"


class TestDocx:
    def test_docx_paragraphs_and_headings(self) -> None:
        result = run(
            make_docx(["Engineer", "Skills: python, sql"], heading_first=True),
            "resume.docx",
        )
        assert "Engineer" in result.text
        assert "python" in result.text
        assert result.source_format == "docx"

    def test_docx_table_text_preserved(self) -> None:
        result = run(
            make_docx_with_table([["Skill", "Years"], ["python", "5"]]),
            "table.docx",
        )
        assert "python" in result.text and "Years" in result.text

    def test_malformed_docx(self) -> None:
        with pytest.raises(DocumentParseError) as excinfo:
            run(b"PK\x03\x04 followed by junk", "broken.docx")
        assert excinfo.value.code == "invalid_document"


class TestValidation:
    def test_unsupported_extension(self) -> None:
        for name, payload in [
            ("resume.doc", b"text"),
            ("image.png", b"\x89PNG\r\n"),
            ("archive.zip", b"PK\x03\x04zzz"),
            ("noext", b"text"),
            ("no.extension.", b"text"),
        ]:
            with pytest.raises(DocumentParseError) as excinfo:
                run(payload, name)
            assert excinfo.value.code == "unsupported_format", name

    def test_traversal_filename_never_used_as_path(self) -> None:
        # Basename is taken for extension inspection only; a traversal-ish
        # name with valid extension + real content parses normally.
        result = run(make_pdf(SAMPLE_RESUME_LINES), "../../evil/resume.pdf")
        assert "Senior Python Engineer" in result.text

    def test_empty_file(self) -> None:
        with pytest.raises(DocumentParseError) as excinfo:
            run(b"", "resume.txt")
        assert excinfo.value.code == "empty_file"

    def test_oversized_file_rejected_before_parsing(self) -> None:
        big = b"a" * (MAX_BYTES + 1)
        with pytest.raises(DocumentParseError) as excinfo:
            run(big, "resume.txt")
        assert excinfo.value.code == "file_too_large"

    def test_mime_extension_mismatch_content_wins(self) -> None:
        # Claims .pdf but is a ZIP/DOCX container -> magic check rejects.
        with pytest.raises(DocumentParseError) as excinfo:
            run(b"PK\x03\x04not really docx", "report.pdf")
        assert excinfo.value.code == "invalid_document"

    def test_safe_extension_traversal_garbage(self) -> None:
        assert safe_extension(None) == ""
        assert safe_extension("") == ""
        assert safe_extension("a/b/c.PDF") == ".pdf"
        assert safe_extension("no\\path\\here.docx") == ".docx"
        assert safe_extension(".hidden") == ""


class TestNormalization:
    def test_line_endings_and_whitespace(self) -> None:
        assert normalize_text("a\r\nb\rc   d") == "a\nb\nc d"

    def test_blank_run_collapse_keeps_paragraph_breaks(self) -> None:
        assert normalize_text("a\n\n\n\n\nb") == "a\n\nb"

    def test_bom_stripped(self) -> None:
        out = normalize_text("\ufeffResume")
        assert out == "Resume"


class TestPiiBoundary:
    def test_error_messages_never_echo_content_or_names(self) -> None:
        secret_name = "Jane Q. Applicant"
        payloads = [
            (make_pdf([f"{secret_name}", "contact jane@example.com"]), "her_resume.pdf"),
            (b"PK\x01\x02jane" + secret_name.encode(), "jane.docx"),
            (f"{secret_name} <jane@example.com>".encode(), "jane.txt"),
        ]
        for data, name in payloads:
            try:
                run(data, name)
            except DocumentParseError as exc:
                blob = f"{exc.message} {exc.code}"
                assert secret_name.lower() not in blob.lower()
                assert "jane@example.com" not in blob.lower()
                assert name not in blob
