"""Template fixo do rascunho e validação determinística da saída do LLM."""
from __future__ import annotations

import json
import re
import unicodedata

from ..errors import DraftError
from ..logging import redact

PENDING = "[PENDENTE]"
SUGGESTION_PREFIX = "_Sugestão (revise):_"
ASSIGNEE = "danielxdrj"
PROJECT_OWNER = "ferreiraeborzone"
PROJECT_NUMBER = 13
PROJECT_TITLE = "IT Backlog"
SCOPE_HEADING = re.compile(r"(?m)^(?:#{1,6}\s*)?escopo(?:\s*:)?\s*$")
SCOPE_MD_HEADING = re.compile(r"(?m)^#{1,6}\s*escopo(?:\s|:|$)")
SCOPE_FORGE = re.compile(
    r"escopo\s+operacional|escopo\s+do\s+forge|configuracao\s+do\s+forge"
)

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
Chaves opcionais de sugestão do board: tipo, prioridade, size (strings).
Não invente fatos.
SEMPRE preencha comportamento_esperado e criterios com a melhor inferência possível a partir
do contexto, mesmo que o pedido seja curto. Cada item inferido DEVE começar exatamente com
_Sugestão (revise):_ (incluindo os underscores). Nunca use [PENDENTE] nessas duas listas.
Use [PENDENTE] em objetivo SOMENTE se o contexto do usuário estiver vazio. Com contexto
não vazio, infira o objetivo; não deixe [PENDENTE].
Use [PENDENTE] em solicitado_por só se o contexto não indicar quem pediu.
Sugira tipo, prioridade e size a partir das opções do board listadas no prompt, quando houver.
Use [PENDENTE] nesses três SOMENTE se o contexto não permitir decidir.
Nunca invente uma opção que não esteja na lista do board.
Nunca use [PENDENTE] em observacoes nem em campos opcionais (novos_problemas): escreva Nenhuma
ou deixe a string vazia.
Se o contexto do usuário contiver o texto [PENDENTE] (mesmo entre aspas, crases ou parênteses),
não o copie para o rascunho; parafraseie o fato sem o marcador.
Não invente pendências nem detalhes sobre como o Forge formata, valida ou publica issues.
Não crie seção/cabeçalho Escopo. A palavra escopo em texto da tarefa é permitida.
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


def _suggestion(value) -> str:
    """Sugestão de board: string limpa ou vazio. [PENDENTE] e não-string viram vazio."""
    if not isinstance(value, str):
        return ""
    text = redact(value).strip()
    if not text or _has_pending(text):
        return ""
    return text


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


def _fold_pt(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).casefold()


def _reject_scope(text: str) -> None:
    folded = _fold_pt(text)
    if SCOPE_HEADING.search(folded) or SCOPE_MD_HEADING.search(folded) or SCOPE_FORGE.search(folded):
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
    if _has_pending(title):
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
        "tipo": _suggestion(data.get("tipo")),
        "prioridade": _suggestion(data.get("prioridade")),
        "size": _suggestion(data.get("size")),
    }
    parsed = fill_inferred_sections(parsed)
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


# Citação do marcador (não é valor): "[PENDENTE]", `[PENDENTE]`, ([PENDENTE]).
_CITED_PENDING = re.compile(
    r'(?i)(?:"\[PENDENTE\]"|\'\[PENDENTE\]\'|`\[PENDENTE\]`|\(\[PENDENTE\]\))'
)


def _has_pending(value) -> bool:
    """True só se [PENDENTE] for usado como valor/lacuna, não como citação."""
    if isinstance(value, list):
        return any(_has_pending(v) for v in value)
    text = _CITED_PENDING.sub(" ", str(value or ""))
    return PENDING.lower() in text.lower()


def _is_suggestion_item(text: str) -> bool:
    return str(text or "").strip().lower().startswith(SUGGESTION_PREFIX.lower())


def _blocking_pending(value) -> bool:
    """[PENDENTE] real bloqueia; item prefixado como sugestão não bloqueia, salvo se a lacuna for só o marcador."""
    if isinstance(value, list):
        return any(_blocking_pending(v) for v in value)
    text = str(value or "").strip()
    if _is_suggestion_item(text):
        rest = text[len(SUGGESTION_PREFIX):].strip()
        return rest == PENDING or rest.lower() == PENDING.lower()
    return _has_pending(text)


def _usable_text(value: str | None) -> str:
    text = (value or "").strip()
    if not text or _has_pending(text):
        return ""
    return text


def _clip(text: str, limit: int = 180) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _as_suggestion(text: str) -> str:
    compact = " ".join((text or "").split())
    if _is_suggestion_item(compact):
        return compact
    return f"{SUGGESTION_PREFIX} {compact}"


def _infer_expected(data: dict, ctx: str) -> str:
    problems = [p for p in (data.get("problemas") or []) if _usable_text(p)]
    if problems:
        return f"O sistema deixa de apresentar o problema: {problems[0]}."
    situacao = _usable_text(data.get("situacao_atual"))
    if situacao:
        return f"Em lugar da situação atual ({_clip(situacao, 80)}), a solicitação descrita passa a ser atendida."
    if ctx:
        return f"A solicitação é atendida ponta a ponta: {_clip(ctx)}."
    who = _usable_text(data.get("solicitado_por"))
    if who:
        return f"A solicitação feita por {who} é atendida e pode ser verificada."
    title = _usable_text(data.get("title"))
    if title:
        bare = re.sub(r"^[^:]+:\s*", "", title).strip() or title
        return f"A solicitação «{bare}» é atendida de ponta a ponta."
    return "A solicitação descrita neste rascunho é atendida de ponta a ponta."


def _infer_acceptance(data: dict, ctx: str) -> str:
    expected = [e for e in (data.get("comportamento_esperado") or []) if _usable_text(e)]
    if expected:
        item = expected[0]
        if _is_suggestion_item(item):
            item = item[len(SUGGESTION_PREFIX):].strip()
        return f"Há verificação observável de que {item.rstrip('.')}."
    if ctx:
        return f"Há um teste ou checagem manual que cobre: {_clip(ctx)}."
    return "Há um teste ou checagem manual que demonstra o resultado descrito."


def _infer_objetivo(data: dict, ctx: str) -> str:
    title = _usable_text(data.get("title"))
    if title and not _has_pending(title):
        bare = re.sub(r"^[^:]+:\s*", "", title).strip()
        if bare:
            return f"Atender a solicitação: {bare}."
    if ctx:
        return f"Atender a solicitação: {_clip(ctx)}."
    return PENDING


def _fill_inferred_list(items, infer) -> list[str]:
    kept = [item for item in (items or []) if not _has_pending(item)]
    if kept:
        return kept
    return [_as_suggestion(infer())]


def fill_inferred_sections(data: dict, user_context: str = "") -> dict:
    """Garante Comportamento esperado e Critérios de aceite inferidos; Objetivo só fica [PENDENTE] sem contexto."""
    data = dict(data)
    ctx = _usable_text(user_context) or _usable_text(data.get("contexto"))
    if _has_pending(data.get("contexto")) and _usable_text(user_context):
        data["contexto"] = user_context.strip()
        ctx = ctx or user_context.strip()
    if _has_pending(data.get("objetivo")):
        if ctx:
            data["objetivo"] = _infer_objetivo(data, ctx)
    data["comportamento_esperado"] = _fill_inferred_list(
        data.get("comportamento_esperado"), lambda: _infer_expected(data, ctx),
    )
    data["criterios"] = _fill_inferred_list(
        data.get("criterios"), lambda: _infer_acceptance(data, ctx),
    )
    return data


def required_pending(data: dict, meta: dict) -> list[str]:
    """Só [PENDENTE] real bloqueia o remoto; itens _Sugestão (revise):_ não bloqueiam."""
    blocked: list[str] = []
    if _blocking_pending(data["title"]) or not TITLE_RE.match(data["title"]):
        blocked.append("title")
    for key in ("solicitado_por", "objetivo", "contexto", "situacao_atual"):
        if _blocking_pending(data.get(key)):
            blocked.append(key)
    if data.get("novos_problemas") and _blocking_pending(data.get("novos_problemas")):
        blocked.append("novos_problemas")
    for key in ("problemas", "comportamento_esperado", "criterios", "observacoes"):
        if _blocking_pending(data.get(key)):
            blocked.append(key)
    for key in ("tipo", "prioridade", "size"):
        if not (meta.get(key) or "").strip() or _blocking_pending(meta.get(key)):
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
