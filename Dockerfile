# Railway api service. The front end is on Vercel, so only the Python side is built here.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend backend
COPY sync sync
COPY src src
# DATA_DIR is the Railway volume (serving.duckdb, app.db, precedent.duckdb live there)
ENV DATA_DIR=/data PYTHONPATH=/app/src:/app PYTHONUNBUFFERED=1
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8765}"]
