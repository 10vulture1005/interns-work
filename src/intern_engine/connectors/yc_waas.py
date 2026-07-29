"""Aggregator fetcher for Y Combinator Work at a Startup (WaaS).

Unlike standard ATS connectors that pull for a single company, this pulls
from the YC aggregator board for all matching startups.
"""

from __future__ import annotations

import json
import os
import re
from html import unescape
from typing import Any

import yaml

from .. import models, paths
from ..net import Net


def load_yc_config() -> dict:
    try:
        with open(
            os.path.join(paths.ROOT, "config", "yc_watch.yaml"), encoding="utf-8"
        ) as f:
            return yaml.safe_load(f) or {}
    except OSError:
        return {}


async def _login(net: Net) -> str | None:
    # Attempt to read a pre-provided session key first (most robust)
    session_key = os.environ.get("YC_WAAS_SESSION_KEY")
    if session_key:
        return session_key

    email = os.environ.get("YC_WAAS_EMAIL")
    password = os.environ.get("YC_WAAS_PASSWORD")
    if not email or not password:
        return None

    # YC Account login is heavily protected and uses Magic Links or reCAPTCHA.
    # A full headless browser login would be required here if session key is not provided.
    # For now, we raise a ValueError to instruct the user to use the session key.
    raise ValueError(
        "YC_WAAS_SESSION_KEY environment variable is required. "
        "Automated login via email/password is blocked by YC's Magic Link/Captcha wall."
    )


def extract_inertia_data(html_text: str) -> dict | None:
    match = re.search(r'data-page="([^"]+)"', html_text)
    if match:
        try:
            return json.loads(unescape(match.group(1)))
        except (json.JSONDecodeError, TypeError):
            pass
    return None


async def fetch(company: dict, net: Net) -> list[models.Job]:
    """Fetch jobs from YC Work at a Startup."""
    cfg = load_yc_config()
    if not cfg.get("enabled", True):
        return []

    # Get authentication
    session_key = await _login(net)
    if not session_key:
        print("Skipping yc_waas: No YC_WAAS_SESSION_KEY provided.")
        return []

    cookies = {"_bf_session_key": session_key}

    # In a real environment, WaaS uses complex Algolia filters or Inertia post requests.
    # We will simulate the request to the main jobs page with query params.
    locations = cfg.get("locations", ["India", "Remote"])
    # We will fetch without locations first if the URL doesn't support it directly,
    # but let's try to pass locations in the query string.
    url = "https://www.workatastartup.com/jobs"

    resp = await net.get(url, cookies=cookies)
    if resp.status_code != 200:
        raise RuntimeError(f"YC WaaS returned status {resp.status_code}")

    data = extract_inertia_data(resp.text)
    if not data:
        raise RuntimeError("Could not find Inertia payload in YC WaaS response")

    props = data.get("props", {})
    raw_jobs = props.get("jobs", [])

    results = []
    for rj in raw_jobs:
        # Some fields might be nested or named differently in the actual WaaS schema
        job_id = str(rj.get("id", ""))
        if not job_id:
            continue

        company_slug = rj.get("companySlug", "unknown")
        company_name = rj.get("companyName", "Unknown Startup")
        title = rj.get("title", "")
        location = rj.get("location", "")

        # WaaS apply links usually redirect through an internal route
        apply_url = (
            rj.get("applyUrl") or f"https://www.workatastartup.com/jobs/{job_id}"
        )

        results.append(
            models.Job(
                id=f"yc_waas:{company_slug}:{job_id}",
                source="yc_waas",
                company=company_name,
                company_slug=company_slug,
                title=title,
                location=location,
                url=apply_url,
                # Description might not be in the summary API, but if it is, we add it
                description=rj.get("description", ""),
            )
        )

    return results
