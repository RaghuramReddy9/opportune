"""
adapters/apify_adapter.py — Apify job scraping adapter.

Uses Apify's Web Scraper actor for sources that need a browser-based fallback.
Install with `opportune[apify]` and set APIFY_TOKEN before enabling it.

Usage:
    from adapters.apify_adapter import scrape_indeed, scrape_linkedin, scrape_generic
"""
import logging
import os
import time


logger = logging.getLogger("adapters.apify")

# Lazy import — only load apify_client when needed
_client = None


def _get_client():
    """Lazy-init the Apify client."""
    global _client
    if _client is None:
        from apify_client import ApifyClient
        token = os.environ.get("APIFY_TOKEN", "")
        if not token:
            raise ValueError("APIFY_TOKEN not configured")
        _client = ApifyClient(token)
    return _client


def _run_actor(actor_id: str, run_input: dict, wait_secs: int = 120) -> list:
    """Run an Apify actor and return dataset items."""
    client = _get_client()

    # Start the run with minimal memory
    run = client.actor(actor_id).call(
        run_input=run_input,
        memory_mbytes=512,
    )

    run_id = run.id if hasattr(run, "id") else run.get("id", "")
    logger.info("Apify run started: %s", run_id)

    # Poll for completion
    for i in range(wait_secs // 5):
        time.sleep(5)
        run_info = client.run(run_id).get()
        status = run_info.get("status", "?") if isinstance(run_info, dict) else getattr(run_info, "status", "?")

        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            logger.info("Apify run %s: %s", run_id, status)

            if status == "SUCCEEDED":
                ds_id = (
                    run_info.get("defaultDatasetId", "")
                    if isinstance(run_info, dict)
                    else getattr(run_info, "defaultDatasetId", "")
                )
                if ds_id:
                    items = list(client.dataset(ds_id).iterate_items())
                    logger.info("Apify: %d results", len(items))
                    return items
            return []

    logger.warning("Apify run %s timed out", run_id)
    return []


def scrape_indeed(query: str = "AI ML intern", location: str = "United States", max_results: int = 10) -> dict:
    """Scrape Indeed jobs via Apify. Returns empty if Indeed blocks (403)."""
    result = {"jobs": [], "raw_count": 0, "error": None}

    page_function = """
    async function pageFunction(context) {
        const { $, request, log, pushData } = context;
        const jobs = [];

        // Try multiple Indeed selectors
        const selectors = [
            '[data-testid="job-title"]',
            '.jobTitle',
            'a.jcs-JobTitle',
            '.jobTitle-color-purple',
            'h2.jobTitle a',
        ];

        for (const sel of selectors) {
            $(sel).each((i, el) => {
                const title = $(el).text().trim();
                let url = $(el).attr('href') || '';
                if (url && !url.startsWith('http')) url = 'https://www.indeed.com' + url;

                const card = $(el).closest(
                    '[data-testid="job"], .job_seen_beacon, .slider_container, .jobsearch-SerpJobCard, [class*="jobCard"]'
                );
                const location = card.find(
                    '[data-testid="textLocation"], .companyLocation, [data-testid="job-location"], [class*="location"]'
                ).text().trim() || '';
                const company = card.find(
                    '[data-testid="company-name"], .companyName, [data-testid="job-company"], [class*="company"]'
                ).text().trim() || '';

                if (title && title.length > 3) {
                    jobs.push({ title, url, company, location, source: 'indeed' });
                }
            });
            if (jobs.length) break;
        }

        log.info(`Found ${jobs.length} jobs on ${request.url}`);
        for (const job of jobs) {
            await pushData(job);
        }
        return jobs;
    }
    """

    items = _run_actor("apify/web-scraper", {
        "startUrls": [{"url": f"https://www.indeed.com/jobs?q={query.replace(' ', '+')}&l={location.replace(' ', '+')}"}],
        "maxPagesPerCrawl": 2,
        "maxRequestsPerCrawl": max_results,
        "pageFunction": page_function,
        "proxyConfiguration": {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"]},
    })

    for item in items:
        title = item.get("title", "")
        if not title:
            continue
        result["jobs"].append({
            "source": "apify_indeed",
            "company": item.get("company", "Unknown"),
            "title": title,
            "location": item.get("location", ""),
            "department": "",
            "employment_type": "",
            "posted_date": "",
            "freshness": "Unknown",
            "description": "",
            "apply_url": item.get("url", ""),
            "job_id": "",
            "raw_url": item.get("url", ""),
            "ats_type": "apify",
            "ats_slug": "indeed",
            "full_text": f"{title} {item.get('company', '')}",
        })

    result["raw_count"] = len(result["jobs"])
    if not result["jobs"]:
        result["error"] = "Indeed returned 0 jobs (likely blocked)"
    return result


def scrape_generic(url: str, company_name: str, selectors: dict, max_results: int = 10) -> dict:
    """Scrape any job page via Apify with custom selectors.

    Args:
        url: The career page URL
        company_name: Company name for the jobs
        selectors: Dict with keys: job_card, title, location, company, url
        max_results: Max jobs to return
    """
    result = {"jobs": [], "raw_count": 0, "error": None}

    # Build page function from selectors
    card_sel = selectors.get("job_card", "body")
    title_sel = selectors.get("title", "h2")
    loc_sel = selectors.get("location", "")
    url_sel = selectors.get("url", "a")

    page_function = """
    async function pageFunction(context) {
        const { $, request, log, pushData } = context;
        const jobs = [];

        $('CARD_SEL').each((i, el) => {
            const title = $(el).find('TITLE_SEL').text().trim();
            let url = $(el).find('URL_SEL').attr('href') || '';
            if (url && !url.startsWith('http')) url = new URL(url, request.url).href;
            const location = $('LOC_SEL').text().trim() || '';

            if (title && title.length > 3) {
                jobs.push({ title, url, company: 'COMPANY_NAME', location, source: 'apify_generic' });
            }
        });

        log.info(`Found ${jobs.length} jobs`);
        for (const job of jobs) {
            await pushData(job);
        }
        return jobs;
    }
    """.replace("CARD_SEL", card_sel).replace("TITLE_SEL", title_sel).replace("URL_SEL", url_sel).replace("LOC_SEL", loc_sel).replace("COMPANY_NAME", company_name)

    items = _run_actor("apify/web-scraper", {
        "startUrls": [{"url": url}],
        "maxPagesPerCrawl": 3,
        "maxRequestsPerCrawl": max_results,
        "pageFunction": page_function,
        "proxyConfiguration": {"useApifyProxy": True},
    })

    for item in items:
        title = item.get("title", "")
        if not title:
            continue
        result["jobs"].append({
            "source": "apify_generic",
            "company": item.get("company", company_name),
            "title": title,
            "location": item.get("location", ""),
            "department": "",
            "employment_type": "",
            "posted_date": "",
            "freshness": "Unknown",
            "description": "",
            "apply_url": item.get("url", ""),
            "job_id": "",
            "raw_url": item.get("url", ""),
            "ats_type": "apify",
            "ats_slug": "generic",
            "full_text": f"{title} {item.get('company', '')}",
        })

    result["raw_count"] = len(result["jobs"])
    return result
