# IncidentCommander OpenEnv — Dockerfile
# Self-contained build using python:3.12-slim.
# Targets Hugging Face Spaces (port 7860) and standard docker run.
#
# Build:   docker build -t incident-commander .
# Run:     docker run -p 7860:7860 \
#            -e HF_TOKEN=<your-token> \
#            -e MODEL_NAME=meta-llama/Llama-3.3-70B-Instruct \
#            -e API_BASE_URL=https://router.huggingface.co/v1 \
#            incident-commander

FROM python:3.12-slim

# System dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Environment
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1
ENV HF_HOME=/tmp/huggingface

# HF Spaces standard port
EXPOSE 7860

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:7860/health || exit 1

# Start server
CMD ["python", "-m", "uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "7860"]
