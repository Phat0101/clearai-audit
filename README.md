# ClearAI Audit

DHL Express customs document auditing system with AI-powered classification, extraction, and validation.

## 📚 Documentation

- **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** - ⚡ Fast reference for common tasks and commands
- **[SIMPLIFIED_SYSTEM_SPEC.md](SIMPLIFIED_SYSTEM_SPEC.md)** - ⭐ **Start here!** Simplified batch processing system specification
- **[DOCKER_SETUP.md](DOCKER_SETUP.md)** - 🐳 Complete Docker setup and deployment guide
- **[AUDIT_SYSTEM_LOGIC.md](AUDIT_SYSTEM_LOGIC.md)** - Detailed logic from audit-v2 (reference for understanding the process)
- **[NEW_ARCHITECTURE_README.md](NEW_ARCHITECTURE_README.md)** - Architecture comparison and migration guide
- **[IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md)** - Phase-by-phase development guide

## 🎯 System Overview

**Simplified Workflow**:
1. **Upload** multiple PDF files (Entry Print, Air Waybill, Commercial Invoice, Packing List)
2. **Auto-group** files by job number (e.g., all files starting with "2219477116")
3. **Process** each job: Classify → Extract → Validate (including tariff classification)
4. **Download** XLSX report with checklist results for brokers

**No database, no complex UI** - just upload, process, and download results.

## Prerequisites

- [Bun](https://bun.sh/) - JavaScript runtime and package manager
- [uv](https://docs.astral.sh/uv/) - Python package manager
- Python 3.11+
- Node.js (for Next.js)

## Project Structure

```
clearai-audit/
├── 📄 SIMPLIFIED_SYSTEM_SPEC.md    # New simplified system spec
├── 📄 AUDIT_SYSTEM_LOGIC.md        # Logic reference from audit-v2
├── 📄 NEW_ARCHITECTURE_README.md   # Architecture guide
│
├── backend/                        # FastAPI backend (Python)
│   ├── src/ai_classifier/
│   │   ├── main.py                # FastAPI app with auth & rate limiting
│   │   ├── document_classifier.py # PDF classification (Gemini 2.5 Flash)
│   │   ├── document_extractor.py  # Data extraction (Gemini 2.5 Flash)
│   │   ├── checklist_models.py    # Checklist configuration & Pydantic models
│   │   ├── checklist_validator.py # Checklist validation (Gemini 2.5 Flash)
│   │   ├── au/classifier.py       # AU tariff classification (Gemini 2.5 Pro)
│   │   ├── nz/classifier.py       # NZ tariff classification (Gemini 2.5 Flash)
│   │   └── au/tools.py            # Tariff lookup tools
│   ├── dev.sh                     # Backend dev script
│   └── start.sh                   # Backend start script
│
├── checklists/                    # Checklist configurations (JSON)
│   ├── au_checklist.json          # Australian customs checklist
│   ├── nz_checklist.json          # New Zealand customs checklist
│   └── README.md                  # Checklist documentation
│
├── frontend/audit/                 # Next.js frontend (TypeScript)
│   ├── src/app/
│   │   ├── page.tsx               # Home page
│   │   ├── classifier/            # CSV classifier UI (current)
│   │   └── api/                   # API proxy routes
│   └── package.json
│
├── audit-v2/                       # LEGACY monolithic app (reference only)
│   ├── src/app/                   # Next.js pages + API routes
│   ├── src/components/            # React components
│   ├── src/lib/                   # Business logic (checklist, extraction, etc.)
│   └── prisma/schema.prisma       # Database schema
│
├── OneDrive_1_09-10-2025/         # Sample test files
│   ├── 2219477116_*.pdf           # Job 1 (3 files)
│   ├── 2219477676_*.pdf           # Job 2 (3 files)
│   └── 2555462195_*.pdf           # Job 3 (3 files)
│
├── install.sh                      # Install all dependencies
├── dev.sh                          # Run both services (dev)
└── start.sh                        # Run both services (production)
```

## Quick Start

### Option 1: Docker (Recommended) 🐳

**Fastest way to get started - no manual dependency installation needed!**

```bash
# 1. Copy environment file
cp env.example .env

# 2. Edit .env and add your Gemini API key and output path
nano .env

# 3. Create output directory
mkdir -p ./output  # or your custom path

# 4. Build and run
docker-compose up

# Services available at:
# - Frontend: http://localhost:3000
# - Backend: http://localhost:8000
# - API Docs: http://localhost:8000/docs
```

**📖 See [DOCKER_SETUP.md](DOCKER_SETUP.md) for complete Docker guide**

---

### Option 2: Local Development

Install dependencies and run locally:

```bash
# Install all dependencies
./install.sh

# Run both services with hot reload
./dev.sh
```

Or install separately:

```bash
# Backend dependencies
cd backend
uv sync

# Frontend dependencies
cd frontend/audit
bun install
```

This starts:
- **Backend**: http://localhost:8000 (FastAPI with auto-reload)
- **Frontend**: http://localhost:3000 (Next.js with Turbopack)

Press `Ctrl+C` to stop both services.

### Run Services Individually

**Backend only:**
```bash
cd backend
./dev.sh
```

**Frontend only:**
```bash
cd frontend/audit
bun run dev
```

### Production Mode

```bash
./start.sh
```

This starts both services in production mode.
Press `Ctrl+C` to stop both services.

## Environment Variables

Create a `.env` file in the root directory:

```env
# Backend
DEBUG=true
ALLOWED_HOSTS=*
AUTH_TOKEN=your-secret-token-here
RATE_LIMIT_ENABLED=true
RATE_LIMIT_MAX_REQUESTS=100
RATE_LIMIT_WINDOW_SECONDS=60
ENABLE_DOCS=true

# API Keys
GOOGLE_GENAI_API_KEY=your-google-api-key
```

## API Documentation

When running in development mode with `ENABLE_DOCS=true`:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## API Endpoints

- `GET /health` - Health check
- `POST /classify/au` - Classify items with Australian HS codes
- `POST /classify/nz` - Classify items with New Zealand tariff codes

## Tech Stack

### Backend
- FastAPI - Web framework
- Granian - ASGI server with hot reload
- uv - Package management
- Pydantic AI - AI/ML integration
- Google Gemini - AI model

### Frontend
- Next.js 15 - React framework
- Bun - Package manager and runtime
- Tailwind CSS - Styling
- TypeScript - Type safety

## Scripts Reference

| Command | Description |
|---------|-------------|
| `./install.sh` | Install all dependencies |
| `./dev.sh` | Run both services in dev mode |
| `./start.sh` | Run both services in production |
| `cd backend && ./dev.sh` | Run backend only (dev) |
| `cd backend && ./start.sh` | Run backend only (production) |
| `cd frontend/audit && bun run dev` | Run frontend only (dev) |
| `cd frontend/audit && bun run start` | Run frontend only (production) |

## Current Status

### ✅ Implemented
- **FastAPI backend** with AU/NZ tariff classification
- **Bearer token authentication** & rate limiting
- **Next.js frontend** with CSV upload classifier
- **API documentation** (Swagger/ReDoc)
- **Concurrent processing** with retry logic
- **Grounded product search** for better accuracy
- **PDF classification** using Gemini 2.5 Flash (Entry Print, AWB, Invoice, Packing List, Other)
- **Data extraction** from Entry Print and Commercial Invoice using Gemini 2.5 Flash
- **File grouping & storage** by job number, date, and run number
- **JSON checklist configurations** for AU and NZ (header + valuation checks)
- **Checklist validation engine** using PydanticAI + Gemini 2.5 Flash

### 🚧 In Progress (See SIMPLIFIED_SYSTEM_SPEC.md)
- Integrate checklist validation into batch processing endpoint
- Line-item validation logic (Python-based, not AI)
- XLSX report generation with multiple sheets
- Frontend UI enhancements for validation results
- Batch processing UI

### 📋 What You Can Do Now
1. Upload CSV with columns: `id`, `description`, `supplier_name`
2. Select region (AU or NZ)
3. Get tariff classification results with reasoning
4. Export results to CSV

### 📋 What's Coming Next
1. Upload multiple PDFs instead of CSV
2. Auto-group PDFs by job number (e.g., "2219477116_*")
3. Process: Classify → Extract → Validate
4. Download XLSX with complete audit results

## Sample Files for Testing

Use the sample files in `OneDrive_1_09-10-2025/` directory:
- Each job has 3 files: Entry Print, Air Waybill, Commercial Invoice
- Perfect for testing the full audit workflow

## Development

The backend uses Granian with `--reload` flag for automatic reloading on file changes.
The frontend uses Next.js with Turbopack for fast hot module replacement.

## License

Private

