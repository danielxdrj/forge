"""Seed de exemplo da aba "Agentes" — só para demonstração, nunca em produção.

Não é chamado automaticamente em nenhum lugar (nem em `create_app`, nem em `start()`).
Quem quiser dados de exemplo chama `seed_demo_agents` explicitamente, com `enabled=True`
(ex.: `FORGE_AGENTS_DEMO_SEED=true` lido pelo chamador). Só grava se a tabela `agents`
estiver vazia: nunca sobrescreve cadastro real.
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from ..storage.sql import SqlRepository

DEMO_AGENTS = (
    {
        "name": "monitor-deploy",
        "description": "Observa o pipeline de deploy e resume falhas (exemplo).",
        "scope": "development",
        "status": "active",
        "trigger": "webhook:ci",
        "engine": "claude",
        "permissions_read": ["github", "logs"],
        "permissions_write": [],
        "permissions_denied": ["ftp", "database", "portainer"],
    },
    {
        "name": "relatorio-semanal",
        "description": "Gera rascunho de relatório semanal (exemplo).",
        "scope": "company_system",
        "status": "paused",
        "trigger": "schedule:cron(0 8 * * MON)",
        "engine": "claude",
        "permissions_read": ["tasks", "github"],
        "permissions_write": [],
        "permissions_denied": ["ftp", "database", "portainer"],
    },
)


def seed_demo_agents(repo: SqlRepository, *, enabled: bool) -> int:
    if not enabled:
        return 0
    count_rows = repo.fetch("SELECT COUNT(*) FROM agents")
    if count_rows and count_rows[0][0]:
        return 0
    ts = datetime.now(UTC).isoformat()
    with repo.transaction() as tx:
        for item in DEMO_AGENTS:
            tx.execute(
                "INSERT INTO agents (id, name, description, scope, status, trigger, engine, "
                "permissions_read, permissions_write, permissions_denied, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()), item["name"], item["description"], item["scope"],
                    item["status"], item["trigger"], item["engine"],
                    json.dumps(item["permissions_read"]), json.dumps(item["permissions_write"]),
                    json.dumps(item["permissions_denied"]), ts, ts,
                ),
            )
        tx.audit("sistema:seed", "agent.seed_demo", "agents:*", f"ok: n={len(DEMO_AGENTS)}")
    return len(DEMO_AGENTS)
