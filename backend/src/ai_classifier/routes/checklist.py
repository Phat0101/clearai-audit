"""
Checklist management routes for viewing and editing AU/NZ checklists.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import json
from pathlib import Path
import logging

import os

router = APIRouter()
logger = logging.getLogger(__name__)

# Path to checklists directory - works for both dev and Docker
checklist_dir_env = os.getenv("CHECKLISTS_DIR")
if checklist_dir_env:
    CHECKLISTS_DIR = Path(checklist_dir_env)
    logger.info(f"Using checklist directory from env: {CHECKLISTS_DIR}")
else:
    # Auto-detect: try Docker path first, then dev path
    docker_path = Path("/app/checklists")
    if docker_path.exists():
        CHECKLISTS_DIR = docker_path
        logger.info(f"Using Docker checklist directory: {CHECKLISTS_DIR}")
    else:
        # Dev: from checklist.py -> routes -> ai_classifier -> src -> backend
        current_file = Path(__file__).resolve()
        # Go up: routes -> ai_classifier -> src -> backend
        backend_dir = current_file.parent.parent.parent.parent
        CHECKLISTS_DIR = backend_dir / "checklists"
        logger.info(f"Using dev checklist directory: {CHECKLISTS_DIR}")


class ChecklistUpdateRequest(BaseModel):
    """Request model for updating a checklist."""
    content: dict


@router.get("/api/checklist/{region}")
async def get_checklist(region: str):
    """
    Get the checklist JSON for a specific region.
    
    Args:
        region: Either "AU" or "NZ"
        
    Returns:
        The checklist JSON content
    """
    region_upper = region.upper()
    
    if region_upper not in ["AU", "NZ"]:
        raise HTTPException(status_code=400, detail="Region must be 'AU' or 'NZ'")
    
    checklist_file = CHECKLISTS_DIR / f"{region.lower()}_checklist.json"
    
    if not checklist_file.exists():
        raise HTTPException(status_code=404, detail=f"Checklist file not found for region {region_upper}")
    
    try:
        with open(checklist_file, 'r', encoding='utf-8') as f:
            content = json.load(f)
        
        logger.info(f"Retrieved checklist for region {region_upper}")
        return {
            "success": True,
            "region": region_upper,
            "content": content,
            "file_path": str(checklist_file)
        }
    except Exception as e:
        logger.error(f"Error reading checklist for {region_upper}: {e}")
        raise HTTPException(status_code=500, detail=f"Error reading checklist: {str(e)}")


@router.put("/api/checklist/{region}")
async def update_checklist(region: str, request: ChecklistUpdateRequest):
    """
    Update the checklist JSON for a specific region.
    
    Args:
        region: Either "AU" or "NZ"
        request: ChecklistUpdateRequest containing the new content
        
    Returns:
        Success message
    """
    region_upper = region.upper()
    
    if region_upper not in ["AU", "NZ"]:
        raise HTTPException(status_code=400, detail="Region must be 'AU' or 'NZ'")
    
    checklist_file = CHECKLISTS_DIR / f"{region.lower()}_checklist.json"
    
    try:
        # Validate JSON structure
        content = request.content
        
        # Basic validation: check required fields
        if "version" not in content or "region" not in content or "categories" not in content:
            raise ValueError("Invalid checklist structure: missing required fields (version, region, categories)")
        
        if content["region"] != region_upper:
            raise ValueError(f"Region mismatch: checklist region '{content['region']}' does not match URL region '{region_upper}'")
        
        # Write to file with pretty formatting
        with open(checklist_file, 'w', encoding='utf-8') as f:
            json.dump(content, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Updated checklist for region {region_upper}")
        return {
            "success": True,
            "message": f"Checklist for {region_upper} updated successfully",
            "region": region_upper,
            "file_path": str(checklist_file)
        }
    except ValueError as e:
        logger.error(f"Validation error updating checklist for {region_upper}: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating checklist for {region_upper}: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating checklist: {str(e)}")

