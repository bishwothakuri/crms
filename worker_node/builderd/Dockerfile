# Use the official Python base image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y curl wget && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install python-on-whales
RUN pip install python-on-whales

# Download and install the Docker CLI (optional if not available)
RUN python-on-whales download-cli

# Install Docker buildx (optional)
RUN mkdir -p ~/.docker/cli-plugins/ && \
    wget https://github.com/docker/buildx/releases/download/v0.6.3/buildx-v0.6.3.linux-amd64 -O ~/.docker/cli-plugins/docker-buildx && \
    chmod a+x  ~/.docker/cli-plugins/docker-buildx

# Install Docker Compose (optional)
RUN mkdir -p ~/.docker/cli-plugins/ && \
    wget https://github.com/docker/compose/releases/download/v2.0.1/docker-compose-linux-x86_64 -O ~/.docker/cli-plugins/docker-compose && \
    chmod a+x ~/.docker/cli-plugins/docker-compose

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install dependencies using pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy the builderd and utils modules
COPY builderd /app/builderd
COPY utils /app/utils
COPY monitoring_config /app/monitoring_config

# Expose necessary ports
EXPOSE 1883 8080

# Set the entrypoint to start the builderd service
ENTRYPOINT ["python", "-m", "builderd.builderd"]
