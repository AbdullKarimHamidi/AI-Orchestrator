# syntax=docker/dockerfile:1
ARG NODE_IMAGE=node:22-alpine
FROM ${NODE_IMAGE} AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM ${NODE_IMAGE} AS build
WORKDIR /app
# Next.js evaluates rewrites at build time, so the internal API address is a build argument.
ARG API_INTERNAL_URL=http://api:8000
ENV API_INTERNAL_URL=$API_INTERNAL_URL NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM ${NODE_IMAGE} AS run
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -S orch && adduser -S orch -G orch
COPY --from=build --chown=orch:orch /app/.next/standalone ./
COPY --from=build --chown=orch:orch /app/.next/static ./.next/static
COPY --from=build --chown=orch:orch /app/public ./public
USER orch
EXPOSE 3000
CMD ["node", "server.js"]
