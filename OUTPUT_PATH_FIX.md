# Output Browser Path Resolution Fix

## The Problem

When browsing directories in the output browser, you encountered this error:

```
Error browsing directory 2025-10-23_run_001: '/Users/pat/Desktop/clearai-audit/output/2025-10-23_run_001/job_2219477116' is not in the subpath of '../output' OR one path is relative and the other is absolute.
```

## Root Cause

The security check in `/backend/src/ai_classifier/routes/output.py` was comparing paths incorrectly:

### Before (Buggy Code)
```python
# OUTPUT_DIR was relative: Path("./output")
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIRECTORY", "./output"))

# In the security check:
full_path = full_path.resolve()  # Becomes absolute: /Users/pat/.../output/...
OUTPUT_DIR.resolve()  # ❌ Called but result not stored!
if not str(full_path).startswith(str(OUTPUT_DIR.resolve())):  # Comparing absolute vs relative
    raise HTTPException(...)
```

The issue:
1. `full_path.resolve()` returned an **absolute path** (e.g., `/Users/pat/Desktop/clearai-audit/output/...`)
2. `OUTPUT_DIR.resolve()` was called but **the result wasn't stored**
3. The comparison used `OUTPUT_DIR` (still relative: `./output`) vs `full_path` (absolute)
4. Python's `startswith()` check failed because you can't reliably compare relative and absolute paths

## The Fix

### Changes Made

**1. Resolve OUTPUT_DIR at initialization**
```python
# Now OUTPUT_DIR is always absolute from the start
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIRECTORY", "./output")).resolve()
logger.info(f"Output directory set to: {OUTPUT_DIR}")
```

**2. Simplified security checks**
```python
# Security check: ensure the path is within OUTPUT_DIR
try:
    full_path = full_path.resolve()  # Make absolute
    # OUTPUT_DIR is already resolved at initialization
    if not str(full_path).startswith(str(OUTPUT_DIR)):  # Both absolute now
        logger.warning(f"Access denied: {full_path} not in {OUTPUT_DIR}")
        raise HTTPException(status_code=403, detail="Access denied: path outside output directory")
except HTTPException:
    raise  # Re-raise HTTPExceptions
except Exception as e:
    logger.error(f"Path validation error: {e}")
    raise HTTPException(status_code=400, detail="Invalid path")
```

**3. Applied to all functions**
Fixed the same issue in:
- `browse_directory()` - Browse folder contents
- `download_file()` - Download individual files  
- `delete_item()` - Delete files or folders

## Files Modified

- `/Users/pat/Desktop/clearai-audit/backend/src/ai_classifier/routes/output.py`

## Testing

After the fix, you should be able to:

1. **List runs**: Click on the Output Browser page
2. **Expand directories**: Click on any run to see jobs inside
3. **Browse recursively**: Click on job folders to see files
4. **Download files**: Hover and click download on any file
5. **Delete items**: Remove unwanted runs or files

## Why It Works Now

Both paths are now absolute and comparable:
- `OUTPUT_DIR`: `/Users/pat/Desktop/clearai-audit/output`
- `full_path`: `/Users/pat/Desktop/clearai-audit/output/2025-10-23_run_001/job_123/file.pdf`

The `startswith()` check correctly validates that `full_path` is within `OUTPUT_DIR`.

## Additional Improvements

Added logging to help debug path issues:
```python
logger.info(f"Output directory set to: {OUTPUT_DIR}")  # At startup
logger.warning(f"Access denied: {full_path} not in {OUTPUT_DIR}")  # If validation fails
```

## Dev Mode vs Docker

This fix works in both environments:

**Dev Mode (`./dev.sh`)**:
- `OUTPUT_DIRECTORY` not set → defaults to `./output`
- Resolves to: `/Users/pat/Desktop/clearai-audit/output`

**Docker Mode**:
- `OUTPUT_DIRECTORY=/app/output` (set in docker-compose.yml)
- Already absolute: `/app/output`

In both cases, OUTPUT_DIR is now always an absolute path.

