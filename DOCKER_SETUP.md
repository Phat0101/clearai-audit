# Docker Setup Guide

Complete guide for running the ClearAI Audit system with Docker.

---

## Prerequisites

- Docker Desktop installed ([Download](https://www.docker.com/products/docker-desktop))
- Docker Compose (included with Docker Desktop)
- Google Gemini API key ([Get one here](https://makersuite.google.com/app/apikey))

---

## Quick Start (5 minutes)

### 1. Set Up Environment Variables

```bash
# Copy the example environment file
cp env.example .env

# Edit the .env file with your settings
nano .env  # or use any text editor
```

**Required settings**:
```bash
# Your Google Gemini API key
GOOGLE_GENAI_API_KEY=your-actual-api-key-here

# Generate a random auth token
AUTH_TOKEN=$(openssl rand -hex 32)

# Where to save audit results on YOUR LOCAL MACHINE
LOCAL_OUTPUT_PATH=/Users/pat/Documents/audit_output
```

### 2. Create Output Directory

```bash
# Create the directory specified in LOCAL_OUTPUT_PATH
mkdir -p /Users/pat/Documents/audit_output

# Or use the default ./output directory
mkdir -p ./output
```

### 3. Build and Run

```bash
# Build Docker images (first time only, ~3-5 minutes)
docker-compose build

# Start services
docker-compose up
```

**That's it!** Services are now running:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

Press `Ctrl+C` to stop.

---

## Services

### Backend (Port 8000)
- FastAPI application
- AI classification (AU/NZ tariff codes)
- Document processing
- File storage management

**Health check**: http://localhost:8000/health

### Frontend (Port 3000)
- Next.js application
- File upload UI
- Results display
- XLSX download

**Home page**: http://localhost:3000

---

## File Storage with Docker

### How It Works

```
Your Local Machine                Docker Container
────────────────                 ─────────────────
/Users/pat/Documents/            /app/output
audit_output/                    (mapped)
├── 2025-10-13_run_001/          
│   ├── job_2219477116/          ← Files appear here
│   │   ├── ...._air_waybill.pdf     immediately
│   │   └── ...._invoice.pdf
│   └── audit_results....xlsx
```

**Key Points**:
- Files are saved to `/app/output` inside the container
- Docker **syncs** them to your `LOCAL_OUTPUT_PATH`
- Files **persist** after stopping the container
- You can open files directly on your local machine

### Verify Storage

```bash
# Run a test batch
# Upload some PDFs via http://localhost:3000

# Check your local output directory
ls -la /Users/pat/Documents/audit_output/

# You should see:
# 2025-10-13_run_001/
#   ├── job_XXXXXXXX/
#   │   └── classified files
#   └── audit_results_2025-10-13_run_001.xlsx
```

---

## Common Docker Commands

### Development Mode

```bash
# Start with logs visible (recommended for development)
docker-compose up

# Start in background (detached mode)
docker-compose up -d

# View logs
docker-compose logs -f

# View logs for specific service
docker-compose logs -f backend
docker-compose logs -f frontend

# Stop services
docker-compose down

# Stop and remove volumes
docker-compose down -v
```

### Rebuilding

```bash
# Rebuild after code changes
docker-compose build

# Rebuild specific service
docker-compose build backend
docker-compose build frontend

# Force rebuild without cache
docker-compose build --no-cache

# Rebuild and restart
docker-compose up --build
```

### Maintenance

```bash
# Remove stopped containers
docker-compose rm

# View running containers
docker-compose ps

# Execute command in running container
docker-compose exec backend bash
docker-compose exec frontend sh

# View container resource usage
docker stats
```

---

## Troubleshooting

### Issue: "Cannot connect to backend"

**Solution 1**: Check if backend is running
```bash
docker-compose ps
# Both services should show "Up"

# Check backend health
curl http://localhost:8000/health
```

**Solution 2**: Check backend logs
```bash
docker-compose logs backend
# Look for errors
```

### Issue: "Files not saving to local directory"

**Solution 1**: Verify LOCAL_OUTPUT_PATH in .env
```bash
cat .env | grep LOCAL_OUTPUT_PATH
# Should show your desired path
```

**Solution 2**: Check directory permissions
```bash
# Make sure the directory exists and is writable
ls -la /Users/pat/Documents/audit_output/
```

**Solution 3**: Check volume mapping
```bash
docker-compose config
# Look for volumes section under backend service
```

### Issue: "API key not working"

**Solution**: Verify environment variables
```bash
# Check if backend received the API key
docker-compose exec backend env | grep GEMINI
# Should show your API key

# If not shown, check .env file
cat .env | grep GEMINI_API_KEY
```

### Issue: "Port already in use"

**Solution**: Change ports in docker-compose.yml
```yaml
services:
  backend:
    ports:
      - "8001:8000"  # Use 8001 instead of 8000
  frontend:
    ports:
      - "3001:3000"  # Use 3001 instead of 3000
```

### Issue: "Out of disk space"

**Solution**: Clean up Docker
```bash
# Remove unused images
docker image prune

# Remove everything (careful!)
docker system prune -a

# Check disk usage
docker system df
```

---

## Production Deployment

### Optimizations

1. **Disable debug mode**:
```bash
# In .env
DEBUG=false
ENABLE_DOCS=false
```

2. **Set resource limits** (docker-compose.yml):
```yaml
services:
  backend:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '1.0'
          memory: 2G
```

3. **Use secrets** for sensitive data:
```yaml
services:
  backend:
    secrets:
      - gemini_api_key
      - auth_token

secrets:
  gemini_api_key:
    file: ./secrets/gemini_api_key.txt
  auth_token:
    file: ./secrets/auth_token.txt
```

### Backup Strategy

```bash
# Backup your output directory regularly
tar -czf audit_backup_$(date +%Y%m%d).tar.gz /Users/pat/Documents/audit_output/

# Or use rsync for incremental backups
rsync -av /Users/pat/Documents/audit_output/ /backup/location/
```

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GOOGLE_GENAI_API_KEY` | ✅ | - | Gemini API key |
| `AUTH_TOKEN` | ✅ | - | Backend auth token |
| `LOCAL_OUTPUT_PATH` | ✅ | `./output` | Local storage path |
| `DEBUG` | ❌ | `true` | Debug mode |
| `ALLOWED_HOSTS` | ❌ | `*` | CORS origins |
| `ENABLE_DOCS` | ❌ | `true` | API documentation |
| `RATE_LIMIT_ENABLED` | ❌ | `true` | Enable rate limiting |
| `RATE_LIMIT_MAX_REQUESTS` | ❌ | `100` | Requests per window |
| `CLASSIFY_MAX_CONCURRENCY` | ❌ | `100` | Concurrent classifications |

See `env.example` for all available variables.

---

## Security Notes

### API Token

- Generate a strong token: `openssl rand -hex 32`
- Never commit `.env` files to git
- Rotate tokens regularly in production

### Network Security

```yaml
# Add network isolation in production
services:
  backend:
    networks:
      - internal
  frontend:
    networks:
      - internal
      - external

networks:
  internal:
    internal: true  # No external access
  external:
```

### File Permissions

```bash
# Restrict output directory permissions
chmod 700 /Users/pat/Documents/audit_output/
```

---

## Performance Tuning

### Increase Gemini Concurrency

For faster processing of large batches:
```bash
# In .env
CLASSIFY_MAX_CONCURRENCY=200
```

### Adjust Rate Limits

For high-volume usage:
```bash
# In .env
RATE_LIMIT_MAX_REQUESTS=500
RATE_LIMIT_WINDOW_SECONDS=60
```

### Monitor Resource Usage

```bash
# Watch container stats
docker stats clearai-audit-backend clearai-audit-frontend

# Check logs for performance issues
docker-compose logs --tail=100 backend | grep "took"
```

---

## Next Steps

1. ✅ Start the services: `docker-compose up`
2. ✅ Open frontend: http://localhost:3000
3. ✅ Upload test PDFs from `OneDrive_1_13-10-2025/`
4. ✅ Check output directory for results
5. ✅ Review XLSX file

For detailed system specifications, see:
- `SIMPLIFIED_SYSTEM_SPEC.md` - Complete workflow
- `IMPLEMENTATION_ROADMAP.md` - Development guide
- `README.md` - Project overview

---

## Support

**Common Issues**: See Troubleshooting section above

**API Documentation**: http://localhost:8000/docs (when ENABLE_DOCS=true)

**Logs**: `docker-compose logs -f`

