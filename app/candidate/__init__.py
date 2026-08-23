"""Phase 3 — Candidate / Resume Intelligence.

Deterministic resume -> CandidateProfile pipeline:

    candidate_input {text | structured}
        -> text acquisition (frozen stdlib parser reuse, size-capped)
        -> resume section segmentation
        -> contact (PII-isolated) / identity / skills / experience /
           education / certifications / projects / preferences extractors
        -> CandidateProfile (every fact: value + status + evidence)
        -> CandidateResult envelope

Rules:
- One candidate_input => one CandidateProfile (no merging).
- No persistence; profile lives in graph state only.
- No PDF/DOCX/OCR; plain text + pre-structured input only.
- No LLM. Deterministic only. UNKNOWN is first-class.
- PII is quarantined in a dedicated contact block, never logged;
  optional ``candidate_redact_pii`` strips values post-construction.
"""

from __future__ import annotations

from app.candidate.analyzer import CandidateResult, ResumeAnalyzer, build_analyzer
from app.candidate.models import (
    CandidateProfile,
    ContactField,
    ExperienceField,
    IdentityField,
)

__all__ = [
    "CandidateProfile",
    "CandidateResult",
    "ContactField",
    "ExperienceField",
    "IdentityField",
    "ResumeAnalyzer",
    "build_analyzer",
]
