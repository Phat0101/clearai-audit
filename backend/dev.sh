#!/bin/bash
# Development mode with hot reload for FastAPI backend

PYTHONUNBUFFERED=1 uv run granian --interface asgi src.ai_classifier.main:app --host 0.0.0.0 --port 8000 --reload --log-level info --access-log
