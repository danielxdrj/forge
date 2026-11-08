# Cursor CLI: risco residual (não é impossível; não há garantia total)

**Atualizado em 08/11/2026.** O bloqueio anterior (“impossível isolar”) foi **substituído** pela decisão do responsável: aceitar o risco residual e usar a Cursor CLI com **pasta temporária vazia** + deny documentado (ADR-015).

A documentação oficial continua dizendo que `--print` tem tools (write e shell). `--mode ask` ainda pode ler código. Não há modo 0% tools. O isolamento desta entrega **não** é sandbox forte.

Operação: [rascunho-issue.md](rascunho-issue.md). Decisão: [ADR-015](../arquitetura/adr/ADR-015-cursor-cli-rascunho.md).
