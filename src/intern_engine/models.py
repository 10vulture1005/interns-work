"""The single normalized job record every connector produces.

Keeping one shape means the pipeline, store, and renderer never care which ATS a
role came from — adding a source touches only its connector.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Fields that exist only during a run and must never be written to the store.
TRANSIENT_FIELDS = ("description",)


@dataclass
class Job:
    id: str  # stable: "<source>:<company_slug>:<external_id>"
    source: str
    company: str
    company_slug: str
    title: str
    location: str
    url: str
    posted_at: str | None = None
    season: str = "Unspecified"
    season_inferred: bool = False
    category: str = "Other"
    salary: str | None = None
    stipend: str | None = None
    experience: str | None = None
    degree: str | None = None
    skills: list[str] | None = None
    description: str | None = None  # transient: raw posting text
