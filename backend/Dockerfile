FROM python:3.14-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod \
    PRIVATE_FILE_ROOT=/var/lib/jimeet/private
WORKDIR /app
COPY requirements/ requirements/
RUN pip install --disable-pip-version-check --no-cache-dir -r requirements/production.txt \
    && groupadd --gid 10001 jimeet \
    && useradd --uid 10001 --gid jimeet --no-create-home jimeet \
    && install -d -o jimeet -g jimeet -m 0700 /var/lib/jimeet/private /run/jimeet
COPY manage.py .
COPY config/ config/
COPY apps/ apps/
COPY deploy/gunicorn.conf.py deploy/healthcheck.py deploy/
USER 10001:10001
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD ["python", "deploy/healthcheck.py"]
CMD ["gunicorn", "--config", "deploy/gunicorn.conf.py", "config.wsgi:application"]
