"""
AU Audit API Routes - Endpoints for Australian customs audit.
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Dict, Any
from pathlib import Path
from datetime import datetime

from ..au_audit import (
    process_grouped_jobs_au,
    clear_audit_markers,
    AUDIT_COMPLETE_MARKER,
)
from ..util.batch_processor import get_input_folder_path


router = APIRouter(prefix="/api/au-audit", tags=["AU Audit"])


class AUAuditJobResult(BaseModel):
    """Result for a single job audit."""
    job_id: str
    success: bool
    error: str | None = None
    job_folder: str | None = None
    csv_path: str | None = None
    extraction: Dict[str, Any] | None = None
    header_validation: Dict[str, str] | None = None
    auditor_comments: str | None = None
    auditor: str | None = None


class AUAuditBatchResponse(BaseModel):
    """Response for batch AU audit processing."""
    success: bool
    message: str
    run_id: str | None = None
    run_path: str | None = None
    total_jobs: int
    successful_jobs: int
    failed_jobs: int
    skipped_jobs: int = 0
    csv_path: str | None = None
    csv_filename: str | None = None
    xlsx_path: str | None = None
    xlsx_filename: str | None = None
    results: List[AUAuditJobResult]


class GroupedFolderInfo(BaseModel):
    """Information about a grouped folder."""
    name: str
    path: str
    job_count: int
    completed_jobs: int = 0
    pending_jobs: int = 0
    created: str


class ListGroupedFoldersResponse(BaseModel):
    """Response for listing grouped folders."""
    success: bool
    input_folder: str
    folders: List[GroupedFolderInfo]


@router.get("/grouped-folders", response_model=ListGroupedFoldersResponse)
async def list_grouped_folders():
    input_folder = get_input_folder_path()
    if not input_folder.exists():
        raise HTTPException(status_code=404, detail=f"Input folder not found: {input_folder}")
    
    grouped_folders = []
    for item in input_folder.iterdir():
        if item.is_dir() and item.name.startswith("grouped_"):
            job_count = 0
            completed_count = 0
            for f in item.iterdir():
                if f.is_dir() and f.name.startswith("job_"):
                    job_count += 1
                    if (f / AUDIT_COMPLETE_MARKER).exists():
                        completed_count += 1
            created = datetime.fromtimestamp(item.stat().st_mtime).isoformat()
            grouped_folders.append(GroupedFolderInfo(
                name=item.name,
                path=str(item),
                job_count=job_count,
                completed_jobs=completed_count,
                pending_jobs=job_count - completed_count,
                created=created
            ))
    grouped_folders.sort(key=lambda x: x.created, reverse=True)
    return ListGroupedFoldersResponse(success=True, input_folder=str(input_folder), folders=grouped_folders)


@router.get("/jobs")
async def list_jobs(folder_name: str = Query(...)):
    from ..au_audit import AUDIT_COMPLETE_MARKER, _load_run_metadata, _load_existing_csv_results
    
    input_folder = get_input_folder_path()
    grouped_folder = input_folder / folder_name
    if not grouped_folder.exists():
        raise HTTPException(status_code=404, detail="Folder not found")
    
    existing_metadata = _load_run_metadata(grouped_folder)
    existing_results = []
    if existing_metadata and existing_metadata.get("csv_path"):
        csv_p = Path(existing_metadata["csv_path"])
        if csv_p.exists():
            existing_results = _load_existing_csv_results(csv_p)
    
    jobs = []
    for item in sorted(grouped_folder.iterdir()):
        if item.is_dir() and item.name.startswith("job_"):
            job_id = item.name.replace("job_", "")
            is_completed = (item / AUDIT_COMPLETE_MARKER).exists()
            pdfs = list(item.glob("*.pdf")) + list(item.glob("*.PDF"))
            
            hawb = None
            for row in existing_results:
                if row.get("WAYBILL #") == job_id or row.get("Entry #") == job_id:
                    hawb = row.get("WAYBILL #")
                    break
            
            jobs.append({
                "job_id": job_id,
                "hawb": hawb or job_id,
                "status": "completed" if is_completed else "pending",
                "has_pdfs": len(pdfs) > 0
            })
    
    return {
        "success": True,
        "folder_name": folder_name,
        "jobs": jobs,
        "total": len(jobs),
        "completed": sum(1 for j in jobs if j["status"] == "completed"),
        "pending": sum(1 for j in jobs if j["status"] == "pending")
    }


@router.post("/process", response_model=AUAuditBatchResponse)
async def process_au_audit(
    folder_name: str = Query(..., description="Name of the grouped folder"),
    broker_name: str = Query("", description="Optional broker name"),
    resume_failed_only: bool = Query(False, description="Only process failed jobs")
):
    input_folder = get_input_folder_path()
    grouped_folder = input_folder / folder_name
    if not grouped_folder.exists():
        raise HTTPException(status_code=404, detail="Grouped folder not found")
    
    try:
        result = await process_grouped_jobs_au(
            grouped_folder=grouped_folder,
            broker_name=broker_name,
            resume_failed_only=resume_failed_only
        )
        
        job_results = []
        for job_data in result.get("results", []):
            row = job_data.get("row", {})
            job_results.append(AUAuditJobResult(
                job_id=job_data.get("job_id", ""),
                success=job_data.get("success", False),
                error=job_data.get("error"),
                extraction={
                    "audit_month": row.get("Month-Year", ""),
                    "entry_number": row.get("Entry #", ""),
                    "waybill_number": row.get("WAYBILL #", ""),
                } if row else None,
                header_validation={
                    # AI-validated fields
                    "OC": row.get("OC", ""),
                    "SC": row.get("SC", ""),
                    "VALUATION": row.get("VALUATION", ""),
                    "ORIGIN": row.get("ORIGIN", ""),
                    "FTA": row.get("FTA", ""),
                    "PRS/PRT": row.get("PRS/PRT", ""),
                    "CURRENCY": row.get("CURRENCY", ""),
                    "INCOTERMS": row.get("INCOTERMS", ""),
                    "T & I": row.get("T & I", ""),
                    "OTH/DISC": row.get("OTH/DISC", ""),
                    # Always "1" fields (no AI)
                    "CP QUESTIONS": row.get("CP QUESTIONS", "1"),
                    "RELATED TRANSACTION": row.get("RELATED TRANSACTION", "1"),
                    "NOTES": row.get("NOTES", "1"),
                    "AQIS": row.get("AQIS", "1"),
                    "PERMITS": row.get("PERMITS", "1"),
                    "OTHER": row.get("OTHER", "1"),
                } if row else None,
                auditor_comments=row.get("FREE TEXT", "") if row else None,
            ))
        
        return AUAuditBatchResponse(
            success=True,
            message=f"AU audit complete. Output: {result.get('run_path', '')}",
            run_id=result.get("run_id"),
            run_path=result.get("run_path"),
            total_jobs=result["total"],
            successful_jobs=sum(1 for r in result["results"] if r.get("success")),
            failed_jobs=sum(1 for r in result["results"] if not r.get("success") and not r.get("skipped")),
            skipped_jobs=sum(1 for r in result["results"] if r.get("skipped")),
            csv_path=result.get("csv_path"),
            xlsx_path=result.get("xlsx_path"),
            results=job_results
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/download-csv")
async def download_csv(csv_path: str = Query(...)):
    if not Path(csv_path).exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=csv_path, filename=Path(csv_path).name, media_type="text/csv")


@router.get("/download-xlsx")
async def download_xlsx(xlsx_path: str = Query(...)):
    if not Path(xlsx_path).exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=xlsx_path, filename=Path(xlsx_path).name, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.post("/clear-markers")
async def clear_markers(folder_name: str = Query(...), new_run: bool = Query(True)):
    input_folder = get_input_folder_path()
    grouped_folder = input_folder / folder_name
    if not grouped_folder.exists():
        raise HTTPException(status_code=404, detail="Folder not found")
    removed = clear_audit_markers(grouped_folder, clear_run_metadata=new_run)
    return {"success": True, "markers_removed": removed}

