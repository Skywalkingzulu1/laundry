# ---- Build Stage ----
FROM python:3.12-slim AS builder

# Set working directory
WORKDIR /app

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

# Install pip and upgrade
RUN pip install --upgrade pip setuptools wheel

# Copy only requirements first for caching
COPY requirements.txt ./
RUN pip install --user -r requirements.txt

# Copy application source code
COPY . ./

# ---- Runtime Stage ----
FROM python:3.12-slim AS runtime

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/root/.local/bin:$PATH

# Create a non-root user
RUN useradd -m appuser
WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local

# Copy application code
COPY --from=builder /app /app

# Change ownership to non-root user
RUN chown -R appuser:appuser /app
USER appuser

# Expose the port FastAPI runs on
EXPOSE 8000

# Default command to start the server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]