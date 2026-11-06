# ADR-009: Versionamento

- **Status:** Aprovado (06/11/2026)
- **Data:** 2026-11-06

## Decisão
O versionamento segue na série 0.x (a partir de 0.9.1): feat = minor, fix/docs/chore/ci = patch. As tags antigas são tratadas como legado. A release é manual, uma por PR, conforme [`docs/RELEASES.md`](../../RELEASES.md).

## Consequências
Sem reinício em 0.1.0; histórico preservado. Quem opera cria tag e GitHub Release à mão.
