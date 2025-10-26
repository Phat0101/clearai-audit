# Checklist Editor - User Guide

## ✅ Overview

The Checklist Editor allows you to view and edit the AU and NZ checklist configurations directly through the web interface. Changes are saved back to the JSON files immediately, making it easy to maintain and update validation rules without touching the code.

## 🎯 Features

### Frontend Features
- **Region Switcher**: Toggle between AU and NZ checklists
- **Form-Based Editor**: User-friendly interface with expandable cards for each check
- **Structured Fields**: Edit all check properties through labeled input fields
- **Real-time Updates**: Changes are tracked automatically
- **Change Tracking**: Shows when you have unsaved changes
- **Auto-reload**: Automatically loads checklist when switching regions
- **Bulk Actions**:
  - Expand/Collapse All: Show or hide all check details
  - Add Check: Create new validation rules
  - Delete Check: Remove unwanted checks
  - Reset Changes: Discard unsaved edits
  - Save: Persist changes to the JSON file

### Backend Features
- **GET `/api/checklist/{region}`**: Retrieve checklist for AU or NZ
- **PUT `/api/checklist/{region}`**: Update checklist with validation
- **Validation**: Ensures JSON structure is correct before saving
- **File Persistence**: Changes are saved directly to `au_checklist.json` and `nz_checklist.json`

## 📁 File Structure

```
clearai-audit/
├── checklists/
│   ├── au_checklist.json          ← Editable via UI
│   ├── nz_checklist.json          ← Editable via UI
│   └── README.md
│
├── backend/
│   └── src/ai_classifier/
│       ├── routes/
│       │   └── checklist.py       ← New API routes
│       └── main.py                 ← Registered checklist router
│
└── frontend/audit/src/app/
    ├── page.tsx                    ← Added navigation button
    └── checklist/
        └── page.tsx                ← New checklist editor page
```

## 🚀 Usage

### Accessing the Editor

1. **From Main Page**:
   - Click the "📋 Manage Checklists" button in the header
   - Or navigate to `/checklist` directly

2. **Editor Interface**:
   ```
   ┌─────────────────────────────────────────────────────────────────────┐
   │  Checklist Manager                                                  │
   │  [AU ▼] [Reset] [Save Changes] [← Back]                            │
   │  ● Unsaved changes                                                  │
   ├─────────────────────────────────────────────────────────────────────┤
   │  Header-Level Checks (13)      [Expand All] [Collapse All] [+ Add] │
   │  ┌─────────────────────────────────────────────────────────────┐   │
   │  │ Check ID    │ # │ Auditing Criteria         │ Actions      │   │
   │  ├─────────────────────────────────────────────────────────────┤   │
   │  │ au_h_001    │ 1 │ [Owner match_________]    │ [Expand][Del]│   │
   │  │                                                              │   │
   │  │ Details (when expanded):                                     │   │
   │  │   Description:      [Verify the correct importer...]        │   │
   │  │   Checking Logic:   [First check the incoterms...]          │   │
   │  │   Pass Conditions:  [Owner on EPR matches...]               │   │
   │  │   Compare Fields:                                            │   │
   │  │     Source: [entry_print ▼] [ownerName, iTerms]             │   │
   │  │     Target: [commercial_invoice ▼] [buyer_...]              │   │
   │  ├─────────────────────────────────────────────────────────────┤   │
   │  │ au_h_002    │ 2 │ [Supplier match______]    │ [Expand][Del]│   │
   │  └─────────────────────────────────────────────────────────────┘   │
   │                                                                      │
   │  Valuation Checks (7)          [Expand All] [Collapse All] [+ Add] │
   │  └─ (similar table structure)                                       │
   └─────────────────────────────────────────────────────────────────────┘
   ```

### Editing a Checklist

1. **Select Region**:
   - Choose AU or NZ from the dropdown
   - Checklist loads automatically

2. **Edit Checks**:
   - Click the expand arrow (▶/▼) to show/hide check details
   - Or use "Expand All" / "Collapse All" for bulk operations
   - Edit any field directly in the input boxes:
     - **Auditing Criteria**: The name/title of the check
     - **Description**: Detailed explanation
     - **Checking Logic**: How to perform the check
     - **Pass Conditions**: When it should pass
     - **Compare Fields**: Source/target documents and fields

3. **Add New Check**:
   - Click "+ Add Check" button in the category header
   - A new check with auto-generated ID is created
   - Fill in the details and save

4. **Delete Check**:
   - Click the "×" button on any check card
   - Confirm the deletion dialog
   - The check is removed immediately

5. **Save Changes**:
   - Click "Save Changes" in the header
   - Backend validates the structure
   - Success/error badge appears

6. **Reset if Needed**:
   - Click "Reset" to discard all unsaved edits
   - Reloads the checklist from the file

## 📝 Checklist JSON Structure

### Required Fields

```json
{
  "version": "1.0.0",              // Checklist version
  "region": "AU",                  // Must match "AU" or "NZ"
  "description": "...",            // Description of the checklist
  "last_updated": "2025-10-14",    // Last update date
  "categories": {
    "header": {                    // Header-level checks
      "name": "...",
      "description": "...",
      "checks": [...]              // Array of check objects
    },
    "valuation": {                 // Valuation checks
      "name": "...",
      "description": "...",
      "checks": [...]              // Array of check objects
    }
  }
}
```

### Check Item Structure

```json
{
  "id": "au_h_001",                           // Unique check ID
  "auditing_criteria": "Owner match",         // What is being checked
  "description": "Verify the correct...",     // Detailed description
  "checking_logic": "First check the...",     // How to perform the check
  "pass_conditions": "Owner on EPR...",       // Conditions for passing
  "compare_fields": {
    "source_doc": "entry_print",              // Source document type
    "source_field": ["ownerName", "iTerms"],  // Field(s) to extract
    "target_doc": "commercial_invoice",       // Target document type
    "target_field": ["buyer_company_name"]    // Field(s) to compare
  }
}
```

## ⚙️ API Endpoints

### GET /api/checklist/{region}

Retrieve the checklist JSON for a specific region.

**Request**:
```bash
GET /api/checklist/AU
```

**Response**:
```json
{
  "success": true,
  "region": "AU",
  "content": {
    "version": "1.0.0",
    "region": "AU",
    ...
  },
  "file_path": "/path/to/au_checklist.json"
}
```

### PUT /api/checklist/{region}

Update the checklist JSON for a specific region.

**Request**:
```bash
PUT /api/checklist/AU
Content-Type: application/json

{
  "content": {
    "version": "1.0.0",
    "region": "AU",
    ...
  }
}
```

**Response**:
```json
{
  "success": true,
  "message": "Checklist for AU updated successfully",
  "region": "AU",
  "file_path": "/path/to/au_checklist.json"
}
```

**Error Response** (400):
```json
{
  "detail": "Invalid checklist structure: missing required fields"
}
```

## 🔒 Security

- ✅ **No Authentication Required**: Checklist endpoints are exempt from auth
- ✅ **Validation**: Backend validates JSON structure before saving
- ✅ **Region Matching**: Ensures region in JSON matches URL region
- ✅ **File Safety**: Only allows editing specific checklist files

## ⚠️ Important Notes

1. **Direct File Editing**:
   - Changes are saved directly to the JSON files
   - No version history or undo beyond the "Reset" button
   - Consider backing up files before major edits

2. **Validation Checks**:
   - Must have valid JSON syntax
   - Must include required fields (version, region, categories)
   - Region in JSON must match the region being edited

3. **Impact on Validation**:
   - Changes take effect immediately on next validation run
   - No need to restart the backend
   - Checklists are loaded dynamically from files

4. **Multiple Editors**:
   - No lock mechanism - last save wins
   - Coordinate with team when editing
   - Refresh page to see latest version

## 🎨 UI Features

### Visual Organization

- **Category Cards**: Separate cards for Header and Valuation checks
- **Table Layout**: Clean table with columns for Check ID, #, Auditing Criteria, and Actions
- **Expandable Rows**: Click "Expand" to reveal detailed form fields below the row
- **Badges**: Show check counts, IDs, and status indicators
- **Sticky Header**: Fixed top bar with controls always visible while scrolling

### Status Indicators

- **Change Indicator**: "● Unsaved changes" badge in header when edits are made
- **Success Badge**: Green badge shows save success
- **Error Badge**: Red badge shows validation errors
- **Check Numbers**: Shows position in list (e.g., "Check #1")

### Interactive Elements

- **Expand/Collapse**: "Expand" / "Collapse" buttons in each row to show/hide check details
- **Delete Buttons**: "Delete" button on each row with confirmation dialog
- **Add Buttons**: "+ Add Check" creates new validation rules
- **Bulk Actions**: "Expand All" / "Collapse All" buttons for entire categories
- **Inline Editing**: Auditing Criteria editable directly in the table row
- **Hover Effects**: Rows highlight on hover for better visual feedback

### Button States

- **Save Changes**: Enabled only when there are unsaved changes
- **Reset**: Enabled only when there are unsaved changes
- **Add Check**: Always enabled
- **Delete (×)**: Always enabled with confirmation dialog
- **All buttons**: Disabled during loading or saving operations

## 🚦 Workflow Examples

### Adding a New Check

1. Navigate to Checklist Manager
2. Select the desired region (AU or NZ)
3. Click "+ Add Check" in the appropriate category (Header or Valuation)
4. The new check appears with auto-generated ID (e.g., `au_h_014`)
5. Click the expand arrow to show the form
6. Fill in the fields:
   - **Auditing Criteria**: "New check name"
   - **Description**: "What this check does"
   - **Checking Logic**: "How to perform it"
   - **Pass Conditions**: "When it passes"
   - **Compare Fields**:
     - Source Doc: Select from dropdown
     - Source Field: Enter field name(s)
     - Target Doc: Select from dropdown
     - Target Field: Enter field name(s)
7. Click "Save Changes" in the header
8. Verify the success badge appears

### Modifying Existing Checks

1. Find the check in the list (shows ID and criteria)
2. Click the expand arrow (▶) to show details
3. Edit any field directly in the input boxes
4. Changes are tracked automatically (● Unsaved changes)
5. Click "Save Changes" when done
6. Test with actual documents to verify

### Deleting a Check

1. Find the check you want to remove
2. Click the "×" button on the right side
3. Confirm the deletion dialog
4. The check is removed immediately
5. Click "Save Changes" to persist the deletion

### Bulk Operations

1. **Expand All Checks**: Click "Expand All" to show all check details at once
2. **Collapse All Checks**: Click "Collapse All" to hide all details
3. **Switch Regions**: Change dropdown to load different checklist
4. **Reset All Changes**: Click "Reset" to discard all unsaved edits

## 📚 Related Documentation

- `checklists/README.md` - Detailed checklist JSON format
- `CHECKLIST_SYSTEM_SUMMARY.md` - How the checklist system works
- `CHECKLIST_VALIDATOR_V2.md` - Validation engine architecture

## 🐛 Troubleshooting

### Error: "Invalid checklist structure: missing required fields"
- **Cause**: Required fields were accidentally deleted or corrupted
- **Fix**: Click "Reset" to reload from file, or manually restore missing fields

### Error: "Region mismatch"
- **Cause**: Internal region field doesn't match the selected region
- **Fix**: This shouldn't happen with the form editor; if it does, click "Reset"

### Changes not appearing in validation
- **Cause**: Cached checklist in validator
- **Fix**: Restart the backend to reload checklists

### Check ID conflicts
- **Cause**: Manually edited IDs causing duplicates
- **Fix**: Use unique IDs following the pattern: `{region}_{category}_{number}` (e.g., `au_h_014`)

### Fields not saving
- **Cause**: Network issue or backend not running
- **Fix**: Check that backend is running on port 8000, check browser console for errors

## ✅ Summary

The Checklist Editor provides a user-friendly, form-based interface for managing validation rules:
- **Easy Access**: One click from the main audit page
- **Intuitive Forms**: Edit checks using structured input fields, no JSON required
- **Visual Organization**: Expandable cards with clear labels for all fields
- **CRUD Operations**: Add, edit, delete checks with simple buttons
- **Safe Editing**: Validation prevents saving invalid structures
- **Immediate Effect**: Changes apply to next validation run
- **No Code Required**: Edit rules without touching Python or TS files

This makes it easy for non-technical users to maintain and update validation rules without ever seeing JSON!

