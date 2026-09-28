FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

# libmagic: server-side content-type detection for uploads
RUN apt-get update \
 && apt-get install -y --no-install-recommends libmagic1 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --uid 10001 --create-home --home-dir /home/qplm qplm

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .

ARG APP_VERSION=0.1.0
ARG GIT_COMMIT=unknown
ARG BUILD_TIME=unknown
ENV PLM_APP_VERSION=${APP_VERSION} PLM_GIT_COMMIT=${GIT_COMMIT} PLM_BUILD_TIME=${BUILD_TIME} \
    PLM_FILESTORE_PATH=/data/filestore

RUN mkdir -p /data/filestore && chown -R qplm:qplm /data
USER qplm
EXPOSE 8000
# Only the gateway can reach this container (internal network), so forwarded headers are trusted from it.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
