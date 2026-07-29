"""Renders the Atom feed + static JSON API under docs/."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from html import escape

from . import config, paths


def write_feed(store_data: dict) -> int:
    """Write an Atom feed of open roles (newest-spotted first)."""
    open_jobs = [r for r in store_data.values() if r.get("is_open")]
    open_jobs.sort(key=lambda r: r.get("first_seen_at", ""), reverse=True)
    entries = open_jobs[:50]

    repo = config.repo_slug()
    base = config.pages_base()
    updated = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    xml_entries = []
    for r in entries:
        xml_entries.append(f"""  <entry>
    <title>{escape(r.get('company', ''))} — {escape(r.get('title', ''))}</title>
    <link href="{escape(r.get('url', ''))}" rel="alternate"/>
    <id>{escape(r.get('id', ''))}</id>
    <updated>{escape(r.get('first_seen_at', updated))}</updated>
    <summary>{escape(r.get('location', ''))} · {escape(r.get('category', ''))} · {escape(r.get('season', ''))}</summary>
  </entry>""")

    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Intern Engine India — New Internships</title>
  <link href="{base}/feed.xml" rel="self"/>
  <link href="{base}/" rel="alternate"/>
  <id>{base}/</id>
  <updated>{updated}</updated>
  <author><name>Intern Engine India</name></author>
{"".join(xml_entries)}
</feed>
"""
    os.makedirs(paths.DOCS_DIR, exist_ok=True)
    with open(paths.FEED_PATH, "w", encoding="utf-8") as f:
        f.write(xml)
    return len(entries)


def write_api(store_data: dict, stats: dict) -> None:
    """Write static JSON API files."""
    open_jobs = [r for r in store_data.values() if r.get("is_open")]
    open_jobs.sort(
        key=lambda r: ((r.get("posted_at") or "")[:10], (r.get("first_seen_at") or "")),
        reverse=True,
    )

    api_jobs = []
    for r in open_jobs:
        api_jobs.append(
            {
                "id": r.get("id"),
                "company": r.get("company"),
                "title": r.get("title"),
                "location": r.get("location"),
                "category": r.get("category"),
                "season": r.get("season"),
                "posted_at": r.get("posted_at"),
                "url": r.get("url"),
                "salary": r.get("salary"),
                "source": r.get("source"),
            }
        )

    os.makedirs(paths.API_DIR, exist_ok=True)
    with open(os.path.join(paths.API_DIR, "jobs.json"), "w", encoding="utf-8") as f:
        json.dump(api_jobs, f, indent=2, ensure_ascii=False)
    with open(os.path.join(paths.API_DIR, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
