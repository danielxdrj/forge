"""API /api/areas: catálogo das áreas e dos agentes planejados (somente leitura)."""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from test_web_agents import HOST, _app, _login

from forge_core.areas.catalog import COMMON, ENGINES, PLANNED, SECTORS, TABS


def test_catalog_is_consistent():
    sectors = {sid for sid, _ in SECTORS} | {COMMON}
    ids = [agent.id for agent in PLANNED]
    assert len(ids) == len(set(ids)), "id de agente planejado repetido"
    for agent in PLANNED:
        assert agent.sector in sectors, agent.id
        assert agent.engine in ENGINES, agent.id
        assert agent.summary and agent.description and agent.trigger and agent.writes
        assert 1 <= agent.phase <= 8
    for sid, _ in SECTORS:
        assert any(a.sector == sid for a in PLANNED), f"setor sem agente planejado: {sid}"
    keys = [(tab.sector, tab.id) for tab in TABS]
    assert len(keys) == len(set(keys))
    assert all(tab.sector in sectors for tab in TABS)
    known = set(ids)
    for tab in TABS:
        assert set(tab.agents) <= known, f"aba {tab.sector}/{tab.id} cita agente inexistente"


def test_areas_requires_login(tmp_path):
    client, _repo = _app(tmp_path)
    assert client.get("/api/areas", headers=HOST).status_code == 401


def test_editor_reads_catalog(tmp_path):
    client, _repo = _app(tmp_path, user=(42, "maria"), role="editor")
    _login(client)
    res = client.get("/api/areas", headers=HOST)
    assert res.status_code == 200
    data = res.json()
    assert [s["id"] for s in data["sectors"]] == ["desenvolvimento", "juridico", "financeiro"]
    assert len(data["planned"]) == len(PLANNED)
    assert {"sector", "id", "label", "summary", "phase", "agents"} <= set(data["tabs"][0])
