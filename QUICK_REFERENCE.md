# Quick Reference Guide

Fast reference for the ClearAI Audit system.

---

## 🚀 Quick Start

```bash
# 1. Setup
cp env.example .env
nano .env  # Add your GOOGLE_GENAI_API_KEY and LOCAL_OUTPUT_PATH

# 2. Run with Docker (Recommended)
docker-compose up

# Access:
# - Frontend: http://localhost:3000
# - Backend: http://localhost:8000/docs
```

---

## 📁 File Organization

After processing, files are organized like this:

```
/your/output/path/
├── 2025-10-13_run_001/                    # Date + Run number
│   ├── job_2219477116/                    # Job folder (by job ID)
│   │   ├── file1_entry_print.pdf          # Classified with label
│   │   ├── file2_air_waybill.pdf
│   │   └── file3_commercial_invoice.pdf
│   ├── job_2219477676/
│   │   └── ...
│   └── audit_results_2025-10-13_run_001.xlsx  # Excel output
└── 2025-10-13_run_002/                    # Next run same day
    └── ...
```

**Key Points**:
- Run folders auto-increment (run_001, run_002, ...)
- Files saved with document type labels: `_entry_print`, `_air_waybill`, `_commercial_invoice`, `_packing_list`
- One Excel file per run with all results

---

## 📊 Workflow

```
Upload PDFs → Auto-group by number → Classify & Save → Extract → Validate → Generate XLSX
```

**Example**:
- Upload: `2219477116_AWB.pdf`, `2219477116_INV.pdf`, `2219477116^^...ENT.pdf`
- Groups into: Job 2219477116 (3 files)
- Classifies each document type
- Saves with labels in job folder
- Extracts structured data
- Validates checklist (header + line items)
- Generates Excel with results

---

## 📋 Document Types

| Type | Label | Contains |
|------|-------|----------|
| Entry Print | `_entry_print` | Customs declaration, line items with HS codes |
| Air Waybill | `_air_waybill` | Shipping details, AWB number, weight |
| Commercial Invoice | `_commercial_invoice` | Supplier, buyer, line items, prices |
| Packing List | `_packing_list` | Packaging details, dimensions |

---

## ✅ Validation Checks

### Header Checks (Document-level)
- Consignee name match (Entry vs Invoice)
- AWB number consistency (across all documents)
- Invoice total vs declared value
- Country of origin match
- Supplier name match
- FTA eligibility
- Incoterms validation

### Line Item Checks (Per item)
- Description consistency
- Quantity match
- Unit price match
- Country of origin per item
- **Tariff code validation** (AU: 8+2 digits, NZ: 8+3 chars)
- FTA claims

---

## 🐳 Docker Commands

```bash
# Start services
docker-compose up

# Start in background
docker-compose up -d

# Stop services
docker-compose down

# View logs
docker-compose logs -f

# Rebuild after changes
docker-compose build

# Remove everything
docker-compose down -v
docker system prune -a
```

---

## 🔑 Environment Variables (Required)

```bash
# In .env file:
GOOGLE_GENAI_API_KEY=your-gemini-api-key
AUTH_TOKEN=your-random-token
LOCAL_OUTPUT_PATH=/path/to/output
```

Generate auth token:
```bash
openssl rand -hex 32
```

---

## 📂 Excel Output Structure

### Sheet 1: Job Summary
- Job ID, files processed, document types present, job folder path, timestamp

### Sheet 2: Header Checklist
- Check ID, criteria, status (PASS/FAIL/QUESTIONABLE), source value, target value, assessment

### Sheet 3: Line Item Checklist
- Line number, description comparison, quantity comparison, price comparison
- **Tariff validation**: declared code vs suggested code, status, AI reasoning

### Sheet 4-5: Extracted Data
- Entry Print data (optional)
- Commercial Invoice data (optional)

---

## 🎯 Test Files

Use sample files in `OneDrive_1_13-10-2025/`:
```
2219477116_AWB_...pdf
2219477116_INV_...pdf
2219477116^^...ENT...pdf
```

Upload all 3 → System groups them → Processes as one job

---

## 🔧 Troubleshooting

| Issue | Solution |
|-------|----------|
| Can't connect to backend | `docker-compose logs backend` |
| Files not saving | Check `LOCAL_OUTPUT_PATH` in .env |
| Port in use | Change ports in docker-compose.yml |
| API errors | Verify `GOOGLE_GENAI_API_KEY` |
| Out of disk space | `docker system prune -a` |

---

## 📖 Full Documentation

- **[SIMPLIFIED_SYSTEM_SPEC.md](SIMPLIFIED_SYSTEM_SPEC.md)** - Complete system specification
- **[DOCKER_SETUP.md](DOCKER_SETUP.md)** - Detailed Docker guide
- **[IMPLEMENTATION_ROADMAP.md](IMPLEMENTATION_ROADMAP.md)** - Development phases
- **[AUDIT_SYSTEM_LOGIC.md](AUDIT_SYSTEM_LOGIC.md)** - Deep dive into validation logic

---

## 🌏 Australia vs New Zealand

| | Australia | New Zealand |
|-|-----------|-------------|
| **HS Format** | 8 digits | 8 digits |
| **Stat Format** | 2 digits | 3 chars (2 digits + 1 letter) |
| **Example** | 61091000.00 | 61091000.00H |
| **Model** | Gemini 2.5 Pro | Gemini 2.5 Flash Lite |
| **Special** | TCO links, Schedule 4 | Simplified tariff |

---

## ⚡ Performance

- **Classification**: ~5 sec/document
- **Extraction**: ~10 sec/document
- **Validation**: ~30 sec/job
- **Total**: ~3-5 min/job

---

## 🔒 Security

- Use strong auth token
- Never commit `.env` to git
- Restrict output directory: `chmod 700 /path/to/output`
- Disable docs in production: `ENABLE_DOCS=false`

---

## 💡 Tips

1. **First run takes longer** - Docker needs to download images
2. **Check health**: http://localhost:8000/health
3. **View API docs**: http://localhost:8000/docs (when enabled)
4. **Monitor logs**: `docker-compose logs -f backend`
5. **Backup output regularly**: `tar -czf backup.tar.gz /path/to/output`

---

## Need Help?

1. Check `DOCKER_SETUP.md` troubleshooting section
2. View logs: `docker-compose logs -f`
3. Check API docs: http://localhost:8000/docs
4. Verify env vars: `docker-compose config`

