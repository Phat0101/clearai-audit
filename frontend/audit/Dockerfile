FROM node:22-slim AS base

ENV NEXT_TELEMETRY_DISABLED=1
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"

# Enable corepack to use pnpm
RUN corepack enable

FROM base AS builder
WORKDIR /app

# Install build dependencies for native modules
RUN apt-get update && apt-get install -y \
    python3 \
    make \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy package files and install dependencies
COPY package.json pnpm-lock.yaml ./

# Install dependencies including optional dependencies (needed for lightningcss)
RUN pnpm install --frozen-lockfile

# Explicitly install the linux x64 gnu version of lightningcss if needed
RUN pnpm add --no-save lightningcss-linux-x64-gnu@1.30.1 || true

# Copy application code
COPY . .

# Accept build arguments from Railway
ARG NEXT_PUBLIC_API_URL
ARG API_URL
ARG NEXT_PUBLIC_AUTH_TOKEN

# Set environment variables for Next.js build (these get baked into the client bundle)
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV API_URL=$API_URL
ENV NEXT_PUBLIC_AUTH_TOKEN=$NEXT_PUBLIC_AUTH_TOKEN

# Build the application
RUN pnpm run build

FROM node:22-slim AS runner
WORKDIR /app

ENV NODE_ENV=production

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

# Copy public assets
COPY --from=builder /app/public ./public

# Copy the standalone build output
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./

# Copy static files
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

# Ensure proper permissions
RUN chown -R nextjs:nodejs /app/.next

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]