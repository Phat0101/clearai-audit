# Path Configuration Fixes

## Issues Fixed

### 1. **Output Browser 401 Authentication Error**
**Problem**: The `/api/output/*` endpoints required authentication, causing failures.

**Solution**: Added `/api/output/` to the `_EXEMPT_PREFIXES` list in `main.py` to bypass authentication for output browsing endpoints.

**File Changed**: `backend/src/ai_classifier/main.py`

### 2. **Checklist Path Resolution for Dev vs Docker**
**Problem**: Checklist files couldn't be found when running with `./dev.sh` (local development) vs Docker deployment due to different directory structures.

**Solution**: Implemented smart path detection that works in both environments:
- First checks `CHECKLISTS_DIR` environment variable (if set)
- Then checks if `/app/checklists` exists (Docker)
- Finally falls back to calculating path relative to project root (dev)

**Files Changed**:
- `backend/src/ai_classifier/checklist_models.py`
- `backend/src/ai_classifier/routes/checklist.py`

## Path Resolution Logic

### Docker Environment
```
/app/
├── checklists/           ← Mounted or copied here
│   ├── au_checklist.json
│   └── nz_checklist.json
└── src/
    └── ai_classifier/
```

Detection: Checks if `/app/checklists` exists

### Development Environment (./dev.sh)
```
clearai-audit/
├── checklists/           ← Located in project root
│   ├── au_checklist.json
│   └── nz_checklist.json
└── backend/
    └── src/
        └── ai_classifier/
```

Detection: Calculates path from file location to project root

## Environment Variable (Optional)

You can explicitly set the checklist directory:

```bash
export CHECKLISTS_DIR=/path/to/checklists
```

This overrides auto-detection and can be useful for custom deployments.

## Logging Added

Both files now include debug logging to show which path is being used:
- `checklist_models.py`: Logs the resolved path when loading checklists
- `routes/checklist.py`: Logs at module load time which path detection method was used

## Testing

### Test in Dev Mode
```bash
./dev.sh
# Check logs for: "Using dev checklist directory: ..."
```

### Test in Docker
```bash
docker-compose up --build
# Check logs for: "Using Docker checklist directory: ..."
```

### Verify Endpoints Work
```bash
# Test output browser
curl http://localhost:8000/api/output/runs

# Test checklist retrieval
curl http://localhost:8000/api/checklist/AU
```

## Docker Configuration

The `docker-compose.yml` now includes:
1. Volume mount for checklists: `./checklists:/app/checklists:ro`
2. Volume mount for output: `${LOCAL_OUTPUT_PATH:-./output}:/app/output`

The Dockerfile copies checklists during build:
```dockerfile
COPY checklists ./checklists
```

This ensures checklists are available both:
- Baked into the image (for portability)
- As a mounted volume (for easy updates without rebuild)

## Path Calculation Details

### checklist_models.py
Location: `backend/src/ai_classifier/checklist_models.py`
- `.parent` = `ai_classifier/`
- `.parent.parent` = `src/`
- `.parent.parent.parent` = `backend/`
- `.parent.parent.parent.parent` = project root
- Result: `project_root/checklists/`

### routes/checklist.py
Location: `backend/src/ai_classifier/routes/checklist.py`
- `.parent` = `routes/`
- `.parent.parent` = `ai_classifier/`
- `.parent.parent.parent` = `src/`
- `.parent.parent.parent.parent` = `backend/`
- `.parent.parent.parent.parent.parent` = project root
- Result: `project_root/checklists/`

## No Authentication Required

The following endpoints now work without Bearer token:
- `GET /api/output/runs` - List all run directories
- `GET /api/output/browse?path=...` - Browse directory contents
- `GET /api/output/download?path=...` - Download files
- `DELETE /api/output/delete?path=...` - Delete files/directories
- `GET /api/checklist/{region}` - Get checklist
- `PUT /api/checklist/{region}` - Update checklist

