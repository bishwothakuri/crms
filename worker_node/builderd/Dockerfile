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
# Install Docker CLI, Buildx, Compose
# ----------------------------
# Use python-on-whales to download Docker CLI
RUN uv run python -m python_on_whales.cli download-cli

# Buildx plugin
RUN mkdir -p $HOME/.docker/cli-plugins/ && \
    wget -q https://github.com/docker/buildx/releases/download/v0.10.5/buildx-v0.10.5.linux-amd64 \
    -O $HOME/.docker/cli-plugins/docker-buildx && \
    chmod a+x $HOME/.docker/cli-plugins/docker-buildx

# Compose plugin
RUN mkdir -p $HOME/.docker/cli-plugins/ && \
    wget -q https://github.com/docker/compose/releases/download/v2.18.1/docker-compose-linux-x86_64 \
    -O $HOME/.docker/cli-plugins/docker-compose && \
    chmod a+x $HOME/.docker/cli-plugins/docker-compose

# ----------------------------
# Copy Application Code
# ----------------------------
COPY builderd /app/builderd
COPY utils /app/utils
COPY monitoring_config /app/monitoring_config

# ----------------------------
# Expose Ports
# ----------------------------
EXPOSE 1883 8080

# ----------------------------
# Entrypoint
# ----------------------------
ENTRYPOINT ["uv", "run", "python", "-m", "builderd.builderd"]
