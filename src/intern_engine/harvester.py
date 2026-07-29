"""Turn a list of candidate company slugs into a validated registry.

Reads data/candidates.json, probes each slug against ATS APIs, and merges
confirmed hits into data/companies.json.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import httpx

from . import paths

PROBES = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
    "smartrecruiters": "https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=1",
    "workable": "https://apply.workable.com/api/v3/accounts/{slug}/jobs",
}

HEADERS = {"User-Agent": "intern-engine-india/1.0"}


def _count(ats: str, payload) -> int:
    if ats == "lever":
        return len(payload) if isinstance(payload, list) else 0
    if ats == "smartrecruiters":
        if isinstance(payload, dict):
            return payload.get("totalFound", len(payload.get("content", [])))
        return 0
    return len(payload.get("jobs", [])) if isinstance(payload, dict) else 0


def detect(candidate: dict, client: httpx.Client) -> dict | None:
    slug = candidate["slug"]
    for ats, template in PROBES.items():
        try:
            resp = client.get(template.format(slug=slug), timeout=12)
            if resp.status_code == 200 and _count(ats, resp.json()) > 0:
                return {"name": candidate["name"], "slug": slug, "ats": ats}
        except Exception:
            continue
    return None


def harvest() -> tuple[list[dict], list[dict]]:
    if not paths.CANDIDATES_PATH or not __import__("os").path.exists(
        paths.CANDIDATES_PATH
    ):
        print("No data/candidates.json — skipping harvest.")
        return [], []

    with open(paths.CANDIDATES_PATH, encoding="utf-8") as f:
        candidates = json.load(f)

    client = httpx.Client(headers=HEADERS, follow_redirects=True)

    found: list[dict] = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        for result in pool.map(lambda c: detect(c, client), candidates):
            if result:
                found.append(result)

    client.close()

    # Merge into existing registry
    merged: dict[tuple[str, str], dict] = {}
    try:
        with open(paths.COMPANIES_PATH, encoding="utf-8") as f:
            for c in json.load(f):
                merged[(c["ats"], c["slug"])] = c
    except (OSError, json.JSONDecodeError, KeyError):
        pass
    for c in found:
        merged.setdefault((c["ats"], c["slug"]), c)

    companies = sorted(merged.values(), key=lambda c: c["name"].lower())
    with open(paths.COMPANIES_PATH, "w", encoding="utf-8") as f:
        json.dump(companies, f, indent=2, ensure_ascii=False)

    return found, candidates
