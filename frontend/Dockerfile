# frontend/Dockerfile
# Multi-stage build producing a minimal runtime image via Next.js standalone output.

FROM node:20-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:20-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Build-time env: NEXT_PUBLIC_* values get baked into the client bundle here.
# Server-only vars (API_BASE_URL, ADMIN_API_KEY, AUTH_SECRET, etc.) are NOT
# needed at build time — they're read at runtime from .env.production.
RUN npm run build

FROM node:20-slim AS runner
WORKDIR /app
ENV NODE_ENV=production
RUN useradd --system --uid 1001 nextjs
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nextjs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nextjs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
ENV PORT=3000
CMD ["node", "server.js"]
