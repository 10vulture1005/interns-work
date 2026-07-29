# CS Internship Tracker — Project Plan (v2)

Fully automated career-page monitor. Runs entirely on GitHub Actions (no VPS, no always-on server), checks company career pages hourly, filters down to **technical internships for CS majors only**, updates a README dashboard, and pushes a WhatsApp alert on every new match.

**What's new in v2:** company onboarding is now automated. You no longer manually hunt down each company's ATS type and board slug — you maintain a flat list of company names, and a separate discovery pipeline resolves each one into a working `companies.yaml` entry, escalating from free deterministic checks up to an LLM only when needed.

---

## 1. Objective

- Poll a configurable list of companies every hour
- Surface **internships only** — no full-time, no senior/experienced roles
- Surface **technical / CS-relevant roles only** — no marketing, sales, HR, non-technical business internships
- Update `README.md` as a live dashboard
- Send a WhatsApp message the moment a new match is found
- **Automate company onboarding** — turn a plain list of company names into working scraper configs without manual slug-hunting
- Zero infrastructure beyond the GitHub repo itself

---

## 2. Match criteria — what actually qualifies

Unchanged from v1. A posting must pass **both** filters below to trigger a notification/README entry.

**Included:** SWE/SDE, Data Engineering, ML/AI, Quant Dev/Research (coding-heavy), DevOps/SRE/Platform, Security, Systems/Infra, Mobile — internships only.

**Excluded by default:** Marketing, Sales, BD, HR, Legal, Ops, non-technical Finance, PM/Design (toggleable), and anything full-time/senior/new-grad even at tracked companies.

**Internship signal, not just the word "intern":** some listings are clearly internship-program roles (stipend, fixed 10–12 week duration, university program page) without the word "intern" in the title. This is why matching is two-stage — see Section 6.

---

## 3. Architecture

There are now two independent pipelines, running at different frequencies, sharing one config file as the handoff point.

```
┌─────────────────────────────────────────────────────────┐
│  DISCOVERY PIPELINE  (on-demand / weekly)                │
│                                                           │
│  data/company_seeds.txt (you maintain this — just names) │
│    → Tier 1: deterministic slug guessing + API check     │
│    → Tier 2: careers-page scan for embedded ATS links    │
│    → Tier 3: LLM-assisted identification (fallback only) │
│    → Tier 4: unresolved → data/needs_manual_review.txt   │
│    → confirmed hits appended to config/companies.yaml    │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  TRACKING PIPELINE  (hourly, unchanged from v1)          │
│                                                           │
│  for each company in config/companies.yaml:               │
│    fetch postings → diff against last snapshot            │
│    Stage 1: keyword pre-filter                            │
│    Stage 2: LLM classifies is_internship / is_technical    │
│    passing postings → README update + WhatsApp queue      │
│  commit snapshots + README → push                         │
└─────────────────────────────────────────────────────────┘
```

Splitting these matters: discovery is bursty and infrequent (you add a few companies, resolve them, done), while tracking needs to run like clockwork every hour regardless. Keeping them as separate workflows means a slow or flaky discovery run never risks the hourly job.

No server ever stays running. State lives in committed files; the repo itself is the database.

---

## 4. Repo structure

```
career-tracker/
├── .github/workflows/
│   ├── track-jobs.yml           # hourly, unchanged
│   └── discover-companies.yml   # NEW — on-demand/weekly
├── config/companies.yaml        # now auto-populated, not hand-written
├── data/
│   ├── company_seeds.txt        # NEW — your only manual input: plain names
│   ├── needs_manual_review.txt  # NEW — discovery's unresolved leftovers
│   ├── snapshots/{slug}.json
│   └── history.jsonl
├── src/
│   ├── discovery/                # NEW
│   │   ├── slug_guesser.py       # Tier 1
│   │   ├── page_scanner.py       # Tier 2
│   │   └── llm_ats_identifier.py # Tier 3
│   ├── fetchers/
│   │   ├── greenhouse.py
│   │   ├── lever.py
│   │   ├── ashby.py
│   │   └── custom.py
│   ├── filters/
│   │   ├── keyword_filter.py
│   │   └── llm_classifier.py
│   ├── notify_whatsapp.py
│   ├── readme_writer.py
│   ├── diff_engine.py
│   └── main.py
├── requirements.txt
└── README.md
```

---

## 5. Company onboarding — automated discovery pipeline

This replaces the old "you write YAML by hand" approach. Your only manual input becomes `data/company_seeds.txt` — a flat list, one company per line, optionally with a domain:

```
Stripe
Notion
Rippling
SomeCustomSiteCo, somecustomsiteco.com
```

Everything else is resolved automatically through four escalating tiers, cheapest first — same philosophy as the existing keyword-then-LLM job filter: never spend an API call on something a free check can already answer.

**Tier 1 — Deterministic slug guessing (free, no LLM, no browser)**
Generate candidate slugs from the company name: strip legal-entity noise (`Inc`, `Labs`, `Technologies`, `HQ`, etc.), try the concatenated form, the hyphenated form, and the first word alone. Hit the real public Greenhouse/Lever/Ashby JSON APIs directly with each candidate. A 200 response with a well-formed job list is a **confirmed** match, not a guess — this resolves the large majority of standard-name companies on standard ATS platforms at zero cost.

**Tier 2 — Careers-page scan (free, no LLM)**
For anything Tier 1 misses, fetch the company's own `/careers` or `/jobs` page (this is why a domain is useful in the seed list) and pattern-scan the raw HTML for embedded or linked ATS URLs — iframe sources, script sources, or plain anchor links pointing at `boards.greenhouse.io`, `jobs.lever.co`, `jobs.ashbyhq.com`. This catches companies whose slug doesn't match any guessable form of their brand name. Any hit found this way still gets run back through the Tier 1 API check before being accepted — a scraped guess is never trusted without live confirmation.

**Tier 3 — LLM-assisted identification (fallback only, reuses existing OpenRouter setup)**
For the stubborn remainder — unusual slugs, JS-rendered careers pages, or an ATS platform outside the three hardcoded ones — feed the fetched page content to an LLM and ask it to:
1. Identify the actual ATS platform in use, including ones beyond Greenhouse/Lever/Ashby (Workday, SmartRecruiters, iCIMS, Breezy, Workable, Personio, JazzHR, Recruitee, BambooHR are all common enough to show up eventually).
2. Extract the board slug or direct listing URL from whatever context clues are present (meta tags, canonical links, apply-form action URLs, visible page text).
3. If no recognized ATS is present at all, propose a CSS-selector strategy for the existing `custom.py` scraper path — the LLM drafts the `css_hint` instead of you hand-inspecting page source.

Same guardrail as the job-classification stage: **the LLM's output is a hypothesis, never written straight to config.** If it names a known ATS + slug, that combination gets one more direct API call to confirm before `companies.yaml` is touched. If it proposes a `css_hint`, that's stored as a best-guess starting point, same as v1's custom-company handling — still fallback-to-LLM-extraction if the selector breaks.

**Tier 4 — Manual review**
If even the LLM can't confidently identify anything (no ATS signal, contradictory clues), the company lands in `data/needs_manual_review.txt` with whatever partial context was gathered — page snippet, LLM's best guess, confidence level — so a 30-second human glance is enough instead of starting from zero.

**Optional extension — drift detection:** ATS platforms migrate occasionally (a company moves from Greenhouse to Ashby). The same discovery pipeline can be re-run periodically against *already-configured* companies, not just new ones, to catch this before it silently breaks the tracking pipeline. Not required for v1 of this feature — worth adding once the core loop is trusted.

---

## 6. Filtering pipeline (unchanged)

Two-stage, as in v1: cheap keyword pre-filter on every posting, then LLM classification (`is_internship`, `is_technical_cs`, `category`, `confidence`) only on Stage-1 survivors that are also new in the diff. The LLM never touches the application link, company name, or date — those stay programmatically extracted, read-only context.

---

## 7. OpenRouter integration

Now used in **two** places: discovery Tier 3 and job-classification Stage 2. Both are low-volume — discovery only calls out on unresolved companies (a handful, one-time per company), classification only on new diffed postings (0–5 per hourly run) — so combined usage stays comfortably inside the free-tier rate limits (50/day free, 1,000/day with $10 credit, 20/min cap). Use the auto-router (`openrouter/free`) rather than pinning a specific `:free` model slug, since free-model availability rotates and pinning is the most common way these integrations quietly break months later.

---

## 8. Diff / state engine (unchanged)

`data/snapshots/{slug}.json` holds job IDs seen as of the last run; overwritten every run regardless of matches, to prevent drift compounding. `data/history.jsonl` appends one line per confirmed match as a permanent audit trail.

---

## 9. WhatsApp delivery (unchanged)

CallMeBot for v1 simplicity, wrapped in a single `send(message)` function so swapping to the official Meta Cloud API later is a one-file change. Matches batched into one message per run.

---

## 10. GitHub Actions workflows

Now two workflows instead of one:

**`track-jobs.yml`** — unchanged from v1. Hourly cron, reads `config/companies.yaml`, runs the tracking pipeline, commits.

**`discover-companies.yml`** — new. Triggered on push to `data/company_seeds.txt`, plus `workflow_dispatch` for on-demand runs, plus an optional low-frequency cron (e.g. weekly) if you want drift detection. Runs the four-tier discovery pipeline, commits updated `config/companies.yaml` and `data/needs_manual_review.txt` back to the repo.

Keeping these separate means a discovery run (which touches the network more unpredictably — external careers pages, occasional LLM calls) never risks the reliability of the hourly tracking job.

---

## 11. README dashboard format (unchanged)

```markdown
<!-- JOBS:START -->
| Company | Role | Location | Found | Link |
|---|---|---|---|---|
| Stripe | Backend Engineering Intern | Bangalore | 2026-07-29 | [Apply](https://job.link/1) |
<!-- JOBS:END -->
```

---

## 12. Secrets checklist

Same as v1 — no new secrets needed. `OPENROUTER_API_KEY` is now shared across both the discovery pipeline's Tier 3 and the tracking pipeline's Stage 2.

| Secret | Purpose |
|---|---|
| `OPENROUTER_API_KEY` | LLM job classification + LLM-assisted ATS/slug discovery |
| `CALLMEBOT_APIKEY` | WhatsApp delivery |
| `WHATSAPP_PHONE` | Your number, for the CallMeBot GET request |

---

## 13. Build phases

**Phase 0 — Company onboarding automation (NEW, build first)**
Tier 1 (deterministic guessing) and Tier 2 (careers-page scan) only — validate against a handful of known companies until slug resolution is reliable. Add Tier 3 (LLM-assisted) afterward, as a fallback layer on top of a working deterministic core, not as the primary path. This keeps discovery fast and free for the common case and reserves LLM calls for genuinely ambiguous companies.

**Phase 1 — Core tracking loop, no filtering intelligence, no WhatsApp yet**
ATS-only companies, basic keyword filter, diff engine, README update, hourly commit. Confirm this runs cleanly for a few days before adding anything else.

**Phase 2 — Two-stage filtering**
Add OpenRouter classification on top of the working Phase 1 loop. Validate on known internship vs. non-internship titles before trusting it live.

**Phase 3 — WhatsApp**
Wire in CallMeBot on top of the now-trusted filter pipeline.

**Phase 4 — Custom scrapers + resilience**
LLM-based extraction for non-ATS career pages (now bootstrapped by Tier 3's proposed `css_hint` from Phase 0, rather than starting blind). Add a "source returned zero results" self-check so a broken selector reads as failure, not "no internships this week."

---

## 14. Known failure modes to design around

**From v1 (unchanged):**
- Silent scraper breakage after a careers-page redesign — alert if a normally-reliable source suddenly returns 0 results.
- Anti-bot protection on some corporate/Workday-hosted sites — may need proper headers or may not be scraper-friendly at all; deprioritize vs. ATS-backed companies.
- False positives from keyword-only filtering — why Stage 2 LLM classification exists.
- OpenRouter free-model rotation — use `openrouter/free`, don't pin a `:free` slug.

**New, from the discovery pipeline:**
- **Slug collision** — a guessed slug happens to be a valid, unrelated company on the same ATS. Mitigation: always cross-check the returned board's company name/job content against the expected company before accepting a Tier 1 match, not just "the API returned 200."
- **LLM hallucinating a plausible but wrong slug** — mitigated by the mandatory re-verification API call before anything from Tier 3 is written to `companies.yaml`. Tier 3 output is a hypothesis until confirmed, never authoritative on its own.
- **JS-rendered careers pages** — Tier 2's raw-HTML scan won't see ATS links injected client-side. These fall through to Tier 3, and since the LLM only sees what the static fetch retrieved, genuinely JS-heavy pages may land in manual review regardless — a known ceiling for this approach without adding a headless browser, which is a deliberate scope cut to stay server-less and simple.

---

## 15. Possible future extensions

- Application deadline tracking / expiry warnings
- Resume-match scoring per posting
- Dedup across ATS platforms when the same role is cross-posted
- Extend beyond internships to new-grad roles as an opt-in category
- Drift detection: periodically re-run discovery on already-configured companies to catch silent ATS migrations
- Expand hardcoded fetchers beyond Greenhouse/Lever/Ashby once Tier 3 discovery shows recurring demand for a specific platform (e.g. several tracked companies turning out to run on Workday would justify building a proper Workday fetcher instead of routing them all through the custom scraper path)