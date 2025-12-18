FROM python:3.10-slim

WORKDIR /app

# System dependencies required by scientific Python packages
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency list from repo root
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source plus shared helper module
COPY core/state_management/ .
COPY env_loader.py ./env_loader.py

# Prepare log directory inside the image
RUN mkdir -p logs

EXPOSE 55103

ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=app.py

# Start gunicorn and point it at state_management_main:app
CMD ["gunicorn", "--bind", "0.0.0.0:55103", "--workers", "4", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-", "state_management_main:app"]
