"""Generic static-HTML signal extraction (no site-specific selectors).

Produces a read-only :class:`DomSignals` record consumed by the orchestrator:
title/h1/meta-description/canonical link, apply-intent anchors, requisition
IDs from URL shapes, the best-effort main-content region, and SPA indicators
that gate the optional browser layer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlsplit

from bs4 import BeautifulSoup, Tag

_APPLY_TEXTS: frozenset[str] = frozenset(
    {
        "apply",
        "apply now",
        "apply for this job",
        "apply for this role",
        "submit application",
        "apply online",
    }
)
_APPLY_PATH_RE = re.compile(r"/apply(?:[/?#]|$)|/jobs/[^/]+/apply", re.IGNORECASE)

_REQUISITION_QUERY_KEYS: frozenset[str] = frozenset(
    {"gh_jid", "jid", "job", "jobid", "ashby_jid", "posting_id", "req_id"}
)
_SLUG_DIGITS_RE = re.compile(r"-(\d{3,})(?:$|[/?#])")

_MAIN_SELECTORS = ("article", "main", '[role="main"]')

_SPA_ROOT_IDS = {"root", "app", "__next", "mount"}


@dataclass(frozen=True)
class DomSignals:
    title_tag: str | None
    h1_text: str | None
    meta_description: str | None
    og_title: str | None
    canonical_link: str | None
    apply_links: list[tuple[str, str]] = field(default_factory=list)
    internal_job_links: int = 0
    requisition_ids: list[str] = field(default_factory=list)
    main_text_len: int = 0
    main_html: str | None = None
    body_text_len: int = 0
    script_char_count: int = 0
    spa_root_present: bool = False

    @property
    def spa_indicators(self) -> bool:
        return (self.spa_root_present or self.body_text_len < 400) and self.script_char_count > 4000


def _text_of(element: Tag | None) -> str | None:
    if element is None:
        return None
    text = element.get_text(" ", strip=True)
    return text or None


def extract_dom_signals(html: str) -> DomSignals:
    soup = BeautifulSoup(html, "html.parser")

    canonical = soup.find("link", attrs={"rel": lambda v: v and "canonical" in v})
    meta_desc = soup.find("meta", attrs={"name": "description"})
    og_title = soup.find("meta", attrs={"property": "og:title"})

    apply_links: list[tuple[str, str]] = []
    for anchor in soup.find_all("a"):
        href = (anchor.get("href") or "").strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        anchor_text = (_text_of(anchor) or "").lower()
        if href.lower().startswith(("http", "/")) and (
            _APPLY_PATH_RE.search(href) or anchor_text in _APPLY_TEXTS
        ):
            apply_links.append((href, _text_of(anchor) or ""))

    scripts_total = sum(len(script.string or "") for script in soup.find_all("script"))

    body = soup.body or soup
    body_text = _text_of(body) or ""
    spa_root = any(soup.find(id=root_id) is not None for root_id in _SPA_ROOT_IDS)

    main_region = None
    for selector in _MAIN_SELECTORS:
        found = soup.select_one(selector)
        if found is not None and len(found.get_text(strip=True)) >= 200:
            main_region = found
            break
    if main_region is None:
        # Density fallback: largest text-bearing container among common wrappers.
        candidates = [
            element
            for element in soup.find_all(["section", "div"])
            if len(element.get_text(strip=True)) >= 200
        ]
        if candidates:
            main_region = max(candidates, key=lambda el: len(el.get_text(strip=True)))

    signals = DomSignals(
        title_tag=_text_of(soup.title),
        h1_text=_text_of(soup.h1),
        meta_description=(meta_desc.get("content", "").strip() if meta_desc else None),
        og_title=og_title.get("content", "").strip() if og_title else None,
        canonical_link=(canonical.get("href", "").strip() if canonical else None),
        apply_links=apply_links,
        internal_job_links=sum(1 for a in soup.find_all("a") if "/jobs" in (a.get("href") or "")),
        requisition_ids=_requisition_ids_from_html(html),
        main_text_len=len(main_region.get_text(" ", strip=True)) if main_region else 0,
        main_html=str(main_region) if main_region else None,
        body_text_len=len(body_text),
        script_char_count=scripts_total,
        spa_root_present=spa_root,
    )
    return signals


def _requisition_ids_from_html(url: str) -> list[str]:
    """Requisition/job ids visible in the page's own URL shapes."""
    parts = urlsplit(url)
    ids: list[str] = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key.lower() in _REQUISITION_QUERY_KEYS and value.strip():
            ids.append(value.strip())
    match = _SLUG_DIGITS_RE.search(parts.path)
    if match:
        ids.append(match.group(1))
    return ids


__all__ = ["DomSignals", "extract_dom_signals"]
