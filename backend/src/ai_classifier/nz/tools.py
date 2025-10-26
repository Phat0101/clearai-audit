from __future__ import annotations

from typing import List, Dict, Any

import httpx
from ai_classifier.util.sanitize import sanitize_payload as _sanitize_payload


# -----------------------------
# External HTTP helper tools (NZ)
# -----------------------------


_CLEAR_BASE = "https://api.clear.ai/api/v1/au_tariff"
_NZ_BOOK_REF = "NZ_INTRODUCTION_HS_2022"


async def nz_tariff_chapter_lookup(hs_code_4_or_more: str) -> Dict[str, Any]:
    """
    Fetch flattened chapter tariffs for a 4–6 digit HS code (NZ book).
    Use 6 digits when confident about the subheading; otherwise 4 digits for broader chapter context.
    Returns a dict with keys: rawData, chapterNotes (None for NZ).
    """
    code = (hs_code_4_or_more or "").strip()
    if not code.isdigit() or len(code) < 4 or len(code) > 6:
        return {"rawData": [], "chapterNotes": None}

    url = f"{_CLEAR_BASE}/tariffs/chapter_flatten_tariffs?code={code}&book_ref={_NZ_BOOK_REF}"

    try:
        async with httpx.AsyncClient(
            limits=httpx.Limits(max_connections=500, max_keepalive_connections=100),
            timeout=30.0
        ) as client:
            res = await client.get(url)
            raw = res.json() if res.status_code == 200 else []
    except (httpx.HTTPError, ValueError):
        raw = []

    print(f'NZ Agent called nz_tariff_chapter_lookup for {code}')
    return {"rawData": _sanitize_payload(raw), "chapterNotes": None}


async def nz_tariff_search(hs_code_2_to_8: str) -> List[Dict[str, Any]]:
    """
    Detailed lookup for specific NZ HS codes (2-8 digits). Returns list of matches.
    """
    code = (hs_code_2_to_8 or "").strip()
    if not code.isdigit() or not (2 <= len(code) <= 8):
        return []

    url = f"{_CLEAR_BASE}/tariffs/chapter_flatten_tariffs?code={code}&book_ref={_NZ_BOOK_REF}"
    print(f'NZ Agent called nz_tariff_search for {code}')
    try:
        async with httpx.AsyncClient(
            limits=httpx.Limits(max_connections=500, max_keepalive_connections=100),
            timeout=30.0
        ) as client:
            res = await client.get(url)
            if res.status_code != 200:
                return []
            data = res.json()
            data_list = data if isinstance(data, list) else []
            return _sanitize_payload(data_list)
    except (httpx.HTTPError, ValueError):
        return []


# Sanitization is now centralized in ai_classifier.util.sanitize


