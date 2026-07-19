"""AdaptiveCrawler page selection, skip-list, 403 fallback (PIPE-01).

RED phase stub — see tests/test_crawl.py. Real implementation follows in the GREEN
commit.
"""

from __future__ import annotations

SKIP_KEYWORDS = ("team", "portfolio", "news", "press", "blog", "insights", "careers", "legal", "privacy", "terms")
WELL_KNOWN_PATHS = ("/about", "/investment-criteria", "/strategy", "/approach")
QUERY = "investment criteria ebitda revenue enterprise value check size deal types"


async def select_pages(url: str) -> dict[str, str]:
    raise NotImplementedError
