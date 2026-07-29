"""Instahyre aggregator connector (India startup jobs)."""

from __future__ import annotations

from ..models import Job
from ..net import Net

URL = "https://www.instahyre.com/api/v1/job_search?search=internship&offset={offset}"
_MAX_PAGES = 5


async def fetch(company: dict, net: Net) -> list[Job]:
    """Fetch internships from Instahyre's global search.

    This is an aggregator, so the `company` parameter is just a dummy trigger.
    The real company name comes from the payload.
    """
    jobs: list[Job] = []

    for page in range(_MAX_PAGES):
        url = URL.format(offset=page * 10)
        data = await net.get_json(url)
        objects = data.get("objects")
        if not objects:
            if page == 0:
                raise RuntimeError("Instahyre returned 0 jobs on page 1")
            break

        for posting in objects:
            title = (posting.get("title") or "").strip()
            if "intern" not in title.lower():
                continue

            employer = posting.get("employer") or {}
            c_name = employer.get("company_name") or "Unknown"
            c_slug = c_name.lower().replace(" ", "")

            jobs.append(
                Job(
                    id=f"instahyre:{c_slug}:{posting.get('id')}",
                    source="instahyre",
                    company=c_name,
                    company_slug=c_slug,
                    title=title,
                    location=(posting.get("locations") or "").strip() or "—",
                    url=posting.get("public_url") or "",
                )
            )

        meta = data.get("meta") or {}
        if not meta.get("next"):
            break

    return jobs
