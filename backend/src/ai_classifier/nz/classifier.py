from __future__ import annotations

import asyncio
import os
import time
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ValidationError

from ai_classifier.au.tools import (
	Item,
	ClassificationRequest,
	search_product_info,
)
from ai_classifier.nz.tools import nz_tariff_chapter_lookup, nz_tariff_search


class NZSuggestedCode(BaseModel):
	hs_code: str = Field(..., description="8-digit HS code without dots")
	stat_key: str = Field(..., description="3-char statistical key, format=2 digits + 1 uppercase letter, e.g. 00H")


class NZLLMClassificationOutput(BaseModel):
	best_suggested_hs_code: str
	best_suggested_stat_key: str  # NZ: 2 digits + 1 char, e.g. 00H
	suggested_codes: List[NZSuggestedCode]
	reasoning: str = Field(..., description="Detailed reasoning for the classification in normal English, No Markdown")


_SYSTEM_PROMPT_NZ = (
	"""
You are a New Zealand tariff classification expert.
Tools available:
- nz_tariff_chapter_lookup(hs_code: string[4–6 digits, NZ book]) → Use 6 digits when confident in the subheading; otherwise 4 digits for broader lookup.
- nz_tariff_search(hs_code: string[2-8 digits, NZ book])

You are provided with a 'Grounded Product Brief' (when present). Use it with the user's description.

Process:
1) Product Analysis: list key characteristics (material, form, function, use, construction).
2) Shortlist Tariff Chapters: up to three 6-digit candidates.
   - For each candidate, choose the lookup specificity: 6 digits when confident; otherwise 4 digits for broader context.
   - Run nz_tariff_chapter_lookup once per candidate with the chosen 4- or 6-digit code.
3) Look Up Codes: from chapter results, shortlist the most relevant 8-digit codes; use nz_tariff_search to validate specifics.
4) Output: choose 1 best (8-digit HS + 3-char statistical key, e.g. 00H) and two alternatives (same format).

Return JSON with fields:
{
  "best_suggested_hs_code": string(8 digits),
  "best_suggested_stat_key": string(3, format=2 digits + 1 uppercase letter),
  "suggested_codes": [
    {"hs_code": string(8 digits), "stat_key": string(3)},
    {"hs_code": string(8 digits), "stat_key": string(3)}
  ],
  "reasoning": string, (Normal English, no Markdown formatting)
}

Constraints:
- HS codes are 8 digits without dots.
- Statistical key is 3 chars: two digits followed by one uppercase letter (e.g., 00H).
- Do not invent unsupported fields.
"""
)


from pydantic_ai import Agent
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.gemini import ThinkingConfig
from pydantic_ai.providers.google import GoogleProvider


def _get_nz_agent():
	api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
	if not api_key:
		raise RuntimeError("GEMINI_API_KEY or GOOGLE_API_KEY environment variable is required")

	model = GoogleModel(
		"gemini-2.5-pro",
		provider=GoogleProvider(api_key=api_key),
	)

	return Agent(
		model=model,
		system_prompt=_SYSTEM_PROMPT_NZ,
		output_type=NZLLMClassificationOutput,
		tools=[nz_tariff_chapter_lookup, nz_tariff_search],
		retries=2,
		model_settings={"gemini_thinking_config": ThinkingConfig(thinking_budget=5000), "temperature": 0.05},
	)


router = APIRouter()


async def _run_nz_llm(agent: Agent, user_text: str):
	result = await agent.run(user_text)
	usage_info = result.usage()
	if usage_info:
		usage = {
			"input_tokens": getattr(usage_info, 'request_tokens', 0),
			"output_tokens": getattr(usage_info, 'response_tokens', 0),
			"total_tokens": getattr(usage_info, 'total_tokens', 0),
		}
	else:
		usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
	return result.output, usage


def _normalize_hs(code: str) -> str:
	digits = "".join(ch for ch in (code or "") if ch.isdigit())
	return (digits + "00000000")[:8] if digits else "00000000"


def _normalize_stat_key(code: str) -> str:
	code = (code or "").strip().upper()
	# Expect NN[A-Z]; fallback to 00H-like default if malformed
	if len(code) == 3 and code[:2].isdigit() and code[2].isalpha():
		return code
	digits = "".join(ch for ch in code if ch.isdigit())[:2]
	letter = next((ch for ch in code if ch.isalpha()), "H")
	return (digits + "00")[:2] + (letter or "H")[0]


_NZ_MAX_RETRIES = int(os.getenv("CLASSIFY_MAX_RETRIES", "4"))
_NZ_RETRY_BACKOFF_SECS = float(os.getenv("CLASSIFY_RETRY_BACKOFF", "0.5"))


class NZClassificationResult(BaseModel):
	id: str
	description: str
	supplier_name: str | None = None
	best_suggested_hs_code: str
	best_suggested_stat_key: str
	other_suggested_codes: List[NZSuggestedCode] = []
	total_time_seconds: float | None = None
	reasoning: str
	grounded_product_brief: str | None = None


class NZClassificationResponse(BaseModel):
	results: List[NZClassificationResult]


@router.post("/classify/nz", response_model=NZClassificationResponse)
async def classify_nz(request: ClassificationRequest) -> NZClassificationResponse:
	if not request.items:
		raise HTTPException(status_code=400, detail="No items provided")

	start_time = time.time()
	print(f'Starting NZ classification batch of {len(request.items)} items')

	agent = _get_nz_agent()

	async def _classify_one(it: Item):
		supplier_prefix = f"Supplier: {it.supplier_name}. " if getattr(it, "supplier_name", None) else ""
		grounded = await search_product_info(getattr(it, "supplier_name", None) or "", it.description)
		grounded_text = grounded.get("content") or ""
		grounded_usage = grounded.get("usage") or {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
		print(f'Grounded product brief for {it.description}: {grounded_usage} len={len(grounded_text)}')
  
		prompt = (
			"Classify the item for New Zealand using the Grounded Product Brief and description. Return JSON with: "
			"best_suggested_hs_code, best_suggested_stat_key (NNX), suggested_codes (2 items with hs_code, stat_key), reasoning.\n\n"
			"Grounded Product Brief (factual context):\n" + (grounded_text[:6000] if isinstance(grounded_text, str) else "") + "\n\n"
			f"{supplier_prefix}Description: {it.description}"
		)

		# Run the NZ agent with retries
		llm_out = None
		usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
		last_exc: Exception | None = None
		for attempt in range(1, _NZ_MAX_RETRIES + 1):
			try:
				llm_out, usage = await _run_nz_llm(agent, prompt)
				# Merge grounded brief token usage into the classification usage
				usage["input_tokens"] += int(grounded_usage.get("input_tokens", 0))
				usage["output_tokens"] += int(grounded_usage.get("output_tokens", 0))
				usage["total_tokens"] += int(grounded_usage.get("total_tokens", 0))
				break
			except (ValidationError, OSError, RuntimeError, ValueError, Exception) as exc:  # retry on model/validation/network errors
				last_exc = exc
				if attempt < _NZ_MAX_RETRIES:
					backoff = _NZ_RETRY_BACKOFF_SECS * (2 ** (attempt - 1))
					print(f"NZ LLM error on attempt {attempt}/{_NZ_MAX_RETRIES}: {exc}")
					print(f"Retrying in {backoff:.2f}s...")
					await asyncio.sleep(backoff)
				else:
					print(f"NZ LLM error after {_NZ_MAX_RETRIES} attempts: {exc}")

		# Normalize outputs
		if llm_out is None:
			best_hs = "00000000"
			best_stat = "00G"
			suggestions = [NZSuggestedCode(hs_code="00000000", stat_key="00G"), NZSuggestedCode(hs_code="00000000", stat_key="00G")]
			reasoning = "Classification failed"
		else:
			best_hs = _normalize_hs(getattr(llm_out, "best_suggested_hs_code", ""))
			best_stat = _normalize_stat_key(getattr(llm_out, "best_suggested_stat_key", ""))
			suggestions = list(getattr(llm_out, "suggested_codes", []) or [])[:2]
			if len(suggestions) < 2:
				while len(suggestions) < 2:
					suggestions.append(NZSuggestedCode(hs_code=best_hs, stat_key=best_stat))
			suggestions = [
				NZSuggestedCode(hs_code=_normalize_hs(sc.hs_code), stat_key=_normalize_stat_key(sc.stat_key))
				for sc in suggestions
			]
			reasoning = getattr(llm_out, "reasoning", "")

		total_time = time.time() - start_time

		result = NZClassificationResult(
			id=it.id,
			description=it.description,
			supplier_name=getattr(it, "supplier_name", None),
			best_suggested_hs_code=best_hs,
			best_suggested_stat_key=best_stat,
			other_suggested_codes=suggestions,
			total_time_seconds=total_time,
			reasoning=reasoning,
			grounded_product_brief=grounded_text or None,
		)

		print(f'NZ Classification completed for item {it.id} in {total_time:.2f} seconds')
		
		# Merge token usage from grounding
		result_usage = {
			"input_tokens": int(usage.get("input_tokens", 0)) + int(grounded_usage.get("input_tokens", 0)),
			"output_tokens": int(usage.get("output_tokens", 0)) + int(grounded_usage.get("output_tokens", 0)),
			"total_tokens": int(usage.get("total_tokens", 0)) + int(grounded_usage.get("total_tokens", 0)),
		}
		return result, result_usage

	# Concurrency
	tasks = [_classify_one(it) for it in request.items]
	results_with_usage = await asyncio.gather(*tasks)

	results_list: List[NZClassificationResult] = []
	total_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
	for res, usage in results_with_usage:
		results_list.append(res)
		total_usage["input_tokens"] += usage["input_tokens"]
		total_usage["output_tokens"] += usage["output_tokens"]
		total_usage["total_tokens"] += usage["total_tokens"]

	batch_time = time.time() - start_time
	print(f'NZ batch completed in {batch_time:.2f}s for {len(results_list)} items; tokens: {total_usage}')

	return NZClassificationResponse(results=results_list)
