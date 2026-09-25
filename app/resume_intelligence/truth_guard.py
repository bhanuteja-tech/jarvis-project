"""Strict Truth Guard enforcing NO FABRICATION POLICY across AI-generated resume content."""

from __future__ import annotations

import re

from app.dedup.normalize import informative_tokens
from app.jdunderstanding.taxonomy import find_skill_hits
from app.resume_intelligence.models import FactCheckResult, StructuredResume

# Regex matching numbers, percentages, and metrics
_NUMBER_OR_METRIC_RE = re.compile(
    r"(?:\d+(?:\.\d+)?%|\$\d+(?:\.\d+)?[KMBkmb]?|\d+k\+?|\b\d{1,3}(?:,\d{3})+\b|\b\d+\b)",
    re.IGNORECASE,
)


class ResumeTruthGuard:
    """Enforces that AI-generated resume content contains no fabricated claims."""

    def __init__(self, resume: StructuredResume) -> None:
        self.resume = resume
        self.allowed_tokens = resume.get_evidence_tokens()
        self.allowed_metrics = set(resume.metrics_extracted)
        self.allowed_technologies = {t.lower() for t in resume.technologies}
        for grp in resume.skills:
            for s in grp.skills:
                self.allowed_technologies.add(s.lower())
        for proj in resume.projects:
            for t in proj.tech_stack:
                self.allowed_technologies.add(t.lower())
        for exp in resume.experience:
            for t in exp.technologies:
                self.allowed_technologies.add(t.lower())
        if resume.raw_text:
            for hit in find_skill_hits(resume.raw_text):
                self.allowed_technologies.add(hit.canonical.lower())

        # Build set of all allowed numbers from the candidate evidence
        self.allowed_numbers: set[str] = set()
        for text in resume.evidence_corpus:
            if isinstance(text, str):
                for match in _NUMBER_OR_METRIC_RE.findall(text):
                    self.allowed_numbers.add(match.strip().lower())
        if resume.raw_text:
            for match in _NUMBER_OR_METRIC_RE.findall(resume.raw_text):
                self.allowed_numbers.add(match.strip().lower())
        for proj in resume.projects:
            for b in proj.bullets:
                for match in _NUMBER_OR_METRIC_RE.findall(b):
                    self.allowed_numbers.add(match.strip().lower())
        for exp in resume.experience:
            for b in exp.bullets:
                for match in _NUMBER_OR_METRIC_RE.findall(b):
                    self.allowed_numbers.add(match.strip().lower())

    def check_text(self, text: str, *, section: str = "general") -> FactCheckResult:
        """Validate text against candidate evidence corpus; flag unverified claims."""
        if not text or not text.strip():
            return FactCheckResult(supported=True)

        flagged_claims: list[str] = []
        notes: list[str] = []

        # 1. Check numbers and metrics
        found_numbers = _NUMBER_OR_METRIC_RE.findall(text)
        for num in found_numbers:
            num_clean = num.strip().lower()
            # Ignore standard bullet counts or tiny indices 1, 2, 3 in non-metric contexts if allowed
            if num_clean not in self.allowed_numbers and num_clean not in {"1", "2", "3", "4", "5", "6"}:
                # If it's a percentage or scale number, it's definitely an invented metric
                if "%" in num or "$" in num or "k" in num_clean or int(re.sub(r"\D", "", num) or 0) > 10:
                    flagged_claims.append(f"Unverified metric/number: {num}")
                    notes.append(f"Metric '{num}' was not found in candidate's original resume evidence.")

        # 2. Check for unsupported technologies
        text_skills = find_skill_hits(text)
        for hit in text_skills:
            skill_name = hit.canonical.lower()
            if skill_name not in self.allowed_technologies:
                # Skill was not found in original candidate profile
                flagged_claims.append(f"Unsupported skill/technology: {hit.canonical}")
                notes.append(
                    f"Skill '{hit.canonical}' appears in generated text but is not evidenced in candidate resume."
                )

        # 3. Informative token containment check (ignoring generic connecting words)
        gen_tokens = informative_tokens(text)
        unsupported_tokens = gen_tokens - self.allowed_tokens
        # Any digit-bearing token must be in allowed tokens
        unsupported_digit_tokens = [t for t in unsupported_tokens if any(c.isdigit() for c in t)]
        for dt in unsupported_digit_tokens:
            if dt not in self.allowed_numbers:
                flagged_claims.append(f"Unverified token with digits: {dt}")

        supported = len(flagged_claims) == 0
        return FactCheckResult(
            supported=supported,
            flagged_claims=list(dict.fromkeys(flagged_claims)),
            verified_tokens=sorted(gen_tokens & self.allowed_tokens),
            notes=notes,
        )

    def sanitize_output(self, text: str) -> str:
        """Strip raw markdown formatting that could alter document typography and remove fake metrics."""
        cleaned = text.strip()

        # Remove markdown bolding: **word** -> word
        cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)
        # Remove markdown headers: ### Header -> Header
        cleaned = re.sub(r"^#+\s*", "", cleaned, flags=re.MULTILINE)
        # Remove backticks: `code` -> code
        cleaned = re.sub(r"`(.*?)`", r"\1", cleaned)

        # Sanitize unverified metrics if detected:
        # e.g. "reduced latency by 35% and boosted throughput by 42%" -> "reduced latency and boosted throughput"
        found_numbers = _NUMBER_OR_METRIC_RE.findall(cleaned)
        for num in found_numbers:
            num_clean = num.strip().lower()
            if num_clean not in self.allowed_numbers and ("%" in num or "$" in num or "k" in num_clean):
                # Replace pattern like "by 35%" or "by 42%" with qualitative phrasing
                cleaned = re.sub(rf"\bby\s+{re.escape(num)}(?!\w)", "significantly", cleaned, flags=re.IGNORECASE)
                cleaned = re.sub(rf"(?<!\w){re.escape(num)}(?!\w)", "", cleaned)

        # Clean multiple spaces and blank lines
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()
