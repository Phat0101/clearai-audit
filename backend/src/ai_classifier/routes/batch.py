"""
Batch processing routes for document classification and organization.
"""
from fastapi import APIRouter, UploadFile, HTTPException
from typing import List, Dict, Any
from pydantic import BaseModel
import asyncio
import json
from pathlib import Path

from ..util.batch_processor import (
    group_files_by_job,
    group_local_files_by_job,
    scan_input_folder,
    get_input_folder_path,
    organize_grouped_files
)
from ..document_classifier import classify_document, get_file_suffix
# from ..document_extractor import extract_document_data  # Commented out - extraction not needed
from ..checklist_validator import validate_all_checks
from ..file_manager import (
    get_next_run_id,
    create_run_directory,
    create_job_directory,
    save_classified_file,
    # save_extraction_json  # Commented out - extraction not needed
)


router = APIRouter()


class FileInfo(BaseModel):
    """Basic file information."""
    filename: str
    content_type: str
    size: int | None


class ClassifiedFileInfo(BaseModel):
    """Information about a classified and saved file."""
    original_filename: str
    saved_filename: str
    saved_path: str
    document_type: str
    extracted_data: Dict[str, Any] | None = None  # Extracted structured data


class GroupedJobSummary(BaseModel):
    """Summary of files grouped by job."""
    job_id: str
    file_count: int
    files: List[FileInfo]


class ProcessedJobResult(BaseModel):
    """Result of processing a single job."""
    job_id: str
    job_folder: str
    file_count: int
    classified_files: List[ClassifiedFileInfo]
    validation_results: Dict[str, Any] | None = None  # Checklist validation results
    validation_file: str | None = None  # Path to validation JSON file


class UploadBatchSummary(BaseModel):
    """Summary of the upload batch grouping."""
    total_files: int
    total_jobs: int
    jobs: List[GroupedJobSummary]


class UploadResponse(BaseModel):
    """Response for simple file upload and grouping."""
    success: bool
    message: str
    summary: UploadBatchSummary


class ProcessBatchResponse(BaseModel):
    """Response for full batch processing with classification."""
    success: bool
    message: str
    run_id: str
    run_path: str
    total_files: int
    total_jobs: int
    jobs: List[ProcessedJobResult]


@router.post("/api/upload-batch", response_model=UploadResponse)
async def upload_batch(files: List[UploadFile]):
    """
    Upload and group files by job ID (Phase 1).
    Does not classify or save files - just groups and reports.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    print("=" * 80, flush=True)
    print(f"📤 BATCH UPLOAD - Received {len(files)} file(s)", flush=True)
    print("=" * 80, flush=True)

    # Group files by job ID
    grouped_jobs = group_files_by_job(files)

    # Create summary
    total_files = len(files)
    total_jobs = len(grouped_jobs)
    
    jobs_summary = []
    for job_id, job_files in grouped_jobs.items():
        job_info = GroupedJobSummary(
            job_id=job_id,
            file_count=len(job_files),
            files=[
                FileInfo(
                    filename=f.filename,
                    size=f.size if hasattr(f, 'size') else None,
                    content_type=f.content_type or "application/pdf"
                )
                for f in job_files
            ]
        )
        jobs_summary.append(job_info)

    # Log summary
    print("\n📊 GROUPING RESULTS:", flush=True)
    print(f"   Total files: {total_files}", flush=True)
    print(f"   Total jobs: {total_jobs}", flush=True)

    # Log job summary (without individual file details)
    for job in jobs_summary:
        print(f"   📁 Job {job.job_id}: {job.file_count} file(s)", flush=True)
    
    print("=" * 80, flush=True)

    summary = UploadBatchSummary(
        total_files=total_files,
        total_jobs=total_jobs,
        jobs=jobs_summary
    )

    return UploadResponse(
        success=True,
        message="Files grouped successfully",
        summary=summary
    )


@router.get("/api/group-local-input", response_model=UploadResponse)
async def group_local_input():
    """
    Scan input folder, unpack zip files, and group PDFs by job ID.
    This endpoint processes files locally without requiring file uploads.
    
    Returns:
        UploadResponse with grouped jobs summary
    """
    print("=" * 80, flush=True)
    print("📂 SCANNING LOCAL INPUT FOLDER", flush=True)
    print("=" * 80, flush=True)
    
    # Get input folder path
    input_folder = get_input_folder_path()
    print(f"   Input folder: {input_folder}", flush=True)
    
    if not input_folder.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Input folder not found: {input_folder}"
        )
    
    # Scan for PDF files and unpack zip files
    pdf_files = scan_input_folder(input_folder)
    
    if not pdf_files:
        raise HTTPException(
            status_code=404,
            detail=f"No PDF files found in input folder: {input_folder}"
        )
    
    print(f"\n📄 Found {len(pdf_files)} PDF file(s)", flush=True)
    
    # Group files by job ID
    grouped_jobs = group_local_files_by_job(pdf_files)
    
    # Create summary
    total_files = len(pdf_files)
    total_jobs = len(grouped_jobs)
    
    # Verify count matches - sum of all files in groups should equal total_files
    grouped_file_count = sum(len(job_files) for job_files in grouped_jobs.values())
    if grouped_file_count != total_files:
        print(f"⚠️  WARNING: File count mismatch!", flush=True)
        print(f"   Scanned PDFs: {total_files}", flush=True)
        print(f"   Grouped files: {grouped_file_count}", flush=True)
        print(f"   Difference: {total_files - grouped_file_count}", flush=True)
    
    jobs_summary = []
    for job_id, job_files in grouped_jobs.items():
        job_info = GroupedJobSummary(
            job_id=job_id,
            file_count=len(job_files),
            files=[
                FileInfo(
                    filename=f.name,
                    size=f.stat().st_size if f.exists() else None,
                    content_type="application/pdf"
                )
                for f in job_files
            ]
        )
        jobs_summary.append(job_info)
    
    # Log summary
    print("\n📊 GROUPING RESULTS:", flush=True)
    print(f"   Total files scanned: {total_files}", flush=True)
    print(f"   Total files grouped: {grouped_file_count}", flush=True)
    print(f"   Total jobs: {total_jobs}", flush=True)
    
    # Log job summary (without individual file details)
    for job in jobs_summary:
        print(f"   📁 Job {job.job_id}: {job.file_count} file(s)", flush=True)
    
    # Organize files into job folders
    grouped_folder = organize_grouped_files(grouped_jobs, input_folder)
    
    print("=" * 80, flush=True)
    
    summary = UploadBatchSummary(
        total_files=total_files,
        total_jobs=total_jobs,
        jobs=jobs_summary
    )
    
    return UploadResponse(
        success=True,
        message=f"Found and grouped {total_files} file(s) from input folder. Files organized in: {grouped_folder.name}",
        summary=summary
    )


@router.post("/api/process-local-input", response_model=ProcessBatchResponse)
async def process_local_input(region: str = "AU"):
    """
    Process files from local input folder: scan, unpack zip files, group, classify, and validate.
    
    This endpoint:
    1. Scans input folder for PDFs and unpacks zip files
    2. Creates a new run directory
    3. Groups files by job ID
    4. Classifies each file using Gemini 2.5 Flash
    5. Saves classified PDFs to job folders
    6. Validates against checklist using Gemini 2.5 Pro
    7. Saves validation results as JSON in run folder root
    8. Returns comprehensive results
    
    Args:
        region: Region code (AU or NZ) for checklist validation
    """
    # Validate region
    if region.upper() not in ["AU", "NZ"]:
        raise HTTPException(status_code=400, detail="Region must be 'AU' or 'NZ'")

    print("=" * 80, flush=True)
    print("🚀 PROCESSING LOCAL INPUT FOLDER", flush=True)
    print(f"   Region: {region.upper()}", flush=True)
    print("=" * 80, flush=True)

    # Step 1: Scan input folder
    input_folder = get_input_folder_path()
    print(f"\n📂 Scanning input folder: {input_folder}", flush=True)
    
    if not input_folder.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Input folder not found: {input_folder}"
        )
    
    pdf_files = scan_input_folder(input_folder)
    
    if not pdf_files:
        raise HTTPException(
            status_code=404,
            detail=f"No PDF files found in input folder: {input_folder}"
        )
    
    print(f"   Found {len(pdf_files)} PDF file(s)", flush=True)

    # Step 2: Initialize run
    run_id = get_next_run_id()
    run_path = create_run_directory(run_id)
    
    print(f"\n📂 Created run directory: {run_path}", flush=True)
    print(f"   Run ID: {run_id}", flush=True)
    print(f"   Region: {region.upper()}", flush=True)

    # Step 3: Group files by job
    grouped_jobs = group_local_files_by_job(pdf_files)
    
    print(f"\n📊 Grouped into {len(grouped_jobs)} job(s)", flush=True)

    # Step 4: Process each job IN PARALLEL
    print(f"\n🚀 Starting parallel processing of {len(grouped_jobs)} job(s)...", flush=True)
    
    async def process_single_job_local(job_id: str, job_files: List[Path]) -> ProcessedJobResult:
        """Process a single job with local file paths."""
        print(f"\n{'='*80}", flush=True)
        print(f"📁 Processing Job: {job_id} ({len(job_files)} files)", flush=True)
        print(f"{'='*80}", flush=True)
        
        # Create job directory
        job_path = create_job_directory(run_path, job_id)
        print(f"   Created job folder: {job_path}", flush=True)
        
        # Classify and save each file IN PARALLEL
        print(f"\n   🚀 Starting parallel classification of {len(job_files)} files...", flush=True)
        
        async def process_single_file_local(file_path: Path, idx: int) -> ClassifiedFileInfo:
            """Process a single local file with retry logic."""
            print(f"\n   [{idx}/{len(job_files)}] Processing: {file_path.name}", flush=True)
            
            try:
                # Read file content
                content = file_path.read_bytes()
                
                # Classify document with retry logic (3 total attempts)
                max_retries = 3
                classification = None
                last_error = None
                
                for attempt in range(1, max_retries + 1):
                    try:
                        print(f"      🔍 Classifying document... (attempt {attempt}/{max_retries})", flush=True)
                        classification = await classify_document(content, file_path.name)
                        print(f"      ✓ Type: {classification.document_type}", flush=True)
                        break  # Success, exit retry loop
                        
                    except Exception as classify_error:
                        last_error = classify_error
                        error_msg = str(classify_error)
                        
                        # Check if it's a retryable error (503, timeout, etc.)
                        is_retryable = (
                            "503" in error_msg or
                            "timeout" in error_msg.lower() or
                            "unavailable" in error_msg.lower() or
                            "rate" in error_msg.lower()
                        )
                        
                        if attempt < max_retries and is_retryable:
                            backoff_time = 2 ** (attempt - 1)  # Exponential backoff: 1s, 2s, 4s
                            print(f"      ⚠️  Classification failed: {error_msg}", flush=True)
                            print(f"      🔄 Retrying in {backoff_time}s... (attempt {attempt + 1}/{max_retries})", flush=True)
                            await asyncio.sleep(backoff_time)
                        else:
                            # Not retryable or final attempt
                            if attempt == max_retries:
                                print(f"      ❌ All {max_retries} classification attempts failed", flush=True)
                            raise classify_error
                
                if classification is None:
                    raise last_error or Exception("Classification failed")
                
                # Save with label
                print(f"      💾 Saving file...", flush=True)
                saved_path = save_classified_file(
                    content,
                    file_path.name,
                    classification.document_type,
                    job_path
                )
                
                print(f"      ✓ Saved as: {saved_path.name}", flush=True)
                
                extracted_data = None
                
                return ClassifiedFileInfo(
                    original_filename=file_path.name,
                    saved_filename=saved_path.name,
                    saved_path=str(saved_path),
                    document_type=classification.document_type,
                    extracted_data=extracted_data
                )
                
            except Exception as e:
                print(f"      ❌ Error processing {file_path.name}: {e}", flush=True)
                raise
        
        # Process all files in parallel
        file_tasks = [
            process_single_file_local(file_path, idx + 1)
            for idx, file_path in enumerate(job_files)
        ]
        classified_files = await asyncio.gather(*file_tasks)
        
        print(f"\n   ✓ All {len(classified_files)} files classified and saved", flush=True)
        
        # Prepare documents for validation
        documents: Dict[str, bytes] = {}
        for cf in classified_files:
            if cf.document_type == "entry_print":
                file_path = Path(cf.saved_path)
                documents["entry_print"] = file_path.read_bytes()
            elif cf.document_type == "commercial_invoice":
                file_path = Path(cf.saved_path)
                documents["commercial_invoice"] = file_path.read_bytes()
            elif cf.document_type == "air_waybill":
                file_path = Path(cf.saved_path)
                documents["air_waybill"] = file_path.read_bytes()
        
        # Validate if we have the required documents
        validation_results = None
        validation_file = None
        
        if len(documents) >= 2:  # Need at least 2 document types
            print(f"\n   ✅ Validating against {region.upper()} checklist...", flush=True)
            try:
                validation_results = await validate_all_checks(
                    region=region.upper(),
                    documents=documents
                )
                
                # Save validation results
                validation_file = run_path / f"job_{job_id}_validation_{region.upper()}.json"
                with open(validation_file, 'w') as f:
                    json.dump(validation_results, f, indent=2, default=str)
                
                print(f"   ✓ Validation complete, saved to {validation_file.name}", flush=True)
            except Exception as validation_error:
                print(f"   ⚠️  Validation failed: {validation_error}", flush=True)
        else:
            print(f"\n   ⚠️  Skipping validation - need at least 2 document types (found {len(documents)})", flush=True)
        
        return ProcessedJobResult(
            job_id=job_id,
            job_folder=str(job_path),
            file_count=len(classified_files),
            classified_files=classified_files,
            validation_results=validation_results,
            validation_file=str(validation_file) if validation_file else None
        )
    
    # Process all jobs in parallel
    job_tasks = [
        process_single_job_local(job_id, job_files)
        for job_id, job_files in grouped_jobs.items()
    ]
    processed_jobs = await asyncio.gather(*job_tasks)
    
    print(f"\n{'='*80}", flush=True)
    print(f"✅ BATCH PROCESSING COMPLETE", flush=True)
    print(f"   Run ID: {run_id}", flush=True)
    print(f"   Total jobs processed: {len(processed_jobs)}", flush=True)
    print(f"{'='*80}", flush=True)
    
    total_files = sum(job.file_count for job in processed_jobs)
    
    return ProcessBatchResponse(
        success=True,
        message=f"Processed {total_files} file(s) from local input folder",
        run_id=run_id,
        run_path=str(run_path),
        total_files=total_files,
        total_jobs=len(processed_jobs),
        jobs=processed_jobs
    )


@router.post("/api/process-batch", response_model=ProcessBatchResponse)
async def process_batch(
    files: List[UploadFile],
    region: str = "AU"  # AU or NZ - default to AU
):
    """
    Full batch processing: upload, group, classify, and validate files.
    
    This endpoint:
    1. Creates a new run directory
    2. Groups files by job ID
    3. Classifies each file using Gemini 2.5 Flash
    4. Saves classified PDFs to job folders
    5. Validates against checklist using Gemini 2.5 Pro (3 parallel LLM calls per job)
    6. Saves validation results as JSON in run folder root
    7. Returns comprehensive results
    
    Args:
        files: List of PDF files to process
        region: Region code (AU or NZ) for checklist validation
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")
    
    # Validate region
    if region.upper() not in ["AU", "NZ"]:
        raise HTTPException(status_code=400, detail="Region must be 'AU' or 'NZ'")

    print("=" * 80, flush=True)
    print(f"🚀 BATCH PROCESSING - Received {len(files)} file(s)", flush=True)
    print(f"   Region: {region.upper()}", flush=True)
    print("=" * 80, flush=True)

    # Step 1: Initialize run
    run_id = get_next_run_id()
    run_path = create_run_directory(run_id)
    
    print(f"\n📂 Created run directory: {run_path}", flush=True)
    print(f"   Run ID: {run_id}", flush=True)
    print(f"   Region: {region.upper()}", flush=True)

    # Step 2: Group files by job
    grouped_jobs = group_files_by_job(files)
    
    print(f"\n📊 Grouped into {len(grouped_jobs)} job(s)", flush=True)

    # Step 3: Process each job IN PARALLEL
    print(f"\n🚀 Starting parallel processing of {len(grouped_jobs)} job(s)...", flush=True)
    
    async def process_single_job(job_id: str, job_files: List[UploadFile]) -> ProcessedJobResult:
        """Process a single job with all its files."""
        print(f"\n{'='*80}", flush=True)
        print(f"📁 Processing Job: {job_id} ({len(job_files)} files)", flush=True)
        print(f"{'='*80}", flush=True)
        
        # Create job directory
        job_path = create_job_directory(run_path, job_id)
        print(f"   Created job folder: {job_path}", flush=True)
        
        # Classify and save each file IN PARALLEL
        print(f"\n   🚀 Starting parallel classification of {len(job_files)} files...", flush=True)
        
        async def process_single_file(file: UploadFile, idx: int) -> ClassifiedFileInfo:
            """Process a single file with retry logic."""
            print(f"\n   [{idx}/{len(job_files)}] Processing: {file.filename}", flush=True)
            
            try:
                # Read file content
                content = await file.read()
                await file.seek(0)  # Reset for potential re-reading
                
                # Classify document with retry logic (3 total attempts)
                max_retries = 3
                classification = None
                last_error = None
                
                for attempt in range(1, max_retries + 1):
                    try:
                        print(f"      🔍 Classifying document... (attempt {attempt}/{max_retries})", flush=True)
                        classification = await classify_document(content, file.filename)
                        print(f"      ✓ Type: {classification.document_type}", flush=True)
                        break  # Success, exit retry loop
                        
                    except Exception as classify_error:
                        last_error = classify_error
                        error_msg = str(classify_error)
                        
                        # Check if it's a retryable error (503, timeout, etc.)
                        is_retryable = (
                            "503" in error_msg or
                            "timeout" in error_msg.lower() or
                            "unavailable" in error_msg.lower() or
                            "rate" in error_msg.lower()
                        )
                        
                        if attempt < max_retries and is_retryable:
                            backoff_time = 2 ** (attempt - 1)  # Exponential backoff: 1s, 2s, 4s
                            print(f"      ⚠️  Classification failed: {error_msg}", flush=True)
                            print(f"      🔄 Retrying in {backoff_time}s... (attempt {attempt + 1}/{max_retries})", flush=True)
                            await asyncio.sleep(backoff_time)
                        else:
                            # Not retryable or final attempt
                            if attempt == max_retries:
                                print(f"      ❌ All {max_retries} classification attempts failed", flush=True)
                            raise classify_error
                
                if classification is None:
                    raise last_error or Exception("Classification failed")
                
                # Save with label
                print(f"      💾 Saving file...", flush=True)
                saved_path = save_classified_file(
                    content,
                    file.filename,
                    classification.document_type,
                    job_path
                )
                
                print(f"      ✓ Saved as: {saved_path.name}", flush=True)
                
                # Extract structured data for supported document types (COMMENTED OUT - not needed)
                extracted_data = None
                # if classification.document_type in ["entry_print", "commercial_invoice"]:
                #     try:
                #         print(f"      📊 Extracting structured data...", flush=True)
                #         extraction_result = await extract_document_data(
                #             content, 
                #             file.filename, 
                #             classification.document_type
                #         )
                #         extracted_data = extraction_result.model_dump()
                #         print(f"      ✓ Extracted {len(extracted_data)} fields", flush=True)
                #         
                #         # Save extracted data as JSON
                #         print(f"      💾 Saving extraction JSON...", flush=True)
                #         json_path = save_extraction_json(
                #             extracted_data,
                #             file.filename,
                #             classification.document_type,
                #             job_path
                #         )
                #         print(f"      ✓ Saved JSON as: {json_path.name}", flush=True)
                #         
                #     except Exception as extract_error:
                #         print(f"      ⚠️  Extraction failed: {extract_error}", flush=True)
                #         # Continue even if extraction fails
                
                return ClassifiedFileInfo(
                    original_filename=file.filename,
                    saved_filename=saved_path.name,
                    saved_path=str(saved_path),
                    document_type=classification.document_type,
                    extracted_data=extracted_data
                )
                
            except Exception as e:
                print(f"      ❌ Error processing {file.filename}: {e}", flush=True)
                # Return error result instead of failing
                return ClassifiedFileInfo(
                    original_filename=file.filename,
                    saved_filename="",
                    saved_path="",
                    document_type="other",
                    extracted_data=None
                )
        
        # Process all files in parallel using asyncio.gather
        tasks = [process_single_file(file, idx) for idx, file in enumerate(job_files, 1)]
        classified_files = await asyncio.gather(*tasks)
        
        # Convert to list
        classified_files = list(classified_files)
        
        # Step 4: Run checklist validation
        validation_results = None
        validation_file_path = None
        
        print(f"\n   📋 Running checklist validation for region {region.upper()}...", flush=True)
        
        try:
            # Load classified PDFs from job folder
            documents = {}
            entry_prints = []  # Collect all entry prints to choose the best one
            
            for classified_file in classified_files:
                if classified_file.saved_filename and classified_file.document_type in ["entry_print", "commercial_invoice", "air_waybill"]:
                    pdf_path = Path(classified_file.saved_path)
                    if pdf_path.exists():
                        pdf_bytes = pdf_path.read_bytes()
                        
                        if classified_file.document_type == "entry_print":
                            # For entry_print, collect all of them (NZ may have E2 and SAD forms)
                            entry_prints.append({
                                "filename": classified_file.saved_filename,
                                "bytes": pdf_bytes,
                                "size": len(pdf_bytes)
                            })
                            print(f"      Loaded {classified_file.document_type} PDF ({len(pdf_bytes):,} bytes) - {classified_file.saved_filename}", flush=True)
                        else:
                            # For other docs, just add directly
                            documents[classified_file.document_type] = pdf_bytes
                            print(f"      Loaded {classified_file.document_type} PDF ({len(pdf_bytes):,} bytes)", flush=True)
            
            # Handle multiple entry prints - prefer larger/more detailed ones
            if entry_prints:
                if len(entry_prints) > 1:
                    # Multiple entry prints found (e.g., NZ E2 + SAD forms)
                    # Prefer SAD (larger) over E2 (smaller summary)
                    # Sort by size descending and take the largest
                    entry_prints.sort(key=lambda x: x["size"], reverse=True)
                    selected = entry_prints[0]
                    print(f"      ℹ️  Multiple entry prints found ({len(entry_prints)}), using largest: {selected['filename']} ({selected['size']:,} bytes)", flush=True)
                    documents["entry_print"] = selected["bytes"]
                else:
                    # Only one entry print
                    documents["entry_print"] = entry_prints[0]["bytes"]
            
            # Check if we have the required documents
            if "entry_print" in documents and "commercial_invoice" in documents:
                print(f"\n   🔄 Starting validation with {len(documents)} document(s)...", flush=True)
                
                # Run validation (3 LLM calls in parallel: header + valuation + tariff extraction)
                validation_results = await validate_all_checks(
                    region=region.upper(),
                    documents=documents,
                    job_id=job_id
                )
                
                # Save validation results to run folder root
                validation_filename = f"job_{job_id}_validation_{region.upper()}.json"
                validation_file_path = run_path / validation_filename
                
                # Convert validation results to serializable format
                serializable_results = {
                    "job_id": job_id,
                    "region": region.upper(),
                    "header": [v.model_dump() for v in validation_results["header"]],
                    "valuation": [v.model_dump() for v in validation_results["valuation"]],
                    "summary": validation_results["summary"]
                }
                
                # Add tariff validations if available
                if validation_results.get("tariff_validations"):
                    serializable_results["tariff_line_checks"] = [v.model_dump() for v in validation_results["tariff_validations"]]
                    serializable_results["tariff_summary"] = validation_results["tariff_summary"]
                
                validation_file_path.write_text(json.dumps(serializable_results, indent=2, ensure_ascii=False))
                
                print(f"\n   ✅ Validation complete!", flush=True)
                print(f"      Saved to: {validation_filename}", flush=True)
                print(f"      Summary: {validation_results['summary']['passed']} PASS, "
                          f"{validation_results['summary']['failed']} FAIL, "
                          f"{validation_results['summary']['questionable']} QUESTIONABLE, "
                          f"{validation_results['summary'].get('not_applicable', 0)} N/A", flush=True)
                
                # Save tariff line items separately if extraction was successful
                if validation_results.get("tariff_lines"):
                    tariff_filename = f"job_{job_id}_tariff_lines.json"
                    tariff_file_path = run_path / tariff_filename
                    
                    # Convert to serializable format
                    tariff_data = {
                        "job_id": job_id,
                        "total_lines": len(validation_results["tariff_lines"]),
                        "line_items": [item.model_dump() for item in validation_results["tariff_lines"]]
                    }
                    
                    tariff_file_path.write_text(json.dumps(tariff_data, indent=2, ensure_ascii=False))
                    
                    print(f"\n   ✅ Tariff extraction complete!", flush=True)
                    print(f"      Saved to: {tariff_filename}", flush=True)
                    print(f"      Total line items: {len(validation_results['tariff_lines'])}", flush=True)
                    
                    # Log tariff validation summary
                    if validation_results.get("tariff_validations"):
                        tariff_sum = validation_results["tariff_summary"]
                        print(f"      Tariff validation: {tariff_sum['passed']} PASS, "
                              f"{tariff_sum['failed']} FAIL, "
                              f"{tariff_sum['questionable']} QUESTIONABLE, "
                              f"{tariff_sum.get('not_applicable', 0)} N/A", flush=True)
                else:
                    print(f"\n   ⚠️  No tariff lines extracted", flush=True)
            else:
                missing = []
                if "entry_print" not in documents:
                    missing.append("entry_print")
                if "commercial_invoice" not in documents:
                    missing.append("commercial_invoice")
                print(f"   ⚠️  Skipping validation - missing required documents: {', '.join(missing)}", flush=True)
                
        except Exception as validation_error:
            print(f"   ❌ Validation failed: {validation_error}", flush=True)
            # Continue even if validation fails
        
        # Build and return job result
        job_result = ProcessedJobResult(
            job_id=job_id,
            job_folder=str(job_path),
            file_count=len(classified_files),
            classified_files=classified_files,
            validation_results=validation_results,
            validation_file=str(validation_file_path) if validation_file_path else None
        )
        
        print(f"\n   ✅ Job {job_id} complete: {len(classified_files)} files processed", flush=True)
        return job_result
    
    # Process all jobs in parallel using asyncio.gather
    job_tasks = [process_single_job(job_id, job_files) for job_id, job_files in grouped_jobs.items()]
    processed_jobs = await asyncio.gather(*job_tasks, return_exceptions=True)
    
    # Filter out any exceptions and log them
    successful_jobs = []
    for i, result in enumerate(processed_jobs):
        if isinstance(result, Exception):
            job_id = list(grouped_jobs.keys())[i]
            print(f"\n❌ Job {job_id} failed with error: {result}", flush=True)
        else:
            successful_jobs.append(result)
    
    processed_jobs = successful_jobs
    total_processed = sum(
        len([f for f in job.classified_files if f.saved_filename != ""])
        for job in processed_jobs
    )

    print(f"\n{'='*80}", flush=True)
    print(f"🎉 BATCH PROCESSING COMPLETE", flush=True)
    print(f"   Run ID: {run_id}", flush=True)
    print(f"   Total files: {total_processed}/{len(files)}", flush=True)
    print(f"   Total jobs: {len(processed_jobs)}", flush=True)
    print(f"   Output: {run_path}", flush=True)
    print(f"{'='*80}\n", flush=True)

    return ProcessBatchResponse(
        success=True,
        message=f"Batch processing complete: {total_processed} files processed",
        run_id=run_id,
        run_path=str(run_path),
        total_files=total_processed,
        total_jobs=len(processed_jobs),
        jobs=processed_jobs
    )
