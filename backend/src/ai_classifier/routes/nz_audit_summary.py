"""
NZ Audit Summary API Routes - Endpoints for generating audit summary reports.

This module provides API endpoints that:
- Accept an uploaded Excel file with completed audit results
- Generate accuracy and error summary by broker
- Return the summary as a downloadable Excel file
"""
from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Dict
from pathlib import Path
from datetime import datetime
import tempfile
import shutil
import os

from ..nz_audit_summary import generate_nz_audit_summary


router = APIRouter(prefix="/api/nz-audit-summary", tags=["NZ Audit Summary"])


class BrokerSummary(BaseModel):
    """Summary for a single broker."""
    broker_name: str
    accuracy: float
    accuracy_percentage: str
    total_rows: int
    total_errors: int
    error_counts: Dict[str, int]
    additional_errors: Dict[str, int] = {}


class SummaryResponse(BaseModel):
    """Response for audit summary generation."""
    success: bool
    message: str
    month: str
    broker_count: int
    brokers: List[BrokerSummary]
    output_file: str
    output_filename: str


@router.post("/generate", response_model=SummaryResponse)
async def generate_summary(
    file: UploadFile = File(..., description="Excel file with completed audit results"),
    month: str = Form("", description="Month for the summary (e.g., 'Jul-24'). Defaults to current month if empty.")
):
    """
    Generate an NZ audit summary from an uploaded Excel file.
    
    This endpoint:
    1. Accepts an Excel file with completed audit results (one sheet per broker)
    2. Calculates accuracy for each broker: 1 - (errors / total)
    3. Counts errors by validation category
    4. Returns summary data and generates a downloadable summary Excel file
    
    Args:
        file: Excel file with audit results (xlsx format)
        month: Month string for the report header (e.g., "Jul-24")
        
    Returns:
        SummaryResponse with broker summaries and output file path
    """
    # Validate file type
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Please upload an Excel file (.xlsx or .xls)"
        )
    
    # Create temp directory for processing
    temp_dir = Path(tempfile.mkdtemp(prefix="nz_audit_summary_"))
    
    try:
        # Save uploaded file
        input_path = temp_dir / file.filename
        with open(input_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Generate output filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"nz_audit_summary_{timestamp}.xlsx"
        
        # Get output folder (use workspace output folder if available)
        output_base = Path(os.getenv("OUTPUT_FOLDER", "/app/output"))
        if not output_base.exists():
            output_base = temp_dir
        
        output_path = output_base / output_filename
        
        # Default month to current if not provided
        if not month:
            month = datetime.now().strftime("%b-%y")
        
        # Generate summary
        result = generate_nz_audit_summary(
            input_path=input_path,
            output_path=output_path,
            month=month
        )
        
        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail="Failed to generate summary"
            )
        
        # Convert broker results to response format
        brokers = []
        for broker_name, data in result.get("broker_results", {}).items():
            total_errors = sum(data["error_counts"].values())
            additional_errors = data.get("additional_errors", {})
            brokers.append(BrokerSummary(
                broker_name=broker_name,
                accuracy=data["accuracy"],
                accuracy_percentage=f"{data['accuracy'] * 100:.0f}%",
                total_rows=data["total_rows"],
                total_errors=total_errors + sum(additional_errors.values()),
                error_counts=data["error_counts"],
                additional_errors=additional_errors
            ))
        
        # Sort by broker name
        brokers.sort(key=lambda x: x.broker_name)
        
        return SummaryResponse(
            success=True,
            message=f"Summary generated for {len(brokers)} brokers",
            month=month,
            broker_count=len(brokers),
            brokers=brokers,
            output_file=str(output_path),
            output_filename=output_filename
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Summary generation failed: {e}", flush=True)
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Summary generation failed: {str(e)}"
        ) from e
    finally:
        # Clean up temp input file (keep output)
        if input_path.exists():
            input_path.unlink()


@router.get("/download")
async def download_summary(
    file_path: str = Query(..., description="Full path to the summary file to download")
):
    """
    Download a generated NZ audit summary Excel file.
    
    Args:
        file_path: Full path to the summary Excel file
        
    Returns:
        Excel file as attachment
    """
    file = Path(file_path)
    
    if not file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Summary file not found: {file_path}"
        )
    
    return FileResponse(
        path=str(file),
        filename=file.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@router.post("/generate-from-path", response_model=SummaryResponse)
async def generate_summary_from_path(
    input_path: str = Query(..., description="Path to the input Excel file"),
    output_path: str = Query(None, description="Optional output path for the summary file"),
    month: str = Query("", description="Month for the summary (e.g., 'Jul-24')")
):
    """
    Generate an NZ audit summary from an Excel file path on the server.
    
    This endpoint is useful for processing files that are already on the server.
    
    Args:
        input_path: Path to the Excel file with audit results
        output_path: Optional output path (defaults to input_path with _summary suffix)
        month: Month string for the report header
        
    Returns:
        SummaryResponse with broker summaries and output file path
    """
    input_file = Path(input_path)
    
    if not input_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Input file not found: {input_path}"
        )
    
    # Default month to current if not provided
    if not month:
        month = datetime.now().strftime("%b-%y")
    
    try:
        # Generate summary
        result = generate_nz_audit_summary(
            input_path=input_file,
            output_path=Path(output_path) if output_path else None,
            month=month
        )
        
        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail="Failed to generate summary"
            )
        
        # Convert broker results to response format
        brokers = []
        for broker_name, data in result.get("broker_results", {}).items():
            total_errors = sum(data["error_counts"].values())
            additional_errors = data.get("additional_errors", {})
            brokers.append(BrokerSummary(
                broker_name=broker_name,
                accuracy=data["accuracy"],
                accuracy_percentage=f"{data['accuracy'] * 100:.0f}%",
                total_rows=data["total_rows"],
                total_errors=total_errors + sum(additional_errors.values()),
                error_counts=data["error_counts"],
                additional_errors=additional_errors
            ))
        
        # Sort by broker name
        brokers.sort(key=lambda x: x.broker_name)
        
        return SummaryResponse(
            success=True,
            message=f"Summary generated for {len(brokers)} brokers",
            month=month,
            broker_count=len(brokers),
            brokers=brokers,
            output_file=result["output_file"],
            output_filename=Path(result["output_file"]).name
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Summary generation failed: {e}", flush=True)
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Summary generation failed: {str(e)}"
        ) from e

