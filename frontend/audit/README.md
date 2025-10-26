# Clear.ai Audit - Frontend

This is the Next.js frontend for the Clear.ai Audit application, providing a tariff classification interface.

## Getting Started

### Prerequisites

- Node.js 18+ or Bun
- The FastAPI backend running (see `backend/` directory)

### Environment Setup

1. Copy the example environment file:
   ```bash
   cp .env.example .env.local
   ```

2. Update `.env.local` with your backend URL:
   ```
   NEXT_PUBLIC_API_URL=http://localhost:8000
   API_URL=http://localhost:8000
   ```

### Installation

Install dependencies using Bun (recommended) or npm:

```bash
bun install
# or
npm install
```

### Development

Run the development server:

```bash
bun dev
# or
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

### Routes

- `/` - Home page with Clear.ai Audit title
- `/classifier` - Tariff classification tool

## Features

### Tariff Classifier (`/classifier`)

The classifier page provides:

- **CSV Upload**: Drag-and-drop or browse to upload CSV files
  - Required columns: `id`, `description`
  - Optional column: `supplier_name` (or `supplier`, or `supplier name`)
  
- **API Token Management**: 
  - Token is stored in localStorage for convenience
  - Show/hide toggle for security
  
- **Region Selection**: 
  - Australia (AU) - shows HS codes, stat codes, and TCO links
  - New Zealand (NZ) - shows HS codes and stat keys
  
- **Real-time Progress**: 
  - Visual progress bar during classification
  - Progress step indicators showing current processing stage
  
- **Results Display**:
  - Summary statistics (total items, average time, TCO availability)
  - Detailed table with all classification results
  - Loading spinners while classification is in progress
  
- **CSV Export**: Download classification results as CSV

## API Routes

The frontend includes proxy routes to the FastAPI backend:

- `POST /api/classify/au` - Classifies items for Australia
- `POST /api/classify/nz` - Classifies items for New Zealand

These routes forward requests to the backend API while adding proper headers and error handling.

## Technology Stack

- **Framework**: Next.js 15 with App Router
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **Package Manager**: Bun (or npm)
- **Backend Integration**: Next.js API routes as proxy

## Development Notes

- The app uses `'use client'` directive for client-side interactivity
- All state management is handled with React hooks (useState, useEffect, useRef)
- The classifier supports real-time progress tracking with simulated progress updates
- TypeScript interfaces ensure type safety for API responses

## Building for Production

```bash
bun run build
# or
npm run build
```

Then start the production server:

```bash
bun start
# or
npm start
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `NEXT_PUBLIC_API_URL` | Backend API URL (client-side) | `http://localhost:8000` |
| `API_URL` | Backend API URL (server-side) | `http://localhost:8000` |

Note: `NEXT_PUBLIC_*` variables are exposed to the browser.
