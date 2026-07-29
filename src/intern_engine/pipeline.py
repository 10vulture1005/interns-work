"""The watcher + spotter.

One async pass per run: quarantine-check every tracked company (circuit breaker),
fetch the healthy ones concurrently, normalize into one shape, keep the roles
that match the configured scope, de-duplicate across sources, merge into the
store, and record run metrics.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

import httpx

from . import config, filters, health, models, paths, quality, store
from .connectors import (ashby, bloomberg, bytedance, google, greenhouse, 
                         icims, instahyre, lever, oracle, rippling, 
                         smartrecruiters, successfactors, uber, workable, 
                         workday, yc_waas)
from .net import HostLimiter, Net

CONNECTORS = {
    "greenhouse": greenhouse.fetch,
    "lever": lever.fetch,
    "ashby": ashby.fetch,
    "smartrecruiters": smartrecruiters.fetch,
    "workable": workable.fetch,
    "instahyre": instahyre.fetch,
    "yc_waas": yc_waas.fetch,
    "workday": workday.fetch,
    "icims": icims.fetch,
    "successfactors": successfactors.fetch,
    "google": google.fetch,
    "oracle": oracle.fetch,
    "rippling": rippling.fetch,
    "bloomberg": bloomberg.fetch,
    "bytedance": bytedance.fetch,
    "uber": uber.fetch,
}

GLOBAL_CONCURRENCY = 32
PER_HOST_CONCURRENCY = 8
USER_AGENT = "intern-engine-india/1.0"


def _load_companies() -> list[dict]:
    with open(paths.COMPANIES_PATH, encoding="utf-8") as f:
        return json.load(f)


async def _fetch_one(company: dict, net: Net):
    """Return (company, jobs, error); never raises."""
    fetch = CONNECTORS.get(company.get("ats"))
    if fetch is None:
        return company, [], f"no connector for {company.get('ats')}"
    try:
        return company, await fetch(company, net), None
    except Exception as exc:
        return company, [], f"{type(exc).__name__}: {exc}"


async def _fetch_all(companies: list[dict]):
    """Fetch every company concurrently."""
    limiter = HostLimiter(PER_HOST_CONCURRENCY)
    gate = asyncio.Semaphore(GLOBAL_CONCURRENCY)

    common = dict(
        limits=httpx.Limits(max_connections=64, max_keepalive_connections=32),
        timeout=httpx.Timeout(20.0, connect=10.0),
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    )

    async with httpx.AsyncClient(**common) as client:
        net = Net(client, limiter)

        async def worker(company: dict):
            async with gate:
                return await _fetch_one(company, net)

        results = await asyncio.gather(*(worker(c) for c in companies))
        return results


def _dedup(jobs: list) -> list:
    jobs = sorted(jobs, key=lambda j: (j.posted_at is None,))
    seen: set[tuple[str, str]] = set()
    unique = []
    for job in jobs:
        key = (
            job.company.lower().strip(),
            re.sub(r"[^a-z0-9]+", "", job.title.lower()),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(job)
    return unique


def _keep_matching(results, cfg, blocklist, existing=None):
    cycles = config.cycles(cfg)
    tech_only = cfg.get("role_scope", "tech") == "tech"
    restrict = config.restrict_region(cfg)
    wants_india = config.want_india(cfg)
    wants_remote = config.want_remote(cfg)
    infer = config.infer_undated(cfg)
    infer_age = config.infer_max_age_days(cfg)
    max_age = config.max_age_days(cfg)
    cutoff = (
        (datetime.now(UTC) - timedelta(days=max_age)).strftime("%Y-%m-%d")
        if max_age
        else None
    )

    existing = existing or {}
    kept = []
    succeeded: set[str] = set()
    errors = 0
    errors_by_ats: Counter = Counter()

    for company, jobs, error in results:
        if error is not None:
            errors += 1
            errors_by_ats[company.get("ats", "?")] += 1
            continue
        succeeded.add(f"{company['ats']}:{company['slug']}")
        if quality.is_blocked(company["name"], blocklist):
            continue
        for job in jobs:
            if not filters.is_internship(job.title):
                continue
            if tech_only and not filters.is_tech(job.title):
                continue
            season = filters.detect_season(job.title, cycles)
            inferred = False
            if season is None:
                if filters.states_explicit_year(job.title):
                    continue
                prior = existing.get(job.id) or {}
                prior_season = prior.get("season")
                if prior_season in cycles:
                    season = prior_season
                    inferred = bool(prior.get("season_inferred"))
                elif infer:
                    season = filters.infer_season(
                        job.title, job.posted_at, cycles, infer_age
                    )
                    inferred = season is not None
            if season is None:
                season = "Term Unconfirmed"
                inferred = True
            if restrict:
                in_region = filters.region_ok(job.location, wants_india, wants_remote)
                if not in_region:
                    continue
            posted_day = (job.posted_at or "")[:10]
            if cutoff and posted_day and posted_day < cutoff:
                continue
            job.season = season
            job.season_inferred = inferred
            job.category = filters.categorize(job.title)
            kept.append(job)
    return kept, succeeded, errors, errors_by_ats


def run_update() -> tuple[dict, dict, list[str]]:
    cfg = config.load_config()
    blocklist = quality.load_blocklist()
    companies = _load_companies()
    existing = store.load(paths.JOBS_PATH)

    health_data = health.load()

    # Inject the YC WaaS aggregator as a virtual company
    companies.append(
        {"name": "Y Combinator (Work at a Startup)", "slug": "yc", "ats": "yc_waas"}
    )

    active, benched = health.partition(companies, health_data)

    started = time.monotonic()
    print(f"Fetching {len(active)} companies ({len(benched)} quarantined)...")

    results = asyncio.run(_fetch_all(active))

    kept, succeeded, errors, errors_by_ats = _keep_matching(
        results, cfg, blocklist, existing
    )
    kept = _dedup(kept)

    for company, _jobs, error in results:
        health.record(health_data, company, error)
    health.save(health_data)

    rows = []
    for job in kept:
        row = asdict(job)
        for field in models.TRANSIENT_FIELDS:
            row.pop(field, None)
        rows.append(row)

    new_ids = store.upsert(existing, rows, succeeded)
    purged = store.purge(existing)
    store.save(paths.JOBS_PATH, existing)

    duration = round(time.monotonic() - started, 1)
    open_records = [r for r in existing.values() if r.get("is_open")]
    attempted = len(companies) - len(benched)

    stats = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "duration_seconds": duration,
        "companies_total": len(companies),
        "companies_by_source": dict(Counter(c["ats"] for c in companies)),
        "quarantined": len(benched),
        "fetched_ok": len(succeeded),
        "fetch_errors": errors,
        "errors_by_source": dict(errors_by_ats),
        "fetch_success_rate": round(len(succeeded) / max(attempted, 1), 3),
        "roles_matched": len(kept),
        "roles_by_source": dict(Counter(j.source for j in kept)),
        "roles_by_cycle": dict(Counter(j.season for j in kept)),
        "roles_by_region": dict(
            Counter(
                (
                    "India"
                    if filters.is_india(j.location)
                    else (
                        "Remote" if filters.is_remote_or_hybrid(j.location) else "Other"
                    )
                )
                for j in kept
            )
        ),
        "purged_this_run": purged,
        "new_this_run": len(new_ids),
        "open_total": len(open_records),
    }

    with open(paths.STATS_PATH, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    _append_history(stats)
    return stats, existing, new_ids


_HISTORY_KEEP = 2000


def _append_history(stats: dict) -> None:
    line = json.dumps(
        {
            "ts": stats["generated_at"],
            "open": stats["open_total"],
            "new": stats["new_this_run"],
            "companies": stats["companies_total"],
            "ok_rate": stats["fetch_success_rate"],
            "secs": stats["duration_seconds"],
        },
        ensure_ascii=False,
    )
    lines = []
    try:
        with open(paths.HISTORY_PATH, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        pass
    lines.append(line)
    os.makedirs(os.path.dirname(paths.HISTORY_PATH), exist_ok=True)
    with open(paths.HISTORY_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines[-_HISTORY_KEEP:]) + "\n")
