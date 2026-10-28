# syntax=docker/dockerfile:1











FROM docker.io/library/python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    AQUATICY_DATA_DIR=/data \
    PLAYWRIGHT_BROWSERS_PATH=/browsers \
    TERM=xterm-256color \
    HOME=/tmp



RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tini libgomp1 libcurl4 libmagic1 \
    && rm -rf /var/lib/apt/lists/*




RUN useradd --create-home --uid 1000 aquaticy \
    && mkdir -p /data /work /browsers \
    && chown -R aquaticy:aquaticy /data /work /browsers \
    && chmod 0777 /data /work

WORKDIR /app
COPY pyproject.toml README.md constraints.txt ./
COPY aquaticy ./aquaticy

COPY docker/workshop-desktop.Dockerfile ./docker/workshop-desktop.Dockerfile
COPY docker/desktop ./docker/desktop

RUN pip install --no-cache-dir -c constraints.txt .




RUN python -m aquaticy.llamacpp install --dir /opt/aquaticy/llama.cpp \
    || echo "llama.cpp: wird beim ersten Einschalten geladen"


RUN python -m aquaticy.messenger_install signal-cli --dir /opt/aquaticy/signal-cli \
    || echo "signal-cli: wird mit aquaticy install-messenger nachgeholt"


RUN python -m aquaticy.website install-cloudflared --dir /opt/aquaticy/cloudflared \
    || echo "cloudflared: wird beim ersten Start mit Domain geladen"



FROM base AS slim

USER aquaticy
WORKDIR /work
ENTRYPOINT ["/usr/bin/tini", "--", "aquaticy"]
CMD []



FROM base AS browser

RUN pip install --no-cache-dir -c constraints.txt playwright \
    && playwright install --with-deps chromium \
    && chmod -R a+rX /browsers \
    && rm -rf /var/lib/apt/lists/* /root/.cache






ENV AQUATICY_BROWSER_NO_SANDBOX=1 \
    AQUATICY_ENABLE_PLAYWRIGHT=true

USER aquaticy
WORKDIR /work
ENTRYPOINT ["/usr/bin/tini", "--", "aquaticy"]
CMD []












FROM browser AS web

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends podman uidmap fuse-overlayfs \
    && rm -rf /var/lib/apt/lists/*






RUN mkdir -p /etc/containers \
    && printf '%s\n' \
        '[storage]' \
        'driver = "vfs"' \
        'runroot = "/tmp/containers"' \
        'graphroot = "/home/aquaticy/.local/share/containers/storage"' \
        '[storage.options]' \
        'ignore_chown_errors = "true"' \
        > /etc/containers/storage.conf \
    && printf '%s\n' \
        '[engine]' \
        'cgroup_manager = "cgroupfs"' \
        'events_logger = "file"' \
        > /etc/containers/containers.conf \
    && printf '%s\n' 'unqualified-search-registries = ["docker.io"]' \
        > /etc/containers/registries.conf \
    && echo 'aquaticy:100000:65536' > /etc/subuid \
    && echo 'aquaticy:100000:65536' > /etc/subgid \
    && mkdir -p /home/aquaticy/.local/share/containers \
    && chown -R aquaticy:aquaticy /home/aquaticy

ENV HOME=/home/aquaticy \
    AQUATICY_VM_RUNTIME=podman \
    AQUATICY_SANDBOXED=1

USER aquaticy
WORKDIR /work
EXPOSE 8765


ENTRYPOINT ["/usr/bin/tini", "--", "aquaticy", "web", "--host", "0.0.0.0"]
CMD []
