"""All the text classification: is it an internship? is it tech? which season?
India-focused location detection.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

# --- internship detection ---
_INTERN_RE = re.compile(r"\b(intern|interns|internship|co[\s-]?op)\b", re.IGNORECASE)
_SENIOR_RE = re.compile(
    r"\b(senior|sr|staff|principal|manager|director|\blead\b|vp|head)\b",
    re.IGNORECASE,
)

# --- tech-role detection ---
_INCLUDE_RE = re.compile(
    r"\b("
    r"software|developer|swe|full[\s-]?stack|front[\s-]?end|back[\s-]?end|"
    r"web developer|web engineer|mobile|ios|android|devops|sre|site reliability|"
    r"infrastructure|platform engineer|platform engineering|distributed systems|"
    r"operating system|compiler|embedded|firmware|"
    r"data science|data scientist|data engineer|data analyst|analytics engineer|"
    r"machine learning|ml|deep learning|ai|artificial intelligence|nlp|computer vision|"
    r"research scientist|applied scientist|research engineer|ml engineer|ai engineer|"
    r"quantitative developer|quant developer|computer science|programming"
    r")\b",
    re.IGNORECASE,
)
_EXCLUDE_RE = re.compile(
    r"\b("
    r"mechanical|aerospace|aeronautical|propulsion|avionics|"
    r"naval|civil engineer|chemical|chemistry|"
    r"biology|biological|materials|structural|thermal|manufacturing|"
    r"industrial engineer|electrical|fpga|asic|pcb|analog|photonics|"
    r"hardware|physical design|silicon|semiconductor|vlsi|"
    r"recruit|recruiting|recruiter|sales|account executive|"
    r"marketing|marketer|unpaid|"
    r"legal|counsel|accounting|human resources|talent|"
    r"supply chain|business development|product design|product designer|"
    r"product manager|product management|ux design|graphic design"
    r")\b",
    re.IGNORECASE,
)

# --- season detection ---
_YEAR_RE = re.compile(r"\b(20\d\d)\b")
_SHORT_YEAR_RE = re.compile(r"['''](\d{2})\b")
_TITLE_GRAD_RE = re.compile(
    r"\b(?:class\s+of|grad(?:uating|uation)?(?:\s+(?:date|year))?:?(?:\s+in)?)\s+['']?(?:20)?\d{2}\b",
    re.IGNORECASE,
)
_CYCLE_RE = re.compile(r"(Summer|Fall|Spring|Winter)\s+(\d{4})", re.IGNORECASE)
_TERM_ROLLOVER_MONTH = {"Summer": 4, "Fall": 8, "Spring": 2, "Winter": 10}


def is_internship(title: str) -> bool:
    return bool(_INTERN_RE.search(title)) and not _SENIOR_RE.search(title)


def is_tech(title: str) -> bool:
    if _EXCLUDE_RE.search(title):
        return False
    return bool(_INCLUDE_RE.search(title))


def is_cycle_label(value) -> bool:
    return bool(value) and bool(_CYCLE_RE.fullmatch(str(value).strip()))


def _normalize_title(title: str) -> str:
    t = title
    t = re.sub(r"\bsu['\s]?([2-9][0-9])\b", r"Summer 20\1", t, flags=re.IGNORECASE)
    t = re.sub(r"\bfa['\s]?([2-9][0-9])\b", r"Fall 20\1", t, flags=re.IGNORECASE)
    t = re.sub(r"\bsp['\s]?([2-9][0-9])\b", r"Spring 20\1", t, flags=re.IGNORECASE)
    t = re.sub(r"\bwi['\s]?([2-9][0-9])\b", r"Winter 20\1", t, flags=re.IGNORECASE)
    t = re.sub(
        r"\b(may|june|jun)[\s\-]+(?:to[\s\-]+)?(august|aug)\s*(20\d\d|['\s]?[2-9][0-9])?\b",
        lambda m: "Summer " + (("20" + m.group(3)[-2:]) if m.group(3) else ""),
        t,
        flags=re.IGNORECASE,
    )
    return t


def states_explicit_year(title: str) -> bool:
    title = _normalize_title(title)
    scannable = _TITLE_GRAD_RE.sub(" ", title)
    return bool(_YEAR_RE.search(scannable) or _SHORT_YEAR_RE.search(scannable))


def detect_season(title: str, cycles=("Summer 2027", "Fall 2026")) -> str | None:
    parsed = []
    for label in cycles:
        m = _CYCLE_RE.match(label.strip())
        if m:
            parsed.append((m.group(1).capitalize(), m.group(2), label))

    title = _normalize_title(title)
    scannable = _TITLE_GRAD_RE.sub(" ", title)
    years = set(_YEAR_RE.findall(scannable))
    years |= {f"20{d}" for d in _SHORT_YEAR_RE.findall(scannable)}
    if not years:
        return None

    t = title.lower()
    if "summer" in t:
        term = "Summer"
    elif "fall" in t or "autumn" in t:
        term = "Fall"
    elif "spring" in t:
        term = "Spring"
    elif "winter" in t:
        term = "Winter"
    else:
        term = None

    for cterm, cyear, label in parsed:
        if cyear in years and term == cterm:
            return label
    for _cterm, cyear, label in parsed:
        if cyear in years and term is None:
            return label
    return None


def infer_season(
    title: str,
    posted_at: str | None,
    cycles=("Summer 2027", "Fall 2026"),
    max_age_days: int = 45,
    now: datetime | None = None,
) -> str | None:
    title = _normalize_title(title)
    if states_explicit_year(title):
        return None
    now = now or datetime.now(UTC)

    if not posted_at:
        posted = now
    else:
        try:
            posted = datetime.strptime(posted_at[:10], "%Y-%m-%d").replace(tzinfo=UTC)
            age_days = (now - posted).days
            if not (-1 <= age_days <= max_age_days):
                return None
        except ValueError:
            posted = now

    t = title.lower()
    if "summer" in t:
        term = "Summer"
    elif "fall" in t or "autumn" in t:
        term = "Fall"
    elif "spring" in t:
        term = "Spring"
    elif "winter" in t:
        term = "Winter"
    else:
        term = "Summer"

    year = (
        posted.year if posted.month <= _TERM_ROLLOVER_MONTH[term] else posted.year + 1
    )
    label = f"{term} {year}"
    return label if label in cycles else None


# --- location: India detection ---
_INDIA_COUNTRY = ("india", "bharat")
_INDIA_CITIES = [
    "bangalore",
    "bengaluru",
    "hyderabad",
    "mumbai",
    "pune",
    "delhi",
    "new delhi",
    "gurgaon",
    "gurugram",
    "noida",
    "chennai",
    "kolkata",
    "ahmedabad",
    "jaipur",
    "lucknow",
    "chandigarh",
    "indore",
    "kochi",
    "coimbatore",
    "thiruvananthapuram",
    "trivandrum",
    "nagpur",
    "bhopal",
    "visakhapatnam",
    "vizag",
    "mysore",
    "mysuru",
    "mangalore",
    "mangaluru",
    "vadodara",
    "surat",
    "goa",
    "patna",
    "ranchi",
    "bhubaneswar",
    "dehradun",
    "agra",
    "varanasi",
    "amritsar",
    "ludhiana",
    "greater noida",
    "faridabad",
    "ghaziabad",
    "navi mumbai",
    "thane",
    "mohali",
    "panchkula",
]
_INDIA_STATES = [
    "karnataka",
    "telangana",
    "maharashtra",
    "tamil nadu",
    "andhra pradesh",
    "west bengal",
    "gujarat",
    "rajasthan",
    "uttar pradesh",
    "madhya pradesh",
    "haryana",
    "kerala",
    "punjab",
    "odisha",
    "jharkhand",
    "uttarakhand",
    "goa",
    "assam",
    "himachal pradesh",
    "chhattisgarh",
    "bihar",
]
_INDIA_CITY_RE = re.compile(
    r"\b(" + "|".join(re.escape(c) for c in _INDIA_CITIES) + r")\b", re.IGNORECASE
)
_INDIA_STATE_RE = re.compile(
    r"\b(" + "|".join(re.escape(s) for s in _INDIA_STATES) + r")\b", re.IGNORECASE
)


def is_india(location: str) -> bool:
    if not location:
        return False
    low = location.lower()
    if any(token in low for token in _INDIA_COUNTRY):
        return True
    if _INDIA_CITY_RE.search(low):
        return True
    if _INDIA_STATE_RE.search(low):
        return True
    return False


_REMOTE_RE = re.compile(
    r"\b(remote|work\s+from\s+home|wfh|anywhere|distributed|virtual)\b",
    re.IGNORECASE,
)
_HYBRID_RE = re.compile(
    r"\b(hybrid|flexible\s+location|partly\s+remote)\b",
    re.IGNORECASE,
)


def is_remote_or_hybrid(location: str) -> bool:
    if not location:
        return False
    return bool(_REMOTE_RE.search(location) or _HYBRID_RE.search(location))


def region_ok(location: str, want_india: bool = True, want_remote: bool = True) -> bool:
    if want_india and is_india(location):
        return True
    if want_remote and is_remote_or_hybrid(location):
        return True
    return False


# --- category tagging ---
_CATEGORY_PATTERNS = [
    ("Quant", re.compile(r"\b(quant|quantitative|trading|trader)\b", re.IGNORECASE)),
    (
        "Data & ML/AI",
        re.compile(
            r"\b(data|machine learning|\bml\b|\bai\b|artificial intelligence|"
            r"deep learning|nlp|computer vision|research scientist|"
            r"applied scientist|analytics)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Software",
        re.compile(
            r"\b(software|developer|swe|backend|frontend|full[\s-]?stack|"
            r"mobile|ios|android|devops|sre|infrastructure|platform|systems|"
            r"cloud|web|compiler|embedded|firmware|engineer|engineering|"
            r"programming|computer science)\b",
            re.IGNORECASE,
        ),
    ),
]


def categorize(title: str) -> str:
    for name, pattern in _CATEGORY_PATTERNS:
        if pattern.search(title):
            return name
    return "Other"
