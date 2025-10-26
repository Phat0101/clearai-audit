# Simplified Audit System - Specification

## Overview

A streamlined document audit system that processes uploaded files and outputs XLSX reports for brokers. No complex UI, no database persistence - just upload, process, and download.

---

## Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  1. UPLOAD FILES                                                │
│     User uploads multiple PDFs                                  │
│     e.g., 2219477116_AWB.pdf, 2219477116_INV.pdf,             │
│          2219477676_AWB.pdf, 2555462195_AWB.pdf               │
│                                                                 │
│  ↓                                                             │
│                                                                 │
│  2. INITIALIZE RUN                                              │
│     Create run folder: 2025-10-13_run_001                      │
│     (auto-increments for same-day runs)                        │
│                                                                 │
│  ↓                                                             │
│                                                                 │
│  3. AUTO-GROUP BY PREFIX                                        │
│     Group files by leading number:                             │
│     - Job 1: 2219477116_* (3 files)                           │
│     - Job 2: 2219477676_* (3 files)                           │
│     - Job 3: 2555462195_* (3 files)                           │
│                                                                 │
│  ↓                                                             │
│                                                                 │
│  4. CLASSIFY & SAVE                                             │
│     For each file:                                             │
│     a) CLASSIFY document → Entry/AWB/Invoice/Packing          │
│     b) CREATE job folder: job_2219477116                      │
│     c) SAVE file with label: filename_air_waybill.pdf         │
│                                                                 │
│  ↓                                                             │
│                                                                 │
│  5. EXTRACT & VALIDATE                                          │
│     For each job:                                              │
│     a) EXTRACT structured data from saved files               │
│     b) VALIDATE checklist across documents                     │
│     c) Include tariff classification validation                │
│                                                                 │
│  ↓                                                             │
│                                                                 │
│  6. GENERATE XLSX OUTPUT                                        │
│     Create Excel file with:                                    │
│     - Job summary sheet                                        │
│     - Header checklist results                                 │
│     - Line item checklist results                              │
│     - Extraction data sheets                                   │
│     Save to: audit_results_2025-10-13_run_001.xlsx            │
│                                                                 │
│  ↓                                                             │
│                                                                 │
│  7. RETURN RESULTS                                              │
│     User receives:                                             │
│     - Run folder path: /output/2025-10-13_run_001/            │
│     - All classified PDFs organized by job                     │
│     - XLSX file download link                                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## File Naming Convention

**Expected Format**: `<JOB_NUMBER>_<DOCUMENT_TYPE>_<SUFFIX>.pdf`

**Examples**:
- `2219477116_AWB_OSA_OAA_8VD_20250929_132113.pdf` (Waybill)
- `2219477116_INV_OSA_OAA_E5D_20250929_132104.pdf` (Invoice)
- `2219477116_582955943_OSA_MEL_250929_0421_P.pdf`   (Waybill)
- `2219477116^^13387052^FRML^CIM^^_ENT_SYD_GTW_099_20251002_062500.pdf` (Entry Print)

**Grouping Logic**:
1. Extract the leading number before the first underscore
2. Group all files with the same leading number into one job
3. Each job should have:
   - 1x Entry Print (usually has longer middle section)
   - 1x Air Waybill (AWB)
   - 1x Commercial Invoice (INV)

---

## Processing Pipeline

### Step 1: Classification

**For each file in a job**:
- Send PDF to Gemini 2.5 Flash
- Identify document type: `entry_print`, `air_waybill`, `commercial_invoice`, `packing_list`, or `other`
- Store result temporarily

**API Call**:
```python
POST /api/classify-document
{
  "file_content": "<base64_encoded_pdf>",
  "filename": "2219477116_AWB.pdf"
}

Response:
{
  "document_type": "air_waybill",
}
```

---

### Step 2: Extraction

**For each classified document**:
- Send PDF + document type to Gemini 2.5 Flash with appropriate schema
- Extract structured data based on document type
- Store result temporarily

**Schemas**:
- **Entry Print**: consignee, declarant, AWB number, items[], totals, FTA info, etc.
- **Air Waybill**: shipper, consignee, AWB number, weight, pieces, origin, destination
- **Commercial Invoice**: supplier, buyer, invoice number, items[], totals, incoterms, etc.
- **Packing List**: items[], quantities, weights, dimensions, packaging details

**API Call**:
```python
POST /api/extract-document
{
  "file_content": "<base64_encoded_pdf>",
  "document_type": "air_waybill"
}

Sample Response:
{
  "document_type": "air_waybill",
  "data": {
    "awb_number": "582955943",
    "shipper_name": "ABC Company",
    "consignee_name": "XYZ Pty Ltd",
    "origin": "USA",
    "destination": "MEL",
    "pieces": 5,
    "weight": 123.5,
    "weight_unit": "KG"
  }
}
```

---

### Step 3: Validation (Checklist)

**For each job** (after all documents are extracted):
- Run header-level checks (document field comparisons)
- Run line-item checks (per-item validations including tariff codes)
- Generate PASS/FAIL/QUESTIONABLE/N/A status for each check

**Header Checks** (examples):
1. Consignee name matches (Entry Print vs Commercial Invoice)
2. AWB number matches (Entry Print vs Air Waybill vs Commercial Invoice)
3. Invoice total matches declared value (Entry Print vs Commercial Invoice)
4. Country of origin matches (Entry Print vs Commercial Invoice)
5. Supplier name matches (Entry Print vs Commercial Invoice)
6. FTA eligibility consistent (Entry Print vs Commercial Invoice)
7. Incoterms match (Entry Print vs Commercial Invoice)

**Line Item Checks** (examples per line):
1. Description consistency (Entry vs Invoice)
2. Quantity matches (Entry vs Invoice)
3. Unit price matches (Entry vs Invoice)
4. Country of origin matches (Entry vs Invoice)
5. **Tariff code validation** (Entry code vs AI-suggested code)
6. FTA claims consistent (Entry vs Invoice)

**Tariff Validation Process**:
```python
For each line item:
  1. Extract: description, supplier_name, declared_hs_code, declared_stat_code
  2. Call classifier:
     - AU: POST /classify/au → 8-digit HS + 2-digit stat + TCO
     - NZ: POST /classify/nz → 8-digit HS + 3-char stat key
  3. Compare:
     - declared_code vs suggested_code
     - Status: PASS (exact match), QUESTIONABLE (differs), FAIL (major error)
  4. Include reasoning from AI
```

**API Call**:
```python
POST /api/validate-job
{
  "job_id": "2219477116",
  "country": "AU",  # or "NZ"
  "extracted_data": {
    "entry_print": { ... },
    "air_waybill": { ... },
    "commercial_invoice": { ... },
    "packing_list": { ... }  # optional
  }
}

Response:
{
  "job_id": "2219477116",
  "header_checks": [
    {
      "check_id": "consignee_match",
      "criteria": "Consignee name verification",
      "status": "PASS",
      "source_value": "XYZ Pty Ltd",
      "target_value": "XYZ PTY LTD",
      "assessment": "Names match despite case difference"
    },
    ...
  ],
  "line_items": [
    {
      "line_number": 1,
      "description": {
        "entry": "Cotton t-shirts",
        "invoice": "100% Cotton T-Shirts",
        "status": "PASS",
        "assessment": "Descriptions are consistent"
      },
      "quantity": { ... },
      "price": { ... },
      "tariff": {
        "entry_hs": "61091000",
        "entry_stat": "00",
        "suggested_hs": "61091000",
        "suggested_stat": "00",
        "status": "PASS",
        "assessment": "Tariff code is correct",
        "reasoning": "AI analysis: Cotton knitted t-shirts correctly classified under 6109.10.00.00"
      }
    },
    ...
  ]
}
```

---

## XLSX Output Format

### Sheet 1: Job Summary
```
| Job ID      | Files Processed | Entry Print | Air Waybill | Invoice | Status    | Job Folder Path                            | Processed At        |
|-------------|----------------|-------------|-------------|---------|-----------|-------------------------------------------|---------------------|
| 2219477116  | 4              | ✓           | ✓           | ✓       | Completed | /output/2025-10-13_run_001/job_2219477116 | 2025-10-13 14:30:00 |
| 2219477676  | 3              | ✓           | ✓           | ✓       | Completed | /output/2025-10-13_run_001/job_2219477676 | 2025-10-13 14:30:05 |
| 2555462195  | 3              | ✓           | ✓           | ✓       | Completed | /output/2025-10-13_run_001/job_2555462195 | 2025-10-13 14:30:10 |
```

### Sheet 2: Header Checklist Results
```
| Job ID     | Check ID | Auditing Criteria              | Priority | Status       | Source Value  | Target Value  | Assessment              |
|------------|----------|--------------------------------|----------|--------------|---------------|---------------|-------------------------|
| 2219477116 | H-01     | Consignee name verification    | High     | PASS         | XYZ Pty Ltd   | XYZ PTY LTD   | Names match             |
| 2219477116 | H-02     | AWB number consistency         | High     | PASS         | 582955943     | 582955943     | AWB numbers match       |
| 2219477116 | H-03     | Invoice total vs declared value| High     | QUESTIONABLE | 5000.00 USD   | 5050.00 USD   | Minor discrepancy (1%)  |
| 2219477116 | H-04     | Country of origin match        | High     | PASS         | China         | CN            | Same country            |
| ...        |          |                                |          |              |               |               |                         |
```

### Sheet 3: Line Item Checklist Results
```
| Job ID     | Line# | Description (Entry)    | Description (Invoice)  | Desc Status | Qty Entry | Qty Invoice | Qty Status | HS Code Entry | HS Code Suggested | Stat Entry | Stat Suggested | Tariff Status | Tariff Assessment                          |
|------------|-------|------------------------|------------------------|-------------|-----------|-------------|------------|---------------|-------------------|------------|----------------|---------------|--------------------------------------------|
| 2219477116 | 1     | Cotton t-shirts        | 100% Cotton T-Shirts   | PASS        | 500       | 500         | PASS       | 61091000      | 61091000          | 00         | 00             | PASS          | Correct classification                     |
| 2219477116 | 2     | Polyester jackets      | Men's Polyester Jacket | PASS        | 200       | 200         | PASS       | 62011000      | 62011310          | 00         | 00             | QUESTIONABLE  | Should be more specific: 6201.13.10.00     |
| 2219477116 | 3     | Leather shoes          | Genuine Leather Shoes  | PASS        | 100       | 100         | PASS       | 64039900      | 64039100          | 00         | 00             | FAIL          | Incorrect: should be 6403.91.00.00 (uppers)|
| ...        |       |                        |                        |             |           |             |            |               |                   |            |                |               |                                            |
```

### Sheet 4 (Optional): Extracted Data - Entry Print
```
| Job ID     | Consignee Name  | Declarant       | AWB Number | Total Value | Currency | FTA | Country of Origin | Line 1 Desc        | Line 1 Qty | Line 1 HS    | ... |
|------------|-----------------|-----------------|------------|-------------|----------|-----|-------------------|--------------------|------------|--------------|-----|
| 2219477116 | XYZ Pty Ltd     | ABC Customs Pty | 582955943  | 5000.00     | USD      | Yes | China             | Cotton t-shirts    | 500        | 61091000.00  | ... |
| ...        |                 |                 |            |             |          |     |                   |                    |            |              |     |
```

### Sheet 5 (Optional): Extracted Data - Commercial Invoice
```
| Job ID     | Supplier Name | Buyer Name   | Invoice Number | Total Amount | Currency | Incoterms | Line 1 Desc           | Line 1 Qty | Line 1 Price | ... |
|------------|---------------|--------------|----------------|--------------|----------|-----------|----------------------|------------|--------------|-----|
| 2219477116 | ABC Company   | XYZ Pty Ltd  | INV-12345      | 5050.00      | USD      | FOB       | 100% Cotton T-Shirts | 500        | 10.10        | ... |
| ...        |               |              |                |              |          |           |                      |            |              |     |
```

---

## API Endpoints (Backend)

### Document Processing
```
POST /api/classify-document
  Input: { file_content: base64, filename: string }
  Output: { document_type: string, confidence: number }

POST /api/extract-document
  Input: { file_content: base64, document_type: string }
  Output: { document_type: string, data: object }

POST /api/validate-job
  Input: { job_id: string, country: "AU"|"NZ", extracted_data: object }
  Output: { job_id: string, header_checks: array, line_items: array }
```

### Batch Processing
```
POST /api/process-batch
  Input: {
    files: [
      { filename: string, content: base64 },
      ...
    ],
    country: "AU" | "NZ"
  }
  Output: {
    jobs: [
      {
        job_id: string,
        files: array,
        classification_results: array,
        extraction_results: object,
        validation_results: object
      },
      ...
    ]
  }

POST /api/generate-xlsx
  Input: { jobs: array }
  Output: { xlsx_content: base64, filename: string }
```

---

## Frontend Flow

### Single Page Application

```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│  📤 Upload Files                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  Drag & drop PDFs here                          │   │
│  │  or click to browse                             │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  🌍 Region: [●] Australia  [ ] New Zealand              │
│                                                         │
│  📁 Detected Jobs (auto-grouped):                       │
│  ├─ 2219477116 (3 files)                               │
│  ├─ 2219477676 (3 files)                               │
│  └─ 2555462195 (3 files)                               │
│                                                         │
│  [Process All Jobs]                                     │
│                                                         │
│  ⏳ Processing Status:                                  │
│  ├─ 2219477116: [████████░░] 80% (Validating...)       │
│  ├─ 2219477676: [██████████] 100% ✓ Complete           │
│  └─ 2555462195: [██░░░░░░░░] 20% (Extracting...)       │
│                                                         │
│  [Download Results XLSX]                                │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### User Experience
1. **Upload**: Drag multiple PDF files
2. **Auto-detect**: System shows grouped jobs by number
3. **Select region**: AU or NZ (affects tariff validation)
4. **Process**: Click button to start batch processing
5. **Monitor**: See real-time progress for each job
6. **Download**: Get XLSX file when complete

---

## Technical Implementation

### Frontend (`frontend/audit`)
```typescript
// Main page: /app/audit/page.tsx
- File upload component
- Auto-grouping logic
- Region selector
- Progress display
- XLSX download button

// API routes: /app/api/
- /api/process-batch/route.ts - Main processing endpoint
- /api/download-xlsx/route.ts - Generate and download XLSX
```

### Backend (`backend`)
```python
# New endpoints in main.py or separate routers
- POST /api/classify-document - Classify single PDF
- POST /api/extract-document - Extract from single PDF
- POST /api/validate-job - Validate one job's documents
- POST /api/process-batch - Process multiple jobs at once
- POST /api/generate-xlsx - Create Excel output

# Reuse existing classifiers
- /classify/au - Already implemented
- /classify/nz - Already implemented

# New modules needed
- document_classifier.py - PDF classification logic
- document_extractor.py - PDF extraction logic
- checklist_validator.py - Validation logic (port from audit-v2)
- xlsx_generator.py - Excel file generation (openpyxl)
```

---

## File Storage Structure

After classification, files are saved with document type labels and organized in a hierarchical folder structure:

```
/output_directory/
├── 2025-10-13_run_001/                                    # Date + Run number
│   ├── job_2219477116/                                    # Job folder
│   │   ├── 2219477116_AWB_OSA_OAA_8VD_20250929_132113_air_waybill.pdf
│   │   ├── 2219477116_INV_OSA_OAA_E5D_20250929_132104_commercial_invoice.pdf
│   │   ├── 2219477116_INV_OSA_OAA_E5D_20250929_132104_commercial_invoice.json  # Extracted data
│   │   ├── 2219477116_582955943_OSA_MEL_250929_0421_P_air_waybill.pdf
│   │   ├── 2219477116^^13387052^FRML^CIM^^_ENT_SYD_GTW_099_20251002_062500_entry_print.pdf
│   │   └── 2219477116^^13387052^FRML^CIM^^_ENT_SYD_GTW_099_20251002_062500_entry_print.json  # Extracted data
│   │
│   ├── job_2219477676/                                    # Another job
│   │   ├── 2219477676_AWB_OSA_OAA_SM3_20250929_132403_air_waybill.pdf
│   │   ├── 2219477676_INV_OSA_OAA_23A_20250929_132427_commercial_invoice.pdf
│   │   ├── 2219477676_INV_OSA_OAA_23A_20250929_132427_commercial_invoice.json
│   │   ├── 2219477676_582955943_OSA_MEL_250929_0424_P_entry_print.pdf
│   │   └── 2219477676_582955943_OSA_MEL_250929_0424_P_entry_print.json
│   │
│   ├── job_2555462195/                                    # Third job
│   │   └── ...
│   │
│   └── audit_results_2025-10-13_run_001.xlsx              # Excel output for this run
│
├── 2025-10-13_run_002/                                    # Second run same day
│   ├── job_2219477200/
│   │   └── ...
│   └── audit_results_2025-10-13_run_002.xlsx
│
└── 2025-10-14_run_001/                                    # Next day
    └── ...
```

### File Naming Convention

**After classification, append document type**:
- Original: `2219477116_AWB_OSA_OAA_8VD_20250929_132113.pdf`
- Saved PDF: `2219477116_AWB_OSA_OAA_8VD_20250929_132113_air_waybill.pdf`
- Saved JSON: Only for `entry_print` and `commercial_invoice`

**Document Type Labels**:
- `_entry_print` - Customs entry/declaration (PDF + JSON extraction)
- `_air_waybill` - Air waybill (AWB) (PDF only, no extraction)
- `_commercial_invoice` - Commercial invoice (PDF + JSON extraction)
- `_packing_list` - Packing list (PDF only, no extraction)
- `_other` - Unclassified documents (PDF only, no extraction)

### Run Number Logic

**For the same date**:
1. Check existing folders starting with today's date (e.g., `2025-10-13_run_*`)
2. Find the highest run number
3. Create new folder with `run_N+1`

**Example**:
- First run today: `2025-10-13_run_001`
- Second run today: `2025-10-13_run_002`
- First run tomorrow: `2025-10-14_run_001`

## Data Flow (With File Storage)

All data is held **in memory** during processing, then saved to disk:

```python
{
  "run_id": "2025-10-13_run_001",
  "output_path": "/output_directory/2025-10-13_run_001",
  "country": "AU",
  "jobs": [
    {
      "job_id": "2219477116",
      "job_folder": "/output_directory/2025-10-13_run_001/job_2219477116",
      "files": [
        {
          "original_filename": "2219477116_AWB.pdf",
          "saved_filename": "2219477116_AWB_OSA_OAA_8VD_20250929_132113_air_waybill.pdf",
          "saved_path": "/output_directory/2025-10-13_run_001/job_2219477116/2219477116_AWB_OSA_OAA_8VD_20250929_132113_air_waybill.pdf",
          "classification": {
            "document_type": "air_waybill"
          },
          "extraction": {
            "awb_number": "582955943",
            "shipper_name": "ABC Company",
            ...
          }
        },
        ...
      ],
      "validation": {
        "header_checks": [...],
        "line_items": [...]
      }
    },
    ...
  ],
  "xlsx_output": "/output_directory/2025-10-13_run_001/audit_results_2025-10-13_run_001.xlsx"
}
```

### Processing Flow with File Storage

1. **Initialize Run**
   - Create run folder: `YYYY-MM-DD_run_NNN`
   - Determine run number based on existing folders

2. **Upload & Group**
   - User uploads multiple PDFs
   - Group by job number

3. **Classify & Save**
   - Classify each document
   - Create job folder: `job_XXXXXXXXX`
   - Save file with document type label
   - Keep original filename + append `_document_type`

4. **Extract Data**
   - Read from saved files
   - Extract structured data
   - Keep in memory for validation

5. **Validate**
   - Run all checklist validations
   - Generate results

6. **Generate XLSX**
   - Create Excel with all results
   - Save to run folder
   - Include file paths in results

7. **Return Paths**
   - Send folder paths to frontend
   - Allow download of XLSX
   - Show where files are saved

---

## Libraries Needed

### Backend
```python
# PDF processing
python-multipart  # File uploads
PyPDF2  # PDF parsing (if needed)

# Excel generation
openpyxl  # Write XLSX files

# Existing
pydantic-ai  # Already have
fastapi  # Already have
google-generativeai  # Already have
```

### Frontend
```typescript
// Excel handling
xlsx or exceljs  # If generating client-side

// Existing
next.js  # Already have
react  # Already have
```

---

## Docker Configuration

### Environment Variables

```bash
# .env file
OUTPUT_DIRECTORY=/app/output           # Internal container path
LOCAL_OUTPUT_PATH=/path/to/your/local/audit_output  # Your local machine path
```

### Backend Dockerfile

```dockerfile
# File: backend/Dockerfile

FROM python:3.11-slim

WORKDIR /app

# Install uv
RUN pip install uv

# Copy project files
COPY pyproject.toml uv.lock ./
COPY src ./src

# Install dependencies
RUN uv sync

# Create output directory
RUN mkdir -p /app/output

# Expose port
EXPOSE 8000

# Run the application
CMD ["uv", "run", "granian", "--host", "0.0.0.0", "--port", "8000", "--interface", "asgi", "src.ai_classifier.main:app"]
```

### Frontend Dockerfile

```dockerfile
# File: frontend/audit/Dockerfile

FROM oven/bun:1 as builder

WORKDIR /app

# Copy package files
COPY package.json bun.lock ./

# Install dependencies
RUN bun install

# Copy source
COPY . .

# Build
RUN bun run build

# Production image
FROM oven/bun:1-slim

WORKDIR /app

COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/public ./public

EXPOSE 3000

CMD ["bun", "start"]
```

### Docker Compose Configuration

```yaml
# File: docker-compose.yml

version: '3.8'

services:
  backend:
    build: ./backend
    container_name: clearai-audit-backend
    ports:
      - "8000:8000"
    environment:
      - DEBUG=true
      - ALLOWED_HOSTS=*
      - AUTH_TOKEN=${AUTH_TOKEN}
      - GOOGLE_GENAI_API_KEY=${GOOGLE_GENAI_API_KEY}
      - OUTPUT_DIRECTORY=/app/output
    volumes:
      # Mount local directory to container output directory
      - ${LOCAL_OUTPUT_PATH}:/app/output
      # Optional: Mount source code for development
      - ./backend/src:/app/src
    networks:
      - audit-network

  frontend:
    build: ./frontend/audit
    container_name: clearai-audit-frontend
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://localhost:8000
      - API_URL=http://backend:8000
    depends_on:
      - backend
    networks:
      - audit-network

networks:
  audit-network:
    driver: bridge
```

### Docker Commands

**Build and Run**:
```bash
# Create .env file with your local output path
echo "LOCAL_OUTPUT_PATH=/Users/pat/Documents/audit_output" > .env
echo "AUTH_TOKEN=your-secret-token" >> .env
echo "GOOGLE_GENAI_API_KEY=your-api-key" >> .env

# Build images
docker-compose build

# Start services
docker-compose up

# Or run in detached mode
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

**File Storage with Docker**:
```bash
# Your local machine path
/Users/pat/Documents/audit_output/
├── 2025-10-13_run_001/
│   ├── job_2219477116/
│   │   └── ...
│   └── audit_results_2025-10-13_run_001.xlsx
└── ...

# This maps to /app/output inside the container
# The backend writes to /app/output
# Docker syncs it to your local path
```

### Volume Mapping Explanation

**How it works**:
1. Backend application thinks it's writing to `/app/output`
2. Docker maps `/app/output` → your local `${LOCAL_OUTPUT_PATH}`
3. Files appear immediately in your local directory
4. Both container and host can read/write

**Benefits**:
- ✅ Files persist after container stops
- ✅ Easy to backup/share local files
- ✅ Can open files directly on local machine
- ✅ No need to copy files out of container

### Backend Code for File Storage

```python
# File: src/ai_classifier/file_manager.py

import os
from pathlib import Path
from datetime import datetime
import re

OUTPUT_BASE_DIR = Path(os.getenv("OUTPUT_DIRECTORY", "/app/output"))

def get_next_run_id() -> str:
    """Generate next run ID for today"""
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Ensure output directory exists
    OUTPUT_BASE_DIR.mkdir(parents=True, exist_ok=True)
    
    # Find existing runs for today
    existing_runs = []
    for folder in OUTPUT_BASE_DIR.iterdir():
        if folder.is_dir() and folder.name.startswith(today):
            match = re.match(rf"{today}_run_(\d+)", folder.name)
            if match:
                existing_runs.append(int(match.group(1)))
    
    # Get next run number
    next_run = max(existing_runs, default=0) + 1
    
    return f"{today}_run_{next_run:03d}"

def create_run_directory(run_id: str) -> Path:
    """Create directory for this run"""
    run_path = OUTPUT_BASE_DIR / run_id
    run_path.mkdir(parents=True, exist_ok=True)
    return run_path

def create_job_directory(run_path: Path, job_id: str) -> Path:
    """Create directory for a job within a run"""
    job_path = run_path / f"job_{job_id}"
    job_path.mkdir(parents=True, exist_ok=True)
    return job_path

def save_classified_file(
    file_content: bytes,
    original_filename: str,
    document_type: str,
    job_path: Path
) -> Path:
    """Save file with document type label"""
    # Remove .pdf extension
    base_name = original_filename.rsplit('.', 1)[0]
    
    # Add document type label
    new_filename = f"{base_name}_{document_type}.pdf"
    
    # Save file
    file_path = job_path / new_filename
    file_path.write_bytes(file_content)
    
    return file_path

# Usage in main processing
@router.post("/api/process-batch")
async def process_batch(files: List[UploadFile], country: str):
    # 1. Initialize run
    run_id = get_next_run_id()
    run_path = create_run_directory(run_id)
    
    # 2. Group files by job
    grouped_jobs = group_files_by_job(files)
    
    results = []
    
    for job_id, job_files in grouped_jobs.items():
        # 3. Create job directory
        job_path = create_job_directory(run_path, job_id)
        
        # 4. Classify and save files
        classified_files = []
        for file in job_files:
            content = await file.read()
            
            # Classify
            classification = await classify_document(content, file.filename)
            
            # Save with label
            saved_path = save_classified_file(
                content,
                file.filename,
                classification.document_type,
                job_path
            )
            
            classified_files.append({
                "original_filename": file.filename,
                "saved_filename": saved_path.name,
                "saved_path": str(saved_path),
                "document_type": classification.document_type
            })
        
        # 5. Extract, validate, etc.
        # ... rest of processing
        
        results.append({
            "job_id": job_id,
            "job_folder": str(job_path),
            "files": classified_files
        })
    
    # 6. Generate XLSX
    xlsx_path = run_path / f"audit_results_{run_id}.xlsx"
    generate_xlsx(results, xlsx_path)
    
    return {
        "run_id": run_id,
        "run_path": str(run_path),
        "xlsx_path": str(xlsx_path),
        "jobs": results
    }
```

## Advantages of This Simplified Approach

1. **No Database** - No persistence needed, faster development
2. **Simple UI** - Single page, drag-drop, download
3. **Broker-friendly** - Just send them the XLSX file or share the folder
4. **Organized Storage** - Files neatly organized by date, run, and job
5. **Easy to deploy** - Just Docker Compose
6. **Fast** - Process and export immediately
7. **Portable** - XLSX can be opened anywhere
8. **Auditable** - All results in one spreadsheet + original files preserved
9. **Docker-friendly** - Volume mapping keeps files on your local machine
10. **Traceable** - Can easily find and review past runs

---

## Migration from audit-v2

**What to Keep**:
- ✅ Classification logic (Gemini with schemas)
- ✅ Extraction logic (Gemini with schemas)
- ✅ Validation logic (checklist system)
- ✅ Tariff classification (AU/NZ classifiers)

**What to Remove**:
- ❌ Database (Prisma, PostgreSQL)
- ❌ OneDrive integration
- ❌ Broker authentication
- ❌ Organization multi-tenancy
- ❌ Job management UI
- ❌ Streaming results
- ❌ Admin panel

**What to Add**:
- ➕ Auto-grouping logic (by filename prefix)
- ➕ Batch processing endpoint
- ➕ XLSX generation
- ➕ Progress tracking (in-memory)

---

## Current Implementation Status

### ✅ Phase 1: File Grouping (COMPLETED)

**Backend (`/backend/src/ai_classifier/`)**:
- ✅ `util/batch_processor.py` - File grouping logic
  - `extract_job_id()` - Extract job number from filename
  - `group_files_by_job()` - Group files by job ID
  - `summarize_grouped_jobs()` - Create summary for logging
- ✅ `routes/batch.py` - Batch processing API route
  - `POST /api/upload-batch` - Upload and group files
  - Detailed logging to backend console
  - Returns grouped job summary
- ✅ Integrated into `main.py`

**Frontend (`/frontend/audit/src/app/page.tsx`)**:
- ✅ Beautiful drag-and-drop file upload interface
- ✅ PDF-only file filtering
- ✅ File list with size display
- ✅ Individual file removal
- ✅ Upload to backend API
- ✅ Display grouped jobs result
- ✅ Error handling

### ✅ Phase 2: Document Classification (COMPLETED)

**Backend (`/backend/src/ai_classifier/`)**:
- ✅ `document_classifier.py` - PDF classification using PydanticAI + Gemini 2.5 Flash
  - `DocumentClassificationOutput` - Structured output model
  - `classify_document()` - Main classification function
  - Document types: `entry_print`, `air_waybill`, `commercial_invoice`, `packing_list`, `other`
  - Returns: document_type

### ✅ Phase 3: Data Extraction (COMPLETED)

**Backend (`/backend/src/ai_classifier/`)**:
- ✅ `document_extractor.py` - Structured data extraction using PydanticAI + Gemini 2.5 Flash
  - **Reusable agent initialization**: `_get_extraction_agent(document_type, output_model)`
  - **Pydantic Models** (converted from TypeScript schemas):
    - `EntryPrintExtraction` - Full customs entry with line items (70+ fields)
    - `CommercialInvoiceExtraction` - Invoice with line items (25+ fields)
    - `AirWaybillExtraction` - Model defined but **extraction disabled** (header data sufficient for validation)
  - **Extraction Functions**:
    - `extract_entry_print()` - Extract from customs entry documents
    - `extract_commercial_invoice()` - Extract from invoice documents
    - `extract_document_data()` - Router function for all types
  - **Active Extraction**: `entry_print`, `commercial_invoice` only
  - **Classification Only**: `air_waybill`, `packing_list`, `other`
  - Parallel extraction with classification
  - Automatic fallback if extraction fails
- ✅ `file_manager.py` - File organization and storage
  - `get_next_run_id()` - Generate run ID with auto-increment
  - `create_run_directory()` - Create date-based run folders
  - `create_job_directory()` - Create job-specific folders
  - `save_classified_file()` - Save files with document type labels
  - `save_extraction_json()` - Save extracted data as JSON with matching filename
- ✅ `routes/batch.py` - Extended with full processing
  - `POST /api/process-batch` - Full classification + extraction pipeline
  - Detailed logging for each classification and extraction step
  - Retry logic: 3 attempts with exponential backoff (1s, 2s, 4s)
  - Handles 503, timeout, and rate limit errors
  - Parallel processing of all files in a job
  - Returns comprehensive results with file paths and extracted data
- ✅ Integrated into `main.py`

**Frontend (`/frontend/audit/src/app/page.tsx`)**:
- ✅ Two-button interface: "Group Files Only" vs "Classify & Process"
- ✅ Processing state with loading indicators
- ✅ Beautiful classification results display
  - Run ID and output path
  - Per-job folder structure
  - Document type badges
  - "✓ Data Extracted" indicator
  - Collapsible extracted data viewer (JSON format)
  - Saved file paths

**How to Test**:
```bash
# 1. Set up environment files

# Backend .env (backend/.env):
# GEMINI_API_KEY=your_api_key_here
# OUTPUT_DIRECTORY=/app/output

# Root .env (project root .env):
# LOCAL_OUTPUT_PATH=./output  # Or absolute path like /Users/pat/Desktop/audit_output

# Quick setup:
cp env.example .env
# Edit .env and set LOCAL_OUTPUT_PATH to your desired location

# 2. Rebuild backend (important for new dependencies)
docker-compose build backend

# 3. Start services
docker-compose up

# 4. Open browser
http://localhost:3000

# 5. Upload sample PDFs from OneDrive_1_09-10-2025/
# - Drag and drop or click to browse
# - Click "🚀 Classify & Process"
# - See classification results on screen
# - Check backend logs for detailed processing info
# - Check LOCAL_OUTPUT_PATH folder for saved files (e.g., ./output/)
```

**Example Backend Log Output**:
```
================================================================================
🚀 BATCH PROCESSING - Received 3 file(s)
================================================================================

📂 Created run directory: /app/output/2025-10-13_run_001
   Run ID: 2025-10-13_run_001

📊 Grouped into 1 job(s)

================================================================================
📁 Processing Job: 2219477116 (3 files)
================================================================================
   Created job folder: /app/output/2025-10-13_run_001/job_2219477116

   [1/3] Processing: 2219477116_AWB_OSA_OAA_8VD_20250929_132113.pdf
      🔍 Classifying document... (attempt 1/3)
      ✓ Type: air_waybill
      💾 Saving file...
      ✓ Saved as: 2219477116_AWB_OSA_OAA_8VD_20250929_132113_air_waybill.pdf

   [2/3] Processing: 2219477116_INV_OSA_OAA_E5D_20250929_132104.pdf
      🔍 Classifying document... (attempt 1/3)
      ⚠️  Classification failed: status_code: 503, model_name: gemini-2.5-flash, message: The request timed out
      🔄 Retrying in 1s... (attempt 2/3)
      🔍 Classifying document... (attempt 2/3)
      ✓ Type: commercial_invoice
      💾 Saving file...
      ✓ Saved as: 2219477116_INV_OSA_OAA_E5D_20250929_132104_commercial_invoice.pdf

   [3/3] Processing: 2219477116^^13387052^FRML^CIM^^_ENT_SYD_GTW_099_20251002_062500.pdf
      🔍 Classifying document... (attempt 1/3)
      ✓ Type: entry_print
      💾 Saving file...
      ✓ Saved as: 2219477116^^13387052^FRML^CIM^^_ENT_SYD_GTW_099_20251002_062500_entry_print.pdf

   ✅ Job 2219477116 complete: 3 files processed

================================================================================
🎉 BATCH PROCESSING COMPLETE
   Run ID: 2025-10-13_run_001
   Total files: 3/3
   Total jobs: 1
   Output: /app/output/2025-10-13_run_001
================================================================================
```

**File Structure After Processing**:
```
/app/output/
└── 2025-10-13_run_001/
    └── job_2219477116/
        ├── 2219477116_AWB_OSA_OAA_8VD_20250929_132113_air_waybill.pdf
        ├── 2219477116_INV_OSA_OAA_E5D_20250929_132104_commercial_invoice.pdf
        ├── 2219477116_INV_OSA_OAA_E5D_20250929_132104_commercial_invoice.json    # ✓ Extracted data
        ├── 2219477116^^13387052^FRML^CIM^^_ENT_SYD_GTW_099_20251002_062500_entry_print.pdf
        └── 2219477116^^13387052^FRML^CIM^^_ENT_SYD_GTW_099_20251002_062500_entry_print.json    # ✓ Extracted data
```

---

## Checklist System

### Overview

The audit system uses JSON-based checklists that define validation rules for customs documents. Each region (AU/NZ) has its own checklist with header-level and valuation checks.

### Checklist Structure

**Location**: `/checklists/` directory in project root

**Files**:
- `au_checklist.json` - Australian customs audit checklist
- `nz_checklist.json` - New Zealand customs audit checklist
- `README.md` - Documentation for checklist format and usage

### Categories

Each checklist is organized into two main categories:

#### 1. Header-Level Cross-Reference Checks
Document-level validations that compare data across multiple documents (entry print, commercial invoice, air waybill).

**Examples**:
- Owner match (based on incoterms)
- Supplier consistency
- Invoice number match
- Currency consistency
- Incoterm validation

#### 2. Valuation Elements Checklist
FOB, CIF, freight, insurance, and other valuation-related validations.

**Examples**:
- FOB value match
- CIF value match
- Transport & Insurance costs
- Invoice total match
- Freight validation (based on incoterm)

### Checklist Item Format

Each checklist item contains:

```json
{
  "id": "au_h_001",
  "auditing_criteria": "Owner match",
  "priority": "High",
  "description": "Detailed description of what to check",
  "checking_logic": "Step-by-step instructions for validation",
  "pass_conditions": "Clear criteria for passing the check",
  "compare_fields": {
    "source_doc": "entry_print",
    "source_field": "ownerName",
    "target_doc": "commercial_invoice",
    "target_field": "buyer_company_name"
  }
}
```

### Validation Output

Each checklist item validation produces:

```python
{
  "check_id": "au_h_001",
  "auditing_criteria": "Owner match",
  "status": "PASS" | "FAIL" | "QUESTIONABLE",
  "assessment": "Detailed reasoning with actual values",
  "source_document": "entry_print",
  "target_document": "commercial_invoice",
  "source_value": "DHL Express Australia Pty Ltd",
  "target_value": "DHL Express Australia"
}
```

### Validation Status

- **PASS**: Clear match or acceptable variation according to pass conditions
- **FAIL**: Clear mismatch or violation of pass conditions
- **QUESTIONABLE**: Ambiguous situation requiring human review

### AU Checklist Summary

**Header Checks (5)**:
1. Owner match (incoterm-based)
2. Supplier match
3. Incoterms consistency
4. Currency match
5. Invoice number match

**Valuation Checks (6)**:
1. FOB value match
2. CIF value match
3. Transport & Insurance costs
4. Invoice total match
5. Freight cost validation
6. Insurance cost validation

### NZ Checklist Summary

**Header Checks (14)**:
1. Entry type (Simplified vs Normal based on value)
2. Client code consistency
3. Supplier code validation
4. Invoice number match
5. Currency match
6. Incoterm match
7. Country of origin consistency
8. Country of export match
9. Port of origin consistency
10. Relationship indicator (Y/R/N)
11. Weight consistency
12. Package count consistency
13. Description consistency
14. Preference claimed validation

**Valuation Checks (4)**:
1. VFD (Value for Duty) validation
2. Freight validation
3. Invoice total consistency
4. Core vs repair value

### Backend Implementation

**Python Modules**:

1. **`checklist_models.py`**:
   - Pydantic models for checklist configuration
   - JSON loader with caching
   - Prompt builder for validation
   - Field extraction utilities

2. **`checklist_validator.py`**:
   - PydanticAI agent using Gemini 2.5 Flash
   - Validation engine for checklist items
   - Batch validation for header and valuation checks
   - Error handling and retry logic

**Usage Example**:
```python
from ai_classifier.checklist_validator import validate_all_checks

# Run all checks for a job
results = await validate_all_checks(
    region="AU",
    extracted_data={
        "entry_print": entry_data,
        "commercial_invoice": invoice_data,
        "air_waybill": awb_data
    }
)

# Results grouped by category
header_results = results["header"]  # List[ChecklistValidationOutput]
valuation_results = results["valuation"]  # List[ChecklistValidationOutput]
summary = results["summary"]  # {"total": 11, "passed": 9, "failed": 1, "questionable": 1}
```

### AI Validation Approach

The system uses **Gemini 2.5 Flash** with structured output (PydanticAI) to:
1. Read the checking logic and pass conditions
2. Compare extracted values from source and target documents
3. Determine PASS/FAIL/QUESTIONABLE status
4. Generate detailed assessment with reasoning

**Key Features**:
- Low temperature (0.2) for consistent validation
- Fuzzy matching for company names
- Smart handling of null/N/A values
- Automatic retry on failures
- Detailed reasoning with actual values cited

### Future Enhancements

**Frontend Checklist Editor** (Planned):
- View all checklist items
- Edit checking logic and pass conditions
- Enable/disable specific checks
- Add custom organization-specific checks
- Export/import checklist configurations
- Version control for checklist changes

**Line-Item Validation** (TODO):
- Will use fixed Python logic (not AI)
- Compare entry line items with invoice line items
- Validate: description, quantity, price, tariff, origin, FTA
- Separate from header/valuation checks

---

## Next Steps

### ✅ Phase 4: Checklist Validation (PARTIALLY COMPLETE)

**Completed**:
- ✅ Created JSON checklist configurations for AU and NZ (`/checklists/`)
- ✅ Built Pydantic models for checklist validation (`checklist_models.py`)
- ✅ Implemented PydanticAI validator with Gemini 2.5 Flash (`checklist_validator.py`)
- ✅ Header-level validation support
- ✅ Valuation validation support
- ✅ Dynamic checklist loading from JSON

**Pending**:
- [ ] Add `POST /api/validate-job` endpoint in batch route
- [ ] Integrate tariff classification validation (AU/NZ classifiers)
- [ ] Save validation results as JSON alongside extracted data
- [ ] Line-item validation (will be added later with fixed logic)

**Files**:
- `/checklists/au_checklist.json` - Australian checklist (5 header + 6 valuation checks)
- `/checklists/nz_checklist.json` - New Zealand checklist (14 header + 4 valuation checks)
- `backend/src/ai_classifier/checklist_models.py` - Pydantic models and config loader
- `backend/src/ai_classifier/checklist_validator.py` - Validation engine with PydanticAI

### Phase 5: XLSX Generation (TODO)
- [ ] Create `xlsx_generator.py`
- [ ] Install openpyxl
- [ ] Generate 5-sheet Excel file
- [ ] Format for readability

### Phase 6: File Storage (TODO)
- [ ] Create `file_manager.py`
- [ ] Implement run folder creation
- [ ] Save classified files with labels
- [ ] Test Docker volume mapping

### Phase 7: Frontend Integration (TODO)
- [ ] Add progress tracking UI
- [ ] Add region selector (AU/NZ)
- [ ] Add XLSX download
- [ ] Polish UI/UX

---

## Testing with Sample Files

Use files from `OneDrive_1_09-10-2025/`:
```
Job 2219477116:
- 2219477116_582955943_OSA_MEL_250929_0421_P.pdf (Entry Print)
- 2219477116_AWB_OSA_OAA_8VD_20250929_132113.pdf (Air Waybill)
- 2219477116_INV_OSA_OAA_E5D_20250929_132104.pdf (Commercial Invoice)

Job 2219477676:
- 2219477676_582955943_OSA_MEL_250929_0424_P.pdf (Entry Print)
- 2219477676_AWB_OSA_OAA_SM3_20250929_132403.pdf (Air Waybill)
- 2219477676_INV_OSA_OAA_23A_20250929_132427.pdf (Commercial Invoice)

Job 2555462195:
- 2555462195_582955943_OSA_MEL_250929_0241_P.pdf (Entry Print)
- 2555462195_AWB_OSA_OAA_GL6_20250929_114144.pdf (Air Waybill)
- 2555462195_INV_OSA_OAA_FQ6_20250929_114155.pdf (Commercial Invoice)
```

---

## Summary

**Input**: Multiple PDFs uploaded at once  
**Processing**: Initialize Run → Auto-group → Classify & Save → Extract → Validate → Generate XLSX  
**Output**: 
- Organized folder structure with run and job folders
- Classified PDFs saved with document type labels
- Single XLSX file with complete audit results
- All stored in designated local directory (Docker volume mapped)

**Time**: ~2-5 minutes per job (depending on complexity)  
**Storage**: 
- Files organized by date and run number
- Permanent storage on local machine
- Easy to share entire run folder with brokers
- Files persist after Docker container stops

**Distribution**: 
- Share entire run folder OR
- Send XLSX file via email/download
- Brokers can access original classified documents

