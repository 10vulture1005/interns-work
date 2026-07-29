from __future__ import annotations
from ..models import Job
from ..net import Net

async def fetch(company: dict, net: Net) -> list[Job]:
    url = "https://jobs.uber.com/en/"
    page = await net.fetch_html(url, needs_interaction=True)
    if not page:
        return []
        
    jobs: list[Job] = []
    job_elements = page.css('a')
    for el in job_elements:
        try:
            link = el.attrib.get('href', '')
            if '/jobs/' in link or 'job_id=' in link:
                title = el.text.strip()
                if title:
                    job_id = link.split("/")[-1] if link else ""
                    job_url = f"https://jobs.uber.com{link}" if link.startswith("/") else link
                    jobs.append(
                        Job(
                            id=f"uber:{job_id}",
                            source="uber",
                            company=company["name"],
                            company_slug=company["slug"],
                            title=title,
                            location="Various",
                            url=job_url,
                            posted_at=None
                        )
                    )
        except Exception:
            pass
    return jobs
