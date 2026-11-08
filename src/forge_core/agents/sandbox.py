"""Executor isolado de agentes (FRG-6, ADR-013): um container não privilegiado por execução.

O supervisor (processo do Forge, no host) controla o `docker` CLI. O filho roda com rede negada, raiz somente
leitura, sem capacidades, não root, sem mounts e sem variáveis do host (`run_args` é o único perfil). O filho
recebe um payload mínimo e devolve UMA linha JSON validada. Nada é desserializado como código.

Confirmação de remoção: só é considerada removida a ausência comprovada (o daemon respondeu e não listou o
container). Falha operacional (daemon inacessível, erro de autenticação, timeout) é `cleanup_unconfirmed`.

Limite honesto: o container compartilha o kernel do host. Isto reduz a superfície, não é sandbox absoluto.
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..config import Settings, load_settings, require_automation_enabled
from ..errors import AgentError
from ..logging import redact
from .approval import PRIVILEGED_DISABLED_MESSAGE
from .runtime import RunResult
from .spec import AgentOutcome

DEFAULT_IMAGE = "forge-agent-sandbox:prod"
IMAGE_ENV = "FORGE_AGENT_SANDBOX_IMAGE"
MAX_OUTPUT_BYTES = 64 * 1024
MAX_LOGS = 50
MAX_LOG_CHARS = 300
MAX_SUMMARY_CHARS = 2000
CHILD_ERRORS = frozenset({"agent_exception", "unknown_agent", "invalid_outcome"})
_KILL_GRACE = 10.0
_DOCKER_TIMEOUT = 20.0
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
    error: str | None = None  # só código fixo (allowlist), nunca texto do agente ou da entrada
    usage: dict | None = None
    cost: float | None = None


def run_args(name: str, image: str, command: tuple[str, ...]) -> list[str]:
    """Argumentos de `docker run` do perfil de execução. Único lugar em que as flags de isolamento existem."""
    return ["run", "--rm", "-i", "--name", name, *_LIMITS, image, *command]


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
    if error is not None and not isinstance(error, str):
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


def interpret_output(raw: bytes) -> SandboxResult:
    """Transforma a saída bruta do filho em resultado. Erro de protocolo nunca carrega o conteúdo recebido."""
    if len(raw) > MAX_OUTPUT_BYTES:
        return SandboxResult("error", error="output_too_large")
    try:
        data = validate_output(raw)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return SandboxResult("error", error="invalid_output")
    if data["status"] == "error":
        code = data["error"] if data["error"] in CHILD_ERRORS else "invalid_output"
        return SandboxResult("error", logs=data["logs"], error=code)
    return SandboxResult(data["status"], data["summary"], data["logs"], usage=data["usage"], cost=data["cost"])


def _docker(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=_DOCKER_TIMEOUT, check=False)


def container_state(name: str) -> str:
    """'present' | 'absent' (comprovado: o daemon respondeu sem listar o nome) | 'unknown' (falha operacional)."""
    try:
        out = _docker("ps", "-aq", "--no-trunc", "--filter", f"name=^{name}$")
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    if out.returncode != 0:
        return "unknown"
    return "present" if out.stdout.strip() else "absent"


def _destroy(name: str, proc: subprocess.Popen, reader: threading.Thread) -> bool:
    """Mata e remove o container e confirma a ausência comprovada. Nunca levanta exceção."""
    deadline = time.monotonic() + _KILL_GRACE
    state = "unknown"
    while True:
        for args in (("kill", "--signal", "KILL", name), ("rm", "-f", name)):
            try:
                _docker(*args)
            except (OSError, subprocess.SubprocessError):
                pass
        state = container_state(name)
        if state != "present" or time.monotonic() > deadline:
            break
        time.sleep(0.2)
    try:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=2)
    except (OSError, subprocess.SubprocessError):
        pass
    reader.join(_KILL_GRACE)
    return state == "absent"


def _pump(proc: subprocess.Popen, request: bytes, box: dict) -> None:
    try:
        proc.stdin.write(request)
        proc.stdin.close()
    except OSError:
        pass
    try:
        box["out"] = proc.stdout.read(MAX_OUTPUT_BYTES + 1)
    except (OSError, ValueError):
        box["out"] = b""


def _cancelled(cancel_event: threading.Event | None) -> bool:
    return cancel_event is not None and cancel_event.is_set()


class DockerSandbox:
    """Executa um agente num container descartável. Falha fechada: nunca cai para execução em thread."""

    def __init__(self, image: str = DEFAULT_IMAGE, *, command: tuple[str, ...] = (
            "python", "-m", "forge_core.agents.sandbox_child")):
        self._image = image
        self._command = command

    def run(self, agent, payload: dict, timeout: float, cancel_event: threading.Event | None = None) -> SandboxResult:
        name = f"{_NAME_PREFIX}{uuid.uuid4().hex}"
        request = json.dumps({"agent": agent.spec.name, "payload": payload}, ensure_ascii=False).encode() + b"\n"
        try:
            proc = subprocess.Popen(["docker", *run_args(name, self._image, self._command)],
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except OSError:
            return SandboxResult("error", error="docker_unavailable")
        box: dict = {}
        reader = threading.Thread(target=_pump, args=(proc, request, box), daemon=True)
        reader.start()
        result = SandboxResult("error", error="supervisor_failed")
        try:
            result = self._collect(proc, reader, box, timeout, cancel_event)
        except Exception:
            pass
        finally:
            confirmed = _destroy(name, proc, reader)
        if not confirmed:
            return SandboxResult("error", error="cleanup_unconfirmed")
        return result

    @staticmethod
    def _collect(proc, reader, box, timeout, cancel_event) -> SandboxResult:
        deadline = time.monotonic() + timeout
        while reader.is_alive() and time.monotonic() < deadline:
            if _cancelled(cancel_event):
                return SandboxResult("cancelled", error="cancelled")
            reader.join(0.05)
        if _cancelled(cancel_event):
            return SandboxResult("cancelled", error="cancelled")
        if reader.is_alive():
            return SandboxResult("timeout", error="timeout")
        raw = box.get("out", b"")
        if len(raw) > MAX_OUTPUT_BYTES:
            return SandboxResult("error", error="output_too_large")
        try:
            proc.wait(timeout=_KILL_GRACE)
        except subprocess.TimeoutExpired:
            return SandboxResult("error", error="sandbox_stalled")
        if _cancelled(cancel_event):
            return SandboxResult("cancelled", error="cancelled")
        if proc.returncode == 125 and not raw:  # docker não conseguiu criar o container (ex.: imagem ausente)
            return SandboxResult("error", error="sandbox_unavailable")
        return interpret_output(raw)


class IsolatedRuntime:
    """Gates e contrato de execução de agentes. A execução exige um DockerSandbox; sem ele, recusa."""

    def __init__(self, sandbox: DockerSandbox | None = None, settings: Settings | None = None):
        self._sandbox = sandbox
        self._settings = settings

    def check_allowed(self, agent) -> None:
        """Gate de execução: automação ligada, agente ativo e somente `read`. Levanta se não puder executar."""
        settings = self._settings if self._settings is not None else load_settings()
        require_automation_enabled(settings)
        spec = agent.spec
        if spec.requires_approval:
            raise AgentError(f"agente {spec.name} não executa: {PRIVILEGED_DISABLED_MESSAGE}")
        if not spec.active or spec.name in settings.agents_disabled:
            raise AgentError(f"agente desativado: {spec.name}")

    def execute(self, agent, ctx, timeout: float | None = None) -> RunResult:
        self.check_allowed(agent)
        if self._sandbox is None:
            raise AgentError("runtime isolado sem sandbox: execução recusada")
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
    import os

    return IsolatedRuntime(DockerSandbox(os.environ.get(IMAGE_ENV) or DEFAULT_IMAGE), settings=settings)
