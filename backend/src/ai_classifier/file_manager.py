"""
File management module for organizing and storing classified documents.
"""
import os
import re
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any


# Output base directory from environment variable
# Smart default: /app/output for Docker, ./output for local dev
_default_output = "/app/output" if os.path.exists("/app") else "../output"
OUTPUT_BASE_DIR = Path(os.getenv("OUTPUT_DIRECTORY", _default_output))


def get_next_run_id() -> str:
    """
    Generate next run ID for today in format: YYYY-MM-DD_run_NNN
    
    Returns:
        Run ID string like "2025-10-13_run_001"
    """
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
    """
    Create directory for this run.
    
    Args:
        run_id: Run identifier (e.g., "2025-10-13_run_001")
        
    Returns:
        Path to the created run directory
    """
    run_path = OUTPUT_BASE_DIR / run_id
    run_path.mkdir(parents=True, exist_ok=True)
    return run_path


def create_job_directory(run_path: Path, job_id: str) -> Path:
    """
    Create directory for a job within a run.
    
    Args:
        run_path: Path to the run directory
        job_id: Job identifier (e.g., "2219477116")
        
    Returns:
        Path to the created job directory
    """
    job_path = run_path / f"job_{job_id}"
    job_path.mkdir(parents=True, exist_ok=True)
    return job_path


def save_classified_file(
    file_content: bytes,
    original_filename: str,
    document_type: str,
    job_path: Path
) -> Path:
    """
    Save file with document type label appended to filename.
    
    Args:
        file_content: Raw file content as bytes
        original_filename: Original filename (e.g., "2219477116_AWB.pdf")
        document_type: Classified document type (e.g., "air_waybill")
        job_path: Path to the job directory
        
    Returns:
        Path to the saved file
        
    Example:
        Input: "2219477116_AWB_OSA_OAA_8VD_20250929_132113.pdf"
        Output: "2219477116_AWB_OSA_OAA_8VD_20250929_132113_air_waybill.pdf"
    """
    # Remove .pdf extension
    base_name = original_filename.rsplit('.', 1)[0] if '.' in original_filename else original_filename
    
    # Add document type label
    new_filename = f"{base_name}_{document_type}.pdf"
    
    # Save file
    file_path = job_path / new_filename
    file_path.write_bytes(file_content)
    
    return file_path


def save_extraction_json(
    extracted_data: Dict[str, Any],
    original_filename: str,
    document_type: str,
    job_path: Path
) -> Path:
    """
    Save extracted data as JSON file with the same base name as the classified PDF.
    
    Args:
        extracted_data: Dictionary of extracted data
        original_filename: Original filename (e.g., "2219477116_AWB.pdf")
        document_type: Classified document type (e.g., "air_waybill")
        job_path: Path to the job directory
        
    Returns:
        Path to the saved JSON file
        
    Example:
        Input: "2219477116_AWB_OSA_OAA_8VD_20250929_132113.pdf"
        Output: "2219477116_AWB_OSA_OAA_8VD_20250929_132113_air_waybill.json"
    """
    # Remove .pdf extension
    base_name = original_filename.rsplit('.', 1)[0] if '.' in original_filename else original_filename
    
    # Add document type label and .json extension
    json_filename = f"{base_name}_{document_type}.json"
    
    # Save JSON file
    json_path = job_path / json_filename
    json_path.write_text(json.dumps(extracted_data, indent=2, ensure_ascii=False))
    
    return json_path


def get_output_base_dir() -> Path:
    """Get the base output directory path."""
    return OUTPUT_BASE_DIR
