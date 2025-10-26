# Implementation Roadmap - Simplified Audit System

This document provides a step-by-step guide to implementing the simplified batch processing system described in `SIMPLIFIED_SYSTEM_SPEC.md`.

---

## Phase 1: File Upload & Auto-Grouping ⏱️ 2-3 days

### Backend (`/backend`)

**1.1 Create file upload endpoint**
```python
# File: src/ai_classifier/batch_processor.py

from fastapi import UploadFile
from typing import List
import re

def extract_job_id(filename: str) -> str:
    """Extract job ID from filename (leading number before first underscore)"""
    match = re.match(r'^(\d+)_', filename)
    return match.group(1) if match else "unknown"

def group_files_by_job(files: List[UploadFile]) -> dict:
    """Group uploaded files by job ID"""
    jobs = {}
    for file in files:
        job_id = extract_job_id(file.filename)
        if job_id not in jobs:
            jobs[job_id] = []
        jobs[job_id].append(file)
    return jobs

@router.post("/api/upload-batch")
async def upload_batch(files: List[UploadFile]):
    """Upload multiple PDFs and group them by job number"""
    grouped = group_files_by_job(files)
    return {
        "total_files": len(files),
        "total_jobs": len(grouped),
        "jobs": {
            job_id: [f.filename for f in files]
            for job_id, files in grouped.items()
        }
    }
```

### Frontend (`/frontend/audit`)

**1.2 Create batch upload UI**
```typescript
// File: src/app/audit/page.tsx

'use client';

import { useState } from 'react';

interface GroupedJob {
  jobId: string;
  files: File[];
}

export default function AuditPage() {
  const [files, setFiles] = useState<File[]>([]);
  const [groupedJobs, setGroupedJobs] = useState<GroupedJob[]>([]);
  
  const handleFileUpload = (uploadedFiles: FileList) => {
    const fileArray = Array.from(uploadedFiles);
    setFiles(fileArray);
    
    // Auto-group by job ID
    const grouped = groupFilesByJobId(fileArray);
    setGroupedJobs(grouped);
  };
  
  const groupFilesByJobId = (files: File[]): GroupedJob[] => {
    const jobs: { [key: string]: File[] } = {};
    
    files.forEach(file => {
      const jobId = file.name.split('_')[0];
      if (!jobs[jobId]) jobs[jobId] = [];
      jobs[jobId].push(file);
    });
    
    return Object.entries(jobs).map(([jobId, files]) => ({
      jobId,
      files
    }));
  };
  
  return (
    <div className="p-8">
      <h1>DHL Express Audit System</h1>
      
      {/* File upload dropzone */}
      <div 
        className="border-2 border-dashed p-8 text-center"
        onDrop={(e) => {
          e.preventDefault();
          handleFileUpload(e.dataTransfer.files);
        }}
        onDragOver={(e) => e.preventDefault()}
      >
        <p>Drag & drop PDFs here or click to browse</p>
        <input
          type="file"
          multiple
          accept=".pdf"
          onChange={(e) => e.target.files && handleFileUpload(e.target.files)}
        />
      </div>
      
      {/* Display grouped jobs */}
      {groupedJobs.length > 0 && (
        <div className="mt-4">
          <h2>Detected Jobs: {groupedJobs.length}</h2>
          {groupedJobs.map(job => (
            <div key={job.jobId} className="border p-4 mb-2">
              <h3>Job {job.jobId}</h3>
              <ul>
                {job.files.map(file => (
                  <li key={file.name}>{file.name}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

**Deliverable**: Upload multiple PDFs and see them grouped by job number

---

## Phase 2: Document Classification ⏱️ 3-4 days

### Backend

**2.1 Port classification logic from audit-v2**
```python
# File: src/ai_classifier/document_classifier.py

from google import generativeai as genai
from pydantic import BaseModel
from enum import Enum

class DocumentType(str, Enum):
    ENTRY_PRINT = "entry_print"
    AIR_WAYBILL = "air_waybill"
    COMMERCIAL_INVOICE = "commercial_invoice"
    PACKING_LIST = "packing_list"
    OTHER = "other"

class ClassificationResult(BaseModel):
    document_type: DocumentType
    confidence: float
    reasoning: str

async def classify_document(pdf_content: bytes, filename: str) -> ClassificationResult:
    """Classify a PDF document using Gemini"""
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    prompt = """
    Analyze this customs document and classify it as one of:
    - entry_print: Customs entry/declaration form
    - air_waybill: Air waybill (AWB) with shipping details
    - commercial_invoice: Commercial invoice from supplier
    - packing_list: Packing list with item details
    - other: Any other document type
    
    Return JSON with: document_type, confidence (0-1), reasoning
    """
    
    # Upload PDF and get classification
    response = await model.generate_content([prompt, {"mime_type": "application/pdf", "data": pdf_content}])
    
    # Parse response and return structured result
    # (Add proper JSON parsing here)
    return ClassificationResult(
        document_type=DocumentType.ENTRY_PRINT,
        confidence=0.95,
        reasoning="Document contains customs entry fields"
    )

@router.post("/api/classify-document")
async def classify_document_endpoint(file: UploadFile):
    """Classify a single PDF document"""
    content = await file.read()
    result = await classify_document(content, file.filename)
    return result
```

**2.2 Batch classification endpoint**
```python
@router.post("/api/classify-batch")
async def classify_batch(files: List[UploadFile]):
    """Classify multiple documents"""
    results = []
    for file in files:
        content = await file.read()
        result = await classify_document(content, file.filename)
        results.append({
            "filename": file.filename,
            "classification": result
        })
    return {"results": results}
```

**Deliverable**: Classify each uploaded PDF as Entry Print, AWB, Invoice, or Packing List

---

## Phase 3: Data Extraction ⏱️ 4-5 days

### Backend

**3.1 Port extraction schemas from audit-v2**
```python
# File: src/ai_classifier/schemas.py

from pydantic import BaseModel, Field
from typing import List, Optional

class LineItem(BaseModel):
    line_number: int
    description: str
    quantity: float
    unit: str
    unit_price: Optional[float] = None
    total_price: Optional[float] = None
    hs_code: Optional[str] = None
    stat_code: Optional[str] = None
    country_of_origin: Optional[str] = None

class EntryPrintData(BaseModel):
    awb_number: str
    consignee_name: str
    declarant_name: str
    country_of_origin: str
    total_value: float
    currency: str
    fta_claimed: bool
    items: List[LineItem]

class AirWaybillData(BaseModel):
    awb_number: str
    shipper_name: str
    consignee_name: str
    origin: str
    destination: str
    pieces: int
    weight: float
    weight_unit: str

class CommercialInvoiceData(BaseModel):
    invoice_number: str
    invoice_date: str
    supplier_name: str
    buyer_name: str
    incoterms: str
    total_amount: float
    currency: str
    items: List[LineItem]

class PackingListData(BaseModel):
    items: List[LineItem]
    total_packages: int
    total_weight: float
```

**3.2 Extraction logic**
```python
# File: src/ai_classifier/document_extractor.py

async def extract_document(
    pdf_content: bytes,
    document_type: DocumentType
) -> dict:
    """Extract structured data from a PDF based on its type"""
    
    schema = {
        DocumentType.ENTRY_PRINT: EntryPrintData,
        DocumentType.AIR_WAYBILL: AirWaybillData,
        DocumentType.COMMERCIAL_INVOICE: CommercialInvoiceData,
        DocumentType.PACKING_LIST: PackingListData,
    }.get(document_type)
    
    if not schema:
        return {"error": "Unsupported document type"}
    
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    prompt = f"""
    Extract all relevant information from this {document_type} document.
    Return data according to this schema: {schema.schema_json()}
    
    For line items, extract each item individually with all available fields.
    """
    
    response = await model.generate_content([
        prompt,
        {"mime_type": "application/pdf", "data": pdf_content}
    ])
    
    # Parse response and validate against schema
    extracted = schema.parse_raw(response.text)
    return extracted.dict()

@router.post("/api/extract-document")
async def extract_document_endpoint(
    file: UploadFile,
    document_type: DocumentType
):
    """Extract structured data from a classified document"""
    content = await file.read()
    result = await extract_document(content, document_type)
    return result
```

**Deliverable**: Extract structured data from each classified document

---

## Phase 4: Checklist Validation ⏱️ 5-7 days

### Backend

**4.1 Port validation logic from audit-v2**
```python
# File: src/ai_classifier/checklist_validator.py

from typing import Dict, List
from enum import Enum

class ValidationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    QUESTIONABLE = "QUESTIONABLE"
    NA = "N/A"

class HeaderCheck(BaseModel):
    check_id: str
    criteria: str
    status: ValidationStatus
    source_value: str
    target_value: str
    assessment: str

class LineItemCheck(BaseModel):
    line_number: int
    description_status: ValidationStatus
    quantity_status: ValidationStatus
    price_status: ValidationStatus
    tariff_status: ValidationStatus
    tariff_assessment: str
    entry_hs_code: str
    suggested_hs_code: str

async def validate_header_checks(
    entry_data: EntryPrintData,
    awb_data: AirWaybillData,
    invoice_data: CommercialInvoiceData
) -> List[HeaderCheck]:
    """Perform header-level validation checks"""
    
    checks = []
    
    # Check 1: AWB number consistency
    awb_check = await validate_awb_numbers(entry_data, awb_data, invoice_data)
    checks.append(awb_check)
    
    # Check 2: Consignee name match
    consignee_check = await validate_consignee(entry_data, invoice_data)
    checks.append(consignee_check)
    
    # Check 3: Supplier name match
    supplier_check = await validate_supplier(entry_data, invoice_data)
    checks.append(supplier_check)
    
    # Add more checks...
    
    return checks

async def validate_line_items(
    entry_data: EntryPrintData,
    invoice_data: CommercialInvoiceData,
    country: str  # "AU" or "NZ"
) -> List[LineItemCheck]:
    """Validate line items including tariff classification"""
    
    results = []
    
    # Match line items between entry and invoice
    matched_items = match_line_items(entry_data.items, invoice_data.items)
    
    for entry_item, invoice_item in matched_items:
        # Validate each field
        desc_status = await validate_descriptions(entry_item, invoice_item)
        qty_status = await validate_quantities(entry_item, invoice_item)
        price_status = await validate_prices(entry_item, invoice_item)
        
        # Validate tariff code using existing classifier
        tariff_result = await validate_tariff_code(
            entry_item,
            invoice_item,
            country
        )
        
        results.append(LineItemCheck(
            line_number=entry_item.line_number,
            description_status=desc_status,
            quantity_status=qty_status,
            price_status=price_status,
            tariff_status=tariff_result['status'],
            tariff_assessment=tariff_result['assessment'],
            entry_hs_code=entry_item.hs_code,
            suggested_hs_code=tariff_result['suggested_code']
        ))
    
    return results

async def validate_tariff_code(
    entry_item: LineItem,
    invoice_item: LineItem,
    country: str
) -> dict:
    """Validate tariff code using AU/NZ classifier"""
    
    # Call existing classifier endpoint
    endpoint = f"/classify/{country.lower()}"
    classification = await call_classifier(
        endpoint,
        {
            "items": [{
                "id": str(entry_item.line_number),
                "description": invoice_item.description,
                "supplier_name": ""  # Get from invoice if available
            }]
        }
    )
    
    suggested_code = classification['results'][0]['best_suggested_hs_code']
    suggested_stat = classification['results'][0]['best_suggested_stat_code']
    reasoning = classification['results'][0]['reasoning']
    
    # Compare with declared code
    if entry_item.hs_code == suggested_code:
        status = ValidationStatus.PASS
        assessment = f"Correct classification. {reasoning}"
    elif entry_item.hs_code[:6] == suggested_code[:6]:
        status = ValidationStatus.QUESTIONABLE
        assessment = f"Possible alternative: {suggested_code}. {reasoning}"
    else:
        status = ValidationStatus.FAIL
        assessment = f"Incorrect classification. Suggested: {suggested_code}. {reasoning}"
    
    return {
        "status": status,
        "assessment": assessment,
        "suggested_code": suggested_code
    }

@router.post("/api/validate-job")
async def validate_job_endpoint(
    job_id: str,
    country: str,
    extracted_data: dict
):
    """Validate all documents in a job"""
    
    entry_data = EntryPrintData(**extracted_data['entry_print'])
    awb_data = AirWaybillData(**extracted_data['air_waybill'])
    invoice_data = CommercialInvoiceData(**extracted_data['commercial_invoice'])
    
    header_checks = await validate_header_checks(entry_data, awb_data, invoice_data)
    line_items = await validate_line_items(entry_data, invoice_data, country)
    
    return {
        "job_id": job_id,
        "header_checks": header_checks,
        "line_items": line_items
    }
```

**Deliverable**: Complete validation with header checks and line-item checks including tariff validation

---

## Phase 5: XLSX Generation ⏱️ 3-4 days

### Backend

**5.1 Install openpyxl**
```bash
cd backend
uv add openpyxl
```

**5.2 Create XLSX generator**
```python
# File: src/ai_classifier/xlsx_generator.py

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from io import BytesIO
from typing import List, Dict

def generate_audit_xlsx(jobs: List[Dict]) -> bytes:
    """Generate XLSX file with all audit results"""
    
    wb = Workbook()
    
    # Sheet 1: Job Summary
    create_summary_sheet(wb, jobs)
    
    # Sheet 2: Header Checklist Results
    create_header_checks_sheet(wb, jobs)
    
    # Sheet 3: Line Item Checklist Results
    create_line_items_sheet(wb, jobs)
    
    # Sheet 4: Extracted Data - Entry Print
    create_extraction_sheet(wb, jobs, "Entry Print")
    
    # Sheet 5: Extracted Data - Commercial Invoice
    create_extraction_sheet(wb, jobs, "Commercial Invoice")
    
    # Save to BytesIO
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()

def create_summary_sheet(wb: Workbook, jobs: List[Dict]):
    """Create job summary sheet"""
    ws = wb.active
    ws.title = "Job Summary"
    
    # Headers
    headers = ["Job ID", "Files Processed", "Entry Print", "Air Waybill", "Invoice", "Packing List", "Status", "Processed At"]
    ws.append(headers)
    
    # Style headers
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        cell.font = Font(color="FFFFFF", bold=True)
    
    # Add job rows
    for job in jobs:
        ws.append([
            job['job_id'],
            len(job['files']),
            "✓" if job.get('entry_print') else "-",
            "✓" if job.get('air_waybill') else "-",
            "✓" if job.get('commercial_invoice') else "-",
            "✓" if job.get('packing_list') else "-",
            job['status'],
            job['processed_at']
        ])

def create_header_checks_sheet(wb: Workbook, jobs: List[Dict]):
    """Create header checklist results sheet"""
    ws = wb.create_sheet("Header Checklist")
    
    headers = ["Job ID", "Check ID", "Auditing Criteria", "Priority", "Status", "Source Value", "Target Value", "Assessment"]
    ws.append(headers)
    
    # Style headers
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="70AD47", end_color="70AD47", fill_type="solid")
        cell.font = Font(color="FFFFFF", bold=True)
    
    # Add check rows
    for job in jobs:
        for check in job.get('header_checks', []):
            row = [
                job['job_id'],
                check['check_id'],
                check['criteria'],
                check.get('priority', 'High'),
                check['status'],
                check['source_value'],
                check['target_value'],
                check['assessment']
            ]
            ws.append(row)
            
            # Color-code status
            status_cell = ws.cell(row=ws.max_row, column=5)
            if check['status'] == 'PASS':
                status_cell.fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
            elif check['status'] == 'FAIL':
                status_cell.fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
            elif check['status'] == 'QUESTIONABLE':
                status_cell.fill = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")

def create_line_items_sheet(wb: Workbook, jobs: List[Dict]):
    """Create line item checklist results sheet"""
    ws = wb.create_sheet("Line Item Checklist")
    
    headers = [
        "Job ID", "Line #", 
        "Description (Entry)", "Description (Invoice)", "Desc Status",
        "Qty Entry", "Qty Invoice", "Qty Status",
        "HS Code Entry", "HS Code Suggested", "Stat Entry", "Stat Suggested",
        "Tariff Status", "Tariff Assessment"
    ]
    ws.append(headers)
    
    # Style and populate...
    # Similar to header checks

@router.post("/api/generate-xlsx")
async def generate_xlsx_endpoint(jobs: List[Dict]):
    """Generate XLSX file from job results"""
    
    xlsx_content = generate_audit_xlsx(jobs)
    
    return Response(
        content=xlsx_content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=audit_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        }
    )
```

**Deliverable**: Download complete audit results as formatted XLSX

---

## Phase 6: Integration & UI Polish ⏱️ 2-3 days

### Frontend

**6.1 Complete batch processing flow**
```typescript
// File: src/app/audit/page.tsx

const handleProcessBatch = async () => {
  setProcessing(true);
  setProgress(0);
  
  // Step 1: Upload files
  const formData = new FormData();
  files.forEach(file => formData.append('files', file));
  
  setProgress(10);
  
  // Step 2: Classify documents
  const classifyResponse = await fetch('/api/classify-batch', {
    method: 'POST',
    body: formData
  });
  const classifications = await classifyResponse.json();
  
  setProgress(30);
  
  // Step 3: Extract data
  const extractResponse = await fetch('/api/extract-batch', {
    method: 'POST',
    body: JSON.stringify({ classifications })
  });
  const extractions = await extractResponse.json();
  
  setProgress(60);
  
  // Step 4: Validate
  const validateResponse = await fetch('/api/validate-batch', {
    method: 'POST',
    body: JSON.stringify({ 
      extractions,
      country: selectedCountry
    })
  });
  const validations = await validateResponse.json();
  
  setProgress(90);
  
  // Step 5: Generate XLSX
  const xlsxResponse = await fetch('/api/generate-xlsx', {
    method: 'POST',
    body: JSON.stringify({ jobs: validations.jobs })
  });
  const blob = await xlsxResponse.blob();
  
  setProgress(100);
  
  // Download file
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `audit_results_${Date.now()}.xlsx`;
  a.click();
  
  setProcessing(false);
};
```

**Deliverable**: Complete end-to-end workflow from upload to XLSX download

---

## Testing Strategy

### Unit Tests
- File grouping logic
- Classification accuracy
- Extraction validation
- Checklist validation logic

### Integration Tests
- End-to-end flow with sample files
- Error handling
- Performance testing

### Test Data
Use files from `OneDrive_1_09-10-2025/`:
- 3 complete jobs with Entry Print, AWB, and Invoice
- Perfect for testing the full workflow

---

## Performance Targets

- Classification: < 5 seconds per document
- Extraction: < 10 seconds per document
- Validation: < 30 seconds per job
- Total processing: < 3 minutes per job
- XLSX generation: < 5 seconds

---

## Deployment Considerations

- No database needed (stateless)
- Can deploy backend and frontend separately
- Backend needs: Python 3.11+, Gemini API key
- Frontend needs: Node.js, environment variable for backend URL
- Consider rate limits for Gemini API
- Add monitoring for API usage and costs

---

## Estimated Timeline

- **Phase 1**: 2-3 days (File upload & grouping)
- **Phase 2**: 3-4 days (Classification)
- **Phase 3**: 4-5 days (Extraction)
- **Phase 4**: 5-7 days (Validation)
- **Phase 5**: 3-4 days (XLSX generation)
- **Phase 6**: 2-3 days (Integration & polish)

**Total**: ~3-4 weeks for complete implementation

---

## Success Criteria

- [ ] Users can upload multiple PDFs
- [ ] System auto-groups files by job number
- [ ] All documents are correctly classified
- [ ] Data is accurately extracted from each document
- [ ] Checklist validation runs successfully
- [ ] Tariff codes are validated using AU/NZ classifiers
- [ ] XLSX file is generated with all results
- [ ] Processing completes in < 5 minutes per job
- [ ] No manual intervention required

---

See `SIMPLIFIED_SYSTEM_SPEC.md` for detailed specifications.

