FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first so this layer is cached between deploys.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Don't run as root.
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

# Render sets $PORT (default 10000). DATABASE_URL and JWT_SECRET come from Render environment variables.
EXPOSE 10000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000} --proxy-headers --forwarded-allow-ips='*'"]
