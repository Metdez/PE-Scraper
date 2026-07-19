"""Manual HTML decongestion (fit_markdown) + content hashing.

RED phase stub — see tests/test_decongest.py. Real implementation follows in the
GREEN commit.
"""

from __future__ import annotations


def decongest(cleaned_html: str, base_url: str) -> str:
    raise NotImplementedError


def content_hash(text: str) -> str:
    raise NotImplementedError
