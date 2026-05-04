# SPEC BRIDGE — Backend API (local development)
# Runs a lightweight FastAPI server that wraps the Lambda handlers
# so you can develop and test locally without deploying to AWS.

FROM python:3.12-slim

# WeasyPrint system dependencies + curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz0b \
    libffi8 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libglib2.0-0 \
    libxml2 \
    libxslt1.1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir fastapi uvicorn[standard] python-multipart

COPY src/ ./src/
COPY local_server.py .

EXPOSE 8000

CMD ["uvicorn", "local_server:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
