FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FLASK_APP=wsgi.py

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

RUN useradd --system --no-create-home checkin \
    && mkdir /data && chown checkin /data \
    && chmod +x docker/entrypoint.sh
USER checkin

VOLUME /data

EXPOSE 8000

ENTRYPOINT ["docker/entrypoint.sh"]
# Socket.IO runs in threading mode, so keep a single worker process (see README).
CMD ["gunicorn", "-k", "gthread", "-w", "1", "--threads", "8", "-b", "0.0.0.0:8000", "--access-logfile", "-", "wsgi:app"]
