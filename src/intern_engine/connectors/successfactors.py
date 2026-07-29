"""SAP SuccessFactors career site connector.

SuccessFactors career portals expose a job search API at various endpoints
depending on the tenant configuration:
    https://{instance}.sapsf.com/xi/ui/pages/entry/openentry.xhtml?company={tenant}

Or via the newer Career Site Builder (CSB):
    https://jobs.sap.com/search/?q=intern  (SAP-hosted)
    https://career{N}.successfactors.com/career?company={tenant}

This connector handles the most common pattern — the SuccessFactors BizX
career portal with OData or XML feeds.
"""

from __future__ import annotations

import re

from ..models import Job
from ..net import Net

_CAREER_URL = "https://{instance}.sapsf.com/career?company={tenant}&career_ns=job_listing&navBarLevel=JOB_SEARCH"
_ODATA_URL = (
    "https://{instance}.sapsf.com/odata/v2/JobReqLocale"
    "?$filter=status eq 'pub'&$format=json&$top=100"
)

_APPLY_URL_TEMPLATE = (
    "https://{instance}.sapsf.com/career?career_job_req_id={req_id}&company={tenant}"
)


def _extract_from_html(html: str, tenant: str, instance: str) -> list[dict]:
    """Parse job listings from SuccessFactors HTML career page."""
    jobs: list[dict] = []

    # SuccessFactors embeds job data in structured JS or HTML elements
    # Look for job requisition IDs and titles in the page
    pattern = re.compile(
        r'career_job_req_id=(\d+)[^"]*"[^>]*>\s*([^<]+)',
        re.I,
    )
    for match in pattern.finditer(html):
        req_id = match.group(1)
        title = match.group(2).strip()
        if title and req_id:
            jobs.append(
                {
                    "id": req_id,
                    "title": title,
                    "location": "—",
                }
            )

    return jobs


async def fetch(company: dict, net: Net) -> list[Job]:
    """Fetch jobs from a SuccessFactors career portal.

    Requires ``company["tenant"]`` and optionally ``company["instance"]``
    (defaults to ``"hcmportal"``).
    """
    tenant = company.get("tenant")
    if not tenant:
        raise ValueError(f"SuccessFactors connector requires 'tenant' — got {company}")

    instance = company.get("instance", "hcmportal")

    jobs: list[Job] = []

    # Try OData endpoint first (returns JSON)
    odata_url = _ODATA_URL.format(instance=instance, tenant=tenant)
    try:
        data = await net.get_json(odata_url)
        if isinstance(data, dict):
            results = data.get("d", {}).get("results", [])
            for item in results:
                req_id = str(item.get("jobReqId", ""))
                title = item.get("jobTitle") or item.get("externalTitle") or ""
                location = item.get("location") or "—"
                if isinstance(location, dict):
                    location = location.get("name", "—")

                if req_id and title:
                    jobs.append(
                        Job(
                            id=f"successfactors:{tenant}:{req_id}",
                            source="successfactors",
                            company=company["name"],
                            company_slug=company.get("slug", tenant),
                            title=title.strip(),
                            location=str(location).strip() or "—",
                            url=_APPLY_URL_TEMPLATE.format(
                                instance=instance,
                                req_id=req_id,
                                tenant=tenant,
                            ),
                        )
                    )
    except Exception:
        pass

    # Fallback: scrape the career page HTML
    if not jobs:
        career_url = _CAREER_URL.format(instance=instance, tenant=tenant)
        try:
            resp = await net._client.get(career_url, timeout=15)
            if resp.status_code == 200:
                parsed = _extract_from_html(resp.text, tenant, instance)
                for item in parsed:
                    jobs.append(
                        Job(
                            id=f"successfactors:{tenant}:{item['id']}",
                            source="successfactors",
                            company=company["name"],
                            company_slug=company.get("slug", tenant),
                            title=item["title"],
                            location=item.get("location", "—"),
                            url=_APPLY_URL_TEMPLATE.format(
                                instance=instance,
                                req_id=item["id"],
                                tenant=tenant,
                            ),
                        )
                    )
        except Exception:
            pass

    return jobs
