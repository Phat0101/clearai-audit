import os
import secrets
import string
import time
from pathlib import Path
from threading import Lock as ThreadLock
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from fastapi.responses import JSONResponse
from fastapi.openapi.docs import (
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
    get_redoc_html,
)
from fastapi.openapi.utils import get_openapi


# Load .env from project root explicitly
_ROOT_DOTENV = Path(__file__).resolve().parents[2] / '.env'
load_dotenv(dotenv_path=_ROOT_DOTENV, override=False)

# Get environment variables
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "*").split(",")

app = FastAPI(
    title="Tariff Classifier API",
    version="0.1.0",
    debug=DEBUG,
    docs_url=None,
    redoc_url=None,
    openapi_url="/api/openapi.json",
)


# -----------------------------
# Custom OpenAPI schema (inject Bearer auth)
# -----------------------------

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description="API for classifying items with Australian HS codes",
        routes=app.routes,
    )
    components = openapi_schema.setdefault("components", {})
    security_schemes = components.setdefault("securitySchemes", {})
    security_schemes["bearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "Token",
    }
    # Apply global security requirement so Swagger UI shows the Authorize button
    openapi_schema["security"] = [{"bearerAuth": []}]
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_HOSTS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Simple Bearer auth middleware
# -----------------------------

def _generate_dev_token(length: int = 30) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


# If AUTH_TOKEN is provided via env, use it; otherwise generate a random 30-char token for development
AUTH_TOKEN = os.getenv("AUTH_TOKEN") or _generate_dev_token(30)

if not os.getenv("AUTH_TOKEN"):
    # Dev helper: print the token so you can use it in clients. Do NOT rely on this in production.
    print(f"[AUTH] Generated development token (30 chars): {AUTH_TOKEN}")
else:
    print("[AUTH] Using AUTH_TOKEN from environment")


_EXEMPT_PATHS = {
    "/",  # serve frontend index
    "/health",  # health checks
    "/openapi.json",  # default schema path (kept for safety)
    "/api/openapi.json",  # custom schema path used by docs
    "/docs",  # swagger (when DEBUG true)
    "/docs/oauth2-redirect",
    "/redoc",  # redoc (when DEBUG true)
    "/api/upload-batch",  # batch upload endpoint (no auth needed for now)
    "/api/process-batch",  # batch process endpoint (no auth needed for now)
    "/api/group-local-input",  # local input grouping endpoint (no auth needed for now)
    "/api/process-local-input",  # local input processing endpoint (no auth needed for now)
}
_EXEMPT_PREFIXES = [
    "/static/",  # static assets
    "/api/checklist/",  # checklist management (no auth needed for editor)
    "/api/output/",  # output browser (no auth needed for browsing results)
    "/api/nz-audit/",  # NZ audit endpoints (no auth needed for now)
]


# -----------------------------
# Simple IP rate limiting (fixed window)
# -----------------------------

RATE_LIMIT_ENABLED = (os.getenv("RATE_LIMIT_ENABLED") or "true").lower() == "true"
RATE_LIMIT_MAX_REQUESTS = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "100"))  # per window
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
TRUST_PROXY = (os.getenv("TRUST_PROXY") or "false").lower() == "true"

_RL_EXEMPT_PATHS = {"/health"}
_RL_EXEMPT_PREFIXES = ["/static/"]

_rate_limit_counters: dict[str, tuple[int, int]] = {}
_rate_limit_lock = ThreadLock()


def _get_client_ip(request: Request) -> str:
    if TRUST_PROXY:
        fwd = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For")
        if fwd:
            return fwd.split(",")[0].strip()
    client = request.client
    return client.host if client else "unknown"


async def _rate_limit_check(request: Request):
    if not RATE_LIMIT_ENABLED:
        return None

    path = request.url.path
    if path in _RL_EXEMPT_PATHS or any(path.startswith(p) for p in _RL_EXEMPT_PREFIXES):
        return None

    ip = _get_client_ip(request)
    now = int(time.time())
    window_start = (now // RATE_LIMIT_WINDOW_SECONDS) * RATE_LIMIT_WINDOW_SECONDS

    with _rate_limit_lock:
        prev = _rate_limit_counters.get(ip)
        if not prev or prev[0] != window_start:
            count = 1
            _rate_limit_counters[ip] = (window_start, count)
        else:
            count = prev[1] + 1
            _rate_limit_counters[ip] = (window_start, count)

    over_limit = count > RATE_LIMIT_MAX_REQUESTS
    remaining = max(RATE_LIMIT_MAX_REQUESTS - count, 0)

    if over_limit:
        retry_after = window_start + RATE_LIMIT_WINDOW_SECONDS - now
        return JSONResponse(
            status_code=429,
            content={"detail": "Too Many Requests"},
            headers={
                "Retry-After": str(max(retry_after, 1)),
                "X-RateLimit-Limit": str(RATE_LIMIT_MAX_REQUESTS),
                "X-RateLimit-Remaining": "0",
            },
        )

    # Attach rate limit headers for visibility
    request.state.rate_limit_headers = {
        "X-RateLimit-Limit": str(RATE_LIMIT_MAX_REQUESTS),
        "X-RateLimit-Remaining": str(remaining),
    }
    return None


async def _security_dispatch(request: Request, call_next):
    # Allow CORS preflight without auth
    if request.method == "OPTIONS":
        return await call_next(request)

    # Rate limiting first
    rate_limit_response = await _rate_limit_check(request)
    if rate_limit_response is not None:
        return rate_limit_response

    path = request.url.path
    if path in _EXEMPT_PATHS or any(path.startswith(pfx) for pfx in _EXEMPT_PREFIXES):
        response = await call_next(request)
        # propagate rate-limit headers if present
        rl_headers = getattr(request.state, "rate_limit_headers", None)
        if rl_headers:
            for k, v in rl_headers.items():
                response.headers[k] = v
        return response

    auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        resp = JSONResponse(
            status_code=401,
            content={"detail": "Unauthorized: missing Bearer token"},
            headers={"WWW-Authenticate": "Bearer realm=api"},
        )
        # Add rate-limit headers on errors too
        rl_headers = getattr(request.state, "rate_limit_headers", None)
        if rl_headers:
            for k, v in rl_headers.items():
                resp.headers[k] = v
        return resp

    token = auth_header.split(" ", 1)[1].strip()
    if token != AUTH_TOKEN:
        resp = JSONResponse(
            status_code=401,
            content={"detail": "Unauthorized: invalid token"},
            headers={"WWW-Authenticate": "Bearer error=invalid_token"},
        )
        rl_headers = getattr(request.state, "rate_limit_headers", None)
        if rl_headers:
            for k, v in rl_headers.items():
                resp.headers[k] = v
        return resp

    response = await call_next(request)
    rl_headers = getattr(request.state, "rate_limit_headers", None)
    if rl_headers:
        for k, v in rl_headers.items():
            response.headers[k] = v
    return response


app.add_middleware(BaseHTTPMiddleware, dispatch=_security_dispatch)

# -----------------------------
# Docs routes (Swagger UI and ReDoc)
# -----------------------------

ENABLE_DOCS = (os.getenv("ENABLE_DOCS") or ("true" if DEBUG else "false")).lower() == "true"

if ENABLE_DOCS:
    @app.get("/docs", include_in_schema=False)
    async def custom_swagger_ui_html():
        return get_swagger_ui_html(
            openapi_url=app.openapi_url,
            title=f"{app.title} - Swagger UI",
            oauth2_redirect_url="/docs/oauth2-redirect",
        )

    @app.get("/docs/oauth2-redirect", include_in_schema=False)
    async def swagger_ui_redirect():
        return get_swagger_ui_oauth2_redirect_html()

    @app.get("/redoc", include_in_schema=False)
    async def redoc_html():
        return get_redoc_html(
            openapi_url=app.openapi_url,
            title=f"{app.title} - ReDoc",
        )

# Mount AU classifier routes first
from .au.classifier import router as au_router
from .nz.classifier import router as nz_router
app.include_router(au_router)
app.include_router(nz_router)

# Mount batch processing routes
from .routes.batch import router as batch_router
app.include_router(batch_router)

# Mount checklist management routes
from .routes.checklist import router as checklist_router
app.include_router(checklist_router)

# Mount output directory browsing routes
from .routes.output import router as output_router
app.include_router(output_router)

# Mount NZ audit routes
from .routes.nz_audit import router as nz_audit_router
app.include_router(nz_audit_router)

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "ai-classifier"}

# Mount static files for frontend
frontend_path = Path(__file__).resolve().parents[2] / "frontend"
if frontend_path.exists():
    print(f"Mounting frontend from: {frontend_path}")
    app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")

# Root route to serve the frontend
@app.get("/")
async def serve_frontend():
    frontend_file = frontend_path / "index.html"
    if frontend_file.exists():
        from fastapi.responses import FileResponse
        return FileResponse(str(frontend_file))
    else:
        return {"message": "AI Classifier API", "version": "0.1.0", "frontend": "not found"}