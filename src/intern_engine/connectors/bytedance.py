from __future__ import annotations
from ..models import Job
from ..net import Net

async def fetch(company: dict, net: Net) -> list[Job]:
    url = "https://joinbytedance.com/search"
    page = await net.fetch_html(url, needs_interaction=True)
    if not page:
        return []
        
    jobs: list[Job] = []
    job_elements = page.css('a')
    for el in job_elements:
        try:
            link = el.attrib.get('href', '')
            if '/position/' in link or '/job/' in link:
                title = el.text.strip()
                if title:
                    job_id = link.split("/")[-1] if link else ""
                    job_url = f"https://joinbytedance.com{link}" if link.startswith("/") else link
                    jobs.append(
                        Job(
                            id=f"bytedance:{job_id}",
                            source="bytedance",
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
