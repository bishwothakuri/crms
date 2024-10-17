# Use the official Python base image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file into the container
COPY ../requirements.txt .

# Install dependencies using pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy the monitord and utils modules to /app directory
COPY monitord /app/monitord
COPY ../utils /app/utils
# COPY monitoring_config /app/monitoring_config

# Set the entrypoint to start the coordinatord service
ENTRYPOINT ["python", "-m", "monitord.monitord"]
