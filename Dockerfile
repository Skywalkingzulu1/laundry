# Use an official lightweight Python image.
FROM python:3.11-slim

# Set environment variables.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user and set work directory.
RUN useradd -m appuser
WORKDIR /app
USER appuser

# Install Python dependencies.
COPY --chown=appuser:appuser requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code.
COPY --chown=appuser:appuser . .

# Expose the port FastAPI will run on.
EXPOSE 8000

# Command to run the FastAPI application.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]