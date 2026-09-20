FROM node:22.19.0-bookworm-slim

ENV NODE_ENV=production \
    WRANGLER_WRITE_LOGS=false \
    WRANGLER_LOG_PATH=/tmp/jarvis-wrangler.log \
    MINIFLARE_REGISTRY_PATH=/tmp/jarvis-miniflare

WORKDIR /app
RUN chown node:node /app
USER node

COPY --chown=node:node apps/jarvis/package.json apps/jarvis/package-lock.json ./
RUN npm ci --include=dev --no-audit --no-fund

COPY --chown=node:node apps/jarvis ./
RUN npm run build && npm prune --omit=dev

EXPOSE 3300

CMD ["npx", "vinext", "start", "--hostname", "0.0.0.0", "--port", "3300"]
