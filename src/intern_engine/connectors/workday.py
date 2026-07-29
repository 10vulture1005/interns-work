"""Workday CXS career site API connector.

Workday's public career pages expose a JSON POST endpoint at:
    https://{tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs

This connector handles:
- Multiple Workday data center variants (wd5, wd1, wd3)
- Pagination via offset
- Normalization to the shared Job model
"""

from __future__ import annotations

from ..models import Job
from ..net import Net

# Data centers to try, in order of frequency.
_DCS = ("wd5", "wd1", "wd3", "wd2", "wd4")

_URL_TEMPLATE = "https://{tenant}.{dc}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
_APPLY_TEMPLATE = "https://{tenant}.{dc}.myworkdayjobs.com/en-US/{site}{path}"

_PAGE_SIZE = 20
_MAX_PAGES = 3


def _build_body(offset: int = 0) -> dict:
    return {
        "appliedFacets": {},
        "limit": _PAGE_SIZE,
        "offset": offset,
        "searchText": "",
    }


def _location(posting: dict) -> str:
    """Extract a human-readable location string."""
    locs = posting.get("locationsText") or posting.get("bulletFields", [""])[0]
    if isinstance(locs, list):
        return ", ".join(locs) or "—"
    return str(locs).strip() or "—"


def _posted_at(posting: dict) -> str | None:
    """Extract posted date if available."""
    date_str = posting.get("postedOn")
    if date_str:
        return str(date_str).strip()
    return None


async def fetch(company: dict, net: Net) -> list[Job]:
    """Fetch jobs from a Workday career site.

    Requires ``company["tenant"]`` and ``company["site"]`` to be set.
    Optionally ``company["dc"]`` to skip data center discovery.
    """
    tenant = company.get("tenant")
    site = company.get("site")
    if not tenant or not site:
        raise ValueError(
            f"Workday connector requires 'tenant' and 'site' — got {company}"
        )

    # Determine data center
    dc = company.get("dc")
    dcs_to_try = [dc] if dc else list(_DCS)

    working_dc = None
    first_page = None

    for try_dc in dcs_to_try:
        url = _URL_TEMPLATE.format(tenant=tenant, dc=try_dc, site=site)
        try:
            data = await net.post_json(url, json=_build_body(0))
            if isinstance(data, dict) and "jobPostings" in data:
                working_dc = try_dc
                first_page = data
                break
        except Exception:
            continue

    if working_dc is None or first_page is None:
        return []  # No working DC found; company may have moved or config is wrong.

    # Parse first page + paginate
    jobs: list[Job] = []
    total = first_page.get("total", 0)

    def _parse_page(data: dict) -> None:
        for posting in data.get("jobPostings", []):
            ext_path = posting.get("externalPath") or ""
            title = posting.get("title") or ""
            jobs.append(
                Job(
                    id=f"workday:{tenant}:{ext_path.lstrip('/')}",
                    source="workday",
                    company=company["name"],
                    company_slug=company.get("slug", tenant),
                    title=title.strip(),
                    location=_location(posting),
                    url=_APPLY_TEMPLATE.format(
                        tenant=tenant,
                        dc=working_dc,
                        site=site,
                        path=ext_path,
                    ),
                    posted_at=_posted_at(posting),
                )
            )

    _parse_page(first_page)

    # Fetch remaining pages
    for page in range(1, _MAX_PAGES):
        offset = page * _PAGE_SIZE
        if offset >= total:
            break
        url = _URL_TEMPLATE.format(tenant=tenant, dc=working_dc, site=site)
        try:
            data = await net.post_json(url, json=_build_body(offset))
            _parse_page(data)
        except Exception:
            break

    return jobs
