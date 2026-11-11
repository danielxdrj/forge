# Autenticação humana: operação e pré-requisitos

Decisões e fronteira: [ADR-014](../arquitetura/adr/ADR-014-autenticacao-humana.md).

## Pré-requisito humano (não automatizado)

1. Uma pessoa com permissão na conta ou organização do GitHub cria um **OAuth App** em *Settings > Developer settings > OAuth Apps*.
2. Nas configurações do app, **habilite o Device Flow**. Sem isso o GitHub responde `device_flow_disabled`.
3. Copie o **Client ID** (público). **Não há client secret para o device flow.**
4. Configure no ambiente de quem opera: `FORGE_GITHUB_CLIENT_ID=<CLIENT_ID_PUBLICO>`.

Sem esse passo o login real não funciona. Os testes do repositório não dependem dele.

## Bootstrap do primeiro dono (uma vez por banco)

O operador legítimo informa, antes de rodar, o **id numérico do GitHub** que será o dono. Esse id é a âncora de confiança e é conferido com a identidade verificada pelo GitHub:

```bash
python -m forge_core.auth.cli bootstrap --expect-github-id <ID_NUMERICO_DO_DONO>
```

- A CLI mostra uma URL e um código no terminal. A pessoa autoriza no navegador.
- Se a conta que autorizou não tiver o id esperado, a CLI recusa com `bootstrap_identity_mismatch` e não grava nada.
- Uma segunda execução, ou uma concorrente, falha com `bootstrap_already_done`.
- Não há owner padrão. Quem controla o banco ou a máquina de quem opera pode contornar isto (ver ADR-014).

## Operação do dia a dia

A sessão Forge fica no banco (`sessions.token_hash`, nunca o token GitHub) e, na CLI, num arquivo 0600 (`$XDG_CONFIG_HOME/forge/session` ou `~/.config/forge/session`; no container, volume `forge_cli_home`). O device flow só corre no primeiro login ou quando a sessão expirar ou for revogada. O prazo padrão é 7 dias (`FORGE_SESSION_TTL_SECONDS`), com renovação deslizante. Papel é relido do banco a cada comando: owner não implica editor.

```bash
python -m forge_core.auth.cli whoami                                   # identidade e papéis
python -m forge_core.auth.cli grant --github-id 1234 --role editor     # só owner
python -m forge_core.auth.cli revoke --grant-id 7                      # só owner; invalida as sessões dessa identidade
python -m forge_core.auth.cli logout                                   # invalida a sessão e apaga o arquivo local
```

- Só quem já entrou ao menos uma vez tem identidade no banco. `grant` recusa `identity_unknown` antes disso.
- O arquivo de sessão contém **somente** o token de sessão do Forge. Risco aceito no volume Docker próprio; nunca monte o keyring/`HOME` do host.
- `FORGE_SESSION_FILE` pode apontar para outro caminho nos testes. Não coloque o token GitHub nesse arquivo.

## Quando algo dá errado

| Código | Causa provável | Ação |
| --- | --- | --- |
| `device_flow_disabled` | Device Flow não habilitado no OAuth App | Habilitar no app (passo 2) |
| `incorrect_client_credentials` | `FORGE_GITHUB_CLIENT_ID` errado | Conferir o Client ID público |
| `expired` | Código expirou (15 min) | Rodar o comando de novo |
| `denied` | Autorização negada na página do GitHub | Refazer e autorizar |
| `network` | Sem acesso a github.com ou api.github.com | Verificar rede e proxy |
| `bootstrap_identity_mismatch` | Conta autorizada não é o id esperado | Usar a conta certa |
| `bootstrap_already_done` | Já existe dono | Nada a fazer |
| `invalid_session` | Sessão revogada ou de outro banco | Rodar o comando de novo |
| `forbidden` | Falta o papel exigido ou foi revogado | Pedir ao owner |
| `last_owner` | Tentativa de revogar o último owner | Conceder owner a outra pessoa antes |

## Testes

- `pytest tests/core` roda autenticação com transporte falso (device flow, bootstrap com identidade esperada e concorrente, papéis, sessão, CLI, ausência de token em disco, log e auditoria). Não há rede.
- O login real com o GitHub **não é testado no CI**. Depende do OAuth App acima e de uma pessoa autorizando no navegador.
