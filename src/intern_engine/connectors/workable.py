"""Workable jobs API: public, no auth. POST v3 endpoint with pagination."""

from __future__ import annotations

from ..models import Job
from ..net import Net

URL = "https://apply.workable.com/api/v3/accounts/{slug}/jobs"
_MAX_PAGES = 3


def _location(job: dict) -> str:
    loc = job.get("location") or {}
    if not isinstance(loc, dict):
        loc = {}
    text = ", ".join(
        p for p in (loc.get("city"), loc.get("region"), loc.get("country")) if p
    )
    if job.get("remote") or job.get("workplace") == "remote":
        text = f"{text} (Remote)" if text else "Remote"
    return text or "—"


async def fetch(company: dict, net: Net) -> list[Job]:
    slug = company["slug"]

    jobs: list[Job] = []
    token = None
    for _ in range(_MAX_PAGES):
        body: dict = {
            "query": "intern",
            "location": [],
            "department": [],
            "worktype": [],
            "remote": [],
        }
        if token:
            body["token"] = token
        data = await net.post_json(URL.format(slug=slug), json=body)
        for j in data.get("results", []):
            shortcode = j.get("shortcode")
            jobs.append(
                Job(
                    id=f"workable:{slug}:{shortcode}",
                    source="workable",
                    company=company["name"],
                    company_slug=slug,
                    title=(j.get("title") or "").strip(),
                    location=_location(j),
                    url=f"https://apply.workable.com/{slug}/j/{shortcode}/",
                    posted_at=j.get("published"),
                )
            )
        token = data.get("nextPage")
        if not token:
            break
    return jobs
