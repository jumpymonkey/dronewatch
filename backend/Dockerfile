# Stage 1: Build Frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Build Backend
FROM node:20-alpine AS backend-builder
WORKDIR /app/backend
COPY backend/package*.json ./
RUN npm ci
COPY backend/ ./
RUN npm run build

# Stage 3: Production Runner
FROM node:20-alpine AS runner
WORKDIR /app

# Install FFmpeg for video frame processing
RUN apk add --no-co-cache ffmpeg

ENV NODE_ENV=production
ENV PORT=8080

COPY backend/package*.json ./
RUN npm ci --only=production

# Copy compiled backend JS and frontend dist
COPY --from=backend-builder /app/backend/dist ./dist
COPY --from=frontend-builder /app/frontend/dist ./public

EXPOSE 8080

CMD ["node", "dist/index.js"]
