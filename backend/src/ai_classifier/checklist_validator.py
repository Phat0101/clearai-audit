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
from pathlib import Path
from typing import Dict, Any, List
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.models.gemini import GeminiModel, ThinkingConfig
from pydantic_ai.providers.google_gla import GoogleGLAProvider

from pydantic import BaseModel

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

**Special Considerations**:
- If both source and target values are not found/missing in the documents, default to PASS
- For company names: Allow fuzzy matching (abbreviations, minor spelling differences, corporate codes)
- For numeric values: Allow reasonable rounding differences (e.g., 100.00 vs 100)
- For currencies and codes: Allow abbreviations (e.g., "USD" vs "US Dollar", "DDP" vs "Delivered Duty Paid")
- For incoterms: Consider that DDP requires special handling for importer identity
- For dates: Allow different formats (e.g., "2025-01-15" vs "15/01/2025")

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
   - Quantities and units
   - Unit prices
   - Total values (line totals)

2. Analyze the Entry Print to extract ALL line items with:
   - Tariff classification codes (8 digits)
   - Statistical codes (2 digits)
   - Complete 10-digit codes (tariff + stat)

3. Match line items between the two documents based on:
   - Line item order and position
   - Product descriptions
   - Quantities and values

4. Return a structured list of ALL line items with:
   - Sequential line numbers (starting from 1)
   - Description from invoice
   - Tariff code (8 digits) from entry print
   - Statistical code (2 digits) from entry print
   - Full 10-digit code
   - Quantity and unit
   - Unit price
   - Total value

**Important Guidelines**:
- Extract ALL line items from both documents
- Match items carefully - the order may not be exactly the same
- If a tariff code is 10 digits, split it into 8-digit tariff + 2-digit stat code
- Keep descriptions exactly as they appear in the invoice
- Include currency symbols in prices (e.g., "USD 25.00")
- Format quantities with units (e.g., "5 PCS", "10.5 KG")
- If a line item appears in one document but not the other, include it with "NOT FOUND" for missing data

**Critical**:
- You MUST return ALL line items found in the documents
- Line numbers should be sequential starting from 1
- Match items based on order, description similarity, and values
- Be thorough and precise in your extraction
"""


def _get_tariff_extractor_agent() -> Agent:
    """Instantiate (or return cached) Gemini 2.5 Pro agent for tariff line extraction."""
    global _tariff_extractor_agent
    
    if _tariff_extractor_agent is not None:
        return _tariff_extractor_agent
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY environment variable is required for Gemini agent")

    model = GeminiModel(
        "gemini-2.5-pro",
        provider=GoogleGLAProvider(api_key=api_key),
    )

    _tariff_extractor_agent = Agent(
        model=model,
        instructions=_TARIFF_EXTRACTION_PROMPT,
        output_type=TariffLineItemsOutput,
        retries=2,
        model_settings={"gemini_thinking_config": ThinkingConfig(thinking_budget=5000), "temperature": 0.1},
    )
    
    return _tariff_extractor_agent


def _get_validator_agent() -> Agent:
    """Instantiate (or return cached) Gemini 2.5 Pro agent for checklist validation."""
    global _validator_agent
    
    if _validator_agent is not None:
        return _validator_agent
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY environment variable is required for Gemini agent")

    model = GeminiModel(
        "gemini-2.5-pro",
        provider=GoogleGLAProvider(api_key=api_key),
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
    agent = _get_tariff_extractor_agent()
    
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
2. ENTRY PRINT DOCUMENT - Contains tariff codes and statistical codes

**Your Task**:
- Extract ALL line items from BOTH documents
- Match each invoice line item with its corresponding entry print tariff code
- Return a complete list with:
  * Line numbers (sequential, starting from 1)
  * Description from invoice
  * 8-digit tariff code from entry print
  * 2-digit statistical code from entry print
  * Complete 10-digit code (tariff + stat)
  * Quantity and unit
  * Unit price
  * Total value

**Instructions**:
- If documents show different numbers of lines, include ALL lines found
- Match lines based on order, descriptions, and values
- Keep descriptions exactly as shown in invoice
- Format codes as strings (e.g., "12345678" for tariff, "01" for stat)
- Include currency in prices (e.g., "USD 125.00")

Return a JSON object with a "line_items" array containing all extracted line items.
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
    
    # Step 2: Classify each line item using the AU tariff classifier
    print(f"\n" + "=" * 80, flush=True)
    print(f"🤖 TARIFF LINE CLASSIFICATION - Job {job_id}", flush=True)
    print(f"=" * 80, flush=True)
    print(f"Classifying {len(tariff_output.line_items)} line items using tariff classifier...", flush=True)
    
    # Only support AU region for now
    if region != "AU":
        print(f"⚠️  Tariff classification only supported for AU region, skipping validation", flush=True)
        return {
            "line_items": tariff_output.line_items,
            "validations": [],
            "summary": {"total": 0, "passed": 0, "failed": 0, "questionable": 0}
        }
    
    # Import the AU classifier
    try:
        from .au.classifier import _classify_single_item
        from .au.tools import Item
    except ImportError as e:
        print(f"❌ Failed to import AU classifier: {e}", flush=True)
        return {
            "line_items": tariff_output.line_items,
            "validations": [],
            "summary": {"total": 0, "passed": 0, "failed": 0, "questionable": 0}
        }
    
    # Classify each line item
    validations: List[TariffLineValidation] = []
    
    for line_item in tariff_output.line_items:
        print(f"\n  Classifying Line {line_item.line_number}: {line_item.description[:60]}...", flush=True)
        
        try:
            # Create Item for classifier
            item = Item(
                id=f"line_{line_item.line_number}",
                description=line_item.description,
                supplier_name=None
            )
            
            # Classify the item
            classification_result, usage = await _classify_single_item(item)
            
            # Compare codes
            extracted_tariff = line_item.tariff_code
            extracted_stat = line_item.stat_code
            suggested_tariff = classification_result.best_suggested_hs_code
            suggested_stat = classification_result.best_suggested_stat_code
            
            # Determine status
            status = "FAIL"
            assessment_parts = []
            
            # Check if best match
            if extracted_tariff == suggested_tariff and extracted_stat == suggested_stat:
                status = "PASS"
                assessment_parts.append(f"Exact match")
            else:
                # Check if in other suggested codes
                match_found = False
                for alt_code in classification_result.other_suggested_codes:
                    if extracted_tariff == alt_code.hs_code and extracted_stat == alt_code.stat_code:
                        status = "QUESTIONABLE"
                        match_found = True
                        assessment_parts.append(f"Partial match")
                        break
                
                if not match_found:
                    status = "FAIL"
                    assessment_parts.append(f"No match")
            
            # Add classification reasoning
            assessment_parts.append(f"{classification_result.reasoning}")
            
            assessment = "\n".join(assessment_parts)
            
            # Build other suggested codes list
            other_codes = [
                f"{sc.hs_code}.{sc.stat_code}" 
                for sc in classification_result.other_suggested_codes
            ]
            
            validation = TariffLineValidation(
                line_number=line_item.line_number,
                description=line_item.description,
                extracted_tariff_code=extracted_tariff,
                extracted_stat_code=extracted_stat,
                suggested_tariff_code=suggested_tariff,
                suggested_stat_code=suggested_stat,
                status=status,
                assessment=assessment,
                other_suggested_codes=other_codes
            )
            
            validations.append(validation)
            print(f"    ✓ Line {line_item.line_number}: {status}", flush=True)
            
        except Exception as classify_error:
            print(f"    ❌ Classification failed for Line {line_item.line_number}: {classify_error}", flush=True)
            # Add a FAIL validation for this line
            validation = TariffLineValidation(
                line_number=line_item.line_number,
                description=line_item.description,
                extracted_tariff_code=line_item.tariff_code,
                extracted_stat_code=line_item.stat_code,
                suggested_tariff_code="ERROR",
                suggested_stat_code="ER",
                status="FAIL",
                assessment=f"Classification error: {str(classify_error)}",
                other_suggested_codes=[]
            )
            validations.append(validation)
    
    # Calculate summary
    total = len(validations)
    passed = sum(1 for v in validations if v.status == "PASS")
    failed = sum(1 for v in validations if v.status == "FAIL")
    questionable = sum(1 for v in validations if v.status == "QUESTIONABLE")
    
    print(f"\n" + "=" * 80, flush=True)
    print(f"✅ Tariff Line Classification Complete", flush=True)
    print(f"   Total lines: {total}", flush=True)
    print(f"   ✅ PASS: {passed}", flush=True)
    print(f"   ❌ FAIL: {failed}", flush=True)
    print(f"   ⚠️  QUESTIONABLE: {questionable}", flush=True)
    print(f"=" * 80, flush=True)
    
    return {
        "line_items": tariff_output.line_items,
        "validations": validations,
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "questionable": questionable
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
    1. ONE call for ALL header checks (13 checks)
    2. ONE call for ALL valuation checks (7 checks)
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
            "summary": {"total": 20, "passed": 15, "failed": 2, "questionable": 3}
        }
    """
    print(f"\n" + "=" * 80, flush=True)
    print(f"🚀 STARTING COMPLETE VALIDATION FOR {region} REGION", flush=True)
    print(f"=" * 80, flush=True)
    print(f"Documents provided: {list(documents.keys())}", flush=True)
    print(f"This will make EXACTLY THREE LLM calls IN PARALLEL:", flush=True)
    print(f"  1. ONE call for ALL 13 header checks (with PDFs)", flush=True)
    print(f"  2. ONE call for ALL 7 valuation checks (with PDFs)", flush=True)
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
    tariff_summary = tariff_result.get("summary", {"total": 0, "passed": 0, "failed": 0, "questionable": 0}) if tariff_result else {"total": 0, "passed": 0, "failed": 0, "questionable": 0}
    
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
    
    print(f"\n" + "=" * 80, flush=True)
    print(f"🎉 COMPLETE VALIDATION FOR {region} REGION", flush=True)
    print(f"=" * 80, flush=True)
    print(f"Header + Valuation checks: {total_checks}", flush=True)
    print(f"  ✅ PASS: {passed}", flush=True)
    print(f"  ❌ FAIL: {failed}", flush=True)
    print(f"  ⚠️  QUESTIONABLE: {questionable}", flush=True)
    if tariff_validations:
        print(f"\nTariff line checks: {tariff_summary['total']}", flush=True)
        print(f"  ✅ PASS: {tariff_summary['passed']}", flush=True)
        print(f"  ❌ FAIL: {tariff_summary['failed']}", flush=True)
        print(f"  ⚠️  QUESTIONABLE: {tariff_summary['questionable']}", flush=True)
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
            "questionable": questionable
        },
        "tariff_summary": tariff_summary
    }

