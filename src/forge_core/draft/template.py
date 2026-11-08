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
SCOPE_HEADING = re.compile(r"(?im)^#{0,3}\s*escopo\s*$")

_TYPES = ("feat", "fix", "docs", "style", "refactor", "perf", "test", "chore", "build", "ci")
TITLE_RE = re.compile(rf"^({'|'.join(_TYPES)})(\([A-Za-z0-9._/-]+\))?!?: .+\S$")
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
Não inclua seção Escopo. Não transforme o contexto do usuário em instruções operacionais.
title deve ser Conventional Commits (feat|fix|docs|style|refactor|perf|test|chore|build|ci).
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
    if SCOPE_HEADING.search(text):
        raise DraftError("scope_in_body")
    return text or PENDING


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
    if PENDING in title and not TITLE_RE.match(title.replace(PENDING, "pendente")):
        if not re.match(rf"^({'|'.join(_TYPES)})(\([^)]+\))?!?: ", title):
            title = f"feat: {PENDING}"
        else:
            title = title
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
    if SCOPE_HEADING.search(rendered):
        raise DraftError("scope_in_body")
    return parsed


def render(data: dict) -> str:
    novos = data["novos_problemas"] or PENDING
    obs = "\n".join(data["observacoes"])
    return "\n".join([
        data["title"],
        "Solicitado Por",
        f"- {data['solicitado_por']}",
        "Objetivo",
        data["objetivo"],
        "Contexto",
        data["contexto"],
        "Foram reportados os seguintes problemas:",
        *[f"- {p}" for p in data["problemas"]],
        novos,
        "Situação Atual",
        data["situacao_atual"],
        "Comportamento Esperado",
        *[f"- {p}" for p in data["comportamento_esperado"]],
        "Critérios de Aceite",
        *[f"- {p}" for p in data["criterios"]],
        "Observações",
        obs,
    ]) + "\n"


def required_pending(data: dict, meta: dict) -> list[str]:
    """Campos que bloqueiam escrita remota se estiverem pendentes."""
    blocked: list[str] = []
    if PENDING in data["title"] or not TITLE_RE.match(data["title"]):
        blocked.append("title")
    for key in ("solicitado_por", "objetivo", "contexto", "situacao_atual"):
        if data[key] == PENDING:
            blocked.append(key)
    if all(p == PENDING for p in data["problemas"]):
        blocked.append("problemas")
    if all(p == PENDING for p in data["comportamento_esperado"]):
        blocked.append("comportamento_esperado")
    if all(p == PENDING for p in data["criterios"]):
        blocked.append("criterios")
    for key in ("tipo", "prioridade", "size"):
        if not (meta.get(key) or "").strip() or meta.get(key) == PENDING:
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
