# Executor isolado de agentes (FRG-6, ADR-013). Construído antes da execução; o agente não instala nada.
# Base fixada por digest do índice multi-arquitetura de python:3.12-slim, obtido do registry Docker Hub em
# 08/11/2026 (sha256:4840d514...). Para atualizar: obter o novo digest, trocar aqui e no ADR-013, e rodar o CI.

FROM python:3.12-slim@sha256:4840d514c583a4d3d8cad3940e68dee6f0f6f3635c12fcd0a3d74c21a5b93a54 AS base
RUN useradd --uid 65532 --no-create-home --shell /usr/sbin/nologin agent
COPY src/forge_core /opt/forge/forge_core
ENV PYTHONPATH=/opt/forge PYTHONDONTWRITEBYTECODE=1
WORKDIR /tmp

# Imagem de produção: só o Core e o filho. Nenhum agente de teste.
FROM base AS prod
USER 65532:65532

# Imagem de TESTE da FRG-6: adiciona o agente de teste `probe` (read) para provar os controles.
FROM base AS test
COPY tests/sandbox/forge_test_probe.py /opt/probe/forge_test_probe.py
ENV PYTHONPATH=/opt/forge:/opt/probe
USER 65532:65532
