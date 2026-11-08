# Executor isolado de agentes (FRG-6, ADR-013). Construído antes da execução; o agente não instala nada.
# Base fixa por tag. Pinar por digest antes de produção (pendência do ADR-013).

FROM python:3.12-slim AS base
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
