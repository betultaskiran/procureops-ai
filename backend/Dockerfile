# ─────────────────────────────────────────────────────────────────────────────
# backend/Dockerfile
#
# Development-optimised image. The docker-compose.yml mounts the ./backend
# directory as a volume so code changes are reflected without rebuilding.
# The --reload flag tells uvicorn to watch for file changes and restart.
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.12-slim

# Set the working directory inside the container.
# All subsequent commands run from here.
WORKDIR /app

# ── Install uv ────────────────────────────────────────────────────────────────
# uv is a fast Python package manager. We install it via pip just once.
# It replaces pip + virtualenv for our use case.
RUN pip install uv --no-cache-dir

# ── Install dependencies ──────────────────────────────────────────────────────
# Copy ONLY the dependency file first. Docker caches each layer.
# If pyproject.toml hasn't changed, Docker reuses the cached layer and
# skips re-installing packages — this makes rebuilds much faster.
COPY pyproject.toml .

# Install all dependencies into the system Python (no virtualenv inside Docker,
# the container itself is already isolated).
RUN uv pip install --system -r pyproject.toml --no-cache

# ── Copy source code ──────────────────────────────────────────────────────────
# In development, docker-compose mounts ./backend:/app so this COPY is
# overridden at runtime. It's here so the production image (built without
# volume mounts) still includes the source code.
COPY . .

# ── Start the server ──────────────────────────────────────────────────────────
# --host 0.0.0.0: listen on all interfaces (required in Docker)
# --port 8000: matches the port exposed in docker-compose.yml
# --reload: watch for file changes and restart (development only)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
