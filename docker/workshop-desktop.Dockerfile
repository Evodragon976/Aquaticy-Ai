# syntax=docker/dockerfile:1























FROM docker.io/library/ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8



RUN (grep -rqs universe /etc/apt/sources.list /etc/apt/sources.list.d/ \
        || echo "deb http://archive.ubuntu.com/ubuntu noble main universe" \
            >> /etc/apt/sources.list) \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        tini python3 ca-certificates iptables locales \
        xvfb x11-xserver-utils xdotool wmctrl openbox tint2 imagemagick dbus-x11 \
        fonts-dejavu-core fonts-liberation2 \
        falkon \
        libreoffice-writer libreoffice-calc libreoffice-impress libreoffice-l10n-de \
        mousepad pcmanfm xterm gimp \
    && rm -rf /var/lib/apt/lists/* \
    && locale-gen de_DE.UTF-8







RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgtk-3-0t64 libdbus-glib-1-2 libasound2t64 libx11-xcb1 libxtst6 \
        libnss3 libgbm1 libxss1 libsecret-1-0 libnotify4 libatspi2.0-0t64 libxkbfile1 \
        libdrm2 libxshmfence1 \
        libxi6 libxxf86vm1 libxfixes3 libxrender1 libgl1 libegl1 libgl1-mesa-dri \
        libxkbcommon0 libsm6 libice6 \
        dpkg xz-utils \
    && rm -rf /var/lib/apt/lists/*



RUN id -u 1000 >/dev/null 2>&1 || useradd --uid 1000 --create-home werkstatt



COPY docker/desktop/aquaticy-desktop /usr/local/bin/aquaticy-desktop
COPY docker/desktop/aquaticy-netz /usr/local/sbin/aquaticy-netz
COPY docker/desktop/aquaticy-addons /usr/local/bin/aquaticy-addons
RUN chmod 0755 /usr/local/bin/aquaticy-desktop /usr/local/bin/aquaticy-addons \
    && chmod 0700 /usr/local/sbin/aquaticy-netz

LABEL org.aquaticy.werkstatt="desktop"
USER 1000
WORKDIR /work
