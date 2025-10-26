#!/bin/bash
# Production mode for FastAPI backend

PYTHONUNBUFFERED=1 uv run granian --interface asgi src.ai_classifier.main:app --host 0.0.0.0 --port 8000 --log-level info --access-log
