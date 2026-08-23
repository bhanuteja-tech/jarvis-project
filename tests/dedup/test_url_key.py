"""URL comparison keys: tracking stripped, identity parameters preserved."""

from __future__ import annotations

from app.dedup.url_key import apply_url_key, job_url_key


def make_job(**overrides):
    base = {
        "source": "greenhouse",
        "source_job_id": "1",
        "title": "Engineer",
        "company": "Acme Inc",
        "location": "New York, NY",
        "job_url": "https://boards.greenhouse.io/acme/jobs/1",
        "apply_url": None,
        "extra": {},
    }
    base.update(overrides)
    return base


class TestJobUrlKey:
    def test_tracking_removed_but_gh_jid_preserved(self) -> None:
        tracked = make_job(
            job_url="https://boards.example.com/jobs?gh_jid=456&utm_source=x&fbclid=zz"
        )
        clean = make_job(job_url="https://boards.example.com/jobs?gh_jid=456")

        assert job_url_key(tracked) == job_url_key(clean)

    def test_scheme_and_www_insensitive(self) -> None:
        a = make_job(job_url="https://www.example.com/jobs/1")
        b = make_job(job_url="http://example.com/jobs/1")

        assert job_url_key(a) == job_url_key(b)

    def test_fragment_and_trailing_slash_normalized(self) -> None:
        a = make_job(job_url="https://example.com/jobs/1#details")
        b = make_job(job_url="https://example.com/jobs/1/")

        assert job_url_key(a) == job_url_key(b)

    def test_sharing_link_excluded_for_google_jobs_engine(self) -> None:
        sharing = make_job(
            source="searchapi",
            extra={"engine": "google_jobs"},
            job_url=(
                "https://www.google.com/search?ibp=htl;jobs&htidocid=2_EkUK_X1ZOKUz-CAAAAAA%3D%3D"
            ),
        )

        assert job_url_key(sharing) is None

    def test_non_google_url_still_keyed_under_google_engine_flag(self) -> None:
        employer = make_job(
            source="searchapi",
            extra={"engine": "google_jobs"},
            job_url="https://careers.example.com/job/7",
        )

        assert job_url_key(employer) is not None

    def test_missing_job_url_returns_none(self) -> None:
        assert job_url_key(make_job(job_url=None)) is None


class TestApplyUrlKey:
    def test_apply_key_is_normalized_corroboration_helper_only(self) -> None:
        job = make_job(apply_url="https://ats.example.com/apply/9?utm_campaign=g&req=42")
        key = apply_url_key(job)

        assert key == "https://ats.example.com/apply/9?req=42"
