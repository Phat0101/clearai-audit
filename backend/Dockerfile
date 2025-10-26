FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install --no-cache-dir uv

# Copy project files (context is backend directory in Railway)
COPY pyproject.toml uv.lock ./
COPY src ./src

# Copy checklists directory
COPY checklists ./checklists

# Install dependencies using uv
RUN uv sync --frozen

# Create output directory for file storage
RUN mkdir -p /app/output

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=300s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application using granian ASGI server with access logs
CMD ["uv", "run", "granian", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--interface", "asgi", \
     "--access-log", \
     "--log-level", "info", \
     "src.ai_classifier.main:app"]
