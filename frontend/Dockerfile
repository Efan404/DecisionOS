FROM node:20-alpine

WORKDIR /app

RUN corepack enable

COPY package.json pnpm-lock.yaml postcss.config.mjs next.config.mjs /app/
COPY frontend /app/frontend

ARG API_INTERNAL_URL=http://127.0.0.1:8000
ENV API_INTERNAL_URL=${API_INTERNAL_URL}

ARG NEXT_PUBLIC_API_SSE_URL=https://api-decision-os.efan404.com
ENV NEXT_PUBLIC_API_SSE_URL=${NEXT_PUBLIC_API_SSE_URL}

RUN HUSKY=0 pnpm install --frozen-lockfile
RUN pnpm build:web

EXPOSE 3000

CMD ["pnpm", "exec", "next", "start", "frontend", "--hostname", "0.0.0.0", "--port", "3000"]
