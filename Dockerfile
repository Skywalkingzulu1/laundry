FROM python:3.12-slim\n\n# Set environment variables\nENV PYTHONDONTWRITEBYTECODE=1\nENV PYTHONUNBUFFERED=1\n\n# Install system dependencies\nRUN apt-get update && apt-get install -y --no-install-recommends \\
    build-essential \\
    gcc \\
    && rm -rf /var/lib/apt/lists/*\n\n# Create working directory\nWORKDIR /app\n\n# Install Python dependencies\nCOPY requirements.txt .\nRUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt\n\n# Copy application code\nCOPY . .\n\n# Expose the port FastAPI runs on\nEXPOSE 8000\n\n# Command to run the application\nCMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]