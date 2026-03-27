# Use an official lightweight Python image.
FROM python:3.12-slim

# Set environment variables.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory.
WORKDIR /app

# Install system dependencies (if any are needed in the future).
# For now, the base image provides everything required.

# Install Python dependencies.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code.
COPY . .

# Expose the port that FastAPI will run on.
EXPOSE 8000

# Command to run the FastAPI application using uvicorn.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]