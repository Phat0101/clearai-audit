# New Architecture - DHL Express Audit System

## Overview

This document explains the **new separated architecture** for the DHL Express Audit System. The system is being refactored from a monolithic Next.js application (audit-v2) into a **frontend/backend separation**.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                       audit-v2 (Current)                      │
│                                                               │
│  ┌────────────────┐  ┌──────────────┐  ┌──────────────────┐ │
│  │   Next.js      │  │  Python      │  │    PostgreSQL    │ │
│  │   (Frontend    │──│  Classifiers │  │    (Supabase)    │ │
│  │   + Backend)   │  │  (External)  │  │                  │ │
│  └────────────────┘  └──────────────┘  └──────────────────┘ │
└──────────────────────────────────────────────────────────────┘

                            ↓ MIGRATION ↓

┌──────────────────────────────────────────────────────────────┐
│                      New Architecture                         │
│                                                               │
│  ┌──────────────┐     ┌────────────────┐    ┌─────────────┐ │
│  │  frontend/   │────→│   backend/     │───→│ PostgreSQL  │ │
│  │  audit/      │     │   FastAPI      │    │             │ │
│  │  (Next.js)   │     │   (Python)     │    │             │ │
│  └──────────────┘     └────────────────┘    └─────────────┘ │
│                                                               │
│     - UI only           - All AI/ML logic    - Same schema   │
│     - API proxies       - Classification     - Migrated data │
│     - State mgmt        - Extraction                          │
│                         - Validation                          │
└──────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
clearai-audit/
├── audit-v2/                    # LEGACY monolithic app (reference)
│   ├── src/
│   │   ├── app/                 # Next.js pages + API routes
│   │   ├── components/          # React components
│   │   └── lib/                 # Business logic
│   ├── prisma/
│   │   └── schema.prisma        # Database schema
│   └── samplecode/              # AU/NZ classifier prototypes
│
├── frontend/audit/              # NEW frontend (Next.js)
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx         # Home page
│   │   │   ├── classifier/      # Tariff classifier UI
│   │   │   └── api/             # API proxy routes
│   │   └── ...
│   └── package.json
│
├── backend/                     # NEW backend (FastAPI)
│   ├── src/
│   │   └── ai_classifier/
│   │       ├── main.py          # FastAPI app entry point
│   │       ├── au/
│   │       │   ├── classifier.py  # AU tariff classification
│   │       │   └── tools.py       # AU tariff tools
│   │       └── nz/
│   │           ├── classifier.py  # NZ tariff classification
│   │           └── tools.py       # NZ tariff tools
│   ├── pyproject.toml
│   └── uv.lock
│
└── AUDIT_SYSTEM_LOGIC.md        # THIS FILE - explains the logic
```

---

## Component Breakdown

### Frontend (`/frontend/audit`)

**Purpose**: User interface only, no business logic

**Technology**:
- Next.js 15 (App Router)
- TypeScript
- Tailwind CSS
- Bun package manager

**Key Features**:
1. **Home Page** (`/`)
   - Landing page with branding

2. **Classifier Page** (`/classifier`)
   - CSV upload interface
   - API token management
   - Region selection (AU/NZ)
   - Real-time progress tracking
   - Results table with export

3. **API Proxy Routes**
   - `/api/classify/au` - forwards to FastAPI backend
   - `/api/classify/nz` - forwards to FastAPI backend
   - Adds headers and error handling
   - No business logic here!

**What It Does**:
- Accepts CSV files with columns: `id`, `description`, `supplier_name` (optional)
- Sends data to backend via API
- Displays classification results
- Exports results as CSV

**What It Does NOT Do**:
- Any AI/ML processing
- Data extraction from PDFs
- Checklist validation
- Database operations

---

### Backend (`/backend`)

**Purpose**: All AI/ML processing and business logic

**Technology**:
- FastAPI (Python)
- PydanticAI + Google Gemini
- Granian ASGI server
- uv for dependency management

**Key Features**:
1. **Authentication**
   - Bearer token authentication
   - Token from `AUTH_TOKEN` env var
   - Auto-generates dev token if not set

2. **Rate Limiting**
   - Fixed window rate limiting per IP
   - Configurable limits (default: 100 req/min)
   - X-RateLimit headers

3. **Classification Endpoints**
   - `POST /classify/au` - Australia tariff classification
   - `POST /classify/nz` - New Zealand tariff classification

4. **Documentation**
   - Swagger UI at `/docs` (when enabled)
   - ReDoc at `/redoc`
   - OpenAPI schema at `/api/openapi.json`

**Classification Process** (Same as audit-v2):

**Australia (`/classify/au`)**:
```python
1. Receive items: [{ id, description, supplier_name }]
2. For each item concurrently:
   a. Grounded search: Get product info from web
   b. Build prompt with grounded info + description
   c. Call Gemini 2.5 Pro with tools:
      - tariff_chapter_lookup(hs_code)
      - tariff_search(hs_code)
      - tariff_concession_lookup(bylaw_number)
   d. AI returns structured output:
      - best_suggested_hs_code (8 digits)
      - best_suggested_stat_code (2 digits)
      - best_suggested_tco_link (URL or null)
      - suggested_codes (2 alternatives)
      - reasoning
3. Return all results with token usage
```

**New Zealand (`/classify/nz`)**:
```python
1. Receive items: [{ id, description, supplier_name }]
2. For each item concurrently:
   a. Grounded search: Get product info from web
   b. Build prompt with grounded info + description
   c. Call Gemini 2.5 Flash Lite with tools:
      - nz_tariff_chapter_lookup(hs_code)
      - nz_tariff_search(hs_code)
   d. AI returns structured output:
      - best_suggested_hs_code (8 digits)
      - best_suggested_stat_key (3 chars: 2 digits + 1 letter)
      - suggested_codes (2 alternatives)
      - reasoning
3. Return all results with token usage
```

**Error Handling**:
- Retry logic with exponential backoff (4 attempts)
- Fallback to "00000000" codes on failure
- Detailed error messages in reasoning field

---

## Current Scope vs Future Scope

### ✅ Current Implementation (Phase 1)

**What's Working Now**:
- Frontend UI for CSV upload and classification
- Backend FastAPI with AU/NZ tariff classification
- Bearer token authentication
- Rate limiting
- Grounded product search
- Concurrent processing
- Swagger documentation

**Use Case**:
- Manual tariff classification from CSV files
- Testing classification accuracy
- Prototyping the separation

---

### 🚧 Future Implementation (Phase 2+)

**What Needs to be Migrated from audit-v2**:

1. **Document Processing Pipeline**
   - PDF upload and storage
   - OneDrive integration
   - Document classification (Entry Print, AWB, Invoice, etc.)
   - Data extraction from PDFs
   - File management

2. **Database Integration**
   - PostgreSQL connection
   - Prisma ORM or SQLAlchemy
   - audit_jobs, audit_job_files tables
   - Store classification/extraction results

3. **Checklist Validation System**
   - Header-level checks
   - Line-item validation
   - Dynamic checklist configurations
   - Streaming validation results

4. **Organization & Broker Management**
   - Multi-tenancy support
   - Organization-specific checklists
   - Broker authentication
   - Role-based access control

5. **Audit Job Workflow**
   - Job creation from OneDrive folders
   - Progress tracking (registered → classified → extracted → validated)
   - Status management (draft → in_progress → completed)
   - Results aggregation

6. **Frontend Features**
   - Full audit job UI
   - Document viewer with PDF preview
   - Checklist results display
   - Admin panel for configurations
   - Broker portal

---

## Migration Strategy

### Phase 1: Classification Only ✅ (DONE)
- [x] FastAPI backend with AU/NZ classifiers
- [x] Next.js frontend with CSV upload
- [x] API proxy routes
- [x] Authentication & rate limiting

### Phase 2: PDF Processing
- [ ] Add document upload to backend
- [ ] Integrate Google Gemini for PDF classification
- [ ] Add extraction endpoints for each document type
- [ ] Store files in cloud storage (Azure Blob or S3)

### Phase 3: Database Integration
- [ ] Set up PostgreSQL connection in FastAPI
- [ ] Migrate Prisma schema to SQLAlchemy models
- [ ] Create database service layer
- [ ] Add audit job CRUD operations

### Phase 4: Checklist System
- [ ] Port checklist validation logic to Python
- [ ] Implement dynamic checklist configurations
- [ ] Add streaming validation endpoint
- [ ] Store validation results

### Phase 5: Full Frontend
- [ ] Migrate all audit-v2 UI components
- [ ] Add document viewer
- [ ] Build checklist results display
- [ ] Create admin panel

### Phase 6: Production Readiness
- [ ] Add comprehensive error handling
- [ ] Implement logging and monitoring
- [ ] Write tests (unit + integration)
- [ ] Set up CI/CD
- [ ] Deploy to Azure/AWS

---

## API Comparison

### audit-v2 (Monolithic)
```
/api/classify          (POST) - Classify document type
/api/extract           (POST) - Extract data from PDF
/api/checklist/[jobId] (POST) - Validate checklist
/api/audit-jobs        (GET/POST) - Manage audit jobs
```

### New Backend (Separated)
```
Current:
  /classify/au         (POST) - Classify items (AU)
  /classify/nz         (POST) - Classify items (NZ)
  /health              (GET)  - Health check
  /docs                (GET)  - Swagger UI
  
Future:
  /documents/classify  (POST) - Classify PDF document type
  /documents/extract   (POST) - Extract data from PDF
  /jobs                (GET/POST/PUT/DELETE) - Audit jobs
  /jobs/{id}/validate  (POST) - Run checklist validation
  /checklists/configs  (GET/POST/PUT/DELETE) - Manage checklists
  /organizations       (GET/POST/PUT/DELETE) - Multi-tenancy
  /brokers            (GET/POST/PUT/DELETE) - Broker management
```

---

## Environment Variables

### Frontend (`frontend/audit/.env.local`)
```bash
NEXT_PUBLIC_API_URL=http://localhost:8000  # Backend URL (client-side)
API_URL=http://localhost:8000              # Backend URL (server-side)
```

### Backend (`backend/.env`)
```bash
# API Settings
DEBUG=true
ALLOWED_HOSTS=http://localhost:3000,http://localhost:5173
AUTH_TOKEN=your-secret-token-here
ENABLE_DOCS=true

# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_MAX_REQUESTS=100
RATE_LIMIT_WINDOW_SECONDS=60
TRUST_PROXY=false

# AI Settings
GEMINI_API_KEY=your-gemini-api-key
GOOGLE_API_KEY=your-google-api-key
CLASSIFY_MAX_CONCURRENCY=100
CLASSIFY_MAX_RETRIES=4
CLASSIFY_RETRY_BACKOFF=0.5

# Future: Database
DATABASE_URL=postgresql://user:pass@localhost:5432/clearai_audit

# Future: Storage
AZURE_STORAGE_CONNECTION_STRING=...
AZURE_STORAGE_CONTAINER_NAME=audit-documents

# Future: OneDrive
MICROSOFT_CLIENT_ID=...
MICROSOFT_CLIENT_SECRET=...
```

---

## Running the System

### Development

**Terminal 1 - Backend**:
```bash
cd backend
uv run dev
# Server starts on http://localhost:8000
# Docs at http://localhost:8000/docs
```

**Terminal 2 - Frontend**:
```bash
cd frontend/audit
bun dev
# App starts on http://localhost:3000
```

### Production

**Backend**:
```bash
cd backend
uv run start
# Uses Granian ASGI server
```

**Frontend**:
```bash
cd frontend/audit
bun run build
bun start
```

---

## Key Differences from audit-v2

| Aspect | audit-v2 (Old) | New Architecture |
|--------|---------------|------------------|
| **Architecture** | Monolithic Next.js | Separated Frontend + Backend |
| **Classification** | External Python scripts | Integrated in FastAPI |
| **API Layer** | Next.js API routes | FastAPI with OpenAPI |
| **Frontend** | Next.js with server components | Next.js client-only |
| **Authentication** | NextAuth.js | Bearer token (backend) |
| **Database** | Prisma (TypeScript) | Future: SQLAlchemy (Python) |
| **Deployment** | Single app deploy | Independent deploys |
| **Testing** | Limited | Future: Pytest + Jest |
| **Documentation** | README files | Swagger/ReDoc |

---

## Benefits of New Architecture

1. **Separation of Concerns**
   - Frontend only handles UI
   - Backend only handles business logic
   - Clear API contracts

2. **Independent Scaling**
   - Scale frontend and backend independently
   - Backend can handle more CPU-intensive AI tasks
   - Frontend can handle more user requests

3. **Technology Flexibility**
   - Use Python for AI/ML (better ecosystem)
   - Use TypeScript for UI (better DX)
   - Can swap either component independently

4. **Better Development Experience**
   - Backend team works in Python
   - Frontend team works in TypeScript
   - No context switching

5. **Easier Testing**
   - Unit test backend with Pytest
   - Unit test frontend with Jest
   - Integration tests via API

6. **API Reusability**
   - Same backend can serve multiple frontends
   - Can build mobile app, CLI, etc.
   - API-first design

---

## Next Steps

For the current implementation:
1. Test the classifier with real CSV data
2. Validate AU/NZ classification accuracy
3. Optimize token usage and performance
4. Add more error handling

For future migration:
1. Review the AUDIT_SYSTEM_LOGIC.md file
2. Start with Phase 2: PDF Processing
3. Gradually migrate features from audit-v2
4. Keep audit-v2 running until full migration

---

## Related Documentation

- `AUDIT_SYSTEM_LOGIC.md` - Detailed explanation of audit-v2 logic
- `audit-v2/README.md` - Original system documentation
- `audit-v2/DYNAMIC_CHECKLIST_README.md` - Checklist system details
- `backend/README.md` - Backend setup instructions
- `frontend/audit/README.md` - Frontend setup instructions

---

## Questions?

This is a work in progress. The current implementation provides a solid foundation for tariff classification, and the architecture is designed to support the full audit system as we migrate from audit-v2.

The key principle: **Keep it simple, keep it separated, keep it maintainable.**

