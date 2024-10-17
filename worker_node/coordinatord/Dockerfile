# Use the official Python base image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# Install system dependencies
RUN apt-get update && apt-get install -y curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file into the container
COPY ../requirements.txt .

# Install dependencies using pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy the coordinatord and utils modules to /app directory
COPY coordinatord /app/coordinatord
COPY ../utils /app/utils

# Expose necessary ports
EXPOSE 6000 6001 54321 12345

# Set the entrypoint to start the coordinatord service
ENTRYPOINT ["python", "-m", "coordinatord.coordinatord"]
