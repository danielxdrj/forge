# Painel local do Core (ADR-017). Distinto do sandbox FRG-6 (ADR-013, --network none).
# Base: mesmo digest multi-arch de python:3.12-slim do ADR-013.
# gh 2.81.0 e Cursor Agent 2026.11.10-731fb78: tarball + SHA-256.

FROM python:3.12-slim@sha256:4840d514c583a4d3d8cad3940e68dee6f0f6f3635c12fcd0a3d74c21a5b93a54

ARG TARGETARCH
ARG GH_VERSION=2.81.0
ARG CURSOR_AGENT_VERSION=2026.11.10-731fb78
ARG NODE_VERSION=22.21.1
ARG CLAUDE_CODE_VERSION=2.1.322

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
    case "${TARGETARCH}" in \
      amd64) NODE_ARCH=x64; NODE_SHA=219a152ea859861d75adea578bdec3dce8143853c13c5187f40c40e77b0143b2 ;; \
      arm64) NODE_ARCH=arm64; NODE_SHA=c86830dedf77f8941faa6c5a9c863bdfdd1927a336a46943decc06a38f80bfb2 ;; \
      *) echo "arquitetura não suportada: ${TARGETARCH}"; exit 1 ;; \
    esac; \
    curl -fsSL -o /tmp/node.tgz \
      "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-${NODE_ARCH}.tar.gz"; \
    echo "${NODE_SHA}  /tmp/node.tgz" | sha256sum -c -; \
    tar -xzf /tmp/node.tgz -C /usr/local --strip-components=1; \
    rm -rf /tmp/gh.tgz /tmp/cursor.tgz /tmp/node.tgz "/tmp/gh_${GH_VERSION}_linux_${GH_ARCH}"; \
    npm install -g "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}"; \
    npm cache clean --force; \
    chmod 0755 /usr/local/bin/gh /opt/cursor-agent/cursor-agent /usr/local/bin/claude

RUN useradd --uid 1000 --create-home --home-dir /home/forge --shell /usr/sbin/nologin forge \
    && mkdir -p /etc/forge/config /graphs /home/forge/.claude \
    && chown -R forge:forge /etc/forge /graphs /home/forge

WORKDIR /opt/forge
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir ".[postgres,web]" \
    && pip install --no-cache-dir "graphifyy==0.9.106" \
    && rm -rf /root/.cache/pip

COPY deploy/web/entrypoint.sh /entrypoint.sh
COPY deploy/web/initdb/01-roles.sh /tmp/check-lf-01-roles.sh
RUN python -c "import pathlib,sys; files=['/entrypoint.sh','/tmp/check-lf-01-roles.sh']; bad=[f for f in files if b'\r' in pathlib.Path(f).read_bytes()];\
 sys.exit('CRLF forbidden in '+', '.join(bad)+'; use LF (.gitattributes, git add --renormalize .)' if bad else 0)" \
    && rm -f /tmp/check-lf-01-roles.sh \
    && chmod 0755 /entrypoint.sh

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/home/forge \
    XDG_CONFIG_HOME=/home/forge/.config \
    XDG_DATA_HOME=/home/forge/.local/share \
    FORGE_CONFIG_DIR=/etc/forge/config \
    FORGE_GH_BIN=/usr/local/bin/gh \
    FORGE_CURSOR_AGENT=/usr/local/bin/cursor-agent \
    FORGE_CLAUDE_BIN=/usr/local/bin/claude \
    FORGE_ENGINE=claude \
    GRAPHIFY_BACKEND=none \
    GRAPHIFY_QUERY_LOG_DISABLE=1 \
    PATH=/usr/local/bin:/home/forge/.local/bin:/usr/sbin:/usr/bin:/bin

EXPOSE 8091
# Processo padrão: uid 1000. O entrypoint ainda tem o ramo root+chown para volume antigo
# se alguém subir com -u 0. Volume novo forge_cli_home herda o dono de /home/forge.
USER forge
ENTRYPOINT ["/entrypoint.sh"]
