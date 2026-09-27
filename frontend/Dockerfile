FROM node:24-alpine AS deps
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json ./
RUN npm ci

# Development: `next dev` with the source bind-mounted by docker-compose.yml.
FROM deps AS dev
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--hostname", "0.0.0.0"]

# Production build. Rewrites (the /api proxy) are fixed at build time, so the backend
# address is a build argument.
FROM deps AS build
ARG BACKEND_URL=http://backend:8000
ENV BACKEND_URL=${BACKEND_URL}
COPY . .
RUN npm run build

# Production: used by docker-compose.prod.yml and the Windows launcher.
FROM build AS prod
ENV NODE_ENV=production
EXPOSE 3000
CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0"]
