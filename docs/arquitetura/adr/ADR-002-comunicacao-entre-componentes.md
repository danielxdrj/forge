# ADR-002: Comunicação entre componentes

- **Status:** Proposto, aguardando aprovação do responsável
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
