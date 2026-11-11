# Painel local do Core (ADR-017). Distinto do sandbox FRG-6 (ADR-013, --network none).
# Base: mesmo digest multi-arch de python:3.12-slim do ADR-013.
# gh 2.81.0 e Cursor Agent 2026.11.10-731fb78: tarball + SHA-256.

FROM python:3.12-slim@sha256:4840d514c583a4d3d8cad3940e68dee6f0f6f3635c12fcd0a3d74c21a5b93a54

ARG TARGETARCH
ARG GH_VERSION=2.81.0
ARG CURSOR_AGENT_VERSION=2026.11.10-731fb78

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl git tar util-linux \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    case "${TARGETARCH}" in \
      amd64) GH_ARCH=amd64; GH_SHA=d507c82e3ae47af875b93472f39e01cbf9f85808ec0a69751e0932a43514d7ff; \
             CURSOR_ARCH=x64; CURSOR_SHA=f39e124227aa179ae16ac0785e293cbe29218b2d1c167ba7adf68bfc8c3812a9 ;; \
      arm64) GH_ARCH=arm64; GH_SHA=766adda9877afaf55f67626ff5d956bcea84f1e5371df5765ba30b1e786a86fd; \
             CURSOR_ARCH=arm64; CURSOR_SHA=5f211675d0e64e6a2f23e7c9bcb518a15855b924837145b5d2b414dc1c6dbf84 ;; \
      *) echo "arquitetura não suportada: ${TARGETARCH}"; exit 1 ;; \
    esac; \
    curl -fsSL -o /tmp/gh.tgz \
      "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_${GH_ARCH}.tar.gz"; \
    echo "${GH_SHA}  /tmp/gh.tgz" | sha256sum -c -; \
    tar -xzf /tmp/gh.tgz -C /tmp; \
    mv "/tmp/gh_${GH_VERSION}_linux_${GH_ARCH}/bin/gh" /usr/local/bin/gh; \
    curl -fsSL -o /tmp/cursor.tgz \
      "https://downloads.cursor.com/lab/${CURSOR_AGENT_VERSION}/linux/${CURSOR_ARCH}/agent-cli-package.tar.gz"; \
    echo "${CURSOR_SHA}  /tmp/cursor.tgz" | sha256sum -c -; \
    mkdir -p /opt/cursor-agent; \
    tar --strip-components=1 -xzf /tmp/cursor.tgz -C /opt/cursor-agent; \
    ln -sf /opt/cursor-agent/cursor-agent /usr/local/bin/cursor-agent; \
    ln -sf /opt/cursor-agent/cursor-agent /usr/local/bin/agent; \
    rm -rf /tmp/gh.tgz /tmp/cursor.tgz "/tmp/gh_${GH_VERSION}_linux_${GH_ARCH}"; \
    chmod 0755 /usr/local/bin/gh /opt/cursor-agent/cursor-agent

RUN useradd --uid 1000 --create-home --home-dir /home/forge --shell /usr/sbin/nologin forge \
    && mkdir -p /etc/forge/config \
    && chown -R forge:forge /etc/forge

WORKDIR /opt/forge
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir ".[postgres,web]" \
    && rm -rf /root/.cache/pip

COPY deploy/web/entrypoint.sh /entrypoint.sh
RUN chmod 0755 /entrypoint.sh

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/home/forge \
    XDG_CONFIG_HOME=/home/forge/.config \
    XDG_DATA_HOME=/home/forge/.local/share \
    FORGE_CONFIG_DIR=/etc/forge/config \
    FORGE_GH_BIN=/usr/local/bin/gh \
    FORGE_CURSOR_AGENT=/usr/local/bin/cursor-agent \
    PATH=/usr/local/bin:/home/forge/.local/bin:/usr/sbin:/usr/bin:/bin

EXPOSE 8091
ENTRYPOINT ["/entrypoint.sh"]
