# ADR-008: Linguagem do Forge Core

- **Status:** Aprovado (06/11/2026)
- **Data:** 2026-11-06
- **Revisar quando:** surgir restrição de equipe ou de plataforma que Python não atenda

## Contexto
A linguagem estava em aberto na FRG-25. O responsável decidiu em 06/11/2026: "Vamos construir o Forge Core em Python".

## Decisão
Python (>= 3.11), com poucas dependências (o Core usa só a biblioteca padrão; `pytest` é dependência de desenvolvimento). O framework web da Forge API **continua em aberto**; a FRG-8 não escolhe nenhum e não cria o esqueleto da API.

## Consequências
Manutenção: baixa. Segurança: dependências mínimas reduzem a superfície. Custo: nulo. O código legado (backend/frontend) não é base do Core.
