# ── Stage 1: Node.js builder (npm, optional future build steps) ───────────────
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install --omit=dev 2>/dev/null || npm install
COPY public/ ./public/

# ── Stage 2: nginx serves the static SPA ──────────────────────────────────────
FROM nginx:1.25-alpine
COPY --from=builder /app/public /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
EXPOSE 80
