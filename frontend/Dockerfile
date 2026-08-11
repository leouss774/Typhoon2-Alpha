FROM node:20-bookworm-slim AS bim-builder

WORKDIR /app/bim-viewer
COPY bim-viewer/package.json bim-viewer/package-lock.json ./
RUN npm ci
COPY bim-viewer/ ./
ENV BIM_VIEWER_BASE=/bim-viewer/
RUN npm run build

FROM node:20-bookworm-slim AS frontend-builder

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
COPY --from=bim-builder /app/bim-viewer/dist ./bim-viewer/dist
ARG VITE_API_BASE=/api
ENV VITE_API_BASE=${VITE_API_BASE}
RUN npm run build

FROM nginx:1.27-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=frontend-builder /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1/healthz || exit 1
