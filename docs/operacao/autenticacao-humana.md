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

Não há arquivo de sessão. Cada comando faz um login próprio (device flow), executa e revoga a sessão ao terminar. **Custo de UX: cada comando pede novo login no navegador.**

```bash
python -m forge_core.auth.cli whoami                                   # identidade e papéis
python -m forge_core.auth.cli grant --github-id 1234 --role editor     # só owner
python -m forge_core.auth.cli revoke --grant-id 7                      # só owner
```

- Só quem já entrou ao menos uma vez tem identidade no banco. `grant` recusa `identity_unknown` antes disso.
- Nenhum token, nenhum código de device e nenhum arquivo de sessão são gravados em disco. Não há `FORGE_SESSION_FILE`.

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
