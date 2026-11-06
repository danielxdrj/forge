# Forge Core

Núcleo do Forge em Python (ADR-001 monólito modular, ADR-005 configuração fora do Core, ADR-008 linguagem). Sem integrações externas.

## Estrutura
```
pyproject.toml
.env.example
src/forge_core/
  app.py          inicialização (start/main)
  config.py       carga e validação de FORGE_* (falha com mensagem clara)
  logging.py      log JSON com redação de segredos
  errors.py       ForgeError, ConfigError
  extension/      interfaces: Integration, Agent, TaskQueue (implementações: FRG-40 e outras)
tests/core/test_core.py
```

## Variáveis de ambiente
| Nome | Obrigatória | Finalidade |
| --- | --- | --- |
| `FORGE_CONFIG_DIR` | sim | diretório da configuração da empresa (fora do Core) |
| `FORGE_LOG_LEVEL` | não (INFO) | nível de log |
| `FORGE_AUTOMATION_ENABLED` | não (true) | chave global de desligamento das automações |

Nunca coloque segredos aqui; use cofre institucional.

## Executar e testar
```
pip install -e ".[dev]"
FORGE_CONFIG_DIR=<CAMINHO> python -m forge_core.app
pytest
```

## Troubleshooting
Saída `forge-core: Configuração inválida:` lista cada variável faltante ou inválida; corrija e reinicie.

## Limitações e próximos passos
Sem Forge API (framework em aberto), fila (FRG-40), persistência (FRG-42), orquestrador (FRG-24). Formato único de configuração: variáveis de ambiente; arquivos da empresa serão lidos de `FORGE_CONFIG_DIR` em etapa futura.
