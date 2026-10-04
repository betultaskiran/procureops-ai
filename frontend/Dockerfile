# ─────────────────────────────────────────────────────────────────────────────
# frontend/Dockerfile
#
# Development-optimised image for Next.js.
# The docker-compose.yml mounts ./frontend/src:/app/src so UI changes
# appear immediately without rebuilding. Next.js hot reload handles the rest.
# ─────────────────────────────────────────────────────────────────────────────

FROM node:20-alpine

WORKDIR /app

# Copy package files first — same Docker layer caching benefit as the backend.
# npm install only re-runs when package.json or package-lock.json changes.
COPY package*.json ./

RUN npm install

# Copy the rest of the source.
# In development, docker-compose overrides this with volume mounts.
COPY . .

# Expose the Next.js development server port.
EXPOSE 3000

# Start the development server with hot reload.
CMD ["npm", "run", "dev"]
