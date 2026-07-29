"""Generate a self-contained dark-mode dashboard for GitHub Pages.

Writes docs/index.html with run metrics, listings table with search/filter,
all baked in as static HTML+CSS+JS. Regenerated every run.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from html import escape

from . import config, paths


def _cards(stats: dict) -> str:
    items = [
        ("Open roles", stats.get("open_total", 0)),
        ("Companies tracked", f"{stats.get('companies_total', 0):,}"),
        ("ATS sources", len(stats.get("companies_by_source", {}))),
        ("Fetch success", f"{int(stats.get('fetch_success_rate', 0) * 100)}%"),
        ("Quarantined boards", stats.get("quarantined", 0)),
        ("New this run", stats.get("new_this_run", 0)),
        ("Last run", f"{stats.get('duration_seconds', 0)}s"),
    ]
    return "".join(
        f'<div class="card"><div class="num">{escape(str(v))}</div>'
        f'<div class="lbl">{escape(label)}</div></div>'
        for label, v in items
    )


def _bars(counter: dict) -> str:
    if not counter:
        return "<p class='muted'>none</p>"
    top = max(counter.values())
    rows = []
    for name, n in sorted(counter.items(), key=lambda kv: -kv[1]):
        pct = int(n / top * 100) if top else 0
        rows.append(
            f'<div class="bar"><span class="bname">{escape(str(name))}</span>'
            f'<span class="btrack"><span class="bfill" style="width:{pct}%"></span></span>'
            f'<span class="bval">{n}</span></div>'
        )
    return "".join(rows)


def _history_points(limit: int = 120) -> list[dict]:
    points = []
    try:
        with open(paths.HISTORY_PATH, encoding="utf-8") as f:
            for line in f.read().splitlines()[-limit:]:
                try:
                    points.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return points


def _sparkline(points: list[dict]) -> str:
    values = [p.get("open", 0) for p in points]
    if len(values) < 2:
        return "<p class='muted'>History chart appears after a few more runs.</p>"
    w, h, pad = 640, 80, 4
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    step = (w - 2 * pad) / (len(values) - 1)
    coords = [
        f"{pad + i * step:.1f},{h - pad - (v - lo) / span * (h - 2 * pad):.1f}"
        for i, v in enumerate(values)
    ]
    return (
        f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="none" class="spark">'
        f'<polyline fill="none" stroke="var(--accent)" stroke-width="2" points="{" ".join(coords)}"/>'
        "</svg>"
        f'<p class="muted" style="font-size:12px;margin:6px 0 0">'
        f"Open roles per run — now {values[-1]}, peak {hi}.</p>"
    )


def _rows(open_jobs: list[dict]) -> str:
    rows = []
    for r in open_jobs:
        posted = (r.get("posted_at") or "")[:10] or "—"
        url = r.get("url") or ""
        apply_link = (
            f'<a href="{escape(url)}" target="_blank" rel="noopener">Apply</a>'
            if url
            else "—"
        )
        cycle_tag = (
            "<span class='tag' title='cycle inferred from posting date'>"
            f"{escape(r.get('season', ''))} ~</span>"
            if r.get("season_inferred")
            else f"<span class='tag'>{escape(r.get('season', ''))}</span>"
        )
        salary = r.get("salary") or ""
        haystack = " ".join(
            str(r.get(k) or "")
            for k in ("company", "title", "location", "category", "season", "salary")
        ).lower()
        rows.append(
            f'<tr data-cycle="{escape(r.get("season", ""))}" '
            f'data-category="{escape(r.get("category", ""))}" '
            f'data-posted="{escape(posted if posted != "—" else "")}" '
            f'data-inferred="{1 if r.get("season_inferred") else 0}" '
            f'data-text="{escape(haystack)}">'
            f"<td>{escape(r.get('company', ''))}</td>"
            f"<td>{escape(r.get('title', ''))}</td>"
            f"<td>{cycle_tag}</td>"
            f"<td>{escape(r.get('category', ''))}</td>"
            f"<td>{escape((r.get('location') or '')[:48])}</td>"
            f"<td class='muted'>{escape(salary[:36])}</td>"
            f"<td>{escape(posted)}</td>"
            f"<td>{apply_link}</td>"
            "</tr>"
        )
    return "".join(rows)


def _options(values: list[str]) -> str:
    return "".join(f'<option value="{escape(v)}">{escape(v)}</option>' for v in values)


def generate(store_data: dict, stats: dict) -> None:
    open_jobs = [r for r in store_data.values() if r.get("is_open")]
    open_jobs.sort(
        key=lambda r: ((r.get("posted_at") or "")[:10], (r.get("first_seen_at") or "")),
        reverse=True,
    )
    cfg = config.load_config()
    updated = datetime.now(UTC).strftime("%b %d, %Y at %H:%M UTC")
    repo = config.repo_slug()

    cycles = sorted({r.get("season", "") for r in open_jobs if r.get("season")})
    categories = sorted({r.get("category", "") for r in open_jobs if r.get("category")})
    by_category: dict[str, int] = {}
    for r in open_jobs:
        cat = r.get("category") or "Other"
        by_category[cat] = by_category.get(cat, 0) + 1

    html_doc = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Intern Engine India — Live Dashboard</title>
<meta name="description" content="India tech internships, auto-refreshed. Search, filter, apply.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  :root {{ --bg:#0a0a0f; --card:#12121a; --line:#1e1e2e; --txt:#e4e4ef;
           --muted:#6c6c8a; --accent:#6366f1; --green:#22c55e;
           --glow:0 0 20px rgba(99,102,241,.15); }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--txt);
          font:15px/1.6 'Inter',-apple-system,sans-serif; }}
  .wrap {{ max-width:1140px; margin:0 auto; padding:36px 20px 80px; }}
  h1 {{ font-size:28px; margin:0 0 4px; background:linear-gradient(135deg,#6366f1,#a855f7);
        -webkit-background-clip:text; -webkit-text-fill-color:transparent; }}
  .sub {{ color:var(--muted); margin:0 0 28px; font-size:14px; }}
  .sub a {{ color:var(--accent); }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
           gap:12px; margin-bottom:32px; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:12px;
           padding:18px; box-shadow:var(--glow); transition:transform .15s; }}
  .card:hover {{ transform:translateY(-2px); }}
  .num {{ font-size:26px; font-weight:700; }}
  .lbl {{ color:var(--muted); font-size:12px; margin-top:2px; text-transform:uppercase;
           letter-spacing:.5px; }}
  h2 {{ font-size:16px; margin:28px 0 10px; }}
  .panels {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; }}
  @media(max-width:680px) {{ .panels {{ grid-template-columns:1fr; }} }}
  .bar {{ display:flex; align-items:center; gap:10px; margin:6px 0; font-size:13px; }}
  .bname {{ width:120px; color:var(--muted); }}
  .btrack {{ flex:1; height:6px; background:#1a1a2e; border-radius:6px; overflow:hidden; }}
  .bfill {{ display:block; height:100%; background:linear-gradient(90deg,#6366f1,#a855f7);
            border-radius:6px; }}
  .bval {{ width:36px; text-align:right; }}
  .spark {{ width:100%; height:80px; display:block; background:var(--card);
            border:1px solid var(--line); border-radius:12px; }}
  .filters {{ display:flex; flex-wrap:wrap; gap:10px; margin:10px 0 4px; align-items:center; }}
  .filters input[type=search], .filters select {{
      background:var(--card); color:var(--txt); border:1px solid var(--line);
      border-radius:10px; padding:8px 12px; font-size:13.5px; font-family:inherit; }}
  .filters input[type=search] {{ flex:1; min-width:200px; }}
  .filters input[type=search]:focus {{ outline:none; border-color:var(--accent);
      box-shadow:0 0 0 3px rgba(99,102,241,.2); }}
  table {{ width:100%; border-collapse:collapse; margin-top:8px; font-size:13.5px; }}
  th,td {{ text-align:left; padding:10px 12px; border-bottom:1px solid var(--line);
           vertical-align:top; }}
  th {{ color:var(--muted); font-weight:600; font-size:11px; text-transform:uppercase;
        letter-spacing:.5px; }}
  a {{ color:var(--accent); text-decoration:none; }}
  a:hover {{ text-decoration:underline; }}
  .tag {{ background:#6366f122; color:#a5b4fc; padding:2px 8px; border-radius:20px;
          font-size:11px; white-space:nowrap; }}
  .muted {{ color:var(--muted); }}
  footer {{ color:var(--muted); font-size:12px; margin-top:40px; border-top:1px solid var(--line);
            padding-top:20px; }}
</style></head><body><div class="wrap">
  <h1>🇮🇳 Intern Engine India</h1>
  <p class="sub">India tech internships, refreshed automatically. Updated {escape(updated)}.
  <a href="api/jobs.json">JSON API</a> ·
  <a href="feed.xml">RSS</a> ·
  <a href="https://github.com/{escape(repo)}">GitHub</a></p>
  <div class="grid">{_cards(stats)}</div>
  {_sparkline(_history_points())}
  <div class="panels">
    <div><h2>Roles by source</h2>{_bars(stats.get("roles_by_source", {}))}</div>
    <div><h2>Roles by cycle</h2>{_bars(stats.get("roles_by_cycle", {}))}</div>
    <div><h2>Roles by category</h2>{_bars(by_category)}</div>
    <div><h2>Roles by region</h2>{_bars(stats.get("roles_by_region", {}))}</div>
  </div>
  <h2>Open roles (<span id="count">{len(open_jobs)}</span>)</h2>
  <div class="filters">
    <input id="q" type="search" placeholder="Search company, role, location, or skill…" autocomplete="off">
    <select id="cycle"><option value="">All cycles</option>{_options(cycles)}</select>
    <select id="cat"><option value="">All categories</option>{_options(categories)}</select>
    <select id="age">
      <option value="">Posted anytime</option>
      <option value="2">Last 48 hours</option>
      <option value="7">Last 7 days</option>
      <option value="30">Last 30 days</option>
    </select>
  </div>
  <table><thead><tr><th>Company</th><th>Role</th><th>Cycle</th><th>Category</th>
  <th>Location</th><th>Salary</th><th>Posted</th><th></th></tr></thead>
  <tbody id="rows">{_rows(open_jobs)}</tbody></table>
  <footer>Generated by the engine on each run. Companies polled across
  {len(stats.get("companies_by_source", {}))} ATS platforms.</footer>
</div>
<script>
(function () {{
  var q = document.getElementById('q'), cycle = document.getElementById('cycle'),
      cat = document.getElementById('cat'), age = document.getElementById('age'),
      rows = Array.prototype.slice.call(document.getElementById('rows').rows),
      count = document.getElementById('count');
  function cutoffISO(days) {{
    var d = new Date(Date.now() - days * 86400000);
    return d.toISOString().slice(0, 10);
  }}
  function apply() {{
    var text = q.value.trim().toLowerCase(), cy = cycle.value, ca = cat.value, shown = 0,
        minPosted = age.value ? cutoffISO(parseInt(age.value, 10)) : '';
    rows.forEach(function (tr) {{
      var ok = (!text || tr.dataset.text.indexOf(text) !== -1)
        && (!cy || tr.dataset.cycle === cy)
        && (!ca || tr.dataset.category === ca)
        && (!minPosted || (tr.dataset.posted && tr.dataset.posted >= minPosted));
      tr.style.display = ok ? '' : 'none';
      if (ok) shown++;
    }});
    count.textContent = shown;
  }}
  [q, cycle, cat, age].forEach(function (el) {{
    el.addEventListener('input', apply); el.addEventListener('change', apply);
  }});
}})();
</script>
</body></html>"""

    os.makedirs(paths.DOCS_DIR, exist_ok=True)
    with open(paths.DASHBOARD_PATH, "w", encoding="utf-8") as f:
        f.write(html_doc)
