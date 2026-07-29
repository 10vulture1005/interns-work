"""iCIMS career site connector.

iCIMS tenants expose job search at:
    https://careers-{tenant}.icims.com/jobs/search?...&mode=job

This connector:
- Takes ``company["tenant"]`` from companies.json
- Searches the tenant's job board
- Normalizes results to the shared Job model
"""

from __future__ import annotations

import re

from ..models import Job
from ..net import Net

_SEARCH_URL = (
    "https://careers-{tenant}.icims.com/jobs/search"
    "?ss=1&searchRelation=keyword_all&in_iframe=1&mode=job"
    "&iis=Job+Listing&mobile=false&width=1200&height=500"
    "&bga=true&needs498LegacyHeader=false&trim498LegacyHeader=false"
)

_JOB_URL_TEMPLATE = "https://careers-{tenant}.icims.com/jobs/{job_id}/job"

_MAX_PAGES = 3


def _extract_jobs_from_html(html: str, tenant: str) -> list[dict]:
    """Parse job listings from iCIMS HTML response.

    iCIMS returns HTML with job cards that contain structured data.
    We extract job ID, title, and location from the listing page.
    """
    jobs: list[dict] = []

    # iCIMS embeds job data in structured elements
    # Pattern: class="iCIMS_JobsTable" contains rows with job data
    # Each job has a link like /jobs/{id}/job and title text
    job_pattern = re.compile(
        r'<a[^>]*href="[^"]*?/jobs/(\d+)/[^"]*"[^>]*class="[^"]*iCIMS_Anchor[^"]*"[^>]*>'
        r"\s*(.*?)\s*</a>",
        re.DOTALL | re.I,
    )

    location_pattern = re.compile(
        r'<span[^>]*class="[^"]*iCIMS_JobHeaderData[^"]*"[^>]*>\s*(.*?)\s*</span>',
        re.DOTALL | re.I,
    )

    # Simpler approach: find all job links and titles
    for match in re.finditer(
        r'/jobs/(\d+)/job[^"]*"[^>]*>\s*<span[^>]*>([^<]+)</span>',
        html,
        re.I,
    ):
        job_id = match.group(1)
        title = match.group(2).strip()
        if title:
            jobs.append(
                {
                    "id": job_id,
                    "title": title,
                    "location": "—",
                }
            )

    # Fallback: broader pattern matching
    if not jobs:
        for match in job_pattern.finditer(html):
            job_id = match.group(1)
            title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
            if title and job_id:
                jobs.append(
                    {
                        "id": job_id,
                        "title": title,
                        "location": "—",
                    }
                )

    return jobs


async def fetch(company: dict, net: Net) -> list[Job]:
    """Fetch jobs from an iCIMS career site.

    Requires ``company["tenant"]`` to be set in companies.json.
    """
    tenant = company.get("tenant")
    if not tenant:
        raise ValueError(f"iCIMS connector requires 'tenant' — got {company}")

    url = _SEARCH_URL.format(tenant=tenant)

    try:
        data = await net.get_json(url)
    except Exception:
        # iCIMS returns HTML, not JSON — we need to handle this differently
        # Fall back to raw HTML parsing
        data = None

    jobs: list[Job] = []

    if isinstance(data, dict):
        # Some iCIMS tenants may return JSON (newer API)
        for posting in data.get("jobs", data.get("jobPostings", [])):
            job_id = str(posting.get("id", ""))
            title = posting.get("title", "")
            location = posting.get("location", "—")
            if isinstance(location, dict):
                location = location.get("name", "—")
            if job_id and title:
                jobs.append(
                    Job(
                        id=f"icims:{tenant}:{job_id}",
                        source="icims",
                        company=company["name"],
                        company_slug=company.get("slug", tenant),
                        title=title.strip(),
                        location=str(location).strip() or "—",
                        url=_JOB_URL_TEMPLATE.format(tenant=tenant, job_id=job_id),
                    )
                )

    # If no JSON results, try HTML scraping approach via raw GET
    if not jobs:
        try:
            # Use the underlying client to get raw HTML
            raw_url = _SEARCH_URL.format(tenant=tenant)
            resp = await net._client.get(raw_url, timeout=15)
            if resp.status_code == 200:
                html = resp.text
                parsed = _extract_jobs_from_html(html, tenant)
                for item in parsed:
                    jobs.append(
                        Job(
                            id=f"icims:{tenant}:{item['id']}",
                            source="icims",
                            company=company["name"],
                            company_slug=company.get("slug", tenant),
                            title=item["title"],
                            location=item.get("location", "—"),
                            url=_JOB_URL_TEMPLATE.format(
                                tenant=tenant,
                                job_id=item["id"],
                            ),
                        )
                    )
        except Exception:
            pass

    return jobs
