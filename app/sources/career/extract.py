"""CareerPageExtractor orchestrator.

Pipeline per candidate URL:
    validate -> robots gate -> guarded fetch -> decode
    -> L1 JSON-LD JobPosting -> L2 embedded job objects (narrow)
    -> L3 generic DOM signals -> verifier (explicit acceptance contract)
    -> [optional browser pass when SPA-suspected] -> canonical Job

Approved rules enforced here:
- Correction #1: only timezone-aware ISO datetimes populate source_created_at/
  source_updated_at; date-only or naive values keep the raw text in
  ``extra.date_posted_display`` / ``extra.date_modified_display``.
- A search snippet is never trusted: everything comes from the fetched page.
- Non-job pages yield NO_JOB_DETECTED(reason=...) — never silent emptiness.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from app.config.settings import Settings
from app.models.job import Job, Salary
from app.sources.base import SourceError, SourceWarning
from app.sources.career.errors import (
    CareerPageError,
    InvalidCareerUrlError,
    RobotsDisallowedError,
    RobotsUnavailableError,
    SourceSSRFBlockedError,
    UnsupportedSchemeError,
)
from app.sources.career.fetch import PAGE_CONTENT_TYPES, GuardedFetcher
from app.sources.career.html_extract import DomSignals, extract_dom_signals
from app.sources.career.jsonld import extract_jobpostings, first_text
from app.sources.career.models import ExtractionResult, SignalBag
from app.sources.career.robots import RobotsGate
from app.sources.career.security import Resolver, validate_url
from app.sources.errors import (
    SourceHTTPError,
    SourceNetworkError,
    SourceTimeoutError,
)

logger = logging.getLogger(__name__)

SOURCE_NAME = "career_page"

_IDENTITY_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL, "https://jarvis.local/career-page/identity"
)

_UNIT_PERIODS = {"hour", "day", "week", "month", "year"}
_MAX_EMBEDDED_NODES = 10


# ---------------------------------------------------------------------------
# Schema.org value helpers
# ---------------------------------------------------------------------------


def parse_schema_datetime(value: Any) -> tuple[datetime | None, str | None]:
    """Correction #1: ONLY timezone-aware ISO datetimes become datetimes.

    Date-only ("2026-08-22"), timezone-naive, or unparseable values return
    ``(None, original_text)`` so callers preserve the display string without
    manufacturing precision.
    """
    if not isinstance(value, str) or not value.strip():
        return None, None
    raw = value.strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None, raw
    if parsed.tzinfo is None:
        return None, raw
    return parsed.astimezone(UTC), raw


def _blank_to_none(value: Any) -> str | None:
    if value is None or not value.strip():
        return None
    return value


def hiring_organization_name(
    posting: Mapping[str, Any],
) -> tuple[str | None, Mapping[str, Any] | None]:
    org: Any = posting.get("hiringOrganization")
    if isinstance(org, list):
        org = next((item for item in org if isinstance(item, (dict, str))), None)
    if isinstance(org, str):
        return _blank_to_none(org), None
    if isinstance(org, Mapping):
        return first_text(org.get("name")), org
    return None, None


def identifier_value(posting: Mapping[str, Any]) -> str | None:
    identifier: Any = posting.get("identifier")
    if isinstance(identifier, str):
        return _blank_to_none(identifier)
    if isinstance(identifier, list):
        identifier = next((item for item in identifier if isinstance(item, Mapping)), None)
    if isinstance(identifier, Mapping):
        return first_text(identifier.get("value"))
    return None


def build_location(posting: Mapping[str, Any]) -> str | None:
    job_location: Any = posting.get("jobLocation")
    items: list[Any]
    if isinstance(job_location, list):
        items = job_location
    elif job_location is not None:
        items = [job_location]
    else:
        items = []

    for item in items[:1]:  # primary location only
        if not isinstance(item, Mapping):
            continue
        address: Any = item.get("address")
        if isinstance(address, Mapping):
            parts = [
                first_text(address.get(key))
                for key in ("addressLocality", "addressRegion", "addressCountry")
            ]
            joined = ", ".join(part for part in parts if part)
            if joined:
                return joined
        elif isinstance(address, str) and address.strip():
            return address.strip()

    location_type = first_text(posting.get("jobLocationType"))
    if location_type is not None and location_type.upper() == "TELECOMMUTE":
        # Machine enum normalization (schema.org value), recorded provenance.
        return "Remote"
    return None


def application_contact_url(posting: Mapping[str, Any]) -> str | None:
    contact = posting.get("applicationContact")
    if isinstance(contact, Mapping):
        url_value = contact.get("url")
        if isinstance(url_value, str) and url_value.strip():
            return url_value.strip()
    return None


def build_salary(posting: Mapping[str, Any]) -> tuple[Salary | None, str | None]:
    """Structured salary extraction only (Schema.org baseSalary family).

    Returns ``(salary, note)``. Arbitrary numbers in prose are never consulted.
    Notes: ``salary_currency_missing`` when amounts exist without currency;
    ``salary_point_value`` when a single value (not a range) was provided.
    """

    def num(value: Any) -> Decimal | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return Decimal(str(value))

    currency = first_text(posting.get("salaryCurrency"))
    base = posting.get("baseSalary")

    min_amount: Decimal | None = None
    max_amount: Decimal | None = None
    period: str | None = None
    point = False

    if isinstance(base, (int, float)) and not isinstance(base, bool):
        min_amount = num(base)
        point = True
    elif isinstance(base, Mapping):
        base_type = str(base.get("@type", "")).lower()
        currency = currency or first_text(
            base.get("currency") or base.get("priceCurrency")
        )
        unit = first_text(base.get("unitText"))
        if unit and unit.lower() in _UNIT_PERIODS:
            period = unit.lower()

        price = num(base.get("price"))
        direct_min = num(base.get("minValue"))
        direct_max = num(base.get("maxValue"))

        value_node: Any = base.get("value")
        if isinstance(value_node, list):
            dict_node = next((v for v in value_node if isinstance(v, Mapping)), None)
            scalar = num(next((v for v in value_node if isinstance(v, (int, float))), None))
            value_node = dict_node if dict_node is not None else scalar

        if price is not None:  # PriceSpecification shape
            min_amount = price
            point = True
        elif isinstance(value_node, Mapping):
            unit_inner = first_text(value_node.get("unitText"))
            if unit_inner and unit_inner.lower() in _UNIT_PERIODS and period is None:
                period = unit_inner.lower()
            min_amount = num(value_node.get("minValue"))
            max_amount = num(value_node.get("maxValue"))
            single = num(value_node.get("value"))
            if single is not None and min_amount is None and max_amount is None:
                min_amount = single
                point = True
        elif isinstance(value_node, (int, float)):
            min_amount = num(value_node) if False else num(value_node)
            point = True
        elif direct_min is not None or direct_max is not None:
            min_amount, max_amount = direct_min, direct_max
        elif base_type == "monetaryamount":
            # MonetaryAmount with nothing recognizable inside: ignore safely.
            pass

    if min_amount is None and max_amount is None:
        return None, None
    if currency is None:
        return None, "salary_currency_missing"
    return (
        Salary(
            min_amount=min_amount,
            max_amount=max_amount,
            currency=currency.upper(),
            period=period,
        ),
        ("salary_point_value" if point else None),
    )


# ---------------------------------------------------------------------------
# Layer 2: embedded structured job data (narrow whitelist scan)
# ---------------------------------------------------------------------------

_EMBEDDED_DEPTH = 6


def _find_embedded_jobs(node: Any, depth: int, out: list[dict[str, Any]]) -> None:
    if depth > _EMBEDDED_DEPTH or len(out) >= _MAX_EMBEDDED_NODES:
        return
    if isinstance(node, list):
        for item in node[:50]:
            _find_embedded_jobs(item, depth + 1, out)
        return
    if not isinstance(node, dict):
        return
    title = node.get("title")
    description = node.get("description")
    if (
        isinstance(title, str)
        and title.strip()
        and isinstance(description, str)
        and len(description.strip()) >= 80
    ):
        out.append(node)
        return  # accepted object: do not recurse further into it
    for key, value in node.items():
        if key.startswith("@"):
            continue
        _find_embedded_jobs(value, depth + 1, out)


def embedded_job_candidates(soup: Any) -> list[dict[str, Any]]:
    """Recognized bootstrap containers only (__NEXT_DATA__, INITIAL_STATE)."""
    scripts: list[str] = []
    next_data = soup.find("script", id="__NEXT_DATA__")
    if next_data is not None:
        scripts.append(next_data.string or "")
    for tag in soup.find_all("script"):
        text = tag.string or ""
        match = re.match(r"\s*window\.__INITIAL_STATE__\s*=\s*", text)
        if match:
            scripts.append(text[match.end():].rstrip().rstrip(";"))

    found: list[dict[str, Any]] = []
    for raw in scripts:
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        _find_embedded_jobs(data, 0, found)
    return found


# ---------------------------------------------------------------------------
# Layer offering + assembly helpers
# ---------------------------------------------------------------------------


def _offer_jsonld(bag: SignalBag, extras: dict[str, Any], posting: Mapping[str, Any]) -> None:
    layer = "jsonld"
    bag.offer("title", layer, first_text(posting.get("title")) or first_text(posting.get("name")))
    bag.offer("description", layer, first_text(posting.get("description")))

    company_name, org_node = hiring_organization_name(posting)
    bag.offer("company", layer, company_name)

    employment_type = first_text(posting.get("employmentType"))
    if employment_type is None and isinstance(posting.get("employmentType"), list):
        employment_type = next(
            (
                item.strip()
                for item in posting["employmentType"]
                if isinstance(item, str) and item.strip()
            ),
            None,
        )
    bag.offer("employment_type", layer, employment_type)
    bag.offer("location", layer, build_location(posting))

    qualifications = first_text(posting.get("qualifications"))
    experience = first_text(posting.get("experienceRequirements"))
    education = first_text(posting.get("educationRequirements"))
    bag.offer("requirements", layer, qualifications or experience or education)
    bag.offer("responsibilities", layer, first_text(posting.get("responsibilities")))
    bag.offer("apply_url", layer, application_contact_url(posting))

    direct_apply = posting.get("directApply")
    if isinstance(direct_apply, bool):
        extras["direct_apply"] = direct_apply
    extras["occupational_category"] = first_text(posting.get("occupationalCategory"))
    skills = posting.get("skills")
    extras["skills"] = first_text(skills) if isinstance(skills, str) else skills
    extras["education_requirements"] = education
    applicant_locations = posting.get("applicantLocationRequirements")
    if applicant_locations is not None:
        extras["applicant_location_requirements"] = applicant_locations
    if isinstance(org_node, Mapping):
        extras["hiring_organization_same_as"] = first_text(org_node.get("sameAs"))

    created, created_display = parse_schema_datetime(posting.get("datePosted"))
    if created is not None:
        bag.offer("source_created_at", layer, created)
    updated, updated_display = parse_schema_datetime(posting.get("dateModified"))
    if updated is not None:
        bag.offer("source_updated_at", layer, updated)

    valid_through, valid_display = parse_schema_datetime(posting.get("validThrough"))
    extras["valid_through"] = valid_through.isoformat() if valid_through else valid_display
    if created_display:
        extras.setdefault("date_posted_display", created_display)
    if updated_display:
        extras.setdefault("date_modified_display", updated_display)

    identifier = identifier_value(posting)
    if identifier:
        extras["jsonld_identifier"] = identifier


def _canonical_pair(final_url: str, html: str) -> tuple[str, bool]:
    from app.sources.career.url_canon import canonicalize_with_declared

    soup = BeautifulSoup(html, "html.parser")
    link = soup.find("link", attrs={"rel": lambda v: v and "canonical" in v})
    declared = link.get("href", "").strip() if link else None
    return canonicalize_with_declared(final_url, declared)


def _main_text(soup: Any) -> str | None:
    from app.sources.career.html_extract import _MAIN_SELECTORS

    for selector in _MAIN_SELECTORS:
        element = soup.select_one(selector)
        if element is not None and len(element.get_text(strip=True)) >= 80:
            return element.get_text(" ", strip=True)
    return None


def _display_dates(soup: Any) -> list[str]:
    """Relative/human date texts from <time> tags, preserved verbatim."""
    displays: list[str] = []
    for time_tag in soup.find_all("time")[:5]:
        text = time_tag.get_text(" ", strip=True)
        datetime_attr = time_tag.get("datetime")
        if text and (not datetime_attr or not _looks_machine(datetime_attr)):
            displays.append(text)
    return displays


def _looks_machine(value: str) -> bool:
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}", value))


def _best_dom_apply(dom: DomSignals, final_url: str) -> str | None:
    for href, _text in dom.apply_links:
        absolute = urljoin(final_url, href)
        parts = urlsplit(absolute)
        if parts.scheme not in {"http", "https"}:
            continue
        host = (parts.hostname or "").lower()
        target_host = (urlsplit(final_url).hostname or "").lower()
        if host and host != target_host:
            return absolute  # external ATS apply links are the strongest signal
    for href, _text in dom.apply_links:
        absolute = urljoin(final_url, href)
        if urlsplit(absolute).scheme in {"http", "https"}:
            return absolute
    return None


def _verify(bag: SignalBag, dom: DomSignals) -> tuple[str | None, str | None]:
    """Acceptance contract. Returns (reason|None, confidence|None)."""
    title = _blank_to_none(bag.get("title"))
    description = _blank_to_none(bag.get("description"))
    if not title or not description:
        reason = (
            "listing_page_detected"
            if dom.internal_job_links >= 5
            else "insufficient_evidence"
        )
        return reason, None

    layers = {bag.layer_of("title"), bag.layer_of("description")}
    if layers == {"jsonld"}:
        return None, "high"
    if "embedded" in layers and "dom" not in layers and "meta" not in layers:
        return None, "medium"
    if bag.get("apply_url") and dom.main_text_len >= 200:
        return None, "medium"

    reason = (
        "listing_page_detected" if dom.internal_job_links >= 5 else "insufficient_evidence"
    )
    return reason, None


def _resolve_identity(
    extras: Mapping[str, Any], dom: DomSignals, canon_final: str
) -> tuple[str, str]:
    jsonld_identifier = extras.get("jsonld_identifier")
    if jsonld_identifier:
        return f"ext:{jsonld_identifier}", "jsonld_identifier"
    if dom.requisition_ids:
        return f"req:{dom.requisition_ids[0]}", "requisition_id"
    stable_hash = uuid.uuid5(_IDENTITY_NAMESPACE, canon_final)
    return f"url:{stable_hash}", "canonical_url"


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class CareerPageExtractor:
    source_name = SOURCE_NAME

    def __init__(
        self,
        settings: Settings,
        *,
        registry: Mapping[str, str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep=None,
        jitter_rng=None,
        resolver: Resolver | None = None,
    ) -> None:
        self._settings = settings
        self._registry = registry
        self._fetcher = GuardedFetcher(
            settings,
            transport=transport,
            sleep=sleep,
            jitter_rng=jitter_rng,
            resolver=resolver,
        )
        self._robots = RobotsGate(self._fetcher, settings)

    async def aclose(self) -> None:
        await self._fetcher.aclose()

    async def __aenter__(self) -> CareerPageExtractor:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def extract(self, url: str) -> ExtractionResult:
        warnings: list[SourceWarning] = []
        errors: list[SourceError] = []

        try:
            validate_url(url, allow_http=self._settings.career_allow_http)
        except (InvalidCareerUrlError, UnsupportedSchemeError, SourceSSRFBlockedError) as exc:
            errors.append(exc)
            return self._failed(exc, warnings)

        try:
            warnings.extend(await self._robots.ensure_allowed(url))
        except (RobotsDisallowedError, RobotsUnavailableError) as exc:
            errors.append(exc)
            return self._failed(exc, warnings)

        try:
            page = await self._fetcher.request_bytes(
                url, allowed_content_types=PAGE_CONTENT_TYPES
            )
        except CareerPageError as exc:
            errors.append(exc)
            return self._failed(exc, warnings)
        except SourceTimeoutError as exc:
            errors.append(exc)
            return self._network_failed("timeout", exc, warnings)
        except SourceNetworkError as exc:
            errors.append(exc)
            return self._network_failed("network_failure", exc, warnings)
        except SourceHTTPError as exc:
            errors.append(exc)
            return ExtractionResult(
                status="FETCH_FAILED",
                reason=f"http_{exc.status_code}" if exc.status_code else "http_error",
                detail=str(exc),
                warnings=tuple(warnings),
                errors=tuple(errors),
            )

        final_url = page.final_url
        if not page.body.strip():
            return ExtractionResult(
                status="NO_JOB_DETECTED",
                reason="non_html",
                detail="response body was empty",
                warnings=tuple(warnings),
                final_url=final_url,
            )
        html = page.body.decode("utf-8", errors="replace")

        canon_final, canon_honored = _canonical_pair(final_url, html)

        bag = SignalBag()
        extras: dict[str, Any] = {
            "requested_url": page.requested_url,
            "http_etag": page.etag,
            "http_last_modified": page.last_modified,
            "canonical_link_honored": canon_honored,
        }

        postings, stats = extract_jobpostings(html)
        extras["jsonld_stats"] = {
            "blocks_found": stats.blocks_found,
            "blocks_parsed": stats.blocks_parsed,
            "blocks_skipped": stats.blocks_skipped,
            "jobposting_nodes": stats.jobposting_nodes,
            "other_nodes": stats.other_nodes,
        }
        if stats.blocks_skipped:
            warnings.append(
                SourceWarning(
                    source=SOURCE_NAME,
                    code="malformed_jsonld_block_skipped",
                    message=f"{stats.blocks_skipped} malformed JSON-LD block(s) skipped",
                )
            )
        if len(postings) > 1:
            others = [p.get("url") for p in postings[1:] if isinstance(p.get("url"), str)]
            extras["additional_posting_urls"] = others
            warnings.append(
                SourceWarning(
                    source=SOURCE_NAME,
                    code="ambiguous_postings",
                    message=(
                        f"page contains {len(postings)} JobPosting nodes; "
                        "the first was extracted"
                    ),
                )
            )

        posting = postings[0] if postings else None
        if posting is not None:
            _offer_jsonld(bag, extras, posting)

        soup = BeautifulSoup(html, "html.parser")
        dom = extract_dom_signals(html)
        extras["display_dates"] = _display_dates(soup)

        if posting is None:
            for candidate in embedded_job_candidates(soup):
                bag.offer("title", "embedded", candidate.get("title"))
                bag.offer("description", "embedded", candidate.get("description"))
                if bag.contains("title") and bag.contains("description"):
                    break

        if "title" not in bag:
            bag.offer("title", "dom", dom.h1_text)
            bag.offer("title", "meta", dom.og_title)
            bag.offer("title", "meta", dom.title_tag)
        if "description" not in bag and dom.main_text_len >= 80:
            bag.offer("description", "dom", _main_text(soup))
        if "description" not in bag:
            bag.offer("description", "meta", dom.meta_description)
        bag.offer("apply_url", "dom", _best_dom_apply(dom, final_url))

        salary, salary_note = build_salary(posting or {})
        if salary_note == "salary_currency_missing":
            warnings.append(
                SourceWarning(
                    source=SOURCE_NAME,
                    code="salary_currency_missing",
                    message="baseSalary present without any resolvable currency",
                )
            )
            salary = None

        verdict_reason, confidence = _verify(bag, dom)
        browser_used = False
        if verdict_reason == "insufficient_evidence" and self._should_try_browser(dom):
            browser_warnings = await self._try_browser(final_url, bag, extras)
            warnings.extend(browser_warnings)
            browser_used = not browser_warnings or any(
                w.code != "browser_unavailable" for w in browser_warnings
            ) and not any(
                w.code in {"browser_unavailable", "browser_render_failed"}
                for w in browser_warnings
            )
            verdict_reason, confidence = _verify(bag, dom)

        if verdict_reason is not None:
            logger.info(
                "career page rejected as job",
                extra={
                    "source": SOURCE_NAME,
                    "operation": "extract",
                    "url": final_url,
                    "reason": verdict_reason,
                },
            )
            return ExtractionResult(
                status="NO_JOB_DETECTED",
                reason=verdict_reason,
                detail=(
                    f"page did not satisfy the acceptance contract ({verdict_reason})"
                ),
                warnings=tuple(warnings),
                final_url=final_url,
            )

        identity, identity_source = _resolve_identity(extras, dom, canon_final)
        job = self._assemble(
            bag, extras, canon_final, confidence or "medium", salary, identity,
            identity_source, browser_used,
        )
        logger.info(
            "career job extracted",
            extra={
                "source": SOURCE_NAME,
                "operation": "extract",
                "url": final_url,
                "confidence": confidence,
                "layers": sorted(set(bag.provenance().values())),
            },
        )
        return ExtractionResult(
            status="JOB_EXTRACTED",
            job=job,
            warnings=tuple(warnings),
            final_url=final_url,
        )

    @staticmethod
    def _failed(
        exc: SourceError, warnings: list[SourceWarning]
    ) -> ExtractionResult:
        return ExtractionResult(
            status="FETCH_FAILED",
            reason=exc.reason or type(exc).__name__,
            detail=str(exc),
            warnings=tuple(warnings),
            errors=(exc,),
        )

    @staticmethod
    def _network_failed(
        reason: str,
        exc: SourceError,
        warnings: list[SourceWarning],
    ) -> ExtractionResult:
        return ExtractionResult(
            status="FETCH_FAILED",
            reason=reason,
            detail=str(exc),
            warnings=tuple(warnings),
            errors=(exc,),
        )

    def _should_try_browser(self, dom: DomSignals) -> bool:
        return bool(self._settings.career_browser_enabled and dom.spa_indicators)

    async def _try_browser(
        self, url: str, bag: SignalBag, extras: dict[str, Any]
    ) -> list[SourceWarning]:
        from app.sources.career.browser import BrowserRenderer

        if not BrowserRenderer.available():
            return [
                SourceWarning(
                    source=SOURCE_NAME,
                    code="browser_unavailable",
                    message=(
                        "SPA indicators present but the optional playwright "
                        "extra is not installed"
                    ),
                )
            ]
        renderer = BrowserRenderer(self._settings)
        try:
            rendered = await renderer.render(url)
        except Exception as exc:  # noqa: BLE001 - browser failures are non-fatal
            logger.warning("browser render failed", exc_info=exc)
            return [
                SourceWarning(
                    source=SOURCE_NAME,
                    code="browser_render_failed",
                    message=f"browser rendering failed: {type(exc).__name__}",
                )
            ]

        rendered_postings, _stats = extract_jobpostings(rendered.html)
        for rendered_posting in rendered_postings[:1]:
            _offer_jsonld(bag, extras, rendered_posting)
        rendered_signals = extract_dom_signals(rendered.html)
        if "title" not in bag:
            bag.offer("title", "dom", rendered_signals.h1_text)
        if "description" not in bag and rendered_signals.main_text_len >= 80:
            rendered_soup = BeautifulSoup(rendered.html, "html.parser")
            bag.offer("description", "dom", _main_text(rendered_soup))
        if "apply_url" not in bag:
            bag.offer(
                "apply_url", "dom", _best_dom_apply(rendered_signals, rendered.final_url)
            )
        return []

    def _assemble(
        self,
        bag: SignalBag,
        extras: Mapping[str, Any],
        canon_final: str,
        confidence: str,
        salary: Salary | None,
        identity: str,
        identity_source: str,
        browser_used: bool,
    ) -> Job:
        company = bag.get("company")
        if company is None and self._registry is not None:
            domain = (urlsplit(canon_final).hostname or "").lower().removeprefix("www.")
            company = self._registry.get(domain)

        extra_out: dict[str, Any] = dict(extras)
        extra_out["provenance"] = bag.provenance()
        extra_out["conflicts"] = list(bag.conflicts)
        extra_out["extraction"] = {
            "confidence": confidence,
            "identity_source": identity_source,
            "browser_used": browser_used,
        }

        return Job(
            source=SOURCE_NAME,
            source_job_id=identity,
            title=str(bag.get("title")).strip(),
            company=_blank_to_none(company),
            location=_blank_to_none(bag.get("location")),
            description=_blank_to_none(bag.get("description")),
            requirements=_blank_to_none(bag.get("requirements")),
            responsibilities=_blank_to_none(bag.get("responsibilities")),
            employment_type=_blank_to_none(bag.get("employment_type")),
            salary=salary,
            job_url=canon_final,
            apply_url=_blank_to_none(bag.get("apply_url")),
            source_created_at=bag.get("source_created_at"),
            source_updated_at=bag.get("source_updated_at"),
            extra=extra_out,
        )


__all__ = ["CareerPageExtractor", "parse_schema_datetime"]
