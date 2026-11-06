# ADR-009: Versionamento

- **Status:** Aprovado (06/11/2026)
- **Data:** 2026-11-06

## Decisão
O versionamento segue na série 0.9.x. As tags antigas são tratadas como legado. A release é manual, uma por PR, conforme [`docs/RELEASES.md`](../../RELEASES.md). Mudança `feat` incrementa o minor (a FRG-8 leva a v0.10.0).

## Consequências
Sem reinício em 0.1.0; histórico preservado. Quem opera cria tag e GitHub Release à mão.
