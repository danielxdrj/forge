# Autenticação humana: operação e pré-requisitos

Decisões e fronteira: [ADR-014](../arquitetura/adr/ADR-014-autenticacao-humana.md).

## Pré-requisito humano (não automatizado)

1. Uma pessoa com permissão na conta ou organização do GitHub cria um **OAuth App** em *Settings > Developer settings > OAuth Apps*.
2. Nas configurações do app, **habilite o Device Flow**. Sem isso o GitHub responde `device_flow_disabled` e a CLI recusa com esse código.
3. Copie o **Client ID** (público). **Não há client secret a guardar para o device flow.**
4. Configure no ambiente de quem opera: `FORGE_GITHUB_CLIENT_ID=<CLIENT_ID_PUBLICO>`.

Sem esse passo, o login real não funciona. Os testes do repositório não dependem dele.

## Bootstrap (uma vez por banco)

Rode logo após a migração, antes de qualquer outra pessoa abrir o banco:

```bash
python -m forge_core.auth.cli bootstrap
```

A CLI mostra uma URL e um código no terminal. Confira a URL (`https://github.com/login/device`), digite o código e autorize. O primeiro dono é a conta que autorizou. Uma segunda execução falha com `bootstrap_already_done`.

## Operação do dia a dia

```bash
python -m forge_core.auth.cli login                         # abre sessão local
python -m forge_core.auth.cli whoami                        # identidade e papéis
python -m forge_core.auth.cli grant --github-id 1234 --role editor     # só owner
python -m forge_core.auth.cli revoke --grant-id 7                      # só owner
python -m forge_core.auth.cli logout                        # revoga a sessão atual
```

- Só a pessoa cadastrada no GitHub (id numérico) pode receber papel. Ela precisa ter feito `login` ao menos uma vez, para existir no banco.
- O arquivo de sessão (`FORGE_SESSION_FILE`, padrão `~/.config/forge/session.json`) tem permissão `0600`. Não o versione nem o copie.
- Erros aparecem como código fixo (`denied`, `expired`, `network`, `sessao_ausente`, `forbidden`...). Não há token nem código de device nos logs.

## Quando algo dá errado

| Código | Causa provável | Ação |
| --- | --- | --- |
| `device_flow_disabled` | Device Flow não habilitado no OAuth App | Habilitar no app (passo 2) |
| `client_id_rejected` | `FORGE_GITHUB_CLIENT_ID` errado | Conferir o Client ID público |
| `expired` | Código expirou (15 min) | Rodar o comando de novo |
| `denied` | Autorização negada na página do GitHub | Refazer e autorizar |
| `network` | Sem acesso a github.com ou api.github.com | Verificar rede e proxy |
| `sessao_ausente` / `invalid_session` | Sem sessão, sessão revogada ou de outro banco | `login` de novo |
| `forbidden` | Falta o papel exigido ou foi revogado | Pedir ao owner |
| `last_owner` | Tentativa de revogar o último owner | Conceder owner a outra pessoa antes |

## Testes

- `pytest tests/core` roda autenticação com transporte falso (device flow, bootstrap concorrente, papéis, sessão, CLI). Não há rede.
- O login real com o GitHub **não é testado no CI**. Ele depende do OAuth App acima e de uma pessoa autorizando no navegador.
