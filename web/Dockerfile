FROM node:26-alpine AS dependencies

WORKDIR /app
RUN npm install --global pnpm@10.30.3
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

FROM node:26-alpine AS builder

WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm install --global pnpm@10.30.3
COPY --from=dependencies /app/node_modules ./node_modules
COPY . .
RUN pnpm build

FROM node:26-alpine AS runner

WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

USER node
CMD ["node", "server.js"]
