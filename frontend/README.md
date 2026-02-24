# Frontend

Next.js 14 frontend for DecisionOS.

## Prerequisites

- Node.js 20+
- [pnpm](https://pnpm.io/)

## Setup

```bash
# From the project root
pnpm install
```

## Start (Development)

Run from the **project root** (not the frontend/ subdirectory):

```bash
pnpm dev:web
```

Or directly:

```bash
next dev frontend --hostname 127.0.0.1 --port 3001
```

Frontend runs at `http://127.0.0.1:3001`.

## API Proxy

All `/api-proxy/*` requests are proxied to `http://127.0.0.1:8000` via Next.js rewrites. The backend must be running before making API calls.

## Build

```bash
pnpm build:web
```
