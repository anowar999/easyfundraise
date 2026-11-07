FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --system --uid 10001 app && chown -R app /app
USER app
EXPOSE 8000
# EF_API_WORKERS: API processes (each has its own DB pool, see EF_DB_POOL_SIZE). 2 suits a small box; use about
# one per CPU core in production.
# Migrations + reference data are idempotent, so running them on boot is safe.
CMD ["sh", "-c", "alembic upgrade head && python -m app.cli seed && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --workers ${EF_API_WORKERS:-2}"]
