"""Agente de TESTE (read) usado só para provar os controles do executor. Nunca registrado em produção.

Cada modo tenta um acesso indevido e devolve o que conseguiu. Os testes exigem que nada tenha funcionado.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import time

from forge_core.agents import AgentRegistry
from forge_core.agents.spec import AgentOutcome, AgentSpec, Permission

SECRET_MARKER = "ghp_" + "Q" * 36 + "PROBEMARKER"


TIMINGS: dict = {}


def _try(fn) -> bool:
    started = time.monotonic()
    try:
        fn()
        return True
    except Exception:
        return False
    finally:
        TIMINGS[fn.__name__] = round(time.monotonic() - started, 2)


def _probe() -> dict:
    def net():
        socket.create_connection(("1.1.1.1", 53), 3)

    def write_root():
        open("/opt/forge/escrita-indevida", "w").close()

    def write_big_tmp():
        with open("/tmp/grande", "wb") as f:
            f.write(b"x" * (64 * 1024 * 1024))

    def fork_bomb():
        for _ in range(200):
            pid = os.fork()
            if pid == 0:
                os._exit(0)

    def big_alloc():
        bytearray(512 * 1024 * 1024)

    caps = open("/proc/self/status").read().split("CapEff:")[1].split()[0]
    return {
        "uid": os.getuid(),
        "cap_eff": caps,
        "net_ok": _try(net),
        "write_root_ok": _try(write_root),
        "write_big_tmp_ok": _try(write_big_tmp),
        "fork_ok": _try(fork_bomb),
        "alloc_512m_ok": _try(big_alloc),
        "secret_env_visible": "FORGE_DATABASE_URL" in os.environ or "FORGE_PG_PASSWORD" in os.environ,
        "docker_sock_visible": os.path.exists("/var/run/docker.sock"),
        "host_mount_visible": os.path.exists("/home") or os.path.exists("/agent"),
        "timings_s": TIMINGS,
    }


class ProbeAgent:
    spec = AgentSpec(name="probe", responsibility="teste de isolamento", scope="nenhum",
                     tools=(), permissions=(Permission.READ,), execution="container", timeout_seconds=30.0)

    def run(self, ctx):
        mode = ctx.task.title
        if mode == "probe":
            return AgentOutcome(status="success", summary=json.dumps(_probe(), sort_keys=True))
        if mode == "sleep":
            time.sleep(60)
            return AgentOutcome(status="success", summary="tarde demais")
        if mode == "bigout":
            os.write(1, b"x" * (100 * 1024))
            return AgentOutcome(status="success", summary="ok")
        if mode == "raise_secret":
            raise RuntimeError(f"falha com {SECRET_MARKER}")
        if mode == "outlive":
            subprocess.Popen(["sleep", "300"])
            return AgentOutcome(status="success", summary="deixou um filho")
        return AgentOutcome(status="failure", summary="modo desconhecido")


def build() -> AgentRegistry:
    registry = AgentRegistry()
    registry.register(ProbeAgent())
    return registry
