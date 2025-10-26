"""
Batch processing module for grouping and managing audit job files.
"""
from typing import List, Dict
from fastapi import UploadFile
import re


def extract_job_id(filename: str) -> str:
    """
    Extract job ID from filename (leading number before first underscore or special char).
    
    Examples:
        "2219477116_AWB.pdf" -> "2219477116"
        "2219477116^^13387052^FRML.pdf" -> "2219477116"
        "2555462195_INV.pdf" -> "2555462195"
    """
    # Match leading digits before first underscore or special character
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

