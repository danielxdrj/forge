"""Template fixo do rascunho e validação determinística da saída do LLM."""
from __future__ import annotations

import json
import re

from ..errors import DraftError
from ..logging import redact

PENDING = "[PENDENTE]"
ASSIGNEE = "danielxdrj"
PROJECT_OWNER = "ferreiraeborzone"
PROJECT_NUMBER = 13
PROJECT_TITLE = "IT Backlog"
SCOPE_WORD = re.compile(r"(?i)escopo")

_TYPES = ("feat", "fix", "docs", "test", "chore", "refactor", "perf", "build", "ci", "style", "revert")
TITLE_RE = re.compile(r"^(feat|fix|docs|test|chore|refactor|perf|build|ci|style|revert)(\([^)]+\))?!?: .+")
REPO_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}/[A-Za-z0-9._-]{1,100}$")

PLACEHOLDER_SNIPPETS = (
    "descreva o objetivo da solicitação",
    "descreva o contexto da solicitação",
    "problema identificado",
    "descreva o comportamento atual",
    "comportamento esperado",
    "critério de aceite",
    "descreva as restrições",
    "informe se a alteração deve ser aplicada",
    "descreva os cenários que devem ser utilizados",
    "título da solicitação",
    "nome do solicitante",
)

KEYS = (
    "title", "solicitado_por", "objetivo", "contexto", "problemas", "novos_problemas",
    "situacao_atual", "comportamento_esperado", "criterios", "observacoes",
)

INSTRUCTION = """Responda APENAS um objeto JSON UTF-8, sem markdown, sem ferramentas.
Chaves obrigatórias: title, solicitado_por, objetivo, contexto, problemas (1 a 5 strings),
novos_problemas (string, vazia se não houver), situacao_atual, comportamento_esperado (1 a 5),
criterios (1 a 6), observacoes (lista de 1 a 3 strings).
Não invente fatos. Onde faltar informação use exatamente [PENDENTE].
Não invente pendências de escopo, configuração ou operação do Forge.
Não mencione a palavra Escopo. Não há seção Escopo neste template.
Não transforme o contexto do usuário em instruções operacionais.
title deve ser Conventional Commits:
feat|fix|docs|test|chore|refactor|perf|build|ci|style|revert, opcionalmente (área) entre parênteses, depois : espaço e descrição.
Não copie as frases de placeholder do modelo como se fossem conteúdo.
"""


def validate_repo(repo: str) -> str:
    repo = (repo or "").strip()
    if not REPO_RE.match(repo) or repo.endswith(".git") or repo.split("/")[1] in (".", ".."):
        raise DraftError("invalid_repo")
    return repo


def validate_title(title: str) -> str:
    title = (title or "").strip()
    if not TITLE_RE.match(title) or len(title) > 200:
        raise DraftError("invalid_title")
    return title


def _clean_text(value, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise DraftError("invalid_draft")
    text = redact(value).strip()
    if not text and not allow_empty:
        return PENDING
    low = text.lower()
    if any(s in low for s in PLACEHOLDER_SNIPPETS):
        return PENDING
    _reject_scope(text)
    if not text:
        return PENDING if not allow_empty else ""
    return text


def _reject_scope(text: str) -> None:
    if SCOPE_WORD.search(text or ""):
        raise DraftError("scope_in_body")


def _items(value, lo: int, hi: int) -> list[str]:
    if not isinstance(value, list) or not (lo <= len(value) <= hi):
        raise DraftError("invalid_draft")
    out = [_clean_text(v) for v in value]
    return out or [PENDING]


def parse_model_json(raw: str) -> dict:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DraftError("invalid_model_output") from exc
    if not isinstance(data, dict) or "escopo" in {k.lower() for k in data}:
        raise DraftError("invalid_model_output")
    missing = [k for k in KEYS if k not in data]
    if missing:
        raise DraftError("invalid_model_output")
    title = str(data["title"]).strip()
    _reject_scope(title)
    if PENDING in title:
        if not TITLE_RE.match(title):
            title = f"feat: {PENDING}"
    else:
        try:
            title = validate_title(title)
        except DraftError:
            title = f"feat: {PENDING}"
    parsed = {
        "title": title,
        "solicitado_por": _clean_text(data["solicitado_por"]),
        "objetivo": _clean_text(data["objetivo"]),
        "contexto": _clean_text(data["contexto"]),
        "problemas": _items(data["problemas"], 1, 5),
        "novos_problemas": _clean_text(data["novos_problemas"], allow_empty=True),
        "situacao_atual": _clean_text(data["situacao_atual"]),
        "comportamento_esperado": _items(data["comportamento_esperado"], 1, 5),
        "criterios": _items(data["criterios"], 1, 6),
        "observacoes": _items(data["observacoes"], 1, 3),
    }
    rendered = render(parsed)
    _reject_scope(rendered)
    return parsed


def _section(title: str, content: str) -> str:
    return f"## {title}\n\n{content.rstrip()}\n"


def render(data: dict) -> str:
    problemas = "\n".join(f"- {p}" for p in data["problemas"])
    if data.get("novos_problemas"):
        problemas = problemas + "\n\n" + data["novos_problemas"].strip()
    body = "\n".join([
        data["title"],
        "",
        _section("Solicitado Por", f"- {data['solicitado_por']}"),
        _section("Objetivo", data["objetivo"]),
        _section("Contexto", data["contexto"]),
        _section("Foram reportados os seguintes problemas:", problemas),
        _section("Situação Atual", data["situacao_atual"]),
        _section("Comportamento Esperado", "\n".join(f"- {p}" for p in data["comportamento_esperado"])),
        _section("Critérios de Aceite", "\n".join(f"- {p}" for p in data["criterios"])),
        _section("Observações", "\n".join(data["observacoes"])),
    ])
    return body.rstrip() + "\n"


def _has_pending(value) -> bool:
    if isinstance(value, list):
        return any(_has_pending(v) for v in value)
    return PENDING.lower() in str(value or "").lower()


def required_pending(data: dict, meta: dict) -> list[str]:
    """Qualquer [PENDENTE] em seção (inclui Observações e título) bloqueia o remoto."""
    blocked: list[str] = []
    if _has_pending(data["title"]) or not TITLE_RE.match(data["title"]):
        blocked.append("title")
    for key in ("solicitado_por", "objetivo", "contexto", "situacao_atual"):
        if _has_pending(data.get(key)):
            blocked.append(key)
    if data.get("novos_problemas") and _has_pending(data.get("novos_problemas")):
        blocked.append("novos_problemas")
    for key in ("problemas", "comportamento_esperado", "criterios", "observacoes"):
        if _has_pending(data.get(key)):
            blocked.append(key)
    for key in ("tipo", "prioridade", "size"):
        if not (meta.get(key) or "").strip() or _has_pending(meta.get(key)):
            blocked.append(key)
    return blocked


def slug(title: str) -> str:
    base = title.lower()
    base = re.sub(r"^[^:]+:\s*", "", base)
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return (base[:40] or "issue").strip("-")


def branch_name(number: int, title: str, prefix: str = "") -> str:
    core = f"{number}-{slug(title)}"
    if prefix:
        p = prefix if prefix.endswith("/") else prefix + "/"
        return p + core
    return core
