# Output Browser Feature

## Overview
The Output Browser allows users to browse, download, and manage historical audit results stored in the output directory.

## Features

### 1. **Browse Output Directories**
- View all run directories sorted by date (newest first)
- See run metadata: modification time and total size

### 2. **Lazy Loading**
- Directories are only loaded when you expand them
- Click on a folder to expand and load its contents
- Click again to collapse the directory

### 3. **Download Files**
- Hover over any file to see the download button
- Click to download individual files (PDFs, JSONs, etc.)
- Files are downloaded with their original names

### 4. **Delete Operations**
- Delete entire run directories
- Confirmation prompt before deletion
- Automatically refreshes the list after deletion

### 5. **File Information**
- File sizes displayed for all files
- Modification timestamps shown
- Visual indicators for files vs directories

## Backend API Endpoints

### `GET /api/output/runs`
Lists all run directories in the output folder.

**Response:**
```json
{
  "success": true,
  "runs": [
    {
      "name": "2025-10-23_run_001",
      "path": "2025-10-23_run_001",
      "modified": 1729670000,
      "size": 1234567
    }
  ]
}
```

### `GET /api/output/browse?path={path}`
Browse contents of a directory within the output folder.

**Parameters:**
- `path`: Relative path within output directory (empty for root)

**Response:**
```json
{
  "path": "2025-10-23_run_001",
  "items": [
    {
      "name": "job_123_validation_AU.json",
      "path": "2025-10-23_run_001/job_123_validation_AU.json",
      "size": 12345,
      "type": "file",
      "modified": 1729670000
    }
  ]
}
```

### `GET /api/output/download?path={path}`
Download a file from the output directory.

**Parameters:**
- `path`: Relative path to the file

**Returns:** File content with appropriate content-type

### `DELETE /api/output/delete?path={path}`
Delete a file or directory from the output folder.

**Parameters:**
- `path`: Relative path to the item

**Response:**
```json
{
  "success": true,
  "message": "Deleted: 2025-10-23_run_001"
}
```

## Frontend Page

**URL:** `/output`

**Access:** Click "Browse Output" button in the main page header

## Security Features

- **Path Validation**: All paths are validated to ensure they're within the output directory
- **No Directory Traversal**: Attempts to access paths outside the output directory are blocked
- **Confirmation Dialogs**: Delete operations require user confirmation

## Technical Details

### Backend
- Location: `backend/src/ai_classifier/routes/output.py`
- Uses FastAPI FileResponse for efficient file serving
- Implements lazy loading at the backend level

### Frontend
- Location: `frontend/audit/src/app/output/page.tsx`
- Built with React hooks (useState, useEffect, useCallback)
- Implements client-side state management for expanded directories
- Uses Lucide React icons for UI elements

## Docker Considerations

The output directory is mounted as a volume in docker-compose.yml:
```yaml
volumes:
  - ${LOCAL_OUTPUT_PATH:-./output}:/app/output
```

This ensures that output files persist outside the container and can be accessed by the Output Browser.

## Usage Example

1. Navigate to the home page
2. Click "Browse Output" in the header
3. Click on a run directory to expand it
4. Navigate through subdirectories by clicking folder names
5. Hover over files to see download/delete options
6. Click download icon to save files locally
7. Click "Delete Run" to remove entire run directories

## Future Enhancements

Potential improvements:
- Bulk download (zip multiple files)
- Search/filter functionality
- Preview for JSON files
- Sorting options (by name, size, date)
- Pagination for large directories

