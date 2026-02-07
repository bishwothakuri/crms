# Base image
FROM python:3.13-slim

# ----------------------------
# Environment Variables
# ----------------------------
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    UV_HOME=/app/.venv

# ----------------------------
# System Dependencies
# ----------------------------
RUN apt-get update && \
    apt-get install -y curl wget unzip git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# ----------------------------
# Set Working Directory
# ----------------------------
WORKDIR /app

# ----------------------------
# Copy Dependency Files First
# ----------------------------
COPY pyproject.toml uv.lock ./

# ----------------------------
# Install uv and Dependencies
# ----------------------------
RUN python -m pip install --upgrade pip && \
    pip install uv && \
    uv sync --no-dev

# ----------------------------
# Copy Application Code
# ----------------------------
COPY coordinatord /app/coordinatord
COPY utils /app/utils

# ----------------------------
# Expose Ports
# ----------------------------
EXPOSE 6000 6001 54321 12345

# ----------------------------
# Entrypoint
# ----------------------------
ENTRYPOINT ["uv", "run", "python", "-m", "coordinatord.coordinatord"]
