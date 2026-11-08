# Imagem do executor isolado de agentes (FRG-6). Construída uma vez, fora da execução do agente.
# Base fixa por tag; pinar por digest antes de produção (pendência registrada no ADR-013).
FROM python:3.12-slim

RUN useradd --uid 65532 --no-create-home --shell /usr/sbin/nologin agent
COPY src/forge_core /opt/forge/forge_core
ENV PYTHONPATH=/opt/forge PYTHONDONTWRITEBYTECODE=1
USER 65532:65532
WORKDIR /tmp
