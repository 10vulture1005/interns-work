"""Verify ALL companies in companies.json against live ATS endpoints.

For supported ATS (greenhouse/lever/ashby/smartrecruiters/workable):
  - Hit the API endpoint and check for jobs > 0
For custom companies (Google, Microsoft, etc.):
  - Check if careers_url is reachable
For workday/icims/successfactors:
  - Probe their specific endpoints
"""

import asyncio
import json
import sys
import time
from collections import Counter

import httpx

HEADERS = {"User-Agent": "intern-engine-india/1.0"}

PROBE_URLS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
    "smartrecruiters": "https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=1",
}

# Workable needs POST
WORKABLE_URL = "https://apply.workable.com/api/v3/accounts/{slug}/jobs"
WORKABLE_BODY = {"query": "", "location": [], "department": [], "worktype": [], "remote": []}


def count_jobs(ats: str, payload) -> int:
    if ats == "lever":
        return len(payload) if isinstance(payload, list) else 0
    if ats == "smartrecruiters":
        return payload.get("totalFound", len(payload.get("content", []))) if isinstance(payload, dict) else 0
    if ats == "workable":
        return len(payload.get("results", [])) if isinstance(payload, dict) else 0
    return len(payload.get("jobs", [])) if isinstance(payload, dict) else 0


async def check_standard(client: httpx.AsyncClient, company: dict, sem: asyncio.Semaphore) -> dict:
    ats = company["ats"]
    slug = company["slug"]
    name = company["name"]
    template = PROBE_URLS[ats]
    url = template.format(slug=slug)

    async with sem:
        try:
            resp = await client.get(url, timeout=12)
            if resp.status_code == 200:
                payload = resp.json()
                jobs = count_jobs(ats, payload)
                return {"name": name, "ats": ats, "slug": slug, "status": "alive" if jobs > 0 else "empty", "jobs": jobs, "http": 200}
            return {"name": name, "ats": ats, "slug": slug, "status": "dead", "jobs": 0, "http": resp.status_code}
        except Exception as e:
            return {"name": name, "ats": ats, "slug": slug, "status": "error", "jobs": 0, "http": 0, "error": str(e)[:80]}


async def check_workable(client: httpx.AsyncClient, company: dict, sem: asyncio.Semaphore) -> dict:
    slug = company["slug"]
    name = company["name"]
    url = WORKABLE_URL.format(slug=slug)

    async with sem:
        try:
            resp = await client.post(url, json=WORKABLE_BODY, timeout=12)
            if resp.status_code == 200:
                payload = resp.json()
                jobs = count_jobs("workable", payload)
                return {"name": name, "ats": "workable", "slug": slug, "status": "alive" if jobs > 0 else "empty", "jobs": jobs, "http": 200}
            return {"name": name, "ats": "workable", "slug": slug, "status": "dead", "jobs": 0, "http": resp.status_code}
        except Exception as e:
            return {"name": name, "ats": "workable", "slug": slug, "status": "error", "jobs": 0, "http": 0, "error": str(e)[:80]}


async def check_workday(client: httpx.AsyncClient, company: dict, sem: asyncio.Semaphore) -> dict:
    tenant = company.get("tenant", "")
    site = company.get("site", "")
    name = company["name"]

    if not tenant or not site:
        return {"name": name, "ats": "workday", "slug": company.get("slug", ""), "status": "missing_config", "jobs": 0, "http": 0}

    for dc in ["wd1", "wd5", "wd3"]:
        url = f"https://{tenant}.{dc}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
        async with sem:
            try:
                resp = await client.post(url, json={"appliedFacets": {}, "limit": 5, "offset": 0, "searchText": ""}, timeout=12)
                if resp.status_code == 200:
                    data = resp.json()
                    total = data.get("total", 0)
                    if total > 0:
                        return {"name": name, "ats": "workday", "slug": company.get("slug", ""), "status": "alive", "jobs": total, "http": 200, "dc": dc}
            except Exception:
                continue

    return {"name": name, "ats": "workday", "slug": company.get("slug", ""), "status": "dead", "jobs": 0, "http": 0}


async def check_custom(client: httpx.AsyncClient, company: dict, sem: asyncio.Semaphore) -> dict:
    name = company["name"]
    url = company.get("careers_url", "")

    if not url:
        return {"name": name, "ats": "custom", "slug": company.get("slug", ""), "status": "no_url", "jobs": 0, "http": 0}

    async with sem:
        try:
            resp = await client.get(url, timeout=15)
            return {"name": name, "ats": "custom", "slug": company.get("slug", ""), "status": "reachable" if resp.status_code == 200 else "unreachable", "jobs": -1, "http": resp.status_code}
        except Exception as e:
            return {"name": name, "ats": "custom", "slug": company.get("slug", ""), "status": "error", "jobs": 0, "http": 0, "error": str(e)[:80]}


async def main():
    with open("data/companies.json") as f:
        companies = json.load(f)

    print(f"Verifying {len(companies)} companies...\n")

    sem = asyncio.Semaphore(24)  # Max concurrent requests
    results = []

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        tasks = []
        for c in companies:
            ats = c["ats"]
            if ats in PROBE_URLS:
                tasks.append(check_standard(client, c, sem))
            elif ats == "workable":
                tasks.append(check_workable(client, c, sem))
            elif ats == "workday":
                tasks.append(check_workday(client, c, sem))
            elif ats == "custom":
                tasks.append(check_custom(client, c, sem))
            elif ats == "icims":
                # Skip icims for now (HTML parsing needed, not API)
                results.append({"name": c["name"], "ats": "icims", "slug": c.get("slug", ""), "status": "skipped", "jobs": 0, "http": 0})
            elif ats == "successfactors":
                results.append({"name": c["name"], "ats": "successfactors", "slug": c.get("slug", ""), "status": "skipped", "jobs": 0, "http": 0})
            else:
                results.append({"name": c["name"], "ats": ats, "slug": c.get("slug", ""), "status": "unknown_ats", "jobs": 0, "http": 0})

        batch_results = await asyncio.gather(*tasks)
        results.extend(batch_results)

    # Report
    status_counts = Counter(r["status"] for r in results)
    ats_alive = Counter()
    ats_dead = Counter()

    for r in results:
        if r["status"] == "alive":
            ats_alive[r["ats"]] += 1
        elif r["status"] in ("dead", "empty", "error"):
            ats_dead[r["ats"]] += 1

    print("=" * 80)
    print(f"VERIFICATION COMPLETE — {len(results)} companies")
    print("=" * 80)
    print()

    print("Status breakdown:")
    for status, count in status_counts.most_common():
        print(f"  {status:20s} {count:5d}")
    print()

    print("Per-ATS alive/dead:")
    all_ats = sorted(set(list(ats_alive.keys()) + list(ats_dead.keys())))
    for ats in all_ats:
        a = ats_alive.get(ats, 0)
        d = ats_dead.get(ats, 0)
        total = a + d
        pct = (a / total * 100) if total else 0
        print(f"  {ats:20s}  alive={a:4d}  dead={d:4d}  ({pct:.0f}% alive)")
    print()

    # List all dead/empty/error entries
    bad = [r for r in results if r["status"] in ("dead", "empty", "error")]
    bad.sort(key=lambda r: r["name"].lower())

    print(f"Dead/empty/error slugs ({len(bad)}):")
    for r in bad:
        err = r.get("error", "")
        detail = f"HTTP {r['http']}" if r["http"] else err[:50]
        print(f"  ❌ {r['name']:35s} {r['ats']:18s} slug={r['slug']:30s} [{r['status']}] {detail}")

    # Dump full results to JSON for analysis
    with open("logs/verify_results.json", "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nFull results saved to logs/verify_results.json")

    return bad


if __name__ == "__main__":
    import os
    os.makedirs("logs", exist_ok=True)
    t0 = time.time()
    bad = asyncio.run(main())
    elapsed = time.time() - t0
    print(f"\nCompleted in {elapsed:.1f}s")
