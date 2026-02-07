FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    DOCKER_CLI_HOME=/root/.docker

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install binaries directly - avoid using Python for system setup
RUN mkdir -p $DOCKER_CLI_HOME/cli-plugins && \
    curl -SL https://github.com/docker/buildx/releases/download/v0.11.2/buildx-v0.11.2.linux-amd64 -o $DOCKER_CLI_HOME/cli-plugins/docker-buildx && \
    curl -SL https://github.com/docker/compose/releases/download/v2.20.2/docker-compose-linux-x86_64 -o $DOCKER_CLI_HOME/cli-plugins/docker-compose && \
    chmod +x $DOCKER_CLI_HOME/cli-plugins/docker-buildx $DOCKER_CLI_HOME/cli-plugins/docker-compose

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

COPY . .

ENTRYPOINT ["uv", "run", "python", "-m", "builderd.builderd"]
