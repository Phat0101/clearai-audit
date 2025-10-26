# DHL Express Audit System - Logic Overview

## Overview

The audit system is designed to automate the auditing of customs documents for DHL Express shipments in Australia (AU) and New Zealand (NZ). It processes multiple document types (Entry Print, Air Waybill, Commercial Invoice, Packing List) through a three-stage pipeline: **Classification → Extraction → Validation**.

## System Architecture

### Technology Stack
- **Frontend**: Next.js 14 (App Router), TypeScript, Tailwind CSS, Shadcn UI
- **Backend API**: Next.js API Routes
- **Database**: PostgreSQL (via Prisma ORM)
- **AI/ML**: 
  - Google Gemini (document classification & extraction)
  - PydanticAI + Gemini 2.5 Pro (tariff classification)
- **Storage**: OneDrive integration for document access
- **Classification Backend**: FastAPI (Python) for AU/NZ tariff classification

---

## Core Processing Pipeline

### 1. Document Classification

**Purpose**: Identify the type of each document in an audit job

**Process**:
- Documents are uploaded or accessed from OneDrive
- Each PDF is sent to Google Gemini Flash 2.5 with a classification schema
- AI analyzes the document structure and content
- Returns classification: `entry_print`, `air_waybill`, `commercial_invoice`, `packing_list`, or `other`

**API Endpoint**: `POST /api/classify`
- Input: `{ fileUrl, fileId, jobId }`
- Output: Classification result stored in `audit_job_files.classification_data`

**Implementation**:
```typescript
// Uses Google AI SDK with structured output
const classification = await evaluatePDF(
  fileUrl,
  "documentClassification",
  "Analyze this document and determine its type according to the schema."
);
```

---

### 2. Data Extraction

**Purpose**: Extract structured data from each classified document

**Process**:
- Based on document type, select appropriate extraction schema:
  - `entry_print` → customsEntryPrint schema
  - `air_waybill` → airWaybill schema
  - `commercial_invoice` → commercialInvoice schema
  - `packing_list` → packingList schema
- Document is sent to Gemini with schema definition
- AI extracts all relevant fields including line items
- Structured data is stored in database

**API Endpoint**: `POST /api/extract`
- Input: `{ fileUrl, fileId, documentType, jobId }`
- Output: Extracted data stored in type-specific columns:
  - `extraction_results_entry_print`
  - `extraction_results_air_waybill`
  - `extraction_results_commercial_invoice`
  - `extraction_results_packing_list`

**Key Features**:
- Schema-driven extraction ensures consistent data structure
- Line items are extracted individually (quantities, prices, descriptions, tariff codes)
- Handles missing or unclear data gracefully

---

### 3. Checklist Validation

**Purpose**: Validate consistency and compliance across documents

**Process**:
The validation system uses a **dynamic checklist configuration** that can be customized per organization. It supports two types of checks:

#### A. Header-Level Checks
Compare document-level fields between different documents (e.g., Entry Print vs Commercial Invoice)

**Common Validations**:
- Consignee/Importer verification
- Supplier name matching
- Country of origin consistency
- Invoice totals vs declared values
- FTA (Free Trade Agreement) eligibility
- Incoterms validation
- AWB number consistency
- Date consistency

**Logic**:
```typescript
// For each header check configuration:
1. Extract source field(s) from source document
2. Extract target field(s) from target document
3. Use AI to compare values based on checking_logic
4. Return status: PASS, FAIL, QUESTIONABLE, or N/A
5. Store result in checklist_results table
```

#### B. Line-Item Checks
Validate individual line items between Entry Print and Commercial Invoice

**Common Validations**:
- Description consistency
- Quantity matching
- Unit price verification
- Country of origin per item
- FTA claims per item
- **Tariff classification** (AU/NZ specific)

**Tariff Classification Process**:

For **Australia**:
- Uses Gemini 2.5 Pro with Schedule 4 concession data
- Tools available:
  - `tariff_chapter_lookup` - lookup HS codes and chapter notes
  - `tariff_search` - validate specific HS codes
  - `tariff_concession_lookup` - check Schedule 4 concessions
  - `search_product_info` - ground product information
- Returns: 8-digit HS code + 2-digit stat code + TCO link (if applicable)

For **New Zealand**:
- Uses Gemini 2.5 Flash Lite
- Tools available:
  - `nz_tariff_chapter_lookup` - lookup NZ tariff chapters
  - `nz_tariff_search` - validate NZ HS codes
- Returns: 8-digit HS code + 3-char statistical key (format: 2 digits + 1 letter, e.g., "00H")

**Line Item Validation Flow**:
```
1. Match line items between Entry Print and Commercial Invoice
2. For each line item pair:
   a. Validate description similarity (AI-based)
   b. Validate quantity and units
   c. Validate unit price
   d. Validate country of origin
   e. Validate FTA claims
   f. Validate tariff classification:
      - Extract item description
      - Call AU or NZ classifier endpoint
      - Compare suggested codes with declared codes
      - Return assessment (PASS/FAIL/QUESTIONABLE)
3. Store results in checklist_lines_results table
```

**API Endpoint**: `POST /api/checklist/[jobId]`
- Input: `{ extractedData }`
- Output: Streaming response with validation results
- Automatically initializes default checklists if not configured

---

## Dynamic Checklist System

The system supports **customizable validation rules** instead of hardcoded checks.

### Configuration Structure

**Header-Level Configuration**:
```json
{
  "name": "Incoterm Validation",
  "check_type": "header",
  "auditing_criteria": "Incoterm consistency check",
  "priority": "High",
  "checking_logic": "Compare incoterms between entry print and commercial invoice",
  "pass_conditions": "Incoterms must match exactly",
  "compare_fields": {
    "source_doc": "entry_print",
    "source_field": "iTerms",
    "target_doc": "commercial_invoice",
    "target_field": "inco_terms"
  }
}
```

**Line-Item Configuration**:
```json
{
  "name": "Enhanced Line Item Validation",
  "check_type": "line_item",
  "auditing_criteria": "Detailed line item comparison",
  "priority": "High",
  "checking_logic": "Compare all critical fields",
  "pass_conditions": "All configured fields must pass",
  "compare_fields": {
    "fields": [
      {
        "name": "description",
        "entry_field": "description",
        "invoice_field": "description",
        "validation_logic": "Descriptions should be substantially similar",
        "is_required": true
      },
      {
        "name": "quantity",
        "entry_field": "quantity",
        "invoice_field": "quantity",
        "validation_logic": "Quantities must match exactly",
        "is_required": true
      }
    ]
  }
}
```

### Configuration Management
- **API**: `/api/checklist-configurations`
- **Database**: `checklist_configurations` table
- **Organization-specific**: Configurations can be linked to organizations
- **Default configurations**: System initializes with standard checks
- **Backward compatible**: Falls back to hardcoded checks if no configurations exist

---

## Database Schema

### Key Tables

**audit_jobs**
- Tracks each audit job
- Links to broker and organization
- Stores processing status: `draft`, `in_progress`, `completed`, `failed`
- Auto-processing stages: `registered`, `classifying`, `classified`, `extracting`, `extracted`, `validating`, `validated`

**audit_job_files**
- Stores individual document files
- Document type classification
- Extraction results (per document type)
- OneDrive integration metadata

**checklist_results**
- Header-level validation results
- Links to checklist configuration
- Stores source/target values and assessment

**checklist_lines_results**
- Line-item validation results
- Stores validation for each field (description, quantity, price, tariff, etc.)
- Dynamic validation results in JSONB format

**checklist_configurations**
- Dynamic checklist definitions
- Organization-specific or default
- Supports header and line-item checks

**organizations**
- Multi-tenancy support
- Organization-specific settings
- Country code for AU/NZ differentiation

**brokers**
- Broker authentication
- Links to organizations (many-to-many)

---

## AU vs NZ Differences

| Aspect | Australia (AU) | New Zealand (NZ) |
|--------|---------------|------------------|
| **HS Code Format** | 8 digits + 2-digit stat code | 8 digits + 3-char stat key (NN[A-Z]) |
| **AI Model** | Gemini 2.5 Pro | Gemini 2.5 Flash Lite |
| **Special Features** | Schedule 4 concessions, TCO links | Simplified tariff structure |
| **Tariff Tools** | `tariff_chapter_lookup`, `tariff_search`, `tariff_concession_lookup` | `nz_tariff_chapter_lookup`, `nz_tariff_search` |
| **Grounding** | Product info grounding with supplier context | Product info grounding with supplier context |
| **Endpoint** | `/classify/au` | `/classify/nz` |

---

## Key Features

### 1. AI-Powered Validation
- Uses Google Gemini for intelligent field comparison
- Handles variations in formatting, abbreviations, and minor differences
- Provides reasoning for each validation decision

### 2. Streaming Results
- Checklist validation streams results in real-time
- Allows UI to show progress as checks complete
- Better user experience for long-running validations

### 3. Organization Multi-Tenancy
- Organizations can have custom checklist configurations
- Brokers can belong to multiple organizations
- Organization-specific settings and rules

### 4. Tariff Classification
- Sophisticated tariff classification using AI agents
- Access to official tariff databases
- Grounded product information for better accuracy
- Retry logic for reliability
- Concurrent processing for performance

### 5. OneDrive Integration
- Browse OneDrive folders
- Create audit jobs from folders
- Automatic file syncing
- No manual file uploads required

### 6. Progress Tracking
- Track processing stage for each job
- Auto-processing status: `manual`, `processing`, `completed`, `failed`
- Stage-by-stage progress indicators

---

## Workflow Summary

```
1. USER: Browse OneDrive → Select folder → Create audit job
   └─> System creates audit_jobs record

2. CLASSIFICATION: For each PDF in folder
   └─> Send to Gemini → Identify document type → Store in audit_job_files
   
3. EXTRACTION: For each classified document
   └─> Send to Gemini with type-specific schema → Extract structured data → Store in audit_job_files
   
4. VALIDATION: When all documents extracted
   └─> Load checklist configurations (header + line-item)
   └─> For each header check:
       └─> Extract source/target values → AI comparison → Store result
   └─> For each line item:
       └─> Match entry/invoice items → Validate all fields → 
           For tariff: Call AU/NZ classifier → Compare codes → 
           Store results
   
5. RESULTS: Display validation results
   └─> Show PASS/FAIL/QUESTIONABLE status for each check
   └─> Provide reasoning and recommendations
   └─> Allow manual review and overrides
```

---

## Error Handling

- **Classification failures**: Mark as "other" type, allow manual reclassification
- **Extraction failures**: Store partial results, flag for manual review
- **Validation failures**: Mark as QUESTIONABLE, provide AI reasoning
- **Tariff lookup failures**: Retry with exponential backoff, fallback to "00000000" codes
- **API rate limits**: Semaphore-based concurrency control

---

## Future Migration Notes

The new version (frontend in `/frontend/audit`, backend in `/backend` with FastAPI) will:
- Separate frontend and backend architectures
- Use FastAPI for all AI/ML processing
- Keep the same core logic and validation rules
- Improve performance with dedicated Python backend
- Maintain backward compatibility with existing data

---

## Configuration Files

**Environment Variables Required**:
- `DATABASE_URL` - PostgreSQL connection string
- `GOOGLE_GENERATIVE_AI_API_KEY` - Gemini API key
- `GEMINI_API_KEY` or `GOOGLE_API_KEY` - For Python classifier
- `NEXTAUTH_URL` - Base URL for the application
- `MICROSOFT_CLIENT_ID` / `MICROSOFT_CLIENT_SECRET` - OneDrive integration
- `CLASSIFY_MAX_CONCURRENCY` - Max concurrent classifications (default: 100)
- `CLASSIFY_MAX_RETRIES` - Max retry attempts (default: 4)

**Key Configuration Files**:
- `prisma/schema.prisma` - Database schema
- `src/lib/schemas.ts` - Zod schemas for extraction
- `src/lib/schemas/checklist.ts` - Checklist validation schemas
- `samplecode/au_classifier.py` - AU tariff classification logic
- `samplecode/nz_classifier.py` - NZ tariff classification logic

---

## Summary

The audit system automates customs document auditing through AI-powered classification, extraction, and validation. It supports dynamic checklist configurations, organization-specific rules, and sophisticated tariff classification for both AU and NZ. The system is built for reliability with retry logic, streaming results, and comprehensive error handling.

