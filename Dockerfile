# ---------- Build backend ----------
FROM python:3.12-slim AS backend-builder

# Set working directory
WORKDIR /app

# Install build dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# ---------- Build frontend (static assets) ----------
FROM node:20-alpine AS frontend-builder

WORKDIR /frontend

# Copy static files (adjust if you have a build step in the future)
COPY index.html style.css ./

# ---------- Final production image ----------
FROM python:3.12-slim

# Set environment variables for production
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENV=production

WORKDIR /app

# Copy Python dependencies from the backend builder stage
COPY --from=backend-builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages

# Copy application code
COPY --from=backend-builder /app /app

# Copy static assets into a directory that can be served by FastAPI
COPY --from=frontend-builder /frontend /app/static

# Expose the port FastAPI will run on
EXPOSE 8000

# Command to run the FastAPI application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]