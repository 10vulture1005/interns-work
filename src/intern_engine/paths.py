"""Central place for every file path, computed from the repo root.

Everything is relative to this file's location, so the project works the same
on your laptop and inside GitHub Actions, regardless of the current directory.
"""

import os

# .../src/intern_engine/paths.py  ->  repo root is two levels up.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

DATA_DIR = os.path.join(ROOT, "data")

CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
BLOCKLIST_PATH = os.path.join(DATA_DIR, "blocklist.json")
CANDIDATES_PATH = os.path.join(DATA_DIR, "candidates.json")
COMPANIES_PATH = os.path.join(DATA_DIR, "companies.json")
COMPANIES_TXT_PATH = os.path.join(ROOT, "companies.txt")
JOBS_PATH = os.path.join(DATA_DIR, "jobs.json")
CSV_PATH = os.path.join(DATA_DIR, "internships.csv")
STATS_PATH = os.path.join(DATA_DIR, "stats.json")
HEALTH_PATH = os.path.join(DATA_DIR, "health.json")
HISTORY_PATH = os.path.join(DATA_DIR, "history.jsonl")

LOGS_DIR = os.path.join(ROOT, "logs")
DISCOVER_LOG_PATH = os.path.join(LOGS_DIR, "discover_attempts.jsonl")
TRACKED_TXT_PATH = os.path.join(ROOT, "tracked_companies.txt")
UNTRACKED_TXT_PATH = os.path.join(ROOT, "untracked_companies.txt")

README_PATH = os.path.join(ROOT, "README.md")
DOCS_DIR = os.path.join(ROOT, "docs")
DASHBOARD_PATH = os.path.join(DOCS_DIR, "index.html")
FEED_PATH = os.path.join(DOCS_DIR, "feed.xml")
API_DIR = os.path.join(DOCS_DIR, "api")
