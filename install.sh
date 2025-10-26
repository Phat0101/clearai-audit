#!/bin/bash
# Install dependencies for both backend and frontend

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Installing ClearAI Audit Dependencies${NC}\n"

# Install backend dependencies
echo -e "${BLUE}[1/2]${NC} Installing backend dependencies with uv..."
cd backend && uv sync
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Backend dependencies installed${NC}\n"
else
    echo -e "${YELLOW}⚠ Backend installation had issues${NC}\n"
fi

# Install frontend dependencies
echo -e "${BLUE}[2/2]${NC} Installing frontend dependencies with bun..."
cd ../frontend/audit && bun install
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Frontend dependencies installed${NC}\n"
else
    echo -e "${YELLOW}⚠ Frontend installation had issues${NC}\n"
fi

cd ../..

echo -e "${GREEN}Installation complete!${NC}"
echo -e "Run ${BLUE}./dev.sh${NC} to start development mode"

