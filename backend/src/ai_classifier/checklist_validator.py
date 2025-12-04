"""
Checklist validator using PydanticAI and Gemini 2.5 Pro for validating customs audit checklists.

This module handles:
- Running header-level validations (with PDF documents)
- Running valuation validations (with PDF documents)
- Direct document analysis by LLM instead of using extracted data
"""
from __future__ import annotations

import os
import asyncio
import aiohttp
from pathlib import Path
from typing import Dict, Any, List
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.gemini import ThinkingConfig
from pydantic_ai.providers.google import GoogleProvider

from pydantic import BaseModel, Field

from .checklist_models import (
    Region,
    ChecklistItemConfig,
    ChecklistValidationOutput,
    TariffLineItem,
    TariffLineItemsOutput,
    TariffLineValidation,
    get_header_checks,
    get_valuation_checks,
)


class BatchValidationOutput(BaseModel):
    """Output model for batch validation of multiple checks in one LLM call."""
    validations: List[ChecklistValidationOutput]


class ConcessionComparisonOutput(BaseModel):
    """Output model for concession description comparison."""
    status: str = Field(..., description="PASS, FAIL, or QUESTIONABLE")
    assessment: str = Field(..., description="Brief explanation of the decision (2-3 sentences)")


# Helper function for tariff concession lookup
async def lookup_tariff_concession(tariff_code: str, claimed_concession: str | None = None) -> Dict[str, Any]:
    """
    Look up tariff concession information from Clear.AI API using tariff code.
    
    Args:
        tariff_code: The 8-digit tariff code (e.g., "49119990")
        claimed_concession: Optional claimed TC/bylaw number to filter for (e.g., "TC 0614117")
        
    Returns:
        Dictionary with concession information including results and any errors
    """
    if not tariff_code or tariff_code.strip() == "":
        return {"error": "No tariff code provided", "results": []}
    
    # Clean the tariff code (extract just digits)
    clean_tariff = ''.join(filter(str.isdigit, tariff_code))
    
    if not clean_tariff:
        return {"error": "Invalid tariff code format", "results": []}
    
    # Debug: Log what we're searching for
    print(f"         API Lookup: Searching for TCO using tariff code '{clean_tariff}' (claimed: '{claimed_concession}')", flush=True)
    
    # Use the tariff concessions search endpoint
    api_url = f"https://api.clear.ai/api/v1/au_tariff/tcos/search/?q={clean_tariff}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    return {"error": f"API request failed with status {response.status}", "results": []}
                
                data = await response.json()
                
                # Debug: Log response structure
                print(f"         API Response type: {type(data).__name__}, length: {len(data) if isinstance(data, (list, dict)) else 'N/A'}", flush=True)
                
                # Handle both dict and list responses
                if isinstance(data, list):
                    # API returns list directly
                    results = data
                elif isinstance(data, dict):
                    # API returns dict with results key
                    results = data.get("results", [])
                else:
                    return {"error": f"Unexpected API response type: {type(data)}", "results": []}
                
                # If a specific concession is claimed, filter results to find it
                filtered_results = results
                if claimed_concession:
                    # Extract TC/instrument number from claimed concession
                    claimed_number = ''.join(filter(str.isdigit, claimed_concession))
                    
                    # Filter results that match the claimed concession
                    filtered_results = []
                    for result in results:
                        if not isinstance(result, dict):
                            continue
                            
                        instrument_no = result.get("instrument_no", "")
                        instrument_type = result.get("instrument_type", "")
                        
                        # Match if the instrument number matches
                        if claimed_number and instrument_no and claimed_number == instrument_no:
                            filtered_results.append(result)
                        # Or if the full instrument string matches (e.g., "TC 0614117")
                        elif f"{instrument_type} {instrument_no}".upper() == claimed_concession.upper():
                            filtered_results.append(result)
                
                return {
                    "tariff_code": clean_tariff,
                    "claimed_concession": claimed_concession,
                    "results": filtered_results if claimed_concession else results,
                    "all_results": results,  # Keep all results for reference
                    "found": len(filtered_results if claimed_concession else results) > 0,
                    "api_url": api_url
                }
                
    except asyncio.TimeoutError:
        return {"error": "API request timed out", "results": []}
    except Exception as e:
        import traceback
        return {"error": f"API error: {str(e)} | Traceback: {traceback.format_exc()}", "results": []}


# Cache for concession comparison agent
_concession_agent: Agent | None = None


def _get_concession_agent() -> Agent:
    """Instantiate (or return cached) Gemini agent for concession comparison."""
    global _concession_agent
    
    if _concession_agent is not None:
        return _concession_agent
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY environment variable is required for Gemini agent")

    model = GoogleModel(
        "gemini-2.5-pro",
        provider=GoogleProvider(api_key=api_key),
    )

    system_prompt = """
You are a customs tariff concession expert for Australian imports.

Your task is to determine if an item qualifies for a claimed tariff concession by comparing descriptions.

Rules:
- PASS: The item clearly matches the concession description (same product type, characteristics, use case)
- FAIL: The item clearly does NOT match the concession description (different product entirely)
- QUESTIONABLE: Uncertain match - similar but unclear, or technical specifications needed

Be strict but reasonable. The item must genuinely qualify for the concession.
"""

    _concession_agent = Agent(
        model=model,
        instructions=system_prompt,
        output_type=ConcessionComparisonOutput,
        retries=1,
        model_settings={"temperature": 0.1},
    )
    
    return _concession_agent


# Helper function to compare item description with concession descriptions using LLM
async def _compare_concession_descriptions(
    item_description: str,
    concession_results: List[Dict[str, Any]],
    bylaw_number: str
) -> Dict[str, str]:
    """
    Use LLM to compare the line item description with Schedule 4 concession descriptions.
    
    Args:
        item_description: The product description from the invoice
        concession_results: List of concession records from the API
        bylaw_number: The claimed by-law/TCO number
        
    Returns:
        Dictionary with "status" (PASS/FAIL/QUESTIONABLE) and "assessment" (explanation)
    """
    if not concession_results:
        return {
            "status": "FAIL",
            "assessment": f"Concession {bylaw_number} found but no description data available"
        }
    
    # Get the concession comparison agent
    agent = _get_concession_agent()
    
    # Build comparison prompt with concession details
    concession_descriptions = []
    for idx, result in enumerate(concession_results, 1):
        heading = result.get("heading", "N/A")
        description = result.get("description", "").replace("<br>", "\n")
        instrument_no = result.get("instrument_no", "N/A")
        instrument_type = result.get("instrument_type", "N/A")
        
        concession_descriptions.append(
            f"Result {idx}:\n"
            f"  Heading: {heading}\n"
            f"  Instrument: {instrument_type} {instrument_no}\n"
            f"  Description: {description}\n"
        )
    
    prompt = f"""
Compare the item description with the Schedule 4 concession description to determine if the concession applies.

**Item Description (from invoice)**:
{item_description}

**Claimed Concession**: {bylaw_number}

**Concession Descriptions (from Schedule 4 database)**:
{''.join(concession_descriptions)}

**Your Task**:
Determine if the item matches the concession criteria and return:
- status: "PASS", "FAIL", or "QUESTIONABLE"
- assessment: Brief explanation (2-3 sentences) with specific reasons
"""
    
    try:
        # Run with structured output
        result = await agent.run(prompt)
        comparison: ConcessionComparisonOutput = result.output
        
        return {
            "status": comparison.status.upper(),
            "assessment": f"Concession {bylaw_number}: {comparison.assessment}"
        }
            
    except Exception as e:
        return {
            "status": "QUESTIONABLE",
            "assessment": f"Concession {bylaw_number} comparison error: {str(e)}"
        }


# System prompt for batch checklist validation
_SYSTEM_PROMPT = """
You are an expert customs compliance auditor specializing in DHL Express shipments for Australia and New Zealand.

Your task is to validate MULTIPLE checklist items in a single pass by directly analyzing the provided PDF documents (entry prints, commercial invoices, and air waybills).

**Your Responsibilities**:
1. Read ALL the checklist items provided in the prompt
2. Analyze the PDF documents to locate and extract all relevant fields for ALL checks
3. For EACH checklist item:
   - Compare the values between source and target documents according to its checking logic
   - Determine if the check passes, fails, or is questionable
   - Provide detailed reasoning with specific values found in the documents
4. Return validation results for ALL checklist items

**Validation Rules**:
- **PASS**: Clear match or acceptable variation according to pass conditions
- **FAIL**: Clear mismatch or violation of pass conditions
- **QUESTIONABLE**: Ambiguous situation requiring human review
- **N/A**: Check is not applicable (e.g., no FTA declared, field not present in documents)

**Special Considerations**:
- If both source and target values are not found/missing in the documents, use N/A for optional fields (like FTA, preference scheme) or PASS for mandatory fields
- For company names: Allow fuzzy matching (abbreviations, minor spelling differences, corporate codes)
- For numeric values: Allow reasonable rounding differences (e.g., 100.00 vs 100)
- For currencies and codes: Allow abbreviations (e.g., "USD" vs "US Dollar", "DDP" vs "Delivered Duty Paid")
- For incoterms: Consider that DDP requires special handling for importer identity
- For dates: Allow different formats (e.g., "2025-01-15" vs "15/01/2025")
- For FTA and preference schemes: Use N/A when no declaration is present or field is not applicable

**Critical**:
- You MUST return a validation result for EVERY checklist item provided
- Always extract and show the specific values you found in each document
- Reference the exact locations where you found the values (e.g., "Found in Entry Print header section")
- Cite the actual checking logic and pass conditions in your reasoning
- Be conservative: When in doubt between PASS and QUESTIONABLE, choose QUESTIONABLE
- Be thorough: Analyze all relevant sections of the documents

Return your validations as a JSON array with one entry per checklist item in the exact format specified.
"""


# Cache agent instances
_validator_agent: Agent | None = None
_tariff_extractor_agent: Agent | None = None


# System prompt for tariff line extraction
_TARIFF_EXTRACTION_PROMPT = """
You are an expert customs data extraction specialist for DHL Express shipments.

Your task is to extract and match line items from the Commercial Invoice and Entry Print documents.

**Your Responsibilities**:
1. Analyze the Commercial Invoice to extract ALL line items with:
   - Product descriptions
   - Quantities and units (invoice_quantity)
   - Unit prices
   - Total values (line totals)

2. Analyze the Entry Print to extract ALL line items with:
   - Tariff classification codes (8 digits)
   - Statistical codes (2 digits)
   - Complete 10-digit codes (tariff + stat)
   - Quantities and units (entry_print_quantity) - may be merged or different from invoice
   - Tariff concession or by-law number (e.g., "1700581", "Schedule 4", "TCO XXXXX") - set to null if not claimed
   - GST exemption indicator (true/false) - check if GST exemption is claimed for this line

3. Match line items between the two documents based on:
   - Line item order and position
   - Product descriptions
   - Quantities and values
   - Note: Entry print may merge multiple invoice lines into one line

4. Return a structured list of ALL line items with:
   - Sequential line numbers (starting from 1)
   - Description from invoice
   - Tariff code (8 digits) from entry print
   - Statistical code (2 digits) from entry print
   - Full 10-digit code
   - invoice_quantity: Quantity and unit from COMMERCIAL INVOICE
   - entry_print_quantity: Quantity and unit from ENTRY PRINT (may differ or be merged)
   - Unit price from invoice
   - Total value from invoice
   - concession_bylaw: Tariff concession or by-law number from entry print (null if not claimed)
   - gst_exemption: Boolean indicating if GST exemption is claimed

**Important Guidelines**:
- Extract ALL line items from both documents
- Match items carefully - the order may not be exactly the same
- If a tariff code is 10 digits, split it into 8-digit tariff + 2-digit stat code
- Keep descriptions exactly as they appear in the invoice
- Include currency symbols in prices (e.g., "USD 25.00")
- Format quantities with units (e.g., "5 PCS", "10.5 KG")
- Extract BOTH invoice_quantity AND entry_print_quantity separately
- Look for concession/bylaw numbers in entry print (column headers like "TCO", "Concession", "By-law")
- Check for GST exemption indicators in entry print
- If a line item appears in one document but not the other, include it with "NOT FOUND" for missing data

**Critical**:
- You MUST return ALL line items found in the documents
- Line numbers should be sequential starting from 1
- Match items based on order, description similarity, and values
- Be thorough and precise in your extraction
- Extract concession_bylaw and gst_exemption information carefully from entry print
"""


# System prompt for NZ tariff line extraction
_TARIFF_EXTRACTION_PROMPT_NZ = """
You are an expert customs data extraction specialist for DHL Express shipments in New Zealand.

Your task is to extract and match line items from the Commercial Invoice and Entry Print documents.

**Your Responsibilities**:
1. Analyze the Commercial Invoice to extract ALL line items with:
   - Product descriptions
   - Quantities and units (invoice_quantity)
   - Unit prices
   - Total values (line totals)

2. Analyze the Entry Print to extract ALL line items with:
   - Tariff classification codes (8 digits)
   - Statistical keys (3 characters: 2 digits + 1 letter, e.g., "00H", "15A")
   - Complete codes (tariff + stat key = 11 characters total)
   - Quantities and units (entry_print_quantity) - may be merged or different from invoice
   - GST exemption indicator (true/false) - check if GST exemption is claimed for this line

3. Match line items between the two documents based on:
   - Line item order and position
   - Product descriptions
   - Quantities and values
   - Note: Entry print may merge multiple invoice lines into one line

4. Return a structured list of ALL line items with:
   - Sequential line numbers (starting from 1)
   - Description from invoice
   - Tariff code (8 digits) from entry print
   - Statistical key (3 characters: NNX format) from entry print
   - Full code (11 characters: 8-digit tariff + 3-char stat key)
   - invoice_quantity: Quantity and unit from COMMERCIAL INVOICE
   - entry_print_quantity: Quantity and unit from ENTRY PRINT (may differ or be merged)
   - Unit price from invoice
   - Total value from invoice
   - gst_exemption: Boolean indicating if GST exemption is claimed

**Important Guidelines**:
- Extract ALL line items from both documents
- Match items carefully - the order may not be exactly the same
- Statistical key format: 2 digits + 1 uppercase letter (e.g., "00H", "15A", "99Z")
- Keep descriptions exactly as they appear in the invoice
- Include currency symbols in prices (e.g., "NZD 25.00", "USD 50.00")
- Format quantities with units (e.g., "5 PCS", "10.5 KG")
- Extract BOTH invoice_quantity AND entry_print_quantity separately
- Check for GST exemption indicators in entry print
- Set concession_bylaw to null (NZ does not use the same system as AU)
- If a line item appears in one document but not the other, include it with "NOT FOUND" for missing data

**Critical**:
- You MUST return ALL line items found in the documents
- Line numbers should be sequential starting from 1
- Match items based on order, description similarity, and values
- Be thorough and precise in your extraction
- Extract gst_exemption information carefully from entry print
"""


def _get_tariff_extractor_agent(region: Region = "AU") -> Agent:
    """Instantiate Gemini 2.5 Pro agent for tariff line extraction with region-specific prompt."""
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY environment variable is required for Gemini agent")

    model = GoogleModel(
        "gemini-2.5-pro",
        provider=GoogleProvider(api_key=api_key),
    )
    
    # Use region-specific prompt
    instructions = _TARIFF_EXTRACTION_PROMPT_NZ if region == "NZ" else _TARIFF_EXTRACTION_PROMPT

    return Agent(
        model=model,
        instructions=instructions,
        output_type=TariffLineItemsOutput,
        retries=2,
        model_settings={"gemini_thinking_config": ThinkingConfig(thinking_budget=5000), "temperature": 0.1},
    )


def _get_validator_agent() -> Agent:
    """Instantiate (or return cached) Gemini 2.5 Pro agent for checklist validation."""
    global _validator_agent
    
    if _validator_agent is not None:
        return _validator_agent
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY environment variable is required for Gemini agent")

    model = GoogleModel(
        "gemini-2.5-pro",
        provider=GoogleProvider(api_key=api_key),
    )

    _validator_agent = Agent(
        model=model,
        instructions=_SYSTEM_PROMPT,
        output_type=BatchValidationOutput,  # Returns multiple validations at once
        retries=2,  # Retry up to 2 times on failure
        model_settings={"gemini_thinking_config": ThinkingConfig(thinking_budget=5000), "temperature": 0.05}, # Low temperature for consistent validation and thinking budget
    )
    
    return _validator_agent


def build_batch_validation_prompt(checks: List[ChecklistItemConfig]) -> str:
    """
    Build a validation prompt for multiple checklist items to be validated in ONE LLM call.
    
    Args:
        checks: List of checklist item configurations to validate together
        
    Returns:
        Formatted prompt string for the LLM
    """
    prompt = f"""
You are analyzing PDF documents to validate {len(checks)} checklist items in a SINGLE pass.

**Documents Provided Below**:
The following labeled PDF documents will be attached after this prompt:
- **ENTRY PRINT DOCUMENT**: The customs entry print/declaration
- **COMMERCIAL INVOICE DOCUMENT**: The commercial invoice
- **AIR WAYBILL DOCUMENT**: The air waybill (if referenced in checks)

Each document will be clearly labeled before its content so you can easily identify which is which.

---

**CHECKLIST ITEMS TO VALIDATE** ({len(checks)} total):

"""
    
    for idx, check in enumerate(checks, 1):
        # Get source and target field information
        source_fields = check.compare_fields.source_field
        if isinstance(source_fields, str):
            source_fields = [source_fields]
        
        target_fields = check.compare_fields.target_field
        if isinstance(target_fields, str):
            target_fields = [target_fields]
        
        prompt += f"""
### [{idx}/{len(checks)}] Check ID: {check.id}
**Auditing Criteria**: {check.auditing_criteria}

**Description**: {check.description}

**Checking Logic**: {check.checking_logic}

**Pass Conditions**: {check.pass_conditions}

**Compare**:
- Source: {check.compare_fields.source_doc} → {', '.join(source_fields)}
- Target: {check.compare_fields.target_doc} → {', '.join(target_fields)}

---
"""
    
    prompt += f"""

**Your Task**:
1. Review the labeled PDF documents provided below (ENTRY PRINT DOCUMENT, COMMERCIAL INVOICE DOCUMENT, AIR WAYBILL DOCUMENT)
2. For EACH of the {len(checks)} checklist items above:
   - Locate and extract the specified fields from the source and target documents
   - The document labels will help you identify which PDF corresponds to each document type
   - Compare the values according to the checking logic
   - Determine PASS/FAIL/QUESTIONABLE based on pass conditions
   - Document what you found with specific values and locations in the labeled documents

**Important**:
- Return a validation result for ALL {len(checks)} checklist items
- Show exact values found in each labeled document
- Reference the document labels (e.g., "Found in ENTRY PRINT DOCUMENT") and specific sections
- If a value is not found, note it as "NOT FOUND"
- Follow each item's pass conditions strictly

Return a JSON object with a "validations" array containing {len(checks)} ChecklistValidationOutput objects (one for each checklist item above).
"""
    
    return prompt


async def validate_batch_checks(
    checks: List[ChecklistItemConfig],
    documents: Dict[str, bytes],
    category: str = "checks"
) -> List[ChecklistValidationOutput]:
    """
    Validate MULTIPLE checklist items in ONE LLM call by analyzing PDF documents directly.
    
    Args:
        checks: List of checklist item configurations to validate together
        documents: Dictionary of document types to PDF binary content
                  Format: {"entry_print": bytes, "commercial_invoice": bytes, "air_waybill": bytes}
        category: Category name for logging (e.g., "header", "valuation")
        
    Returns:
        List of ChecklistValidationOutput (one for each check)
        
    Raises:
        Exception: If validation fails after retries
    """
    agent = _get_validator_agent()
    
    print(f"   Validating {len(checks)} {category} checks in ONE LLM call with PDFs...", flush=True)
    
    # Check if we have the required documents
    required_docs = set()
    for check in checks:
        required_docs.add(check.compare_fields.source_doc)
        required_docs.add(check.compare_fields.target_doc)
    
    missing_docs = [doc for doc in required_docs if doc not in documents or not documents[doc]]
    if missing_docs:
        print(f"❌ Missing required documents: {missing_docs}", flush=True)
        # Return FAIL for all checks
        return [
            ChecklistValidationOutput(
                check_id=check.id,
                auditing_criteria=check.auditing_criteria,
                status="FAIL",
                assessment=f"Required documents not available: {missing_docs}",
                source_document=check.compare_fields.source_doc,
                target_document=check.compare_fields.target_doc,
                source_value="DOCUMENT NOT FOUND",
                target_value="DOCUMENT NOT FOUND"
            )
            for check in checks
        ]
    
    # Build message parts list with text prompt and PDF documents
    message_parts = []
    
    # Add text prompt with ALL checks
    prompt = build_batch_validation_prompt(checks)
    message_parts.append(prompt)
    
    # Add ALL PDF documents with clear labels
    doc_labels = {
        "entry_print": "ENTRY PRINT DOCUMENT",
        "commercial_invoice": "COMMERCIAL INVOICE DOCUMENT",
        "air_waybill": "AIR WAYBILL DOCUMENT"
    }
    
    for doc_type in ["entry_print", "commercial_invoice", "air_waybill"]:
        if doc_type in documents and documents[doc_type]:
            # Add label before the PDF
            message_parts.append(f"\n**{doc_labels[doc_type]}**:\n")
            
            # Add the PDF binary content
            message_parts.append(BinaryContent(
                data=documents[doc_type],
                media_type="application/pdf"
            ))
            print(f"     Added {doc_type} PDF ({len(documents[doc_type]):,} bytes)", flush=True)
    
    # Run batch validation with PDFs - ONE LLM CALL for all checks
    try:
        print(f"   🔄 Calling Gemini with {len(checks)} checks and {len([m for m in message_parts if isinstance(m, BinaryContent)])} PDFs...", flush=True)
        result = await agent.run(message_parts)
        batch_output: BatchValidationOutput = result.output
        
        if len(batch_output.validations) != len(checks):
            print(f"⚠️  Expected {len(checks)} validations, got {len(batch_output.validations)}", flush=True)
        
        print(f"   ✅ Received {len(batch_output.validations)} validation results", flush=True)
        return batch_output.validations
        
    except Exception as e:
        print(f"❌ Failed to validate batch of {len(checks)} checks: {e}", flush=True)
        # Return FAIL for all checks
        return [
            ChecklistValidationOutput(
                check_id=check.id,
                auditing_criteria=check.auditing_criteria,
                status="FAIL",
                assessment=f"Batch validation error: {str(e)}",
                source_document=check.compare_fields.source_doc,
                target_document=check.compare_fields.target_doc,
                source_value="ERROR",
                target_value="ERROR"
            )
            for check in checks
        ]


async def validate_header_checks(
    region: Region,
    documents: Dict[str, bytes]
) -> List[ChecklistValidationOutput]:
    """
    Validate all header-level checks for a region using PDF documents.
    
    This makes ONE LLM call for ALL header checks together.
    
    Args:
        region: Region code (AU or NZ)
        documents: Dictionary of document types to PDF binary content
                  Format: {"entry_print": bytes, "commercial_invoice": bytes, "air_waybill": bytes}
        
    Returns:
        List of validation results for header checks
    """
    header_checks = get_header_checks(region)
    
    print(f"=" * 80, flush=True)
    print(f"🔍 HEADER VALIDATION - {region} Region", flush=True)
    print(f"=" * 80, flush=True)
    print(f"Running {len(header_checks)} header-level checks in ONE LLM call with PDF documents", flush=True)
    
    # ONE LLM call for all header checks
    results = await validate_batch_checks(header_checks, documents, category="header")
    
    # Log results
    for result in results:
        print(f"   ✓ {result.check_id}: {result.status}", flush=True)
    
    print(f"\n✅ Header checks complete: {len(results)} checks processed in ONE LLM call", flush=True)
    return results


async def validate_valuation_checks(
    region: Region,
    documents: Dict[str, bytes]
) -> List[ChecklistValidationOutput]:
    """
    Validate all valuation checks for a region using PDF documents.
    
    This makes ONE LLM call for ALL valuation checks together.
    
    Args:
        region: Region code (AU or NZ)
        documents: Dictionary of document types to PDF binary content
                  Format: {"entry_print": bytes, "commercial_invoice": bytes, "air_waybill": bytes}
        
    Returns:
        List of validation results for valuation checks
    """
    valuation_checks = get_valuation_checks(region)
    
    print(f"\n" + "=" * 80, flush=True)
    print(f"💰 VALUATION VALIDATION - {region} Region", flush=True)
    print(f"=" * 80, flush=True)
    print(f"Running {len(valuation_checks)} valuation checks in ONE LLM call with PDF documents", flush=True)
    
    # ONE LLM call for all valuation checks
    results = await validate_batch_checks(valuation_checks, documents, category="valuation")
    
    # Log results
    for result in results:
        print(f"   ✓ {result.check_id}: {result.status}", flush=True)
    
    print(f"\n✅ Valuation checks complete: {len(results)} checks processed in ONE LLM call", flush=True)
    return results


async def extract_and_validate_tariff_lines(
    documents: Dict[str, bytes],
    job_id: str,
    region: Region
) -> Dict[str, Any]:
    """
    Extract line items with descriptions and tariff codes from invoice and entry print,
    then classify each item and validate the tariff codes.
    
    Args:
        documents: Dictionary of document types to PDF binary content
                  Format: {"entry_print": bytes, "commercial_invoice": bytes}
        job_id: Job ID for logging and output file naming
        region: Region code (AU or NZ) - determines which classifier to use
        
    Returns:
        Dictionary with:
            - line_items: List of extracted TariffLineItem objects
            - validations: List of TariffLineValidation objects with comparison results
            - summary: Dict with total, passed, failed, questionable counts
        
    Raises:
        Exception: If extraction fails after retries
    """
    agent = _get_tariff_extractor_agent(region=region)
    
    print(f"\n" + "=" * 80, flush=True)
    print(f"📋 TARIFF LINE EXTRACTION - Job {job_id}", flush=True)
    print(f"=" * 80, flush=True)
    print(f"Extracting line items from Invoice and Entry Print...", flush=True)
    
    # Check if we have the required documents
    required_docs = ["commercial_invoice", "entry_print"]
    missing_docs = [doc for doc in required_docs if doc not in documents or not documents[doc]]
    
    if missing_docs:
        print(f"❌ Missing required documents: {missing_docs}", flush=True)
        raise ValueError(f"Missing required documents for tariff extraction: {missing_docs}")
    
    # Build message parts list with text prompt and PDF documents
    message_parts = []
    
    # Add text prompt
    prompt = """
Extract ALL line items from the Commercial Invoice and Entry Print documents provided below.

**Documents Provided**:
1. COMMERCIAL INVOICE DOCUMENT - Contains product descriptions, quantities, prices
2. ENTRY PRINT DOCUMENT - Contains tariff codes, statistical codes, concessions, quantities, and GST info

**Your Task**:
- Extract ALL line items from BOTH documents
- Match each invoice line item with its corresponding entry print line
- Return a complete list with:
  * Line numbers (sequential, starting from 1)
  * Description from commercial invoice
  * 8-digit tariff code from entry print
  * 2-digit statistical code from entry print
  * Complete 10-digit code (tariff + stat)
  * invoice_quantity: Quantity and unit from COMMERCIAL INVOICE
  * entry_print_quantity: Quantity and unit from ENTRY PRINT (may be merged or different)
  * Unit price from invoice
  * Total value from invoice
  * concession_bylaw: Tariff concession or by-law number from entry print (null/empty if not claimed)
  * gst_exemption: Boolean - true if GST exemption is claimed in entry print, false otherwise

**Instructions**:
- If documents show different numbers of lines, include ALL lines found
- Entry print may merge multiple invoice lines - extract BOTH quantities separately
- Match lines based on order, descriptions, and values
- Keep descriptions exactly as shown in invoice
- Format codes as strings (e.g., "12345678" for tariff, "01" for stat)
- Include currency in prices (e.g., "USD 125.00")
- Look for concession/TCO/by-law columns in entry print (e.g., "1700581", "Schedule 4")
- Check for GST exemption indicators in entry print (columns like "GST", "Exemption", or special codes)
- Set concession_bylaw to null if no concession is claimed
- Set gst_exemption to false if no GST exemption is indicated

Return a JSON object with a "line_items" array containing all extracted line items with ALL fields.
"""
    message_parts.append(prompt)
    
    # Add Commercial Invoice PDF
    message_parts.append("\n**COMMERCIAL INVOICE DOCUMENT**:\n")
    message_parts.append(BinaryContent(
        data=documents["commercial_invoice"],
        media_type="application/pdf"
    ))
    print(f"  Added Commercial Invoice PDF ({len(documents['commercial_invoice']):,} bytes)", flush=True)
    
    # Add Entry Print PDF
    message_parts.append("\n**ENTRY PRINT DOCUMENT**:\n")
    message_parts.append(BinaryContent(
        data=documents["entry_print"],
        media_type="application/pdf"
    ))
    print(f"  Added Entry Print PDF ({len(documents['entry_print']):,} bytes)", flush=True)
    
    # Run extraction
    try:
        print(f"🔄 Calling Gemini to extract tariff line items...", flush=True)
        result = await agent.run(message_parts)
        tariff_output: TariffLineItemsOutput = result.output
        
        print(f"✅ Extracted {len(tariff_output.line_items)} line items", flush=True)
        
        # Log extracted line items
        for item in tariff_output.line_items:
            print(f"  Line {item.line_number}: {item.full_code} - {item.description[:60]}...", flush=True)
        
    except Exception as e:
        print(f"❌ Failed to extract tariff line items: {e}", flush=True)
        raise
    
    # Step 2: Validate each line item with 4 checks
    print(f"\n" + "=" * 80, flush=True)
    print(f"🤖 LINE ITEM VALIDATION - Job {job_id}", flush=True)
    print(f"=" * 80, flush=True)
    # Display check counts based on region
    total_checks = 4 if region == "AU" else 3
    print(f"Validating {len(tariff_output.line_items)} line items with {total_checks} checks each:", flush=True)
    if region == "AU":
        print(f"  1. Tariff Classification & Stat Code", flush=True)
        print(f"  2. Tariff/Bylaw Concession", flush=True)
        print(f"  3. Quantity Consistency", flush=True)
        print(f"  4. GST Exemption", flush=True)
    else:  # NZ
        print(f"  1. Tariff Classification & Stat Key", flush=True)
        print(f"  2. Quantity Consistency", flush=True)
        print(f"  3. GST Exemption", flush=True)
    
    # Import the appropriate classifier based on region
    if region == "AU":
        try:
            from .au.classifier import _classify_single_item
            from .au.tools import Item
        except ImportError as e:
            print(f"❌ Failed to import AU classifier: {e}", flush=True)
            return {
                "line_items": tariff_output.line_items,
                "validations": [],
                "summary": {"total": 0, "passed": 0, "failed": 0, "questionable": 0, "not_applicable": 0}
            }
    elif region == "NZ":
        try:
            from .nz.classifier import classify_nz, ClassificationRequest
            from .au.tools import Item
        except ImportError as e:
            print(f"❌ Failed to import NZ classifier: {e}", flush=True)
            return {
                "line_items": tariff_output.line_items,
                "validations": [],
                "summary": {"total": 0, "passed": 0, "failed": 0, "questionable": 0, "not_applicable": 0}
            }
    else:
        print(f"⚠️  Unsupported region: {region}", flush=True)
        return {
            "line_items": tariff_output.line_items,
            "validations": [],
            "summary": {"total": 0, "passed": 0, "failed": 0, "questionable": 0, "not_applicable": 0}
        }
    
    # Validate each line item with ALL checks
    validations: List[TariffLineValidation] = []
    
    for line_item in tariff_output.line_items:
        print(f"\n  Validating Line {line_item.line_number}: {line_item.description[:60]}...", flush=True)
        
        try:
            # ===== CHECK 1: Tariff Classification & Stat Code/Key =====
            check_num = "[1/4]" if region == "AU" else "[1/3]"
            print(f"    {check_num} Tariff Classification...", flush=True)
            item = Item(
                id=f"line_{line_item.line_number}",
                description=line_item.description,
                supplier_name=None
            )
            
            if region == "AU":
                classification_result, _ = await _classify_single_item(item)
                extracted_tariff = line_item.tariff_code
                extracted_stat = line_item.stat_code
                suggested_tariff = classification_result.best_suggested_hs_code
                suggested_stat = classification_result.best_suggested_stat_code
                other_codes = [f"{sc.hs_code}.{sc.stat_code}" for sc in classification_result.other_suggested_codes]
                reasoning = classification_result.reasoning
                
            elif region == "NZ":
                # NZ classification - call existing classify_nz function
                # Create Item using dict to avoid Pydantic validation issues
                item_dict = {
                    "id": f"line_{line_item.line_number}",
                    "description": line_item.description,
                    "supplier_name": None
                }
                nz_item = Item(**item_dict)
                request_dict = {"items": [item_dict]}
                request = ClassificationRequest(**request_dict)
                nz_response = await classify_nz(request)
                classification_result = nz_response.results[0]
                
                extracted_tariff = line_item.tariff_code
                extracted_stat = line_item.stat_code
                suggested_tariff = classification_result.best_suggested_hs_code
                suggested_stat = classification_result.best_suggested_stat_key
                other_codes = [f"{sc.hs_code}.{sc.stat_key}" for sc in classification_result.other_suggested_codes]
                reasoning = classification_result.reasoning
            else:
                # This should never happen due to earlier region check, but handle it for safety
                raise ValueError(f"Unsupported region: {region}")
            
            # Determine tariff classification status (common logic for both regions)
            tariff_status = "FAIL"
            tariff_assessment_parts = []
            
            if extracted_tariff == suggested_tariff and extracted_stat == suggested_stat:
                tariff_status = "PASS"
                tariff_assessment_parts.append(f"Exact match: {extracted_tariff}.{extracted_stat}")
            else:
                match_found = False
                for alt_code in other_codes:
                    if f"{extracted_tariff}.{extracted_stat}" in alt_code:
                        tariff_status = "QUESTIONABLE"
                        match_found = True
                        tariff_assessment_parts.append(f"Partial match in alternatives")
                        break
                
                if not match_found:
                    tariff_status = "FAIL"
                    tariff_assessment_parts.append(f"No match. Expected: {suggested_tariff}.{suggested_stat}, Found: {extracted_tariff}.{extracted_stat}")
            
            tariff_assessment_parts.append(f"Reasoning: {reasoning}")
            tariff_assessment = "\n".join(tariff_assessment_parts)
            
            print(f"       → {tariff_status}", flush=True)
            
            # ===== CHECK 2: Tariff/Bylaw Concession (AU ONLY) =====
            if region == "AU":
                print(f"    [2/4] Concession/Bylaw...", flush=True)
                concession_status = "N/A"
                concession_assessment = "No concession claimed"
                concession_link = None
                
                if line_item.concession_bylaw and line_item.concession_bylaw.strip():
                    # Concession is claimed, verify it using the tariff code
                    print(f"       Checking concession: {line_item.concession_bylaw} for tariff {extracted_tariff}", flush=True)
                    concession_data = await lookup_tariff_concession(
                        tariff_code=extracted_tariff,
                        claimed_concession=line_item.concession_bylaw
                    )
                    
                    if "error" in concession_data and concession_data.get("results", []) == []:
                        concession_status = "FAIL"
                        concession_assessment = f"Concession {line_item.concession_bylaw} claimed but lookup failed. Error: {concession_data['error']}"
                    elif concession_data.get("found"):
                        # Concession found in database, now compare descriptions using LLM
                        # Don't include API URL in output
                        results = concession_data.get("results", [])
                        all_results_count = len(concession_data.get("all_results", []))
                        
                        # Use LLM to compare item description with concession descriptions
                        print(f"       Found {len(results)} matching concession(s) (out of {all_results_count} for this tariff)", flush=True)
                        print(f"       Comparing descriptions with LLM...", flush=True)
                        comparison_result = await _compare_concession_descriptions(
                            line_item.description,
                            results,
                            line_item.concession_bylaw
                        )
                        
                        concession_status = comparison_result["status"]
                        concession_assessment = comparison_result["assessment"]
                        # Keep link as None - don't expose API URLs in output
                    else:
                        # No matching concession found for this tariff code
                        all_results_count = len(concession_data.get("all_results", []))
                        if all_results_count > 0:
                            concession_status = "FAIL"
                            concession_assessment = f"Concession {line_item.concession_bylaw} claimed but not found for tariff {extracted_tariff}. Found {all_results_count} other concession(s) for this tariff, but none match the claimed TC."
                        else:
                            concession_status = "FAIL"
                            concession_assessment = f"Concession {line_item.concession_bylaw} claimed but no concessions available for tariff {extracted_tariff}"
                
                print(f"       → {concession_status}", flush=True)
            else:
                # NZ doesn't use concessions
                concession_status = "N/A"
                concession_assessment = "Not applicable for NZ region"
                concession_link = None
            
            # ===== CHECK 3 (or 2 for NZ): Quantity Validation =====
            check_num = "[3/4]" if region == "AU" else "[2/3]"
            print(f"    {check_num} Quantity...", flush=True)
            
            # Check for missing quantities first
            if "NOT FOUND" in line_item.invoice_quantity or "NOT FOUND" in line_item.entry_print_quantity:
                quantity_status = "FAIL"
                quantity_assessment = f"Quantity missing - Invoice: {line_item.invoice_quantity}, Entry: {line_item.entry_print_quantity}"
            else:
                # Extract numbers for comparison
                import re
                invoice_nums = re.findall(r'\d+\.?\d*', line_item.invoice_quantity)
                entry_nums = re.findall(r'\d+\.?\d*', line_item.entry_print_quantity)
                
                # Normalize units for comparison (PCS, PC, PIECES, etc.)
                invoice_unit = re.sub(r'\d+\.?\d*\s*', '', line_item.invoice_quantity).strip().upper()
                entry_unit = re.sub(r'\d+\.?\d*\s*', '', line_item.entry_print_quantity).strip().upper()
                
                # Map common unit variations
                unit_mappings = {
                    'PCS': 'PIECES', 'PC': 'PIECES', 'PIECE': 'PIECES',
                    'KGS': 'KG', 'KILOGRAMS': 'KG', 'KILOGRAM': 'KG',
                    'LBS': 'LB', 'POUNDS': 'LB', 'POUND': 'LB',
                    'UNITS': 'UNIT', 'U': 'UNIT',
                    'BOXES': 'BOX', 'BX': 'BOX',
                    'CARTONS': 'CARTON', 'CTN': 'CARTON',
                    'SETS': 'SET',
                    'PAIRS': 'PAIR', 'PR': 'PAIR'
                }
                
                # Normalize units
                normalized_invoice_unit = unit_mappings.get(invoice_unit, invoice_unit)
                normalized_entry_unit = unit_mappings.get(entry_unit, entry_unit)
                
                if invoice_nums and entry_nums:
                    invoice_qty = float(invoice_nums[0])
                    entry_qty = float(entry_nums[0])
                    
                    # Check if quantities match
                    if invoice_qty == entry_qty and normalized_invoice_unit == normalized_entry_unit:
                        quantity_status = "PASS"
                        quantity_assessment = f"Quantities match: {line_item.invoice_quantity} = {line_item.entry_print_quantity}"
                    elif invoice_qty == entry_qty:
                        # Same quantity but different unit abbreviations (should still pass)
                        quantity_status = "PASS"
                        quantity_assessment = f"Quantities match: {line_item.invoice_quantity} ≈ {line_item.entry_print_quantity} (different unit abbreviation)"
                    else:
                        # Different quantities - may be merged lines
                        quantity_status = "QUESTIONABLE"
                        quantity_assessment = f"Quantity mismatch - Invoice: {line_item.invoice_quantity}, Entry: {line_item.entry_print_quantity} (may be merged lines)"
                else:
                    # Could not extract numbers
                    quantity_status = "QUESTIONABLE"
                    quantity_assessment = f"Could not parse quantities - Invoice: {line_item.invoice_quantity}, Entry: {line_item.entry_print_quantity}"
            
            print(f"       → {quantity_status}", flush=True)
            
            # ===== CHECK 4 (or 3 for NZ): GST Exemption =====
            check_num = "[4/4]" if region == "AU" else "[3/3]"
            print(f"    {check_num} GST Exemption...", flush=True)
            gst_status = "N/A"
            gst_assessment = "No GST exemption claimed"
            
            if line_item.gst_exemption:
                # GST exemption is claimed - would need to verify against concession or other rules
                # For now, we'll mark as QUESTIONABLE if claimed (requires manual review)
                gst_status = "QUESTIONABLE"
                gst_assessment = "GST exemption claimed - requires manual verification against concession eligibility"
            
            print(f"       → {gst_status}", flush=True)
            
            # ===== Determine Overall Status (worst case) =====
            status_priority = {"FAIL": 4, "QUESTIONABLE": 3, "PASS": 2, "N/A": 1}
            all_statuses = [tariff_status, concession_status, quantity_status, gst_status]
            overall_status = max(all_statuses, key=lambda s: status_priority[s])
            
            validation = TariffLineValidation(
                line_number=line_item.line_number,
                description=line_item.description,
                # Tariff classification
                extracted_tariff_code=extracted_tariff,
                extracted_stat_code=extracted_stat,
                suggested_tariff_code=suggested_tariff,
                suggested_stat_code=suggested_stat,
                tariff_classification_status=tariff_status,
                tariff_classification_assessment=tariff_assessment,
                other_suggested_codes=other_codes,
                # Concession
                claimed_concession=line_item.concession_bylaw,
                concession_status=concession_status,
                concession_assessment=concession_assessment,
                concession_link=concession_link,
                # Quantity
                invoice_quantity=line_item.invoice_quantity,
                entry_print_quantity=line_item.entry_print_quantity,
                quantity_status=quantity_status,
                quantity_assessment=quantity_assessment,
                # GST
                gst_exemption_claimed=line_item.gst_exemption,
                gst_exemption_status=gst_status,
                gst_exemption_assessment=gst_assessment,
                # Overall
                overall_status=overall_status
            )
            
            validations.append(validation)
            print(f"    ✅ Line {line_item.line_number} Overall: {overall_status}", flush=True)
            
        except Exception as classify_error:
            print(f"    ❌ Validation failed for Line {line_item.line_number}: {classify_error}", flush=True)
            # Add a FAIL validation for this line with all required fields
            validation = TariffLineValidation(
                line_number=line_item.line_number,
                description=line_item.description,
                # Tariff classification
                extracted_tariff_code=line_item.tariff_code,
                extracted_stat_code=line_item.stat_code,
                suggested_tariff_code="ERROR",
                suggested_stat_code="ER",
                tariff_classification_status="FAIL",
                tariff_classification_assessment=f"Validation error: {str(classify_error)}",
                other_suggested_codes=[],
                # Concession
                claimed_concession=line_item.concession_bylaw,
                concession_status="FAIL",
                concession_assessment="Validation failed",
                concession_link=None,
                # Quantity
                invoice_quantity=line_item.invoice_quantity,
                entry_print_quantity=line_item.entry_print_quantity,
                quantity_status="FAIL",
                quantity_assessment="Validation failed",
                # GST
                gst_exemption_claimed=line_item.gst_exemption,
                gst_exemption_status="FAIL",
                gst_exemption_assessment="Validation failed",
                # Overall
                overall_status="FAIL"
            )
            validations.append(validation)
    
    # Calculate summary based on overall_status
    total = len(validations)
    passed = sum(1 for v in validations if v.overall_status == "PASS")
    failed = sum(1 for v in validations if v.overall_status == "FAIL")
    questionable = sum(1 for v in validations if v.overall_status == "QUESTIONABLE")
    not_applicable = sum(1 for v in validations if v.overall_status == "N/A")
    
    print(f"\n" + "=" * 80, flush=True)
    print(f"✅ Line Item Validation Complete ({total_checks} checks per line)", flush=True)
    print(f"   Total lines: {total}", flush=True)
    print(f"   ✅ PASS: {passed}", flush=True)
    print(f"   ❌ FAIL: {failed}", flush=True)
    print(f"   ⚠️  QUESTIONABLE: {questionable}", flush=True)
    print(f"   ➖ N/A: {not_applicable}", flush=True)
    print(f"=" * 80, flush=True)
    
    return {
        "line_items": tariff_output.line_items,
        "validations": validations,
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "questionable": questionable,
            "not_applicable": not_applicable
        }
    }


async def validate_all_checks(
    region: Region,
    documents: Dict[str, bytes],
    job_id: str
) -> Dict[str, Any]:
    """
    Validate all checks (header + valuation) + extract tariff line items for a region using PDF documents.
    
    This function makes EXACTLY THREE LLM calls IN PARALLEL:
    1. ONE call for ALL header checks (8 checks)
    2. ONE call for ALL valuation checks (3 checks)
    3. ONE call for tariff line extraction (invoice + entry print)
    
    All three calls run simultaneously using asyncio.gather() for maximum performance.
    
    Args:
        region: Region code (AU or NZ)
        documents: Dictionary of document types to PDF binary content
                  Format: {"entry_print": bytes, "commercial_invoice": bytes, "air_waybill": bytes}
        job_id: Job ID for logging and output
        
    Returns:
        Dictionary with results grouped by category:
        {
            "header": [ChecklistValidationOutput, ...],
            "valuation": [ChecklistValidationOutput, ...],
            "tariff_lines": [TariffLineItem, ...],
            "summary": {"total": 11, "passed": 8, "failed": 1, "questionable": 2}
        }
    """
    print(f"\n" + "=" * 80, flush=True)
    print(f"🚀 STARTING COMPLETE VALIDATION FOR {region} REGION", flush=True)
    print(f"=" * 80, flush=True)
    print(f"Documents provided: {list(documents.keys())}", flush=True)
    print(f"This will make EXACTLY THREE LLM calls IN PARALLEL:", flush=True)
    print(f"  1. ONE call for ALL 8 header checks (with PDFs)", flush=True)
    print(f"  2. ONE call for ALL 3 valuation checks (with PDFs)", flush=True)
    print(f"  3. ONE call for tariff line extraction (with PDFs)", flush=True)
    print(f"  Total: 3 LLM calls running simultaneously", flush=True)
    print(f"", flush=True)
    
    # Run header checks, valuation checks, AND tariff extraction IN PARALLEL
    print(f"🔄 Starting all three processes in parallel...", flush=True)
    
    # Create tasks - tariff extraction may fail if documents are missing, so handle gracefully
    tasks = [
        validate_header_checks(region, documents),
        validate_valuation_checks(region, documents),
    ]
    
    # Add tariff extraction and validation if we have the required documents
    tariff_task = None
    if "entry_print" in documents and "commercial_invoice" in documents:
        tariff_task = extract_and_validate_tariff_lines(documents, job_id, region)
        tasks.append(tariff_task)
    else:
        print(f"⚠️  Skipping tariff extraction - missing required documents", flush=True)
    
    # Run all tasks in parallel
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Unpack results
    header_results = results[0] if not isinstance(results[0], Exception) else []
    valuation_results = results[1] if not isinstance(results[1], Exception) else []
    
    # Tariff results contain both line_items and validations
    tariff_result = results[2] if len(results) > 2 and not isinstance(results[2], Exception) else None
    tariff_lines = tariff_result.get("line_items", []) if tariff_result else []
    tariff_validations = tariff_result.get("validations", []) if tariff_result else []
    tariff_summary = tariff_result.get("summary", {"total": 0, "passed": 0, "failed": 0, "questionable": 0, "not_applicable": 0}) if tariff_result else {"total": 0, "passed": 0, "failed": 0, "questionable": 0, "not_applicable": 0}
    
    # Log any exceptions
    for idx, result in enumerate(results):
        if isinstance(result, Exception):
            task_name = ["header", "valuation", "tariff"][idx]
            print(f"⚠️  {task_name} task failed: {result}", flush=True)
    
    # Summary for header + valuation checks
    total_checks = len(header_results) + len(valuation_results)
    passed = sum(1 for r in (header_results + valuation_results) if r.status == "PASS")
    failed = sum(1 for r in (header_results + valuation_results) if r.status == "FAIL")
    questionable = sum(1 for r in (header_results + valuation_results) if r.status == "QUESTIONABLE")
    not_applicable = sum(1 for r in (header_results + valuation_results) if r.status == "N/A")
    
    print(f"\n" + "=" * 80, flush=True)
    print(f"🎉 COMPLETE VALIDATION FOR {region} REGION", flush=True)
    print(f"=" * 80, flush=True)
    print(f"Header + Valuation checks: {total_checks}", flush=True)
    print(f"  ✅ PASS: {passed}", flush=True)
    print(f"  ❌ FAIL: {failed}", flush=True)
    print(f"  ⚠️  QUESTIONABLE: {questionable}", flush=True)
    print(f"  ➖ N/A: {not_applicable}", flush=True)
    if tariff_validations:
        print(f"\nTariff line checks: {tariff_summary['total']}", flush=True)
        print(f"  ✅ PASS: {tariff_summary['passed']}", flush=True)
        print(f"  ❌ FAIL: {tariff_summary['failed']}", flush=True)
        print(f"  ⚠️  QUESTIONABLE: {tariff_summary['questionable']}", flush=True)
        print(f"  ➖ N/A: {tariff_summary['not_applicable']}", flush=True)
    print(f"=" * 80, flush=True)
    
    return {
        "header": header_results,
        "valuation": valuation_results,
        "tariff_lines": tariff_lines,
        "tariff_validations": tariff_validations,
        "summary": {
            "total": total_checks,
            "passed": passed,
            "failed": failed,
            "questionable": questionable,
            "not_applicable": not_applicable
        },
        "tariff_summary": tariff_summary
    }

