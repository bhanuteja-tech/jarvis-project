"""Tolerant evidence-path resolver over the CandidateProfile dump.

Supported path grammar (dot-separated segments, optional single bracket):

    resume.skills.items[name=python]
    resume.experience[0]            # negative indices allowed
    resume.experience[-1].title
    resume.experience[0].highlights[2]
    resume.projects[1].url
    resume.education.items[0].degree
    resume.certifications.items[name=aws certified ...]
    resume.summary.text

Bracket payloads are either an integer list index or a ``name=<value>``
filter over ``items`` lists (case-insensitive, trimmed). Unresolvable paths
return ``(False, None)`` — never raise.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_SEGMENT_RE = re.compile(r"^([A-Za-z_]+)(?:\[(.+)\])?$")


def _val(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _apply_bracket(container: Any, payload: str) -> tuple[bool, Any]:
    payload = payload.strip()
    # Field-wrapper tolerance: experience/projects/... are {status, items}
    # dicts; a numeric index on the wrapper means the items list.
    if isinstance(container, Mapping) and isinstance(container.get("items"), (list, tuple)):
        container = container["items"]
    if payload.startswith("name="):
        wanted = payload.split("=", 1)[1].strip().strip("'\"").lower()
        if not isinstance(container, list):
            return False, None
        for item in container:
            if isinstance(item, Mapping):
                name = item.get("name")
                if isinstance(name, str) and name.strip().lower() == wanted:
                    return True, item
        return False, None
    try:
        index = int(payload)
    except ValueError:
        return False, None
    if not isinstance(container, (list, tuple)):
        return False, None
    if -len(container) <= index < len(container):
        return True, container[index]
    return False, None


def resolve_path(profile: Mapping[str, Any], path: str) -> tuple[bool, Any]:
    """Resolve an evidence-ref path against the candidate profile dump."""
    if not isinstance(profile, Mapping) or not isinstance(path, str) or not path.strip():
        return False, None

    # Strip "resume." namespace prefix — paths are relative to profile root.
    clean_path = re.sub(r"^resume\.", "", path.strip())
    if not clean_path:
        return False, None

    current: Any = profile
    for raw_segment in clean_path.split("."):
        match = _SEGMENT_RE.match(raw_segment.strip())
        if match is None:
            return False, None
        key, bracket = match.group(1), match.group(2)

        if isinstance(current, list):
            # Attribute-style access on list elements is unsupported.
            return False, None
        if not isinstance(current, Mapping):
            return False, None

        current = _val(current.get(key)) if key in current else current.get(key)
        if current is None:
            return False, None
        if isinstance(current, Mapping):
            current = {str(k): v for k, v in current.items()}

        if bracket is not None:
            found, current = _apply_bracket(current, bracket)
            if not found:
                return False, None
    return True, current


def gather_evidence_corpus(profile: Mapping[str, Any]) -> list[str]:
    """All candidate-authored text spans — the factuality universe.

    Mirrors the Phase-5 collector field-for-field so T1 containment uses the
    identical universe.
    """
    texts: list[str] = []
    summary = profile.get("summary") or {}
    text_value = summary.get("text")
    if isinstance(text_value, str):
        texts.append(text_value)

    skills_section = profile.get("skills") or {}
    for item in skills_section.get("items") or []:
        for key in ("name", "matched_as"):
            value = item.get(key)
            if isinstance(value, str):
                texts.append(value)

    experience_section = profile.get("experience") or {}
    for item in experience_section.get("items") or []:
        for key in ("title", "company", "date_range_raw"):
            value = item.get(key)
            if isinstance(value, str):
                texts.append(value)
        highlights = item.get("highlights") or []
        texts.extend(h for h in highlights if isinstance(h, str))

    projects_section = profile.get("projects") or {}
    for item in projects_section.get("items") or []:
        for key in ("name", "description", "url"):
            value = item.get(key)
            if isinstance(value, str):
                texts.append(value)

    education_section = profile.get("education") or {}
    for item in education_section.get("items") or []:
        texts.extend(str(value) for value in item.values() if isinstance(value, str))

    certifications_section = profile.get("certifications") or {}
    for item in certifications_section.get("items") or []:
        name = item.get("name")
        if isinstance(name, str):
            texts.append(name)

    return texts


def collect_evidence_refs(tailored_resume: Mapping[str, Any]) -> list[str]:
    """Every evidence ref/path declared anywhere in the tailored artifact."""
    refs: list[str] = []

    summary = tailored_resume.get("summary") or {}
    refs.extend(summary.get("evidence_refs") or [])

    for section_key in ("skills", "experience", "projects", "education", "certifications"):
        for item in tailored_resume.get(section_key) or []:
            refs.extend(item.get("evidence_refs") or [])
            bullet_ref = item.get("evidence_ref")
            if isinstance(bullet_ref, str):
                refs.append(bullet_ref)
            for bullet in item.get("highlights") or []:
                bullet_ref_inner = bullet.get("evidence_ref")
                if isinstance(bullet_ref_inner, str):
                    refs.append(bullet_ref_inner)

    changes = tailored_resume.get("changes") or []
    for change in changes:
        refs.extend(change.get("evidence_refs") or [])

    return [ref for ref in refs if isinstance(ref, str) and ref.strip()]


__all__ = [
    "collect_evidence_refs",
    "gather_evidence_corpus",
    "resolve_path",
]
