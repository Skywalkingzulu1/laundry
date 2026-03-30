# Use an official lightweight Python image.
FROM python:3.11-slim

# Set environment variables.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory.
WORKDIR /app

# Install system dependencies (if any) and then Python dependencies.
# For this simple FastAPI app, only Python packages are required.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code.
COPY . .

# Expose the port that uvicorn will run on.
EXPOSE 8000

# Command to run the FastAPI application.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]