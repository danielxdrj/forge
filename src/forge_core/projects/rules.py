"""Regras puras de validação de projeto e repositório (sem banco, sem rede)."""
from __future__ import annotations

import json
import re

from ..errors import ProjectRuleError
from ..logging import TOKEN_SHAPE, redact

PROVIDERS = ("github",)
SETTINGS_MAX_BYTES = 8 * 1024
SETTINGS_KEYS = ("branch_prefix", "issue_labels", "base_branch_override")
MAX_LABELS = 20

_OWNER = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")
_REPO = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
_BAD_REF_CHARS = re.compile(r"[\x00-\x20\x7f~^:?*\[\\]")
_PREFIX = re.compile(r"^[A-Za-z0-9._/-]{1,40}$")


def _text(value, label: str, max_len: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProjectRuleError(f"{label} é obrigatório")
    if len(value) > max_len or any(ord(c) < 32 for c in value):
        raise ProjectRuleError(f"{label} inválido (até {max_len} caracteres, sem controle)")
    return value.strip()


def validate_title(title) -> str:
    return _text(title, "título do projeto", 200)


def validate_description(description) -> str:
    if not isinstance(description, str) or len(description) > 2000:
        raise ProjectRuleError("descrição inválida (texto de até 2000 caracteres)")
    return description


def validate_name(name) -> str:
    return _text(name, "nome do repositório", 100)


def validate_provider(provider) -> str:
    if provider not in PROVIDERS:
        raise ProjectRuleError("invalid_provider: provider não suportado")
    return provider


def validate_owner(owner) -> str:
    if not isinstance(owner, str) or not _OWNER.match(owner):
        raise ProjectRuleError("owner inválido (1-39 letras, números ou hífen; sem hífen no início, fim ou duplo)")
    return owner


def validate_repo_name(repo_name) -> str:
    if (not isinstance(repo_name, str) or not _REPO.match(repo_name) or repo_name in (".", "..")
            or repo_name.lower().endswith(".git")):
        raise ProjectRuleError("repo_name inválido (letras, números, '.', '_' ou '-'; até 100; não termina em .git)")
    return repo_name


def validate_branch(branch, label: str = "branch") -> str:
    ok = (isinstance(branch, str) and 1 <= len(branch) <= 255 and not _BAD_REF_CHARS.search(branch)
          and ".." not in branch and "@{" not in branch and "//" not in branch and branch != "@"
          and not branch.startswith(("/", "-")) and not branch.endswith(("/", "."))
          and not any(p.startswith(".") or p.endswith(".lock") for p in branch.split("/")))
    if not ok:
        raise ProjectRuleError(f"invalid_branch: {label} não permitida")
    return branch


def _validate_prefix(value) -> str:
    if not isinstance(value, str) or not _PREFIX.match(value) or ".." in value or "//" in value \
            or value.startswith(("/", "-", ".")) or any(p.endswith(".lock") or p.startswith(".")
                                                         for p in value.split("/")):
        raise ProjectRuleError("branch_prefix inválido (até 40 caracteres de letras, números, '.', '_', '-', '/')")
    return value


def _validate_labels(value) -> list[str]:
    if not isinstance(value, list) or len(value) > MAX_LABELS:
        raise ProjectRuleError(f"issue_labels deve ser uma lista de até {MAX_LABELS} textos")
    out = []
    for label in value:
        if not isinstance(label, str) or not label.strip() or len(label) > 50 or "," in label \
                or any(ord(c) < 32 for c in label):
            raise ProjectRuleError("issue_labels: cada label tem 1-50 caracteres, sem vírgula nem controle")
        out.append(label.strip())
    if len({l.lower() for l in out}) != len(out):
        raise ProjectRuleError("issue_labels: labels repetidas")
    return out


def _reject_secret_like(values: list[str]) -> None:
    for v in values:
        if TOKEN_SHAPE.search(v) or redact(v) != v:
            raise ProjectRuleError("settings com cara de segredo recusadas: segredo não vai para o banco")


def validate_settings(settings) -> dict:
    """Só chaves conhecidas, até 8 KB, valores validados e sem cara de segredo. Devolve uma cópia normalizada."""
    if not isinstance(settings, dict):
        raise ProjectRuleError("settings deve ser um objeto")
    try:
        size = len(json.dumps(settings, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError):
        raise ProjectRuleError("settings deve conter apenas valores JSON") from None
    if size > SETTINGS_MAX_BYTES:
        raise ProjectRuleError(f"settings acima de {SETTINGS_MAX_BYTES} bytes")
    unknown = sorted(str(k) for k in settings if k not in SETTINGS_KEYS)
    if unknown:
        raise ProjectRuleError(f"unknown_settings_key: {len(unknown)} chave(s) de settings desconhecida(s)")
    out: dict = {}
    if "branch_prefix" in settings:
        out["branch_prefix"] = _validate_prefix(settings["branch_prefix"])
    if "issue_labels" in settings:
        out["issue_labels"] = _validate_labels(settings["issue_labels"])
    if "base_branch_override" in settings:
        out["base_branch_override"] = validate_branch(settings["base_branch_override"], "base_branch_override")
    strings = [v for v in out.values() if isinstance(v, str)] + [l for v in out.values() if isinstance(v, list) for l in v]
    _reject_secret_like(strings)
    return out
