# ADR-002: Comunicação entre componentes

- **Status:** Aprovado com ajuste (06/11/2026)
- **Data:** 2026-11-06
- **Revisar quando:** surgir tarefa longa/assíncrona que não caiba no processo ou integração por evento externo

## Contexto
Componentes ficam no mesmo processo (ADR-001). Queue / Event Bus está previsto no planejamento.

## Alternativas
| Opção | Prós | Contras |
| --- | --- | --- |
| Chamada direta entre módulos | Simples, fácil de testar e rastrear | Acoplamento temporal; tarefa longa ocupa o processo |
| Fila/eventos desde já | Desacopla, retentativa, assíncrono | Infraestrutura extra, ordem e idempotência a tratar, mais difícil de entender |
| Direta agora, fila atrás de uma interface | Simplicidade hoje, caminho de evolução | Exige manter a interface limpa |

## Recomendação
Chamada direta, com o estado da tarefa persistido (permite retomar). Queue / Event Bus fica como **futuro**, atrás de uma porta, sem remover do planejamento.

## Consequências
Manutenção: baixa. Segurança: sem broker a proteger. Custo: nenhum extra agora.

## Ajuste aprovado
A fila não fica para depois: a FRG-40 e a Fase 1 exigem fila já nesta fundação. Mantém-se a interface (porta) e implementa-se uma fila simples, em processo ou no banco, sem sistema de fila pesado. A chamada direta entre módulos do Core continua válida.

## Decisão FRG-40 (06/11/2026)
Fila de jobs **persistida no banco atual** (PostgreSQL com SQLite nos testes), atrás da porta `JobQueue` (substitui a antiga `TaskQueue`, que não tinha implementação nem uso). Alternativas descartadas: fila em processo (perde jobs no reinício, não serve a vários processos) e broker dedicado Redis/RabbitMQ (serviço novo a operar e proteger, sem necessidade comprovada). Se o volume pedir, o broker entra atrás da mesma porta.
- Entrega pelo menos uma vez; handlers idempotentes. Retry com backoff exponencial (30 s dobrando, teto 1 h), 5 tentativas, lease de 5 min, todos por parâmetro. Falha definitiva fica em `failed` até `requeue()` manual.
- Sem duplicidade: Postgres usa `FOR UPDATE SKIP LOCKED`; SQLite usa `BEGIN IMMEDIATE`. Idempotência de enfileiramento por `idempotency_key` única.
- Com `FORGE_AUTOMATION_ENABLED=false`, o consumo (`claim`) é bloqueado e o `enqueue` continua permitido (ADR-006).
