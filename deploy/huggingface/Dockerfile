# Verixa Control Plane API — Hugging Face Spaces Dockerfile (CP-17).
#
# Builds a self-contained image carrying the FastAPI Control Plane
# with the financial-services demo data pre-seeded. HF Spaces runs
# this with no env vars by default; the seeded /v1/control/workflows
# returns 1 workflow + 3 audit entries + 1 pre-signed dossier on
# the first request, so judges see something interesting immediately.
#
# Image size budget: this is a Phase-0 demo container, NOT a
# production runtime. We use python:3.12-slim + pip install of just
# the runtime dependencies (no dev tools, no testcontainers, no
# Poetry). Final image ~150 MB.
#
# Build locally:
#   docker build -f deploy/huggingface/Dockerfile -t verixa-cp .
#   docker run -p 7860:7860 verixa-cp
# Then visit http://localhost:7860/docs
#
# HF Spaces auto-detects this Dockerfile when placed at the Space's
# repo root. The companion README.md carries the Space metadata.

FROM python:3.12-slim AS base

# Avoid bytecode noise + ensure stdout/stderr stream live so HF
# Spaces' log panel updates in real time.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps. build-essential only present for the cryptography
# wheel build fallback; on python:3.12-slim with current pip the
# wheel is prebuilt so this is belt-and-braces.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install only the runtime dependencies -- NOT the dev group. Keeps
# the image lean and free of test/lint tooling. List mirrors
# pyproject.toml [project.dependencies] verbatim (Phase-0 hack:
# duplication; Phase-1 will use a generated requirements.txt).
RUN pip install --no-cache-dir \
        "fastapi>=0.115.0,<0.116.0" \
        "uvicorn[standard]>=0.32.0,<0.33.0" \
        "pydantic>=2.9.0,<3.0.0" \
        "pydantic-settings>=2.6.0,<3.0.0" \
        "cryptography>=43.0.3,<44.0.0" \
        "pynacl>=1.5.0,<2.0.0" \
        "redis>=5.2.0,<6.0.0" \
        "minio>=7.2.10,<8.0.0" \
        "httpx>=0.27.2,<0.28.0" \
        "pyyaml>=6.0.2,<7.0.0" \
        "structlog>=24.4.0,<25.0.0" \
        "openai>=1.54.0,<2.0.0"

# Copy the three Python packages that make up Verixa's runtime
# surface. We do NOT copy tests, docs, deploy configs, etc.
COPY apps/runtime/verixa_runtime /app/verixa_runtime
COPY apps/control-plane-api/verixa_control_plane /app/verixa_control_plane
COPY packages/verixa-python/verixa /app/verixa

# Drop privileges. HF Spaces enforces non-root execution; the
# user must exist with a writable HOME for any libs that touch
# the filesystem.
RUN useradd --create-home --shell /bin/bash verixa
USER verixa

# HF Spaces convention: app must bind to port 7860.
EXPOSE 7860

# Uvicorn loads the pre-seeded FastAPI app from
# verixa_control_plane.asgi:app. The asgi module's import-time
# seed runs once per container start, so /v1/control/workflows
# returns the demo workflow on the first request.
CMD ["uvicorn", "verixa_control_plane.asgi:app", \
     "--host", "0.0.0.0", \
     "--port", "7860", \
     "--workers", "1"]
