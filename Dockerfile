# Multi-arch base image (works on amd64 and arm64)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install minimal OS deps; add build tools if you later add native deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only project metadata first to maximize Docker layer cache
COPY pyproject.toml README.md ./

# Copy source and install the package (installs dependencies declared in pyproject)
COPY realm_bot ./realm_bot

# If you have tests or other optional folders, they are not copied

# Upgrade pip tooling and install the project
RUN python -m pip install --upgrade pip setuptools wheel \ 
 && pip install .

# Create a data directory for persistent state (mounted via compose)
RUN mkdir -p /app/data

# Default command runs the Discord bot
CMD ["python", "-m", "realm_bot.main"]
