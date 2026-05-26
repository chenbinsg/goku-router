# syntax=docker/dockerfile:1.6

# ── Stage 1: build the Vite bundle ─────────────────────────────────────────────
FROM node:20-alpine AS build
WORKDIR /build

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .

# At build time, Vite inlines this URL into the bundle. The browser uses it
# directly, so set it to the public URL your backend container is reachable at.
# Default works for local docker-compose where backend exposes 8159.
ARG VITE_BACKEND_URL=http://localhost:8159
ENV VITE_BACKEND_URL=$VITE_BACKEND_URL

RUN npm run build

# ── Stage 2: nginx serves the static bundle with SPA fallback ──────────────────
FROM nginx:alpine

COPY --from=build /build/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://127.0.0.1:80/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
