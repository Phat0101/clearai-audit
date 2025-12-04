"""
Batch processing module for grouping and managing audit job files.
"""
from typing import List, Dict
from fastapi import UploadFile
from pathlib import Path
import re
import zipfile
import os
import shutil
from datetime import datetime


def extract_job_id(filename: str) -> str:
    """
    Extract job ID from filename (leading number before first underscore or special char).
    Handles both standard format and holdingarea_ prefix format.
    
    Examples:
        "2219477116_AWB.pdf" -> "2219477116"
        "2219477116^^13387052^FRML.pdf" -> "2219477116"
        "2555462195_INV.pdf" -> "2555462195"
        "holdingarea_1470585675_25GBBPO9L3RIAI4AR1___20251023__BACKUP_LV__EMA.pdf" -> "1470585675"
        "holdingarea_3796663441_25GBBVXD0YBYXQSAR7___20251027__BACKUP_DHLD__EMA.pdf" -> "3796663441"
    """
    # First check for holdingarea_ prefix format
    holdingarea_match = re.match(r'^holdingarea_(\d+)', filename, re.IGNORECASE)
    if holdingarea_match:
        return holdingarea_match.group(1)
    
    # Otherwise, match leading digits before first underscore or special character
    match = re.match(r'^(\d+)', filename)
    if match:
        return match.group(1)
    return "unknown"


def group_files_by_job(files: List[UploadFile]) -> Dict[str, List[UploadFile]]:
    """
    Group uploaded files by job ID extracted from filename.
    
    Args:
        files: List of uploaded PDF files
        
    Returns:
        Dictionary with job_id as key and list of files as value
    """
    jobs: Dict[str, List[UploadFile]] = {}
    
    for file in files:
        job_id = extract_job_id(file.filename)
        
        if job_id not in jobs:
            jobs[job_id] = []
        
        jobs[job_id].append(file)
    
    return jobs


def summarize_grouped_jobs(grouped_jobs: Dict[str, List[UploadFile]]) -> Dict:
    """
    Create a summary of grouped jobs for logging and response.
    
    Args:
        grouped_jobs: Dictionary of job_id -> files
        
    Returns:
        Summary dictionary with job information
    """
    summary = {
        "total_files": sum(len(files) for files in grouped_jobs.values()),
        "total_jobs": len(grouped_jobs),
        "jobs": []
    }
    
    for job_id, files in grouped_jobs.items():
        job_info = {
            "job_id": job_id,
            "file_count": len(files),
            "files": [
                {
                    "filename": file.filename,
                    "size": file.size if hasattr(file, 'size') else None,
                    "content_type": file.content_type
                }
                for file in files
            ]
        }
        summary["jobs"].append(job_info)
    
    return summary


def group_local_files_by_job(file_paths: List[Path]) -> Dict[str, List[Path]]:
    """
    Group local file paths by job ID extracted from filename.
    
    Args:
        file_paths: List of Path objects pointing to PDF files
        
    Returns:
        Dictionary with job_id as key and list of file paths as value
    """
    jobs: Dict[str, List[Path]] = {}
    
    for file_path in file_paths:
        job_id = extract_job_id(file_path.name)
        
        if job_id not in jobs:
            jobs[job_id] = []
        
        jobs[job_id].append(file_path)
    
    return jobs


def scan_input_folder(input_folder: Path) -> List[Path]:
    """
    Scan input folder for PDF files, unpacking any zip files found.
    Recursively scans all subdirectories for PDFs (case-insensitive).
    
    Args:
        input_folder: Path to the input folder
        
    Returns:
        List of Path objects pointing to PDF files (including extracted ones)
    """
    pdf_files_set: set[Path] = set()
    
    if not input_folder.exists():
        return list(pdf_files_set)
    
    # First, handle zip files and extract them
    zip_files = [item for item in input_folder.iterdir() if item.is_file() and item.suffix.lower() == '.zip']
    
    for zip_item in zip_files:
        # Extract zip file
        print(f"📦 Extracting zip file: {zip_item.name}", flush=True)
        try:
            with zipfile.ZipFile(zip_item, 'r') as zip_ref:
                # Extract to a temporary subfolder with zip name
                extract_dir = input_folder / zip_item.stem
                extract_dir.mkdir(exist_ok=True)
                zip_ref.extractall(extract_dir)
                
                # Find all PDFs in extracted folder (case-insensitive)
                extracted_count = 0
                for extracted_file in extract_dir.rglob('*'):
                    if extracted_file.is_file():
                        # Check extension case-insensitively
                        if extracted_file.suffix.lower() == '.pdf':
                            pdf_files_set.add(extracted_file.resolve())
                            extracted_count += 1
                
                print(f"   ✓ Extracted {extracted_count} PDF file(s) from {zip_item.name}", flush=True)
                    
        except (zipfile.BadZipFile, OSError, zipfile.LargeZipFile) as e:
            print(f"   ✗ Error extracting {zip_item.name}: {e}", flush=True)
    
    # Now recursively scan for all PDF files in the input folder (case-insensitive)
    # This will find PDFs that were already there, as well as extracted ones
    for item in input_folder.rglob('*'):
        if item.is_file() and item.suffix.lower() == '.pdf':
            resolved = item.resolve()
            if resolved not in pdf_files_set:
                pdf_files_set.add(resolved)
    
    pdf_files = list(pdf_files_set)
    print(f"📊 Total PDF files found: {len(pdf_files)}", flush=True)
    
    return pdf_files


def get_input_folder_path() -> Path:
    """
    Get the input folder path, handling both Docker and local dev environments.
    
    Returns:
        Path to the input folder
    """
    # Check if we're in Docker (common indicator)
    if os.path.exists("/app"):
        # In Docker, input folder should be at /app/input or mounted
        input_path = Path("/app/input")
    else:
        # Local dev - go up from backend/src/ai_classifier/util to project root
        current_file = Path(__file__)
        project_root = current_file.parent.parent.parent.parent.parent
        input_path = project_root / "input"
    
    return input_path


def organize_grouped_files(
    grouped_jobs: Dict[str, List[Path]],
    base_folder: Path
) -> Path:
    """
    Organize grouped files into job folders for easy access by auditors.
    
    Creates a folder structure like:
    input/grouped_YYYY-MM-DD_HHMMSS/
        job_1234567890/
            file1.pdf
            file2.pdf
        job_0987654321/
            file1.pdf
    
    Args:
        grouped_jobs: Dictionary mapping job_id to list of file paths
        base_folder: Base folder (typically input folder) where to create grouped folder
        
    Returns:
        Path to the created grouped folder
    """
    # Create grouped folder with timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    grouped_folder = base_folder / f"grouped_{timestamp}"
    grouped_folder.mkdir(parents=True, exist_ok=True)
    
    print(f"\n📁 Organizing files into job folders...", flush=True)
    print(f"   Grouped folder: {grouped_folder}", flush=True)
    
    total_copied = 0
    for job_id, job_files in grouped_jobs.items():
        # Create job folder
        job_folder = grouped_folder / f"job_{job_id}"
        job_folder.mkdir(parents=True, exist_ok=True)
        
        # Copy files to job folder
        for file_path in job_files:
            try:
                # Copy file to job folder, preserving original filename
                dest_path = job_folder / file_path.name
                shutil.copy2(file_path, dest_path)
                total_copied += 1
            except (OSError, shutil.Error, PermissionError) as e:
                print(f"   ⚠️  Error copying {file_path.name} to job_{job_id}: {e}", flush=True)
        
        print(f"   ✓ Job {job_id}: {len(job_files)} file(s) → {job_folder.name}/", flush=True)
    
    print(f"\n✅ Organized {total_copied} file(s) into {len(grouped_jobs)} job folder(s)", flush=True)
    print(f"   Location: {grouped_folder}", flush=True)
    
    return grouped_folder

