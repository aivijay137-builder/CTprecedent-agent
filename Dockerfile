# Railway api service. The front end is on Vercel, so only the Python side is built here.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend backend
COPY sync sync
COPY src src
# seed/precedent.seed (11 MB copy of precedent.duckdb, not in git) is copied to the volume once, on first start, if it is not already there
COPY seed /seed
# DATA_DIR is the Railway volume (serving.duckdb, app.db, precedent.duckdb live there)
ENV DATA_DIR=/data PYTHONPATH=/app/src:/app PYTHONUNBUFFERED=1
CMD ["sh", "-c", "mkdir -p /data; [ -f /data/precedent.duckdb ] || cp /seed/precedent.seed /data/precedent.duckdb 2>/dev/null; uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8765}"]
