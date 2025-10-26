# Customs Audit Checklists

This directory contains JSON configuration files for customs audit checklists for different regions.

## Overview

Each checklist file defines validation rules for customs documents (entry prints, commercial invoices, air waybills) organized into categories:
- **Header-Level Checks**: Document-level cross-reference validations
- **Valuation Checks**: FOB, CIF, freight, insurance, and other valuation elements

## Files

### `au_checklist.json` & `nz_checklist.json`
**Both checklists are now identical** - they contain the same validation rules for consistency across AU and NZ regions.

The only difference is the region-specific ID prefixes (`au_` vs `nz_`) and the region field in the JSON header.

**Total Checks**: 20 (13 header + 7 valuation)

### Header Checks (13 items)
1. Owner match (based on incoterms)
2. Supplier match
3. Incoterms consistency
4. Currency match
5. Invoice number match
6. Shipper consistency
7. Consignee consistency
8. Country of origin consistency
9. Country of export match
10. Port of origin consistency
11. Weight consistency
12. Package count consistency
13. Description consistency

### Valuation Checks (7 items)
1. VFD (Value for Duty) validation
2. FOB value match
3. CIF value match
4. Freight validation
5. Insurance cost validation
6. Transport & Insurance costs match
7. Invoice total match

## JSON Schema

Each checklist follows this structure:

```json
{
  "version": "1.0.0",
  "region": "AU|NZ",
  "description": "...",
  "last_updated": "YYYY-MM-DD",
  "categories": {
    "header": {
      "name": "Header-Level Cross-Reference Checks",
      "description": "...",
      "checks": [
        {
          "id": "region_category_number",
          "auditing_criteria": "What is being checked",
          "description": "Detailed description",
          "checking_logic": "How to perform the check",
          "pass_conditions": "Conditions for passing",
          "compare_fields": {
            "source_doc": "entry_print|air_waybill|commercial_invoice",
            "source_field": "field_name or [array of fields]",
            "target_doc": "entry_print|air_waybill|commercial_invoice",
            "target_field": "field_name or [array of fields]"
          },
          "reference_url": "Optional external reference"
        }
      ]
    },
    "valuation": {
      "name": "Valuation Elements Checklist",
      "description": "...",
      "checks": [ /* same structure */ ]
    }
  }
}
```

## Usage

The backend Python code loads these checklists dynamically:

```python
from ai_classifier.checklist_models import load_checklist, get_header_checks, get_valuation_checks

# Load full checklist
au_checklist = load_checklist("AU")
nz_checklist = load_checklist("NZ")

# Get specific category checks
au_header_checks = get_header_checks("AU")
nz_valuation_checks = get_valuation_checks("NZ")
```

The checklist validator uses PydanticAI with Gemini 2.5 Flash to perform validations:

```python
from ai_classifier.checklist_validator import validate_all_checks

# Validate all checks for a job
results = await validate_all_checks(
    region="AU",
    extracted_data={
        "entry_print": {...},
        "commercial_invoice": {...},
        "air_waybill": {...}
    }
)
```

## Validation Output

Each checklist item validation returns:

```python
{
  "check_id": "au_h_001",
  "auditing_criteria": "Owner match",
  "status": "PASS|FAIL|QUESTIONABLE",
  "assessment": "Detailed reasoning with actual values compared",
  "source_document": "entry_print",
  "target_document": "commercial_invoice",
  "source_value": "DHL Express Australia Pty Ltd",
  "target_value": "DHL Express Australia"
}
```

## Editing Checklists

### Backend (Current)
Edit the JSON files directly in this directory. Changes take effect immediately (no rebuild required).

### Frontend (Planned)
A future UI will allow brokers/admins to:
- View all checklist items
- Edit checking logic and pass conditions
- Enable/disable specific checks
- Add custom organization-specific checks
- Export/import checklist configurations

## Best Practices

1. **IDs**: Use descriptive IDs with region prefix (e.g., `au_h_001`, `nz_v_003`)
2. **Checking Logic**: Be specific and actionable for the AI validator
3. **Pass Conditions**: Define clear, unambiguous criteria
4. **Field Names**: Match the extraction schema field names exactly
5. **References**: Include official customs URLs where applicable (especially for NZ supplier codes, concession codes)

## Version History

- **v1.0.0** (2025-10-14): Initial release with AU and NZ checklists
  - Both regions: 13 header + 7 valuation checks (20 total)
  - Identical validation rules for consistency across regions
  - Priority field removed for simplified structure
  - Reference URLs removed from all checks

## References

- **NZ Customs Supplier Codes**: https://www.customs.govt.nz/business/import/lodge-your-import-entry/supplier-codes-and-names
- **NZ Auditing CSV**: See `NZ auditing.csv` in project root
- **AU Checklist Source**: See `audit-v2/src/lib/schemas/checklist.ts`

