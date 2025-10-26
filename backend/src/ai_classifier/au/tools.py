from __future__ import annotations

from typing import List, Dict, Any, Optional
import asyncio

from pydantic import BaseModel, Field, ValidationError
import httpx
import os
from google import genai
from google.genai.types import GenerateContentConfig, GoogleSearch, Tool
from ai_classifier.util.sanitize import sanitize_payload as _sanitize_payload


# -----------------------------
# Data models shared by agent
# -----------------------------


class Item(BaseModel):
    id: str = Field(..., description="Item identifier")
    description: str = Field(..., description="Free-text item description")
    supplier_name: Optional[str] = Field(
        default=None,
        description="Optional supplier/manufacturer/brand name for additional context",
    )


class SuggestedCode(BaseModel):
    hs_code: str = Field(..., description="8-digit HS code without dots")
    stat_code: str = Field(..., description="2-digit statistical code")
    tco_link: Optional[str] = Field(
        default=None,
        description="TCO link when tariff_orders is True (format as `https://www.abf.gov.au/tariff-classification-subsite/Pages/TariffConcessionOrders.aspx?tcn={94012000}. Note the schema removes all periods and is always 8 digits (ie the 8-digit tariff code)`), otherwise null",
    )


class ClassificationResult(BaseModel):
    id: str
    description: str
    supplier_name: Optional[str] = Field(
        default=None,
        description="Echoed supplier name when provided in the request",
    )
    best_suggested_hs_code: str
    best_suggested_stat_code: str
    best_suggested_tco_link: Optional[str] = Field(
        default=None,
        description="TCO link for the best suggestion if applicable (format as `https://www.abf.gov.au/tariff-classification-subsite/Pages/TariffConcessionOrders.aspx?tcn={94012000}. Note the schema removes all periods and is always 8 digits (ie the 8-digit tariff code)`), otherwise null",
    )
    other_suggested_codes: List[SuggestedCode] = Field(
        default_factory=list,
        description="Two additional suggested HS+stat code pairs",
    )
    total_time_seconds: Optional[float] = Field(
        default=None,
        description="Total time taken for classification in seconds",
    )
    reasoning: str = Field(..., description="Detailed reasoning for the classification in Markdown format")
    grounded_product_brief: Optional[str] = Field(
        default=None,
        description="Grounded product brief used for classification in Markdown format",
    )


class ClassificationRequest(BaseModel):
    items: List[Item]


class ClassificationResponse(BaseModel):
    results: List[ClassificationResult]


# -----------------------------
# External HTTP helper tools
# -----------------------------


_CLEAR_BASE = "https://api.clear.ai/api/v1/au_tariff"


async def tariff_chapter_lookup(hs_code_4_or_more: str) -> Dict[str, Any]:
    """
    Fetch flattened chapter tariffs and chapter notes for a 4–6 digit HS code.
    Use 6 digits when confident about the subheading; otherwise 4 digits for a broader chapter view.
    Returns a dict with keys: rawData, chapterNotes.
    """
    code = hs_code_4_or_more.strip()
    if not code.isdigit() or len(code) < 4 or len(code) > 6:
        return {"rawData": [], "chapterNotes": None}

    chapter_code = code[:2]
    tariffs_url = f"{_CLEAR_BASE}/tariffs/chapter_flatten_tariffs?code={code}"
    notes_url = f"{_CLEAR_BASE}/chapters/by_code?code={chapter_code}"

    async with httpx.AsyncClient(
        limits=httpx.Limits(max_connections=500, max_keepalive_connections=100),
        timeout=30.0
    ) as client:
        tariffs_task = client.get(tariffs_url)
        notes_task = client.get(notes_url)
        tariffs_res, notes_res = await asyncio.gather(tariffs_task, notes_task)

    raw = []
    notes = None
    try:
        if tariffs_res.status_code == 200:
            raw = tariffs_res.json()
    except (ValueError, httpx.HTTPError):
        raw = []
    try:
        if notes_res.status_code == 200:
            notes = notes_res.json()
    except (ValueError, httpx.HTTPError):
        notes = None
    print(f'Agent called tariff_chapter_lookup for {code}')

    # Sanitize rawData and chapterNotes (including any flatten_goods / notes fields)
    return {"rawData": _sanitize_payload(raw), "chapterNotes": _sanitize_payload(notes) if notes is not None else None}


async def tariff_search(hs_code_2_to_8: str) -> List[Dict[str, Any]]:
    """
    Detailed lookup for specific HS codes (2-8 digits). Returns list of matches.
    """
    code = hs_code_2_to_8.strip()
    if not code.isdigit() or not (2 <= len(code) <= 8):
        return []
    print(f'Agent called tariff_search for {code}')
    url = f"{_CLEAR_BASE}/tariffs/chapter_flatten_tariffs?code={code}"
    try:
        async with httpx.AsyncClient(
        limits=httpx.Limits(max_connections=500, max_keepalive_connections=100),
        timeout=30.0
    ) as client:
            res = await client.get(url)
            if res.status_code != 200:
                return []
            data = res.json()
            return data if isinstance(data, list) else []
    except (httpx.HTTPError, ValueError):
        return []


async def tariff_concession_lookup(bylaw_number: str) -> Dict[str, Any]:
    """
    Lookup schedule 4 concession information by by-law number.
    """
    num = bylaw_number.strip()
    if not num.isdigit():
        return {"results": [], "content": "invalid by-law number"}
    print(f'Agent called tariff_concession_lookup for {num}')
    url = (
        "https://api.clear.ai/api/v1/au_tariff/book_nodes/search"
        f"?term={num}&book_ref=AU_TARIFF_SCHED4_2022"
    )
    try:
        async with httpx.AsyncClient(
        limits=httpx.Limits(max_connections=500, max_keepalive_connections=100),
        timeout=30.0
    ) as client:
            res = await client.get(url)
            if res.status_code != 200:
                return {"results": []}
            return res.json()
    except (httpx.HTTPError, ValueError):
        return {"results": []}


# -----------------------------
# Grounded product brief via Google GenAI
# -----------------------------


async def search_product_info(brand: str, product_description: str) -> Dict[str, Any]:
    """
    Generate a grounded product brief using Google GenAI (Gemini Flash) with Google Search grounding.
    Returns a dict with key: content (string markdown).
    """
    brand = (brand or "").strip()
    product_description = (product_description or "").strip()
    if not product_description:
        return {"content": "Missing product_description"}

    print(f'Grounded product brief generation for {brand} {product_description[:80]}')

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return {"content": "GEMINI_API_KEY or GOOGLE_API_KEY not set in environment"}

    model_name = os.getenv("GENAI_GROUNDED_MODEL", "gemini-2.5-flash")

    prompt = (
        "You are compiling a concise, factual Product Brief for customs tariff classification.\n"
        "Use grounded web knowledge via Google Search to extract verifiable facts.\n"
        "Do not fabricate. If unknown, state 'Unknown'.\n\n"
        "Keep the product brief concise and factual. Do not include any opinions or subjective assessments.\n\n"
        f"Brand/Supplier: {brand or 'Unknown'}\n"
        f"Product description: {product_description}\n\n"
        "Produce markdown with the following sections: \n"
        "1) Official product name and model\n"
        "2) Materials and composition (percentages if available)\n"
        "3) Construction/manufacturing method (e.g., knitted vs woven; injection-molded; etc.)\n"
        "4) Primary function and end use\n"
        "5) Key physical specs (dimensions, weight, capacity, voltage/power, fiber content, etc.)\n"
        "6) Included accessories and packaging\n"
        "7) Certifications/standards/compliance marks (e.g., CE, FCC, safety ratings)\n"
        "8) HS-relevant classification cues (e.g., footwear upper material; textile type; toy vs model; electronics type)\n"
        "9) Notable exclusions/ambiguities\n"
        "10) Sources (list URLs used)."
    )

    def _run_genai_sync() -> tuple[str, Dict[str, int]]:
        client = genai.Client(api_key=api_key)
        cfg = GenerateContentConfig(
            temperature=0.1,
            top_p=0.95,
            max_output_tokens=2048,
            tools=[Tool(google_search=GoogleSearch())]
        )
        resp = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=cfg,
        )
        text = getattr(resp, "text", None)
        # Extract token usage when available
        usage_meta = getattr(resp, "usage_metadata", None)
        def _as_int(v: Any) -> int:
            return int(v) if isinstance(v, (int, float)) else 0
        if usage_meta is not None:
            prompt_tokens = _as_int(getattr(usage_meta, "prompt_token_count", 0)) + _as_int(getattr(usage_meta, "tool_use_prompt_token_count", 0))
            response_tokens = _as_int(getattr(usage_meta, "candidates_token_count", 0)) + _as_int(getattr(usage_meta, "thoughts_token_count", 0))
            total_tokens = _as_int(getattr(usage_meta, "total_token_count", 0))
            if total_tokens == 0:
                total_tokens = prompt_tokens + response_tokens
            usage = {
                "input_tokens": prompt_tokens,
                "output_tokens": response_tokens,
                "total_tokens": total_tokens,
            }
        else:
            usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        content_text = text if isinstance(text, str) and text.strip() else ""
        return content_text, usage

    try:
        text, usage = await asyncio.to_thread(_run_genai_sync)
    except (ValidationError, RuntimeError, ValueError, OSError) as exc:
        return {"content": f"Error generating grounded product brief: {type(exc).__name__}", "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}}

    return {"content": text or "", "usage": usage}
