from __future__ import annotations
from scrapling.fetchers import Fetcher
from ..models import Job
from ..net import Net
import asyncio

async def fetch(company: dict, net: Net) -> list[Job]:
    """Fetch jobs from Google Careers."""
    jobs: list[Job] = []
    
    # We will search for 'intern' and 'apprentice' specifically to avoid 
    # pulling 10,000 full time jobs, since Google's UI has pagination.
    queries = ["intern", "apprentice"]
    
    # Scrapling is synchronous by default unless we wrap it in a thread.
    def fetch_sync(query):
        url = f"https://www.google.com/about/careers/applications/jobs/results/?q={query}"
        try:
            page = Fetcher.get(url, timeout=15)
            if page.status == 200:
                return page
        except Exception as e:
            print(f"Google fetch failed for {query}: {e}")
        return None

    for q in queries:
        page = await asyncio.to_thread(fetch_sync, q)
        if not page:
            continue
            
        try:
            job_elements = page.css('.VfPpkd-WsjYwc')
            for el in job_elements:
                try:
                    title_el = el.css('h3')[0]
                    title = title_el.text.strip()
                except IndexError:
                    title = "Unknown"
                    
                try:
                    link_el = el.css('a')[0]
                    link = link_el.attrib.get('href', '')
                except IndexError:
                    link = ""
                    
                job_url = f"https://www.google.com/about/careers/applications{link}" if link.startswith("/") else link
                
                try:
                    loc_el = el.css('.pwO9Dc')[0]
                    location = loc_el.text.strip()
                except IndexError:
                    location = ""
                
                job_id = link.split("/")[-1] if link else None
                if not job_id:
                    continue
                    
                if title != "Unknown":
                    jobs.append(
                        Job(
                            id=f"google:{job_id}",
                            source="google",
                            company=company["name"],
                            company_slug=company["slug"],
                            title=title,
                            location=location,
                            url=job_url,
                            posted_at=None
                        )
                    )
        except Exception as e:
            print(f"Failed to parse Google {q}: {e}")
            
    # deduplicate by ID
    unique = {j.id: j for j in jobs}
    return list(unique.values())
