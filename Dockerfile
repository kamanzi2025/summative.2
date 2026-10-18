# Shared application image layers. The final target remains development so the existing
# Compose profile continues to use Django's development server.
FROM python:3.12-slim AS app-base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /app/data

EXPOSE 8000
# Explicit opt-in production web runtime. Build with --target production.
FROM app-base AS production
ENTRYPOINT ["sh", "/app/docker/production-entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "config.wsgi:application"]

# Keep this as the final/default target for local Compose development.
FROM app-base AS development
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
