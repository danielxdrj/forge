"""Pontuação determinística do radar. Função pura: mesmos itens e mesma data, mesmo resultado.

A IA não decide a ordem. Ela só resume (ver `service.py`). Cada ponto vem com o motivo
em texto, para a pessoa conferir por que a issue subiu.

Critérios (pontos):
- prioridade do board: Urgente 40, Alta 25, Média 10, Baixa 0, sem prioridade 5;
- segurança (tipo "Security Project" ou label com segurança/security): +20;
- status Reaberto: +15; Aguardando validação parado há 3 dias ou mais: +8;
- parada (sem atividade na issue nem no item do board) há `stale_days` dias ou mais:
  +10, mais 1 por dia além do limite (teto +20);
- sprint encerrada sem a issue concluída: +15;
- data alvo vencida: +20; data alvo nos próximos 3 dias: +10;
- Urgente ou Alta sem responsável: +5;
- aberta há mais de 60 dias: +5.

"Concluir agora" exige, além de pontuação mínima, um sinal de urgência: prioridade Urgente
ou Alta, segurança, prazo ou sprint vencidos, ou issue reaberta. Ficar parada sozinha não
basta: isso vai para a lista "Paradas".
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from ..draft.github_gh import DONE_STATUS_ALIASES, fold_option_name

PRIORITY_POINTS = {"urgente": 40, "alta": 25, "media": 10, "baixa": 0}
NO_PRIORITY_POINTS = 5
NOW_THRESHOLD = 35
NOW_LIMIT = 5
STALE_LIMIT = 10
INVESTIGATE_LIMIT = 8
TRIAGE_DAYS = 7
OLD_DAYS = 60
SECURITY_MARKERS = ("security", "seguranca")


def _parse_ts(raw: str) -> datetime | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _parse_day(raw: str) -> date | None:
    text = (raw or "").strip()[:10]
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _fmt_day(day: date) -> str:
    return day.strftime("%d/%m")


def _days(n: int) -> str:
    return "1 dia" if n == 1 else f"{n} dias"


def _is_security(item: dict) -> bool:
    tipo = fold_option_name(item.get("tipo") or "")
    if any(m in tipo for m in SECURITY_MARKERS):
        return True
    return any(any(m in fold_option_name(lbl) for m in SECURITY_MARKERS) for lbl in item.get("labels") or [])


def _sprint_end(sprint: dict) -> date | None:
    start = _parse_day(str((sprint or {}).get("start") or ""))
    try:
        duration = int((sprint or {}).get("duration"))
    except (TypeError, ValueError):
        return None
    if start is None or duration <= 0:
        return None
    return start + timedelta(days=duration)


def score_item(item: dict, *, now: datetime, stale_days: int, allowed_repos: set[str]) -> dict | None:
    """Pontua um item aberto. Devolve None para itens concluídos."""
    status = item.get("status") or ""
    folded_status = fold_option_name(status)
    if folded_status in DONE_STATUS_ALIASES:
        return None
    today = now.date()
    activity = [t for t in (_parse_ts(item.get("issue_updated_at")), _parse_ts(item.get("item_updated_at"))) if t]
    last_activity = max(activity) if activity else None
    idle_days = max(0, (now - last_activity).days) if last_activity else 0
    created = _parse_ts(item.get("created_at"))
    age_days = max(0, (now - created).days) if created else 0
    status_changed = _parse_ts(item.get("status_changed_at"))
    in_status_days = max(0, (now - status_changed).days) if status_changed else idle_days

    score = 0
    urgent = False
    reasons: list[str] = []
    prioridade = item.get("prioridade") or ""
    folded_prio = fold_option_name(prioridade)
    if folded_prio in PRIORITY_POINTS:
        score += PRIORITY_POINTS[folded_prio]
        if PRIORITY_POINTS[folded_prio] >= PRIORITY_POINTS["alta"]:
            reasons.append(f"Prioridade {prioridade}")
            urgent = True
    else:
        score += NO_PRIORITY_POINTS
    if _is_security(item):
        score += 20
        urgent = True
        reasons.append("Segurança")
    if folded_status == "reaberto":
        score += 15
        urgent = True
        reasons.append("Reaberta")
    elif folded_status == "aguardando validacao" and in_status_days >= 3:
        score += 8
        reasons.append(f"Aguardando validação há {_days(in_status_days)}")
    if idle_days >= stale_days:
        score += 10 + min(20, idle_days - stale_days)
        reasons.append(f"Parada há {_days(idle_days)}")
    sprint = item.get("sprint") or {}
    end = _sprint_end(sprint)
    if end is not None and end <= today:
        score += 15
        urgent = True
        reasons.append(f"{sprint.get('title') or 'Sprint'} encerrada em {_fmt_day(end - timedelta(days=1))}")
    target = _parse_day(item.get("target_date") or "")
    if target is not None:
        if target < today:
            score += 20
            urgent = True
            reasons.append(f"Prazo vencido em {_fmt_day(target)}")
        elif (target - today).days <= 3:
            score += 10
            reasons.append(f"Prazo em {_fmt_day(target)}")
    assignees = item.get("assignees") or []
    if not assignees and folded_prio in ("urgente", "alta"):
        score += 5
        reasons.append("Sem responsável")
    if age_days > OLD_DAYS:
        score += 5
        reasons.append(f"Aberta há {_days(age_days)}")

    repo = item.get("repo") or ""
    number = int(item.get("number") or 0)
    return {
        "key": f"{repo}#{number}",
        "repo": repo,
        "number": number,
        "title": item.get("title") or "",
        "url": item.get("url") or "",
        "status": status,
        "prioridade": prioridade,
        "tipo": item.get("tipo") or "",
        "size": item.get("size") or "",
        "escopo": item.get("escopo") or "",
        "sprint": sprint.get("title") or "",
        "assignees": list(assignees),
        "idle_days": idle_days,
        "age_days": age_days,
        "in_status_days": in_status_days,
        "score": score,
        "urgent": urgent,
        "reasons": reasons,
        "investigable": repo.lower() in allowed_repos,
    }


def _investigate_reasons(entry: dict) -> list[str]:
    out = []
    status = fold_option_name(entry["status"])
    if status == "triagem" and entry["in_status_days"] >= TRIAGE_DAYS:
        out.append(f"Na triagem há {_days(entry['in_status_days'])}")
    if status == "reaberto":
        out.append("Reaberta: a correção anterior não resolveu")
    if not entry["prioridade"]:
        out.append("Sem prioridade definida")
    if not entry["size"]:
        out.append("Sem estimativa (size)")
    return out


def analyze(items: list[dict], *, now: datetime, stale_days: int, allowed_repos: set[str]) -> dict:
    """Separa os itens em três listas e calcula os números do topo do relatório."""
    allowed = {r.lower() for r in allowed_repos}
    entries = []
    for item in items:
        scored = score_item(item, now=now, stale_days=stale_days, allowed_repos=allowed)
        if scored is not None:
            entries.append(scored)
    by_score = sorted(entries, key=lambda e: (-e["score"], -e["idle_days"], e["key"]))
    now_list = [e for e in by_score if e["urgent"] and e["score"] >= NOW_THRESHOLD][:NOW_LIMIT]
    now_keys = {e["key"] for e in now_list}
    stale = sorted(
        (e for e in entries if e["idle_days"] >= stale_days),
        key=lambda e: (-e["idle_days"], -e["score"], e["key"]),
    )[:STALE_LIMIT]
    investigate = []
    for entry in by_score:
        if entry["key"] in now_keys:
            continue
        why = _investigate_reasons(entry)
        if why:
            investigate.append({**entry, "investigate_reasons": why})
        if len(investigate) >= INVESTIGATE_LIMIT:
            break
    stats = {
        "open": len(entries),
        "now": len(now_list),
        "stale": sum(1 for e in entries if e["idle_days"] >= stale_days),
        "urgent": sum(1 for e in entries if fold_option_name(e["prioridade"]) == "urgente"),
        "unassigned": sum(1 for e in entries if not e["assignees"]),
    }
    return {"now": now_list, "stale": stale, "investigate": investigate, "stats": stats}
