"""Executor isolado de agentes (FRG-6, ADR-013): um container não privilegiado por execução.

Supervisor (processo do Forge, no host) controla o `docker` CLI; o filho roda com rede negada, raiz somente
leitura, sem capacidades, não root, sem mounts e sem variáveis do host. O filho só recebe um payload mínimo
(id, título, objetivo da tarefa) e devolve UMA linha JSON validada. Nada de desserialização executável.

Limite honesto: o container compartilha o kernel do host. Isto reduz a superfície, não é sandbox absoluto.
Para a regra "escrita só pelo pai", o filho nunca fala com o banco nem com a auditoria.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
import threading
import time
import uuid
from dataclasses import dataclass, field

from ..logging import redact
from .runtime import AgentRuntime, RunResult
from .spec import AgentOutcome

DEFAULT_IMAGE = "forge-agent-sandbox:prod"
IMAGE_ENV = "FORGE_AGENT_SANDBOX_IMAGE"
MAX_OUTPUT_BYTES = 64 * 1024
MAX_LOGS = 50
MAX_LOG_CHARS = 300
MAX_SUMMARY_CHARS = 2000
_KILL_GRACE = 10.0
_NAME_PREFIX = "forge-agent-"

_LIMITS = (
    "--network", "none",
    "--read-only",
    "--cap-drop", "ALL",
    "--security-opt", "no-new-privileges",
    "--user", "65532:65532",
    "--memory", "128m", "--memory-swap", "128m",
    "--cpus", "0.5",
    "--pids-limit", "32",
    "--ulimit", "fsize=16777216",
    "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m,mode=1777",
    "--stop-timeout", "2",
)


@dataclass(frozen=True)
class SandboxResult:
    status: str  # success | failure | error | timeout | cancelled
    summary: str = ""
    logs: list[str] = field(default_factory=list)
    error: str | None = None  # só código fixo, nunca texto do agente ou da entrada
    usage: dict | None = None
    cost: float | None = None


def validate_output(raw: bytes) -> dict:
    """Aceita exatamente uma linha JSON objeto, com chaves e tipos fixos. Qualquer outra coisa é erro."""
    if len(raw) > MAX_OUTPUT_BYTES:
        raise ValueError("output_too_large")
    lines = raw.decode("utf-8", "strict").splitlines()
    if len(lines) != 1:
        raise ValueError("invalid_output")
    data = json.loads(lines[0])
    if not isinstance(data, dict) or set(data) - {"status", "summary", "logs", "error", "usage", "cost"}:
        raise ValueError("invalid_output")
    if data.get("status") not in ("success", "failure", "error"):
        raise ValueError("invalid_output")
    summary = data.get("summary", "")
    logs = data.get("logs", [])
    if not isinstance(summary, str) or len(summary) > MAX_SUMMARY_CHARS:
        raise ValueError("invalid_output")
    if not isinstance(logs, list) or len(logs) > MAX_LOGS or not all(
            isinstance(x, str) and len(x) <= MAX_LOG_CHARS for x in logs):
        raise ValueError("invalid_output")
    error = data.get("error")
    if error is not None and (not isinstance(error, str) or len(error) > 80):
        raise ValueError("invalid_output")
    usage = data.get("usage")
    if usage is not None and (not isinstance(usage, dict) or len(usage) > 20 or not all(
            isinstance(k, str) and len(k) <= 40 and isinstance(v, (int, float)) and not isinstance(v, bool)
            for k, v in usage.items())):
        raise ValueError("invalid_output")
    cost = data.get("cost")
    if cost is not None and (not isinstance(cost, (int, float)) or isinstance(cost, bool)):
        raise ValueError("invalid_output")
    return {"status": data["status"], "summary": summary, "logs": [redact(x) for x in logs],
            "error": error, "usage": usage, "cost": cost}


def _docker(*args: str, timeout: float = 15.0) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, timeout=timeout, check=False)


def _container_exists(name: str) -> bool:
    return _docker("container", "inspect", name).returncode == 0


class DockerSandbox:
    """Executa um agente num container descartável. Falha fechada: nunca cai para execução em thread."""

    def __init__(self, image: str = DEFAULT_IMAGE, *, command: tuple[str, ...] = ("python", "-m",
                 "forge_core.agents.sandbox_child"), extra_env: dict | None = None):
        self._image = image
        self._command = command
        self._extra = extra_env or {}

    def run(self, agent, payload: dict, timeout: float, cancel_event=None) -> SandboxResult:
        name = f"{_NAME_PREFIX}{uuid.uuid4().hex}"
        request = json.dumps({"agent": agent.spec.name, "payload": payload}, ensure_ascii=False).encode() + b"\n"
        args = ["run", "--rm", "-i", "--name", name, *_LIMITS]
        for k, v in self._extra.items():
            args += ["--env", f"{k}={v}"]
        args += [self._image, *self._command]
        try:
            proc = subprocess.Popen(["docker", *args], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL)
        except OSError:
            return SandboxResult("error", error="docker_unavailable")
        box: dict = {}

        def talk():
            try:
                proc.stdin.write(request)
                proc.stdin.close()
            except OSError:
                pass
            box["out"] = proc.stdout.read(MAX_OUTPUT_BYTES + 1)

        reader = threading.Thread(target=talk, daemon=True)
        reader.start()
        deadline = time.monotonic() + timeout
        while reader.is_alive() and time.monotonic() < deadline:
            if cancel_event is not None and cancel_event.is_set():
                break
            reader.join(0.05)
        cancelled = reader.is_alive() and cancel_event is not None and cancel_event.is_set()
        timed_out = reader.is_alive() and not cancelled
        if cancelled or timed_out or len(box.get("out", b"")) > MAX_OUTPUT_BYTES:
            if not self._destroy(name, proc, reader):
                return SandboxResult("error", error="cleanup_unconfirmed")
            if cancelled:
                return SandboxResult("cancelled", error="cancelled")
            return SandboxResult("timeout", error="timeout") if timed_out else SandboxResult(
                "error", error="output_too_large")
        proc.wait(timeout=_KILL_GRACE)
        if not self._destroy(name, proc, reader):
            return SandboxResult("error", error="cleanup_unconfirmed")
        if proc.returncode == 125 and not box.get("out"):  # docker não conseguiu criar o container
            return SandboxResult("error", error="sandbox_unavailable")
        try:
            data = validate_output(box.get("out", b""))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return SandboxResult("error", error="invalid_output")
        if data["status"] == "error":
            return SandboxResult("error", logs=data["logs"], error=data["error"] or "agent_error")
        return SandboxResult(data["status"], data["summary"], data["logs"], usage=data["usage"], cost=data["cost"])

    def _destroy(self, name: str, proc: subprocess.Popen, reader: threading.Thread) -> bool:
        """Mata o container (e, com ele, todos os processos descendentes), remove e confirma a remoção."""
        _docker("kill", "--signal", "KILL", name)
        _docker("rm", "-f", name)
        try:
            proc.wait(timeout=_KILL_GRACE)
        except subprocess.TimeoutExpired:
            proc.kill()
        reader.join(_KILL_GRACE)
        deadline = time.monotonic() + _KILL_GRACE
        while time.monotonic() < deadline:
            if not _container_exists(name):
                return True
            _docker("rm", "-f", name)
            time.sleep(0.2)
        return not _container_exists(name)


class IsolatedRuntime(AgentRuntime):
    """Mesmo contrato do AgentRuntime (gates, RunResult), com a execução dentro do DockerSandbox.

    Sem fallback: se o sandbox falhar, o resultado é `error` (ou `timeout`); nunca roda em thread.
    O pai continua dono de banco, auditoria e transições: o filho só devolve o resultado.
    """

    def __init__(self, sandbox: DockerSandbox, settings=None):
        super().__init__(settings=settings)
        self._sandbox = sandbox

    def execute(self, agent, ctx, timeout: float | None = None) -> RunResult:
        self.check_allowed(agent)
        timeout = agent.spec.timeout_seconds if timeout is None else timeout
        started = datetime.now(timezone.utc).isoformat()
        payload = {"task_id": ctx.task.id, "title": ctx.task.title, "objective": ctx.task.objective}
        res = self._sandbox.run(agent, payload, timeout, ctx.cancel_event)
        logs = ctx.logs + res.logs
        ctx.seal()
        finished = datetime.now(timezone.utc).isoformat()
        if res.status in ("success", "failure"):
            outcome = AgentOutcome(status=res.status, summary=res.summary, usage=res.usage, cost=res.cost)
            return RunResult(res.status, outcome, None, started, finished, logs)
        if res.status == "timeout":
            return RunResult("timeout", None, f"timeout após {timeout}s", started, finished, logs)
        if res.status == "cancelled":
            return RunResult("cancelled", None, "cancelado", started, finished, logs)
        return RunResult("error", None, res.error or "error", started, finished, logs)


def default_runtime(settings=None) -> IsolatedRuntime:
    """Runtime padrão do Orchestrator: Docker. Sem Docker ou imagem, o despacho falha fechado (sem thread)."""
    return IsolatedRuntime(DockerSandbox(os.environ.get(IMAGE_ENV) or DEFAULT_IMAGE), settings=settings)
