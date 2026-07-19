"""Hand-verified golden set for the Phase 3 accuracy benchmark.

Each entry's ``pages`` text was fetched live from the real firm site this
session and read by hand (see 03-SUMMARY.md) to determine ``expected`` — the
fields genuinely stated on that page. Fields not mentioned on the page are
intentionally omitted from ``expected`` (the correct pipeline answer is null;
the benchmark only scores fields with a real, verifiable answer). Page text is
frozen here (not re-crawled) so the benchmark is a deterministic regression
suite — reruns after a prompt/model change measure real drift, not site churn.
"""

from __future__ import annotations

GOLDEN_SET = [
    {
        "firm_name": "A&M Capital Advisors",
        "website": "https://www.a-mcapital.com",
        "golden_page_url": "https://www.a-mcapital.com/",
        "pages": {
            "https://www.a-mcapital.com/": (
                "About Us: Alvarez & Marsal Capital ('AMC') is a multi-strategy "
                "private equity investment firm with over $5.9 billion in assets "
                "under management across 4 investment strategies. Headquartered in "
                "Greenwich, CT with offices in Manhattan Beach, CA and London, "
                "England. AMC combines a focus on middle-market private equity "
                "investing with deep operational expertise."
            ),
        },
        "expected": {
            "state": "CT",
            "city": "Greenwich",
            "aum_musd": 5900.0,
        },
    },
    {
        "firm_name": "AE Industrial Partners",
        "website": "https://www.aeroequity.com",
        "golden_page_url": "https://www.aeroequity.com/strategies/",
        "pages": {
            "https://www.aeroequity.com/strategies/": (
                "Our Strategies: Private Equity. Drawing on decades of experience, "
                "we make control-oriented investments in strategically important "
                "middle-market companies, often as the first institutional partner "
                "following years of founder, family, or corporate ownership. As a "
                "growth-oriented investor, we partner with management teams to "
                "drive long-term value through both organic initiatives and "
                "strategic acquisitions."
            ),
        },
        "expected": {
            "deal_types": "Buyout",
        },
    },
    {
        "firm_name": "Agellus Capital",
        "website": "https://www.agellus.com",
        "golden_page_url": "https://www.agellus.com/",
        "pages": {
            "https://www.agellus.com/": (
                "Trusted Partners for Transformational Growth. 200+ career deals "
                "closed by senior team. $400M Fund I. 38+ years combined PE "
                "investment history."
            ),
        },
        "expected": {
            "aum_musd": 400.0,
            "fund_name": "Fund I",
        },
    },
]
