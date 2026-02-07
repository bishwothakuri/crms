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
COPY monitord /app/monitord
COPY utils /app/utils
COPY monitoring_config /app/monitoring_config

# ----------------------------
# Expose Ports (if needed)
# ----------------------------
# EXPOSE 1883 8080   # Uncomment if monitord serves ports

# ----------------------------
# Entrypoint
# ----------------------------
ENTRYPOINT ["uv", "run", "python", "-m", "monitord.monitord"]
