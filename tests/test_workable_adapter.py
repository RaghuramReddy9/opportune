"""Workable public careers-feed adapter tests."""
from unittest.mock import MagicMock, patch

from adapters.workable_adapter import scrape


def test_workable_normalizes_public_jobs_and_requests_details():
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "jobs": [
            {
                "id": "job-123",
                "shortcode": "ABC123",
                "title": "AI Engineer",
                "department": "Engineering",
                "employment_type": "Full time",
                "published_on": "2026-07-14T12:00:00Z",
                "url": "https://apply.workable.com/example/j/ABC123/",
                "location": {
                    "location_str": "Remote, United States",
                    "telecommuting": True,
                },
                "description": "<p>Build production RAG systems.</p>",
                "requirements": ["Python", "One year of experience"],
            },
            {
                "state": "closed",
                "title": "Closed role",
                "url": "https://apply.workable.com/example/j/CLOSED/",
            },
        ]
    }

    with patch("adapters.workable_adapter.SESSION.get", return_value=response) as get:
        result = scrape("Example AI", "example")

    get.assert_called_once_with(
        "https://www.workable.com/api/accounts/example",
        params={"details": "true"},
        timeout=get.call_args.kwargs["timeout"],
    )
    assert result["error"] is None
    assert result["raw_count"] == 1
    job = result["jobs"][0]
    assert job["source"] == "workable"
    assert job["job_id"] == "job-123"
    assert job["posted_date"] == "2026-07-14"
    assert job["freshness_source"] == "workable_published_on"
    assert job["location"] == "Remote, United States"
    assert "production RAG" in job["description"]
    assert "Python" in job["description"]


def test_workable_reports_http_failure_without_partial_snapshot():
    response = MagicMock(status_code=503)
    with patch("adapters.workable_adapter.SESSION.get", return_value=response):
        result = scrape("Example AI", "example")

    assert result == {"jobs": [], "raw_count": 0, "error": "Workable HTTP 503"}
