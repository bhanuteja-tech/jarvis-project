"""Section segmentation: heading variants, pseudo-headings, retention."""

from __future__ import annotations

from app.jdunderstanding.models import SectionKind
from app.jdunderstanding.sections import segment_document
from app.jdunderstanding.text import bullet_items, extract_text_document


def _segment(raw: str, max_chars: int = 20_000):
    return segment_document(extract_text_document(raw, max_chars=max_chars))


class TestHeadingVariants:
    def test_canonical_and_variant_headings_map_to_same_kind(self) -> None:
        raw = (
            "WHAT YOU'LL DO\n- Build models\n"
            "Required Qualifications\n- 5 years Python\n"
            "Bonus points\n- Kubernetes\n"
            "About the team\nWe are a startup.\n"
        )
        segmentation = _segment(raw)

        kinds = [section.kind for section in segmentation.sections if section.blocks]
        assert SectionKind.RESPONSIBILITIES in kinds
        assert SectionKind.REQUIREMENTS in kinds
        assert SectionKind.PREFERRED in kinds
        assert SectionKind.ABOUT_COMPANY in kinds

    def test_prefix_rules_cover_unlisted_variants(self) -> None:
        raw = "Minimum Qualifications We Love\n- Curiosity\n"
        segmentation = _segment(raw)

        assert any(section.kind is SectionKind.REQUIREMENTS for section in segmentation.sections)

    def test_unknown_heading_retained_as_other(self) -> None:
        raw = "Our Galactic Mission\nExplore strange new worlds.\n"
        segmentation = _segment(raw)

        assert segmentation.unrecognized_headings == 1
        joined = "\n".join(s.text for s in segmentation.sections)
        assert "strange new worlds" in joined  # content never dropped

    def test_plain_text_pseudo_heading_detected(self) -> None:
        raw = "Requirements\nPython required.\n"
        segmentation = _segment(raw)

        assert any(section.kind is SectionKind.REQUIREMENTS for section in segmentation.sections)


class TestContentIntegrity:
    def test_html_script_content_dropped(self) -> None:
        raw = "<script>var tracking = 1;</script><h2>Requirements</h2><p>Go</p>"
        document = extract_text_document(raw, max_chars=10_000)

        assert "tracking" not in document.plain_text.lower()
        assert "Go" in document.plain_text

    def test_truncation_reported_not_silent(self) -> None:
        raw = "word " * 5000
        document = extract_text_document(raw, max_chars=100)

        assert document.truncated is True
        assert len(document.plain_text) <= 101


class TestBulletSplitting:
    def test_dash_bullets_split(self) -> None:
        items = bullet_items("- Build ML models\n- Deploy models to production")

        assert items == ["Build ML models", "Deploy models to production"]

    def test_numbered_bullets_split(self) -> None:
        items = bullet_items("1. Design pipelines\n2. Collaborate with DS")

        assert len(items) == 2

    def test_paragraph_without_bullets_stays_whole(self) -> None:
        items = bullet_items("Own the roadmap end to end.")

        assert items == ["Own the roadmap end to end."]
