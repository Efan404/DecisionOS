# =============================================================================
# Stage 1: Build Next.js standalone bundle
# =============================================================================
FROM node:20-alpine AS nextjs-builder

WORKDIR /build

RUN corepack enable

# Copy workspace files needed for the build (mirrors frontend/Dockerfile context)
COPY package.json pnpm-lock.yaml postcss.config.mjs next.config.mjs ./
COPY frontend ./frontend

ARG API_INTERNAL_URL=http://127.0.0.1:8000
ENV API_INTERNAL_URL=${API_INTERNAL_URL}

# Install deps and build — produces frontend/.next/standalone
RUN HUSKY=0 pnpm install --frozen-lockfile
RUN pnpm build:web

# =============================================================================
# Stage 2: Final single-container image
# =============================================================================
FROM python:3.12-slim

# Install Node.js (for Next.js server.js), supervisor, and curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs \
    supervisor \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python backend dependencies
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy FastAPI backend
COPY backend/app /home/user/app/backend/app

# Copy Next.js standalone output from build stage
# Structure: standalone/frontend/ contains server.js + .next/server/ (no static!)
#            Original .next/static/ contains CSS/JS chunks
# We need: server.js + .next/ (with server/ AND static/) + node_modules/

# Copy frontend/ (contains server.js and .next/server/)
COPY --from=nextjs-builder /build/frontend/.next/standalone/frontend/ /home/user/app/frontend/
# Copy node_modules from parent
COPY --from=nextjs-builder /build/frontend/.next/standalone/node_modules/ /home/user/app/frontend/node_modules/
# Copy static assets (CSS/JS) - NOT included in standalone, must copy from original .next
COPY --from=nextjs-builder /build/frontend/.next/static/ /home/user/app/frontend/.next/static/
# Copy public assets
COPY --from=nextjs-builder /build/frontend/public/ /home/user/app/frontend/public/

# Supervisor config
COPY supervisord.conf /etc/supervisord.conf

WORKDIR /home/user/app

# Persistent storage mount point
RUN mkdir -p /mnt/workspace

# Environment variable defaults
ENV DECISIONOS_DB_PATH=/mnt/workspace/decisionos.db
ENV API_INTERNAL_URL=http://127.0.0.1:8000
ENV PORT=7860
ENV HOSTNAME=0.0.0.0

EXPOSE 7860

ENTRYPOINT ["supervisord", "-c", "/etc/supervisord.conf"]
