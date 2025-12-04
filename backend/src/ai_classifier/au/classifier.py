from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ValidationError
from typing import Optional
import threading

from ai_classifier.au.tools import (
    Item,
    SuggestedCode,
    ClassificationResult,
    ClassificationRequest,
    ClassificationResponse,
    tariff_chapter_lookup,
    tariff_search,
    tariff_concession_lookup,
    search_product_info,
)


# -----------------------------
# Load Schedule 4 info once
# -----------------------------

_SCHEDULE4_TEXT: str = ""
_SCHEDULE4_PATH = Path(__file__).with_name("schedule4_info.txt")
try:
    _SCHEDULE4_TEXT = _SCHEDULE4_PATH.read_text(encoding="utf-8")
except OSError:
    _SCHEDULE4_TEXT = "Schedule 4 information unavailable."


# -----------------------------
# Pydantic models for LLM output
# -----------------------------


class LLMClassificationOutput(BaseModel):
    """Structured output returned by the LLM for a single item."""

    best_suggested_hs_code: str
    best_suggested_stat_code: str
    best_suggested_tco_link: Optional[str] = None
    suggested_codes: List[SuggestedCode]
    reasoning: str = Field(..., description="Detailed reasoning for the classification in normal English, No Markdown")


# -----------------------------
# LLM agent (PydanticAI + Gemini)
# -----------------------------


_SYSTEM_PROMPT = (
    """
You are an Australian tariff classification expert. You have access to tools:
- tariff_chapter_lookup(hs_code: string[4–6 digits]) → returns chapter_flatten_tariffs data and chapter notes. Use 6 digits when confident; otherwise 4 digits.
- tariff_search(hs_code: string[2-8 digits]) → verifies and fetches details for a specific 2-8 digit HS code
- tariff_concession_lookup(bylaw_number: numeric string) → returns Schedule 4 concession details by by-law

Follow this STRICT classification process without asking follow-up questions:
Use the provided 'Grounded Product Brief' (if present) as factual context in addition to the user's description.
1) Product Analysis
   - Extract and list key characteristics from the user's description: material, form, function, use, species/type, etc.
   - Keep it brief but complete.

2) Shortlist Tariff Chapters
   - Identify up to three 6-digit candidate headings (or fewer if highly confident).
   - For each candidate, choose the appropriate prefix for lookup: use 6 digits when confident in the subheading; otherwise use 4 digits for a broader chapter view.
   - Run tariff_chapter_lookup once per candidate with the chosen 4- or 6-digit code. Do not call both for the same candidate unless revising based on new evidence.

3) Look Up Tariff Codes
   - From each chapter lookup's rawData + chapterNotes, shortlist the most relevant 8-digit codes.
   - Use tariff_search only if you need to validate 6-8 digit codes explicitly.
   - When chapter results contain a field indicating tariff concession orders (e.g. "tariff_orders": true), set the TCO link using this schema:
     https://www.abf.gov.au/tariff-classification-subsite/Pages/TariffConcessionOrders.aspx?tcn={8-digit-number-without-dots}
     - Example: 94012000 → https://www.abf.gov.au/tariff-classification-subsite/Pages/TariffConcessionOrders.aspx?tcn=94012000

4) Check Schedule 4 Concessions (if applicable)
   - Use your embedded reference below to determine if a Schedule 4 concession likely applies.
   - Only call tariff_concession_lookup when you can infer a specific by-law number from the reference.
   - Schedule 4 is separate from the base tariff classification; do not mix concession conditions with HS/stat code selection.

5) Recommended Classifications (structured output)
   - Choose exactly 1 best suggestion (8-digit HS + 2-digit stat code), and two additional alternatives (total 3 codes).
   - Include TCO links if and only if the chapter/search data indicates a TCO is available; otherwise use null.
   - JSON schema you must satisfy:
     {{
       "best_suggested_hs_code": string(8 digits),
       "best_suggested_stat_code": string(2 digits),
       "best_suggested_tco_link": string | null,
       "suggested_codes": [
         {{"hs_code": string(8 digits), "stat_code": string(2 digits), "tco_link": string | null}},
         {{"hs_code": string(8 digits), "stat_code": string(2 digits), "tco_link": string | null}}
       ],
       "reasoning": string, (Normal English, no Markdown formatting)
     }}

Important constraints:
- HS codes must be 8 digits without dots. Statistical codes must be 2 digits.
- Use the lookup tool results and chapter notes to justify your selection.
- Do not ask questions or await confirmation.
- Do not include extra keys not in the schema.
"""
    + "\n\nSchedule 4 reference:\n"
    + _SCHEDULE4_TEXT
)


_agent_lock = threading.Lock()
_classifier_agent = None


def _get_or_create_agent():
    """Create or return a cached PydanticAI Agent for Gemini 2.5 Pro."""
    global _classifier_agent
    if _classifier_agent is not None:
        return _classifier_agent

    with _agent_lock:
        if _classifier_agent is not None:
            return _classifier_agent

        from pydantic_ai import Agent
        from pydantic_ai.models.google import GoogleModel
        from pydantic_ai.models.gemini import ThinkingConfig
        from pydantic_ai.providers.google import GoogleProvider

        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY or GOOGLE_API_KEY environment variable is required")

        model = GoogleModel(
            "gemini-2.5-pro",
            provider=GoogleProvider(api_key=api_key),
        )

        _classifier_agent = Agent(
            model=model,
            system_prompt=_SYSTEM_PROMPT,
            output_type=LLMClassificationOutput,
            tools=[tariff_chapter_lookup, tariff_search, tariff_concession_lookup],
            retries=2,
            model_settings={"gemini_thinking_config": ThinkingConfig(thinking_budget=5000), "temperature": 0.05},
        )
        return _classifier_agent


async def _run_llm_with_pydantic_ai(user_text: str) -> tuple[LLMClassificationOutput, dict]:
    agent = _get_or_create_agent()
    result = await agent.run(user_text)
    usage_info = result.usage()

    # PydanticAI Usage dataclass has request_tokens, response_tokens, total_tokens
    if usage_info:
        return result.output, {
            "input_tokens": getattr(usage_info, 'request_tokens', 0),
            "output_tokens": getattr(usage_info, 'response_tokens', 0),
            "total_tokens": getattr(usage_info, 'total_tokens', 0),
        }
    else:
        return result.output, {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }

_CLASSIFY_SEMAPHORE = asyncio.Semaphore(int(os.getenv("CLASSIFY_MAX_CONCURRENCY", "100")))
_MAX_RETRIES = int(os.getenv("CLASSIFY_MAX_RETRIES", "4"))
_RETRY_BACKOFF_SECS = float(os.getenv("CLASSIFY_RETRY_BACKOFF", "0.5"))

async def _classify_single_item(item: Item) -> tuple[ClassificationResult, dict]:
    """Classify a single item using the LLM agent with structured output."""
    start_time = time.time()

    # Merge supplier_name into the description context for better classification when provided
    supplier_prefix = f"Supplier: {item.supplier_name}. " if getattr(item, "supplier_name", None) else ""
    
    grounded_product_brief = await search_product_info(getattr(item, "supplier_name", None) or "", item.description)
    grounded_product_brief_text = grounded_product_brief.get("content") or ""
    grounded_usage = grounded_product_brief.get("usage") or {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    print(f'Grounded product brief for {item.description}: {grounded_usage} len={len(grounded_product_brief_text)}')
    
    prompt = (
        "Classify the item using the provided Grounded Product Brief and description. Return a JSON object with keys: "
        "best_suggested_hs_code, best_suggested_stat_code, suggested_codes (array of 2 with hs_code, stat_code), reasoning.\n\n"
        "Grounded Product Brief (factual context):\n" + (grounded_product_brief_text[:6000] if isinstance(grounded_product_brief_text, str) else "") + "\n\n"
        f"{supplier_prefix}Description: {item.description}"
    )

    print(f'Classifying item: {item.description} (Supplier: {item.supplier_name})')
    async with _CLASSIFY_SEMAPHORE:
        llm_out = None
        usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        last_exc: Optional[BaseException] = None
        def _exception_brief(exc: BaseException) -> str:
            try:
                parts: list[str] = [f"type={type(exc).__name__}"]
                msg = str(exc)
                if msg:
                    parts.append(f"msg={msg}")
                resp = getattr(exc, "response", None)
                status = getattr(resp, "status_code", None)
                if status:
                    parts.append(f"status={status}")
                code = getattr(exc, "code", None) or getattr(exc, "status", None)
                if code:
                    parts.append(f"code={code}")
                return "; ".join(parts)[:500]
            except Exception:
                return type(exc).__name__
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                llm_out, usage = await _run_llm_with_pydantic_ai(prompt)
                # Merge grounded brief token usage into the classification usage
                usage["input_tokens"] += int(grounded_usage.get("input_tokens", 0))
                usage["output_tokens"] += int(grounded_usage.get("output_tokens", 0))
                usage["total_tokens"] += int(grounded_usage.get("total_tokens", 0))
                break
            except (ValidationError, OSError, RuntimeError, ValueError, Exception) as exc:  # retry on model/validation/network errors
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    backoff = _RETRY_BACKOFF_SECS * (2 ** (attempt - 1))
                    print(f"LLM error on attempt {attempt}/{_MAX_RETRIES}: {_exception_brief(exc)}")
                    print(f"Retrying in {backoff:.2f}s...")
                    await asyncio.sleep(backoff)
                    continue
                else:
                    # Will fall back to default values below
                    pass

    total_time = time.time() - start_time

    # If all attempts failed, build a safe default structured output
    if llm_out is None:
        llm_out = LLMClassificationOutput(
            best_suggested_hs_code="00000000",
            best_suggested_stat_code="00",
            suggested_codes=[
                SuggestedCode(hs_code="00000000", stat_code="00"),
                SuggestedCode(hs_code="00000000", stat_code="00"),
            ],
            reasoning=f"Classification failed after {_MAX_RETRIES} attempts: {type(last_exc).__name__ if last_exc else 'UnknownError'}",
        )

    # Normalize the suggested list to exactly 2 items
    suggestions = list(llm_out.suggested_codes or [])
    if len(suggestions) < 2:
        # Pad with duplicates of best or zeros
        while len(suggestions) < 2:
            suggestions.append(
                SuggestedCode(
                    hs_code=(llm_out.best_suggested_hs_code or "00000000")[:8].ljust(8, "0"),
                    stat_code=(llm_out.best_suggested_stat_code or "00")[:2].ljust(2, "0"),
                )
            )
    else:
        suggestions = suggestions[:2]

    # Normalize codes
    def _digits_only(s: str) -> str:
        return "".join(ch for ch in s if ch.isdigit())

    def _normalize_hs(code: str) -> str:
        d = _digits_only(code)
        return (d + "00000000")[:8] if d else "00000000"

    def _normalize_stat(code: str) -> str:
        d = _digits_only(code)
        return (d + "00")[:2] if d else "00"

    normalized_best_hs = _normalize_hs(llm_out.best_suggested_hs_code or "")
    normalized_best_stat = _normalize_stat(llm_out.best_suggested_stat_code or "")
    normalized_suggestions = [
        SuggestedCode(hs_code=_normalize_hs(sc.hs_code), stat_code=_normalize_stat(sc.stat_code))
        for sc in suggestions
    ]

    print(f'Classification completed for item {item.id} in {total_time:.2f} seconds')

    result = ClassificationResult(
        id=item.id,
        description=item.description,
        supplier_name=getattr(item, "supplier_name", None),
        best_suggested_hs_code=normalized_best_hs,
        best_suggested_stat_code=normalized_best_stat,
        best_suggested_tco_link=getattr(llm_out, "best_suggested_tco_link", None),
        other_suggested_codes=normalized_suggestions,
        total_time_seconds=total_time,
        reasoning=llm_out.reasoning or "",
        grounded_product_brief=grounded_product_brief_text or None,
    )

    return result, usage


async def _classify_items_concurrently(items: List[Item]) -> tuple[List[ClassificationResult], dict]:
    tasks = [_classify_single_item(it) for it in items]
    results_with_usage = await asyncio.gather(*tasks)

    # Separate results and usage
    results = []
    total_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    for result, usage in results_with_usage:
        results.append(result)
        total_usage["input_tokens"] += usage["input_tokens"]
        total_usage["output_tokens"] += usage["output_tokens"]
        total_usage["total_tokens"] += usage["total_tokens"]

    return results, total_usage


router = APIRouter()


@router.post("/classify/au", response_model=ClassificationResponse)
async def classify_au(request: ClassificationRequest) -> ClassificationResponse:
    if not request.items:
        raise HTTPException(status_code=400, detail="No items provided")

    start_time = time.time()
    print(f'Starting classification batch of {len(request.items)} items')

    results, total_usage = await _classify_items_concurrently(request.items)

    total_batch_time = time.time() - start_time
    print(f'Batch classification completed in {total_batch_time:.2f} seconds for {len(request.items)} items')
    print(f'Total token usage - Input: {total_usage["input_tokens"]:,}, Output: {total_usage["output_tokens"]:,}, Total: {total_usage["total_tokens"]:,}')

    return ClassificationResponse(results=results)
