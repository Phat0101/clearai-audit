#!/bin/bash
# Development mode - runs both backend and frontend with hot reload

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo -e "${GREEN}Starting ClearAI Audit in Development Mode${NC}"
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}\n"

# Function to cleanup background processes on exit
cleanup() {
    echo -e "\n${YELLOW}Stopping all services...${NC}"
    kill $(jobs -p) 2>/dev/null
    wait
    echo -e "${GREEN}All services stopped${NC}"
    exit 0
}

# Set up trap to catch Ctrl+C and call cleanup
trap cleanup SIGINT SIGTERM

# Start backend in background with proper path handling and unbuffered output
echo -e "${BLUE}[BACKEND]${NC} Starting FastAPI on http://localhost:8000"
(cd "$SCRIPT_DIR/backend" && PYTHONUNBUFFERED=1 exec uv run granian --interface asgi src.ai_classifier.main:app --host 0.0.0.0 --port 8000 --reload --log-level info --access-log 2>&1 | while IFS= read -r line; do echo "[BACKEND] $line"; done) &
BACKEND_PID=$!

# Give backend a moment to start
sleep 2

# Start frontend in background with proper path handling
echo -e "${BLUE}[FRONTEND]${NC} Starting Next.js on http://localhost:3000"
(cd "$SCRIPT_DIR/frontend/audit" && exec bun run dev 2>&1 | while IFS= read -r line; do echo "[FRONTEND] $line"; done) &
FRONTEND_PID=$!

# Wait for both processes
wait

