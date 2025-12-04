"""
NZ Audit API Routes - Endpoints for New Zealand customs audit.

This module provides API endpoints that:
- Skip document classification
- Dump all job PDFs into the model for extraction
- Perform header-only validation
- Output CSV results
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Literal
from pathlib import Path
from datetime import datetime

from ..nz_audit import (
    run_nz_audit,
    process_grouped_jobs_nz,
    get_audit_status,
    clear_audit_markers,
    AUDIT_COMPLETE_MARKER,
)
from ..util.batch_processor import get_input_folder_path


router = APIRouter(prefix="/api/nz-audit", tags=["NZ Audit"])


class NZAuditJobResult(BaseModel):
    """Result for a single job audit."""
    job_id: str
    success: bool
    error: str | None = None
    job_folder: str | None = None  # Path to output job folder
    csv_path: str | None = None  # Path to individual job CSV
    extraction: Dict[str, Any] | None = None
    header_validation: Dict[str, str] | None = None
    auditor_comments: str | None = None
    auditor: str | None = None


class NZAuditBatchResponse(BaseModel):
    """Response for batch NZ audit processing."""
    success: bool
    message: str
    run_id: str | None = None  # Run identifier
    run_path: str | None = None  # Path to output run folder
    total_jobs: int
    successful_jobs: int
    failed_jobs: int
    skipped_jobs: int = 0  # Jobs skipped (already complete)
    csv_path: str | None = None  # Path to combined CSV
    csv_filename: str | None = None
    xlsx_path: str | None = None  # Path to combined XLSX (with broker sheets)
    xlsx_filename: str | None = None
    results: List[NZAuditJobResult]


class GroupedFolderInfo(BaseModel):
    """Information about a grouped folder."""
    name: str
    path: str
    job_count: int
    completed_jobs: int = 0  # Jobs with .audit_complete marker
    pending_jobs: int = 0    # Jobs without marker
    created: str


class ListGroupedFoldersResponse(BaseModel):
    """Response for listing grouped folders."""
    success: bool
    input_folder: str
    folders: List[GroupedFolderInfo]


@router.get("/grouped-folders", response_model=ListGroupedFoldersResponse)
async def list_grouped_folders():
    """
    List all grouped folders in the input directory.
    
    Returns folders matching pattern: grouped_YYYY-MM-DD_HHMMSS
    """
    input_folder = get_input_folder_path()
    
    if not input_folder.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Input folder not found: {input_folder}"
        )
    
    # Find all grouped folders
    grouped_folders = []
    for item in input_folder.iterdir():
        if item.is_dir() and item.name.startswith("grouped_"):
            # Count job folders and their completion status
            job_count = 0
            completed_count = 0
            for f in item.iterdir():
                if f.is_dir() and f.name.startswith("job_"):
                    job_count += 1
                    if (f / AUDIT_COMPLETE_MARKER).exists():
                        completed_count += 1
            
            # Get creation time
            created = datetime.fromtimestamp(item.stat().st_mtime).isoformat()
            
            grouped_folders.append(GroupedFolderInfo(
                name=item.name,
                path=str(item),
                job_count=job_count,
                completed_jobs=completed_count,
                pending_jobs=job_count - completed_count,
                created=created
            ))
    
    # Sort by creation time (newest first)
    grouped_folders.sort(key=lambda x: x.created, reverse=True)
    
    return ListGroupedFoldersResponse(
        success=True,
        input_folder=str(input_folder),
        folders=grouped_folders
    )


@router.post("/process", response_model=NZAuditBatchResponse)
async def process_nz_audit(
    folder_name: str = Query(..., description="Name of the grouped folder to process (e.g., 'grouped_2025-12-01_120000')"),
    broker_name: str = Query("", description="Optional broker name to pre-fill"),
    resume_failed_only: bool = Query(False, description="If True, only process jobs that failed previously (skip jobs with .audit_complete marker)")
):
    """
    Process all jobs in a grouped folder for NZ audit.
    
    This endpoint:
    1. Reads all job subfolders from the specified grouped folder
    2. For each job, dumps ALL PDFs into the model (no classification)
    3. Extracts audit metadata and performs header validations
    4. Outputs a CSV file with all results
    
    When resume_failed_only=True:
    - Skips jobs that have .audit_complete marker
    - Reuses the existing run folder and merges results into the same CSV
    
    Args:
        folder_name: Name of the grouped folder (e.g., 'grouped_2025-12-01_120000')
        broker_name: Optional broker name to pre-fill if not found in documents
        resume_failed_only: Skip already-completed jobs and append to existing CSV
        
    Returns:
        NZAuditBatchResponse with results and CSV path
    """
    input_folder = get_input_folder_path()
    grouped_folder = input_folder / folder_name
    
    if not grouped_folder.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Grouped folder not found: {grouped_folder}"
        )
    
    print(f"\n{'='*80}", flush=True)
    print(f"🇳🇿 NZ AUDIT API - Processing {folder_name}", flush=True)
    if resume_failed_only:
        print(f"🔄 RESUME MODE - Only processing failed jobs", flush=True)
    print(f"{'='*80}", flush=True)
    
    try:
        result = await process_grouped_jobs_nz(
            grouped_folder=grouped_folder,
            broker_name=broker_name,
            resume_failed_only=resume_failed_only
        )
        
        # Convert results to response format
        job_results = []
        for job_data in result.get("job_results", []):
            row = job_data.get("result", {})
            job_results.append(NZAuditJobResult(
                job_id=job_data.get("job_id", ""),
                success=job_data.get("success", False),
                error=job_data.get("error"),
                job_folder=job_data.get("job_folder"),
                csv_path=job_data.get("csv_path"),
                extraction={
                    "audit_month": row.get("Audit Month (month entry lodged)", ""),
                    "tl": row.get("TL", ""),
                    "broker": row.get("Broker", ""),
                    "dhl_job_number": row.get("DHL Job Nmb", ""),
                    "hawb": row.get("HAWB", ""),
                    "import_export": row.get("Import/Export", ""),
                    "entry_number": row.get("Entry Number", ""),
                    "entry_date": row.get("Entry Date", ""),
                } if row else None,
                header_validation={
                    "client_code_name_correct": row.get("Client code/name correct?\nIE & EE", ""),
                    "client_code_name_reasoning": row.get("Client code/name reasoning", ""),
                    "supplier_or_cnee_correct": row.get("IE - Supplier code/name correct?\nEE - Cnee name correct?", ""),
                    "supplier_or_cnee_reasoning": row.get("Supplier/Cnee reasoning", ""),
                    "invoice_number_correct": row.get("Invoice Number Correct", ""),
                    "invoice_number_reasoning": row.get("Invoice Number reasoning", ""),
                    "vfd_correct": row.get("VFD Correct", ""),
                    "vfd_reasoning": row.get("VFD reasoning", ""),
                    "currency_correct": row.get("Currency Correct", ""),
                    "currency_reasoning": row.get("Currency reasoning", ""),
                    "incoterm_correct": row.get("Incoterm Correct", ""),
                    "incoterm_reasoning": row.get("Incoterm reasoning", ""),
                    "freight_zero_if_inclusive_incoterm": row.get("If freight inclusive incoterm and no freight on invoice, is freight zero?", ""),
                    "freight_zero_reasoning": row.get("Freight zero reasoning", ""),
                    "freight_correct": row.get("Freight correct?\nRate card/ETS\nN/A if freight zero\nN/A for exports", ""),
                    "freight_correct_reasoning": row.get("Freight correct reasoning", ""),
                    "load_port_correct": row.get("Load Port Air/Sea", ""),
                    "load_port_reasoning": row.get("Load Port reasoning", ""),
                    "relationship_indicator_correct": row.get("Relationship Indicator Correct Yes/No?", ""),
                    "relationship_indicator_reasoning": row.get("Relationship Indicator reasoning", ""),
                    "country_of_export_correct": row.get("Country of Export", ""),
                    "country_of_export_reasoning": row.get("Country of Export reasoning", ""),
                    "correct_weight_of_goods": row.get("Correct weight of goods", ""),
                    "correct_weight_reasoning": row.get("Weight reasoning", ""),
                    "cgo_correct": row.get("CGO (for Exports, where applicable)", ""),
                    "cgo_reasoning": row.get("CGO reasoning", ""),
                } if row else None,
                auditor_comments=row.get("Auditor: Auditor Comments", "") if row else None,
                auditor=row.get("Auditor", "DTAL") if row else None
            ))
        
        # Extract CSV filename from path
        csv_filename = None
        if result.get("csv_path"):
            csv_filename = Path(result["csv_path"]).name
        
        skipped = result.get("skipped_jobs", 0)
        msg_parts = [f"NZ audit complete: {result['successful_jobs']} successful"]
        if result['failed_jobs'] > 0:
            msg_parts.append(f"{result['failed_jobs']} failed")
        if skipped > 0:
            msg_parts.append(f"{skipped} skipped")
        msg_parts.append(f"of {result['total_jobs']} total")
        
        return NZAuditBatchResponse(
            success=True,
            message=f"{', '.join(msg_parts)}. Output: {result.get('run_path', '')}",
            run_id=result.get("run_id"),
            run_path=result.get("run_path"),
            total_jobs=result["total_jobs"],
            successful_jobs=result["successful_jobs"],
            failed_jobs=result["failed_jobs"],
            skipped_jobs=skipped,
            csv_path=result.get("csv_path"),
            csv_filename=csv_filename,
            results=job_results
        )
        
    except Exception as e:
        print(f"❌ NZ Audit processing failed: {e}", flush=True)
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"NZ audit processing failed: {str(e)}"
        ) from e


@router.get("/download-csv")
async def download_csv(
    csv_path: str = Query(..., description="Full path to the CSV file to download")
):
    """
    Download an NZ audit CSV file.
    
    Args:
        csv_path: Full path to the CSV file
        
    Returns:
        CSV file as attachment
    """
    csv_file = Path(csv_path)
    
    if not csv_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"CSV file not found: {csv_path}"
        )
    
    return FileResponse(
        path=str(csv_file),
        filename=csv_file.name,
        media_type="text/csv"
    )


@router.get("/download-xlsx")
async def download_xlsx(
    xlsx_path: str = Query(..., description="Full path to the XLSX file to download")
):
    """
    Download an NZ audit XLSX file (with broker sheets).
    
    Args:
        xlsx_path: Full path to the XLSX file
        
    Returns:
        XLSX file as attachment
    """
    xlsx_file = Path(xlsx_path)
    
    if not xlsx_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"XLSX file not found: {xlsx_path}"
        )
    
    return FileResponse(
        path=str(xlsx_file),
        filename=xlsx_file.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


class JobStatus(BaseModel):
    """Status of a single job."""
    job_id: str
    hawb: str | None = None
    dhl_job_number: str | None = None
    broker: str | None = None
    status: Literal["completed", "pending", "failed"]
    has_pdfs: bool


class JobListResponse(BaseModel):
    """Response for listing jobs in a grouped folder."""
    success: bool
    folder_name: str
    jobs: List[JobStatus]
    total: int
    completed: int
    pending: int


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    folder_name: str = Query(..., description="Name of the grouped folder")
):
    """
    List all jobs in a grouped folder with their status.
    
    Args:
        folder_name: Name of the grouped folder
        
    Returns:
        JobListResponse with list of jobs and their status
    """
    from ..nz_audit import AUDIT_COMPLETE_MARKER, _load_run_metadata
    
    input_folder = get_input_folder_path()
    grouped_folder = input_folder / folder_name
    
    if not grouped_folder.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Grouped folder not found: {grouped_folder}"
        )
    
    # Load existing results to get job details
    existing_metadata = _load_run_metadata(grouped_folder)
    existing_results: List[Dict[str, str]] = []
    
    if existing_metadata and existing_metadata.get("csv_path"):
        from ..nz_audit import _load_existing_csv_results
        existing_csv = Path(existing_metadata["csv_path"])
        if existing_csv.exists():
            existing_results = _load_existing_csv_results(existing_csv)
    
    # Build lookup by HAWB
    results_by_hawb: Dict[str, Dict[str, str]] = {}
    for row in existing_results:
        hawb = row.get("HAWB", "")
        if hawb:
            results_by_hawb[hawb] = row
    
    # Find all job folders
    jobs: List[JobStatus] = []
    for item in sorted(grouped_folder.iterdir()):
        if item.is_dir() and item.name.startswith("job_"):
            job_id = item.name.replace("job_", "")
            
            # Check if completed
            marker_file = item / AUDIT_COMPLETE_MARKER
            is_completed = marker_file.exists()
            
            # Check for PDFs
            pdf_files = list(item.glob("*.pdf")) + list(item.glob("*.PDF"))
            has_pdfs = len(pdf_files) > 0
            
            # Try to get job details from existing results
            # Look for HAWB in folder name or try to match by job_id
            hawb = None
            dhl_job_number = None
            broker = None
            
            # Try to find in existing results by matching job_id patterns
            for row in existing_results:
                row_hawb = row.get("HAWB", "")
                row_dhl = row.get("DHL Job Nmb", "")
                # If HAWB matches job_id or DHL job number matches
                if row_hawb == job_id or row_dhl.startswith(job_id[:8]):
                    hawb = row_hawb
                    dhl_job_number = row_dhl
                    broker = row.get("Broker", "")
                    break
            
            # If not found, try to extract from folder name patterns
            if not hawb:
                # Sometimes job_id is the HAWB
                if job_id.isdigit() and len(job_id) == 10:
                    hawb = job_id
            
            status: Literal["completed", "pending", "failed"] = "completed" if is_completed else "pending"
            
            jobs.append(JobStatus(
                job_id=job_id,
                hawb=hawb,
                dhl_job_number=dhl_job_number,
                broker=broker,
                status=status,
                has_pdfs=has_pdfs
            ))
    
    completed = sum(1 for j in jobs if j.status == "completed")
    pending = sum(1 for j in jobs if j.status == "pending")
    
    return JobListResponse(
        success=True,
        folder_name=folder_name,
        jobs=jobs,
        total=len(jobs),
        completed=completed,
        pending=pending
    )


@router.post("/process-single-job", response_model=NZAuditJobResult)
async def process_single_job(
    folder_name: str = Query(..., description="Name of the grouped folder"),
    job_id: str = Query(..., description="Job ID to process (e.g., '1234567890')"),
    broker_name: str = Query("", description="Optional broker name"),
    update_combined: bool = Query(True, description="Whether to update the combined CSV/XLSX files")
):
    """
    Process a single job for NZ audit.
    
    This endpoint processes just one job folder within a grouped folder.
    After processing, it updates the combined CSV/XLSX files if update_combined=True.
    
    Args:
        folder_name: Name of the grouped folder
        job_id: The job ID to process
        broker_name: Optional broker name
        update_combined: Whether to update combined CSV/XLSX after processing
        
    Returns:
        NZAuditJobResult for the single job
    """
    from ..nz_audit import (
        run_nz_audit, create_csv_row, write_audit_csv, write_audit_xlsx,
        _load_run_metadata, _load_existing_csv_results, _save_run_metadata,
        AUDIT_COMPLETE_MARKER
    )
    from ..file_manager import create_job_directory
    
    input_folder = get_input_folder_path()
    grouped_folder = input_folder / folder_name
    job_folder = grouped_folder / f"job_{job_id}"
    
    if not job_folder.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Job folder not found: {job_folder}"
        )
    
    # Get PDF files
    pdf_files = list(job_folder.glob("*.pdf")) + list(job_folder.glob("*.PDF"))
    
    if not pdf_files:
        raise HTTPException(
            status_code=404,
            detail=f"No PDF files found in job folder: {job_folder}"
        )
    
    try:
        # Get run metadata to find output folder
        existing_metadata = _load_run_metadata(grouped_folder)
        if not existing_metadata:
            raise HTTPException(
                status_code=400,
                detail="No existing run found. Please run full audit first."
            )
        
        run_path = Path(existing_metadata["run_path"])
        run_id = existing_metadata["run_id"]
        
        # Create job folder in output
        output_job_path = create_job_directory(run_path, job_id)
        
        # Run audit
        audit_result, token_usage = await run_nz_audit(
            job_id=job_id,
            pdf_files=pdf_files,
            broker_name=broker_name,
            output_job_path=output_job_path
        )
        
        # Convert to CSV row
        row = create_csv_row(audit_result)
        
        # Save individual job CSV
        job_csv_path = output_job_path / f"nz_audit_{job_id}.csv"
        write_audit_csv([row], job_csv_path)
        
        # Mark job as complete
        marker_file = job_folder / AUDIT_COMPLETE_MARKER
        marker_file.write_text(f"Completed: {run_id}\n")
        
        # Update combined CSV/XLSX if requested
        if update_combined:
            combined_csv_path = run_path / f"nz_audit_combined_{run_id}.csv"
            combined_xlsx_path = run_path / f"nz_audit_combined_{run_id}.xlsx"
            
            # Load existing results
            existing_results = []
            if combined_csv_path.exists():
                existing_results = _load_existing_csv_results(combined_csv_path)
            
            # Remove old entry for this job (by HAWB)
            hawb = row.get("HAWB", "")
            existing_results = [r for r in existing_results if r.get("HAWB") != hawb]
            
            # Add new result
            existing_results.append(row)
            
            # Write updated CSV
            write_audit_csv(existing_results, combined_csv_path)
            
            # Write updated XLSX
            try:
                write_audit_xlsx(existing_results, combined_xlsx_path)
            except Exception as e:
                print(f"⚠️  Failed to update XLSX: {e}", flush=True)
            
            # Update metadata
            _save_run_metadata(grouped_folder, run_id, run_path, combined_csv_path)
        
        return NZAuditJobResult(
            job_id=job_id,
            success=True,
            extraction=audit_result.extraction.model_dump(),
            header_validation={
                "client_code_name_correct": audit_result.header_validation.client_code_name_correct,
                "client_code_name_reasoning": audit_result.header_validation.client_code_name_reasoning,
                "supplier_or_cnee_correct": audit_result.header_validation.supplier_or_cnee_correct,
                "supplier_or_cnee_reasoning": audit_result.header_validation.supplier_or_cnee_reasoning,
                "invoice_number_correct": audit_result.header_validation.invoice_number_correct,
                "invoice_number_reasoning": audit_result.header_validation.invoice_number_reasoning,
                "vfd_correct": audit_result.header_validation.vfd_correct,
                "vfd_reasoning": audit_result.header_validation.vfd_reasoning,
                "currency_correct": audit_result.header_validation.currency_correct,
                "currency_reasoning": audit_result.header_validation.currency_reasoning,
                "incoterm_correct": audit_result.header_validation.incoterm_correct,
                "incoterm_reasoning": audit_result.header_validation.incoterm_reasoning,
                "freight_zero_if_inclusive_incoterm": audit_result.header_validation.freight_zero_if_inclusive_incoterm,
                "freight_zero_reasoning": audit_result.header_validation.freight_zero_reasoning,
                "freight_correct": audit_result.header_validation.freight_correct,
                "freight_correct_reasoning": audit_result.header_validation.freight_correct_reasoning,
                "load_port_correct": audit_result.header_validation.load_port_correct,
                "load_port_reasoning": audit_result.header_validation.load_port_reasoning,
                "relationship_indicator_correct": audit_result.header_validation.relationship_indicator_correct,
                "relationship_indicator_reasoning": audit_result.header_validation.relationship_indicator_reasoning,
                "country_of_export_correct": audit_result.header_validation.country_of_export_correct,
                "country_of_export_reasoning": audit_result.header_validation.country_of_export_reasoning,
                "correct_weight_of_goods": audit_result.header_validation.correct_weight_of_goods,
                "correct_weight_reasoning": audit_result.header_validation.correct_weight_reasoning,
                "cgo_correct": audit_result.header_validation.cgo_correct,
                "cgo_reasoning": audit_result.header_validation.cgo_reasoning,
            },
            auditor_comments=audit_result.auditor_comments,
            auditor=audit_result.auditor,
            job_folder=str(output_job_path),
            csv_path=str(job_csv_path)
        )
        
    except Exception as e:
        return NZAuditJobResult(
            job_id=job_id,
            success=False,
            error=str(e)
        )


class ClearMarkersResponse(BaseModel):
    """Response for clearing audit markers."""
    success: bool
    message: str
    markers_removed: int


@router.post("/clear-markers", response_model=ClearMarkersResponse)
async def clear_markers(
    folder_name: str = Query(..., description="Name of the grouped folder to clear markers from"),
    new_run: bool = Query(True, description="If True, also clears run metadata so next run creates a new output folder")
):
    """
    Clear all .audit_complete markers from a grouped folder.
    
    Use this to reset a folder and re-run all jobs from scratch.
    If new_run=True (default), also clears run metadata so a new output folder is created.
    
    Args:
        folder_name: Name of the grouped folder
        new_run: Whether to also clear run metadata for a completely fresh start
        
    Returns:
        Number of markers removed
    """
    input_folder = get_input_folder_path()
    grouped_folder = input_folder / folder_name
    
    if not grouped_folder.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Grouped folder not found: {grouped_folder}"
        )
    
    removed = clear_audit_markers(grouped_folder, clear_run_metadata=new_run)
    
    msg = f"Cleared {removed} audit markers from {folder_name}"
    if new_run:
        msg += " (will create new run folder)"
    
    return ClearMarkersResponse(
        success=True,
        message=msg,
        markers_removed=removed
    )
