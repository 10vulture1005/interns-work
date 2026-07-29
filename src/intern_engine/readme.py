"""Renders README.md + data/internships.csv from the job store."""

from __future__ import annotations

import csv
import io
import json
import os
from datetime import UTC, datetime
from html import escape

from . import config, filters, paths


def _flag(job: dict) -> str:
    first_seen = job.get("first_seen_at") or ""
    try:
        dt = datetime.fromisoformat(first_seen.replace("Z", "+00:00"))
        if (datetime.now(UTC) - dt).total_seconds() < 48 * 3600:
            return " 🆕"
    except (ValueError, TypeError):
        pass
    return ""


def generate(store_data: dict) -> dict:
    cfg = config.load_config()
    cycle_list = config.cycles(cfg)
    repo = config.repo_slug()

    open_jobs = [r for r in store_data.values() if r.get("is_open")]
    open_jobs.sort(
        key=lambda r: ((r.get("posted_at") or "")[:10], (r.get("first_seen_at") or "")),
        reverse=True,
    )

    # Load valid company slugs
    try:
        with open(paths.COMPANIES_TXT_PATH, encoding="utf-8") as f:
            valid_companies = {line.strip().lower() for line in f if line.strip()}
    except OSError:
        valid_companies = set()

    # Filter by valid companies and group by cycle + region
    sections: dict[str, list[dict]] = {}

    # Initialize sections for known cycles
    for c in cycle_list:
        sections[f"{c} (India)"] = []
        sections[f"{c} (Remote)"] = []

    filtered_jobs = []
    for job in open_jobs:
        source = job.get("source")
        slug = job.get("company_slug")

        # Keep only YC WaaS jobs OR jobs from companies in companies.txt
        if source != "yc_waas" and slug not in valid_companies:
            continue

        filtered_jobs.append(job)

        s = job.get("season", "Unspecified")
        loc = job.get("location", "")

        if filters.is_remote_or_hybrid(loc):
            group_key = f"{s} (Remote)"
        else:
            group_key = f"{s} (India)"

        if group_key not in sections:
            sections[group_key] = []
        sections[group_key].append(job)

    open_jobs = filtered_jobs

    lines = [
        '<div align="center">',
        '  <h1>🇮🇳 India Tech Internships</h1>',
        '  <p><strong>A self-updating engine tracking top tech internships in India so you don\'t have to.</strong></p>',
        '  <p>',
        f'    <a href="https://{repo.split("/")[0].lower()}.github.io/{repo.split("/")[1]}/">',
        '      <img src="https://img.shields.io/badge/Live_Dashboard-000000?style=for-the-badge&logo=github&logoColor=white" alt="Live Dashboard" />',
        '    </a>',
        f'    <a href="https://{repo.split("/")[0].lower()}.github.io/{repo.split("/")[1]}/api/jobs.json">',
        '      <img src="https://img.shields.io/badge/JSON_API-007ACC?style=for-the-badge&logo=json&logoColor=white" alt="JSON API" />',
        '    </a>',
        '  </p>',
        '  <p>',
        f'    <img src="https://img.shields.io/badge/Open%20Roles-{len(open_jobs)}-6366f1?style=for-the-badge" alt="Open Roles" />',
        '    <img src="https://img.shields.io/badge/Updates-Every%20Hour-22c55e?style=for-the-badge" alt="Updates" />',
        '  </p>',
        f'  <p><em>Last updated: {datetime.now(UTC).strftime("%b %d, %Y at %H:%M UTC")}</em></p>',
        '</div>',
        '',
        '---',
        '',
    ]

    inferred_count = 0
    for label, jobs in sections.items():
        if not jobs:
            continue
        lines.append(f"## {label} <kbd>{len(jobs)} open</kbd>")
        lines.append("")
        lines.append("| 🏢 Company | 💼 Role | 🏷️ Category | 📍 Location | 📅 Posted | 🔗 Apply |")
        lines.append("|---|---|---|---|---|:---:|")
        for job in jobs:
            posted = (job.get("posted_at") or "")[:10] or "—"
            url = job.get("url") or ""
            apply_link = f"[Apply ↗]({url})" if url else "—"
            tilde = " <sup>~</sup>" if job.get("season_inferred") else ""
            flag = " <span title='New within 48h'>✨</span>" if _flag(job) else ""
            if job.get("season_inferred"):
                inferred_count += 1
            lines.append(
                f"| **{job.get('company', '')}** | {job.get('title', '')}{tilde}{flag} "
                f"| `{job.get('category', '')}` "
                f"| {(job.get('location') or '')[:40]} | {posted} | {apply_link} |"
            )
        lines.append("")

    if inferred_count:
        lines.append(
            f"_~ = the title doesn't state a year; bucketed here from its posting date "
            f"({inferred_count} of {len(open_jobs)})._"
        )
        lines.append("")

    # Recently closed
    closed = [
        r for r in store_data.values() if not r.get("is_open") and r.get("closed_at")
    ]
    closed.sort(key=lambda r: r.get("closed_at", ""), reverse=True)
    recent_closed = closed[:20]
    if recent_closed:
        lines.append("<details>")
        lines.append(
            f"<summary><strong>Recently closed</strong> — {len(recent_closed)} roles taken down</summary>"
        )
        lines.append("")
        lines.append("| Company | Role | Cycle | Closed |")
        lines.append("|---|---|---|---|")
        for r in recent_closed:
            lines.append(
                f"| {r.get('company', '')} | {r.get('title', '')} | {r.get('season', '')} "
                f"| {(r.get('closed_at') or '')[:10]} |"
            )
        lines.append("")
        lines.append("</details>")
        lines.append("")

    lines.extend(
        [
            "---",
            "",
            "## How it works",
            "",
            "A Python engine reads public company hiring feeds directly, keeps the internships "
            "that match the scope (India-based tech roles), de-duplicates across sources, and "
            "regenerates this page through GitHub Actions. The full source is in this repo.",
            "",
            "## Contributing",
            "",
            "Add a company to `companies.txt` and run `python run.py discover`.",
            "",
        ]
    )

    with open(paths.README_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # CSV
    _write_csv(open_jobs)

    return {"open": len(open_jobs)}


def _write_csv(jobs: list[dict]) -> None:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["Company", "Title", "Category", "Location", "Season", "Posted", "URL"]
    )
    for job in jobs:
        writer.writerow(
            [
                job.get("company", ""),
                job.get("title", ""),
                job.get("category", ""),
                job.get("location", ""),
                job.get("season", ""),
                (job.get("posted_at") or "")[:10],
                job.get("url", ""),
            ]
        )
    os.makedirs(os.path.dirname(paths.CSV_PATH), exist_ok=True)
    with open(paths.CSV_PATH, "w", encoding="utf-8", newline="") as f:
        f.write(buf.getvalue())
