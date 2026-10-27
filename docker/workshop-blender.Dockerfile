# syntax=docker/dockerfile:1






















FROM docker.io/library/python:3.12-slim





RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        blender \
        libgl1 \
        libxi6 \
        libxrender1 \
        libxxf86vm1 \
        libxfixes3 \
        libxkbcommon0 \
        libsm6 \
    && rm -rf /var/lib/apt/lists/*




RUN useradd --create-home --uid 1000 werkstatt
USER werkstatt
WORKDIR /work
