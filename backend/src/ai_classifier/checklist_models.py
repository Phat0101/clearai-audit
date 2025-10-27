"""
Pydantic models for checklist validation using PydanticAI and Gemini 2.5 Flash.

This module handles:
- Loading checklist JSON configurations
- Converting checklist items to Pydantic validation models
- Generating validation prompts for LLM
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal, Dict, Any, List
from pydantic import BaseModel, Field


# Base types for checklist validation
ChecklistStatus = Literal["PASS", "FAIL", "QUESTIONABLE", "N/A"]
DocumentType = Literal["entry_print", "air_waybill", "commercial_invoice"]
Region = Literal["AU", "NZ"]


class CompareFields(BaseModel):
    """Fields to compare between documents."""
    source_doc: DocumentType = Field(..., description="Source document type")
    source_field: str | List[str] = Field(..., description="Field(s) to extract from source document")
    target_doc: DocumentType = Field(..., description="Target document type")
    target_field: str | List[str] = Field(..., description="Field(s) to extract from target document")


class ChecklistItemConfig(BaseModel):
    """Configuration for a single checklist item."""
    id: str = Field(..., description="Unique identifier for the checklist item")
    auditing_criteria: str = Field(..., description="What is being audited")
    description: str = Field(..., description="Detailed description of the check")
    checking_logic: str = Field(..., description="How to perform the check")
    pass_conditions: str = Field(..., description="Conditions for passing the check")
    compare_fields: CompareFields = Field(..., description="Fields to compare")
    reference_url: str | None = Field(None, description="Optional reference URL for additional info")


class ChecklistValidationOutput(BaseModel):
    """
    Output model for a single checklist validation.
    This is the structured output that Gemini will generate.
    """
    check_id: str = Field(..., description="The ID of the checklist item being validated")
    auditing_criteria: str = Field(..., description="The auditing criteria being checked")
    status: ChecklistStatus = Field(
        ..., 
        description="PASS if validation succeeds, FAIL if validation fails, QUESTIONABLE if unclear or partially matching, N/A if not applicable"
    )
    assessment: str = Field(
        ..., 
        description="Detailed reasoning explaining the validation result. Include what was compared and why the status was assigned."
    )
    source_document: DocumentType = Field(..., description="The source document used for validation")
    target_document: DocumentType = Field(..., description="The target document used for validation")
    source_value: str = Field(
        ..., 
        description="The actual value(s) extracted from the source document. For multiple values, format as a string (e.g., 'field1: value1, field2: value2' or use JSON string format)."
    )
    target_value: str = Field(
        ..., 
        description="The actual value(s) extracted from the target document. For multiple values, format as a string (e.g., 'field1: value1, field2: value2' or use JSON string format)."
    )


class TariffLineItem(BaseModel):
    """Model for a single line item with description and tariff code."""
    line_number: int = Field(..., description="Line item number (sequential starting from 1)")
    description: str = Field(..., description="Product description from commercial invoice")
    tariff_code: str = Field(..., description="8-digit tariff classification code from entry print")
    stat_code: str = Field(..., description="Statistical code from entry print (AU: 2-digit, NZ: 3-char like 00H)")
    full_code: str = Field(..., description="Complete code (AU: 10 digits = tariff + stat, NZ: 11 chars = tariff + stat key)")
    invoice_quantity: str = Field(..., description="Quantity and unit from commercial invoice (e.g., '5 PCS', '10.5 KG')")
    entry_print_quantity: str = Field(..., description="Quantity and unit from entry print (e.g., '5 PCS', '10.5 KG')")
    unit_price: str = Field(..., description="Unit price from invoice (e.g., 'USD 25.00')")
    total_value: str = Field(..., description="Total line value from invoice (e.g., 'USD 125.00')")
    concession_bylaw: str | None = Field(None, description="Tariff concession or by-law number from entry print (e.g., '1700581', 'Schedule 4'). Set to None or empty if no concession claimed.")
    gst_exemption: bool = Field(False, description="Whether GST exemption is claimed for this line in entry print")
    
    
class TariffLineItemsOutput(BaseModel):
    """Output model for all line items extracted from invoice and entry print."""
    line_items: List[TariffLineItem] = Field(..., description="List of all line items with descriptions and tariff codes")


class LineItemCheck(BaseModel):
    """Individual check result for a line item."""
    check_name: str = Field(..., description="Name of the check (e.g., 'Tariff Classification & Stat code', 'Tariff/Bylaw Concession', 'Quantity', 'GST Exemption')")
    status: ChecklistStatus = Field(..., description="PASS/FAIL/QUESTIONABLE/N/A")
    assessment: str = Field(..., description="Detailed assessment for this specific check")
    

class TariffLineValidation(BaseModel):
    """Comprehensive validation result for a single tariff line item with all checks."""
    line_number: int = Field(..., description="Line item number")
    description: str = Field(..., description="Product description")
    
    # Tariff Classification Check
    extracted_tariff_code: str = Field(..., description="8-digit tariff code extracted from entry print")
    extracted_stat_code: str = Field(..., description="Stat code from entry print (AU: 2-digit, NZ: 3-char)")
    suggested_tariff_code: str = Field(..., description="System-suggested 8-digit tariff code")
    suggested_stat_code: str = Field(..., description="System-suggested stat code (AU: 2-digit, NZ: 3-char)")
    tariff_classification_status: ChecklistStatus = Field(..., description="Status for tariff classification check")
    tariff_classification_assessment: str = Field(..., description="Assessment for tariff classification")
    other_suggested_codes: List[str] = Field(default_factory=list, description="Other suggested tariff codes")
    
    # Concession/Bylaw Check
    claimed_concession: str | None = Field(None, description="Concession or by-law number claimed in entry print")
    concession_status: ChecklistStatus = Field(..., description="Status for concession validation")
    concession_assessment: str = Field(..., description="Assessment for concession check")
    concession_link: str | None = Field(None, description="TCO/Schedule 4 reference link if applicable")
    
    # Quantity Check
    invoice_quantity: str = Field(..., description="Quantity from commercial invoice")
    entry_print_quantity: str = Field(..., description="Quantity from entry print")
    quantity_status: ChecklistStatus = Field(..., description="Status for quantity validation")
    quantity_assessment: str = Field(..., description="Assessment for quantity check")
    
    # GST Exemption Check
    gst_exemption_claimed: bool = Field(..., description="Whether GST exemption is claimed")
    gst_exemption_status: ChecklistStatus = Field(..., description="Status for GST exemption check")
    gst_exemption_assessment: str = Field(..., description="Assessment for GST exemption")
    
    # Overall Status (worst of all checks)
    overall_status: ChecklistStatus = Field(..., description="Overall status: worst case of all checks (FAIL > QUESTIONABLE > PASS > N/A)")


class ChecklistCategory(BaseModel):
    """Category of checklist items (header or valuation)."""
    name: str
    description: str
    checks: List[ChecklistItemConfig]


class ChecklistConfiguration(BaseModel):
    """Full checklist configuration for a region."""
    version: str
    region: Region
    description: str
    last_updated: str
    categories: Dict[str, ChecklistCategory]


# Cache for checklist configurations
_checklist_cache: Dict[Region, ChecklistConfiguration] = {}


def get_checklist_path(region: Region) -> Path:
    """Get the path to the checklist JSON file for a region."""
    import os
    import logging
    logger = logging.getLogger(__name__)
    
    # Try environment variable first (for Docker or custom deployments)
    checklist_dir_env = os.getenv("CHECKLISTS_DIR")
    if checklist_dir_env:
        checklist_dir = Path(checklist_dir_env)
        logger.debug(f"Using CHECKLISTS_DIR from env: {checklist_dir}")
    else:
        # Auto-detect: try multiple possible locations
        # This file is at: src/ai_classifier/checklist_models.py
        current_file = Path(__file__).resolve()
        
        # Try 1: Docker structure (/app/checklists)
        docker_path = Path("/app/checklists")
        if docker_path.exists():
            checklist_dir = docker_path
            logger.debug(f"Using Docker checklist path: {checklist_dir}")
        else:
            # Try 2: Development - go up to backend/ directory
            # current_file.parent = ai_classifier/
            # current_file.parent.parent = src/
            # current_file.parent.parent.parent = backend/
            backend_dir = current_file.parent.parent.parent
            checklist_dir = backend_dir / "checklists"
            logger.debug(f"Using dev checklist path: {checklist_dir}")
    
    filename = f"{region.lower()}_checklist.json"
    full_path = checklist_dir / filename
    logger.debug(f"Full checklist path for {region}: {full_path}")
    return full_path


def load_checklist(region: Region) -> ChecklistConfiguration:
    """
    Load checklist configuration from JSON file.
    
    Args:
        region: Region code (AU or NZ)
        
    Returns:
        ChecklistConfiguration object
        
    Raises:
        FileNotFoundError: If checklist file doesn't exist
        ValueError: If JSON is invalid
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Return cached version if available
    if region in _checklist_cache:
        return _checklist_cache[region]
    
    checklist_path = get_checklist_path(region)
    logger.info(f"Loading checklist for {region} from: {checklist_path}")
    
    if not checklist_path.exists():
        logger.error(f"Checklist file not found for region {region}: {checklist_path}")
        raise FileNotFoundError(
            f"Checklist file not found for region {region}: {checklist_path}"
        )
    
    with open(checklist_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Parse and validate using Pydantic
    config = ChecklistConfiguration(**data)
    
    # Cache it
    _checklist_cache[region] = config
    
    return config


def get_header_checks(region: Region) -> List[ChecklistItemConfig]:
    """Get all header-level checks for a region."""
    config = load_checklist(region)
    return config.categories.get("header", ChecklistCategory(name="", description="", checks=[])).checks


def get_valuation_checks(region: Region) -> List[ChecklistItemConfig]:
    """Get all valuation checks for a region."""
    config = load_checklist(region)
    return config.categories.get("valuation", ChecklistCategory(name="", description="", checks=[])).checks


def get_all_checks(region: Region) -> List[ChecklistItemConfig]:
    """Get all checks (header + valuation) for a region."""
    return get_header_checks(region) + get_valuation_checks(region)


def build_validation_prompt(
    check: ChecklistItemConfig,
    source_data: Dict[str, Any],
    target_data: Dict[str, Any]
) -> str:
    """
    Build a validation prompt for the LLM based on a checklist item.
    
    Args:
        check: Checklist item configuration
        source_data: Extracted data from source document
        target_data: Extracted data from target document
        
    Returns:
        Formatted prompt string for the LLM
    """
    # Extract values from source document
    source_fields = check.compare_fields.source_field
    if isinstance(source_fields, str):
        source_fields = [source_fields]
    
    source_values = {}
    for field in source_fields:
        value = source_data.get(field, "N/A")
        source_values[field] = value
    
    # Extract values from target document
    target_fields = check.compare_fields.target_field
    if isinstance(target_fields, str):
        target_fields = [target_fields]
    
    target_values = {}
    for field in target_fields:
        value = target_data.get(field, "N/A")
        target_values[field] = value
    
    # Build prompt
    prompt = f"""
**Checklist Item ID**: {check.id}
**Auditing Criteria**: {check.auditing_criteria}

**Description**: {check.description}

**Checking Logic**: {check.checking_logic}

**Pass Conditions**: {check.pass_conditions}

---

**Source Document**: {check.compare_fields.source_doc}
**Source Field(s)**:
{json.dumps(source_values, indent=2, ensure_ascii=False)}

**Target Document**: {check.compare_fields.target_doc}
**Target Field(s)**:
{json.dumps(target_values, indent=2, ensure_ascii=False)}

---

**Instructions**:
1. Compare the source and target values according to the checking logic
2. Determine if the check passes, fails, or is questionable based on the pass conditions
3. Provide a detailed assessment explaining your reasoning
4. Include the actual values compared in your response

**Important Rules**:
- If both values are null/N/A/missing, return PASS (comparing null to null is acceptable)
- Use QUESTIONABLE only when there's genuine ambiguity
- Be specific in your assessment - mention the actual values you compared
- Consider fuzzy matching for company names (minor spelling differences, abbreviations, etc.)
- For numeric values, consider reasonable rounding differences

Return your validation in the required JSON format with all fields populated.
"""
    
    return prompt


def extract_field_value(data: Dict[str, Any], field_path: str) -> Any:
    """
    Extract a field value from nested data using dot notation.
    
    Args:
        data: The data dictionary
        field_path: Field path in dot notation (e.g., "supplier.name")
        
    Returns:
        The extracted value or "N/A" if not found
        
    Example:
        extract_field_value({"supplier": {"name": "ABC"}}, "supplier.name") -> "ABC"
    """
    if not field_path or not data:
        return "N/A"
    
    parts = field_path.split(".")
    current = data
    
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
            if current is None:
                return "N/A"
        else:
            return "N/A"
    
    return current if current is not None else "N/A"

