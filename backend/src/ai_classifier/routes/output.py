"""
Output directory browsing and file download routes.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
import logging
import os
from typing import List, Dict, Any
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)

# Get output directory from environment or use default - resolve to absolute path
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIRECTORY", "./output")).resolve()
logger.info(f"Output directory set to: {OUTPUT_DIR}")


class FileItem(BaseModel):
    """Represents a file in the directory listing."""
    name: str
    path: str
    size: int
    type: str  # "file" or "directory"
    modified: float


class DirectoryContents(BaseModel):
    """Response model for directory contents."""
    path: str
    items: List[FileItem]


@router.get("/api/output/runs")
async def list_runs():
    """
    List all run directories in the output folder.
    
    Returns:
        List of run directory names sorted by modification time (newest first)
    """
    try:
        if not OUTPUT_DIR.exists():
            return {
                "success": True,
                "runs": []
            }
        
        runs = []
        for item in OUTPUT_DIR.iterdir():
            if item.is_dir():
                stats = item.stat()
                runs.append({
                    "name": item.name,
                    "path": str(item.relative_to(OUTPUT_DIR)),
                    "modified": stats.st_mtime,
                    "size": sum(f.stat().st_size for f in item.rglob('*') if f.is_file())
                })
        
        # Sort by modification time, newest first
        runs.sort(key=lambda x: x["modified"], reverse=True)
        
        logger.info(f"Listed {len(runs)} run directories")
        return {
            "success": True,
            "runs": runs
        }
    except Exception as e:
        logger.error(f"Error listing runs: {e}")
        raise HTTPException(status_code=500, detail=f"Error listing runs: {str(e)}")


@router.get("/api/output/browse")
async def browse_directory(path: str = ""):
    """
    Browse contents of a directory within the output folder.
    
    Args:
        path: Relative path within the output directory
        
    Returns:
        DirectoryContents with files and subdirectories
    """
    try:
        # Construct the full path
        if path:
            full_path = OUTPUT_DIR / path
        else:
            full_path = OUTPUT_DIR
        
        # Security check: ensure the path is within OUTPUT_DIR
        try:
            full_path = full_path.resolve()
            # OUTPUT_DIR is already resolved at initialization
            if not str(full_path).startswith(str(OUTPUT_DIR)):
                logger.warning(f"Access denied: {full_path} not in {OUTPUT_DIR}")
                raise HTTPException(status_code=403, detail="Access denied: path outside output directory")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Path validation error: {e}")
            raise HTTPException(status_code=400, detail="Invalid path")
        
        if not full_path.exists():
            raise HTTPException(status_code=404, detail="Directory not found")
        
        if not full_path.is_dir():
            raise HTTPException(status_code=400, detail="Path is not a directory")
        
        items = []
        for item in full_path.iterdir():
            stats = item.stat()
            relative_path = str(item.relative_to(OUTPUT_DIR))
            
            items.append(FileItem(
                name=item.name,
                path=relative_path,
                size=stats.st_size if item.is_file() else 0,
                type="directory" if item.is_dir() else "file",
                modified=stats.st_mtime
            ))
        
        # Sort: directories first, then files, both alphabetically
        items.sort(key=lambda x: (x.type == "file", x.name.lower()))
        
        logger.info(f"Browsed directory: {path or 'root'} ({len(items)} items)")
        return DirectoryContents(
            path=path,
            items=items
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error browsing directory {path}: {e}")
        raise HTTPException(status_code=500, detail=f"Error browsing directory: {str(e)}")


@router.get("/api/output/download")
async def download_file(path: str):
    """
    Download a file from the output directory.
    
    Args:
        path: Relative path to the file within the output directory
        
    Returns:
        File content as a download
    """
    try:
        # Construct the full path
        full_path = OUTPUT_DIR / path
        
        # Security check: ensure the path is within OUTPUT_DIR
        try:
            full_path = full_path.resolve()
            # OUTPUT_DIR is already resolved at initialization
            if not str(full_path).startswith(str(OUTPUT_DIR)):
                logger.warning(f"Access denied: {full_path} not in {OUTPUT_DIR}")
                raise HTTPException(status_code=403, detail="Access denied: path outside output directory")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Path validation error: {e}")
            raise HTTPException(status_code=400, detail="Invalid path")
        
        if not full_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        
        if not full_path.is_file():
            raise HTTPException(status_code=400, detail="Path is not a file")
        
        logger.info(f"Downloading file: {path}")
        
        # Determine media type based on file extension
        media_type = "application/octet-stream"
        if path.endswith('.pdf'):
            media_type = "application/pdf"
        elif path.endswith('.json'):
            media_type = "application/json"
        elif path.endswith('.csv'):
            media_type = "text/csv"
        
        return FileResponse(
            path=str(full_path),
            filename=full_path.name,
            media_type=media_type
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading file {path}: {e}")
        raise HTTPException(status_code=500, detail=f"Error downloading file: {str(e)}")


@router.delete("/api/output/delete")
async def delete_item(path: str):
    """
    Delete a file or directory from the output folder.
    
    Args:
        path: Relative path to the item within the output directory
        
    Returns:
        Success message
    """
    try:
        # Construct the full path
        full_path = OUTPUT_DIR / path
        
        # Security check: ensure the path is within OUTPUT_DIR
        try:
            full_path = full_path.resolve()
            # OUTPUT_DIR is already resolved at initialization
            if not str(full_path).startswith(str(OUTPUT_DIR)):
                logger.warning(f"Access denied: {full_path} not in {OUTPUT_DIR}")
                raise HTTPException(status_code=403, detail="Access denied: path outside output directory")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Path validation error: {e}")
            raise HTTPException(status_code=400, detail="Invalid path")
        
        if not full_path.exists():
            raise HTTPException(status_code=404, detail="Item not found")
        
        # Delete file or directory
        if full_path.is_file():
            full_path.unlink()
            logger.info(f"Deleted file: {path}")
        elif full_path.is_dir():
            import shutil
            shutil.rmtree(full_path)
            logger.info(f"Deleted directory: {path}")
        
        return {
            "success": True,
            "message": f"Deleted: {path}"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting {path}: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting item: {str(e)}")

