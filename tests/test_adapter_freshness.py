"""Adapter freshness must distinguish posting dates from source update times."""
from unittest.mock import MagicMock, patch

from adapters.greenhouse_adapter import scrape


def test_greenhouse_updated_at_is_not_reported_as_posted_date():
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "jobs": [
            {
                "id": 123,
                "title": "Entry Level AI Engineer",
                "updated_at": "2026-07-14T12:00:00Z",
                "absolute_url": "https://job-boards.greenhouse.io/example/jobs/123",
                "location": {"name": "New York, NY"},
            }
        ]
    }

    with patch("adapters.greenhouse_adapter.SESSION.get", return_value=response):
        result = scrape("Example", "example")

    job = result["jobs"][0]
    assert job["posted_date"] == ""
    assert job["freshness"] == "Unknown"
    assert job["source_updated_at"] == "2026-07-14T12:00:00Z"
    assert job["freshness_source"] == "ats_updated_at"


def test_ashby_public_feed_includes_description_and_published_date():
    from adapters.ashby_adapter import scrape as scrape_ashby

    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "jobs": [
            {
                "title": "Applied AI Engineer",
                "location": "New York, NY",
                "department": "Engineering",
                "employmentType": "FullTime",
                "descriptionPlain": "Build production RAG and agent systems with Python.",
                "publishedAt": "2026-07-14T12:00:00Z",
                "jobUrl": "https://jobs.ashbyhq.com/example/abc-123",
                "applyUrl": "https://jobs.ashbyhq.com/example/abc-123/apply",
                "isListed": True,
            }
        ]
    }

    with patch("adapters.ashby_adapter.SESSION.get", return_value=response):
        result = scrape_ashby("Example", "example")

    job = result["jobs"][0]
    assert job["posted_date"] == "2026-07-14"
    assert job["freshness_source"] == "ashby_published_at"
    assert "production RAG" in job["description"]
    assert job["apply_url"].endswith("/apply")
    assert job["job_id"] == "abc-123"
