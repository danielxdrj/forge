# ADR-014: autenticação humana e autorização por operação

- **Status:** aceito (implementado no PR da autenticação humana; supera a regra textual `pessoa:*` do ADR-011).
- **Data:** 2026-11-08.
- **Relaciona:** ADR-010 (modelo de tarefa), ADR-011 (aprovação e agentes), ADR-013 (isolamento).

## Contexto

Até aqui o ator era texto livre. `TaskService`, `ProjectService` e a aprovação gravavam o que o chamador informava, e um prefixo `pessoa:` era a única barreira. Isso é declaratório: quem chama escolhe a autoria, e uma linha forjada no `audit_log` bastava para parecer aprovação.

## Decisões

- **D1. Login externo, só linha de comando local.** Provedor GitHub, OAuth device flow (RFC 8628). Nenhum servidor, interface web, IdP adicional, serviço ou custo novo. O código de verificação aparece só no terminal de quem executa.
- **D2. Identidade = id numérico do GitHub** (`gh:<id>`). O login é só exibição e fica como snapshot na sessão. Renomear ou trocar de token não cria outra identidade.
- **D3. Escopo mínimo.** O device flow é feito sem escopos (`scope=""`). Com token sem escopo, `GET /user` devolve o id e o login públicos, e isso é tudo que o Forge lê. Nenhum acesso a repositório ou organização.
- **D4. Client id é público e configurado** em `FORGE_GITHUB_CLIENT_ID`. O device flow não usa `client_secret` (documentação oficial). Não há segredo do OAuth App no projeto.
- **D5. Papéis:** `owner`, `editor` (cria e edita tarefas e projetos, ajusta status), `approver` (concede aprovação). Uma pessoa pode ter mais de um papel, **exceto** que nenhuma pessoa aprova a própria edição (D8). Owner concede e revoga papéis; não há expiração de concessão, só revogação.
- **D6. Bootstrap explícito e único.** `bootstrap` cria o primeiro owner. Uma linha singleton em `bootstrap_owner` com PK fixa faz a segunda tentativa, inclusive concorrente, falhar. Não há owner padrão nem backdoor. Quem roda o `bootstrap` primeiro em banco novo fica como dono: esse é o trust root, e o runbook manda rodar logo após a migração.
- **D7. Revogação checada a cada operação.** Papel e sessão são verificados no banco em cada chamada de escrita, sem cache. Revogação é linha nova em `role_revocations` ou `session_revocations`; nunca UPDATE ou DELETE. Último owner não pode ser revogado.
- **D8. Sem autoaprovação e aprovação ligada à versão.** `approval_grants` guarda a identidade do aprovador e a versão da tarefa aprovada. A concessão é recusada se o aprovador aparece em `task_changes` ou `task_history` da tarefa, em qualquer versão. A reserva confere, no momento do consumo, que a versão ainda é a aprovada e que o aprovador ainda tem o papel. Se a tarefa tiver autoria textual legada (`pessoa:*`), a aprovação falha fechado (`untrusted_authorship`).
- **D9. Texto e objetos do chamador não concedem autoridade.** Só `Principal` (criado por `resolve_session`, a partir de um token que confere no banco) passa nas operações humanas. `SystemActor` existe só para a transição de status do orquestrador; ele não edita nem aprova. A API legada `SqlRepository.create_task` e `set_task_status` recusa autoria humana.
- **D10. Token de sessão.** O servidor guarda só o SHA-256 do token. O cliente guarda o token em arquivo `0600` (`FORGE_SESSION_FILE` ou `~/.config/forge/session.json`). Isso é credencial local, necessária sem servidor; é o ponto que o responsável deve conferir (ver pendências).
- **D11. Transporte.** O transporte real aceita só `https://github.com` e `https://api.github.com`, não segue redirecionamento e falha com códigos fixos. Os testes usam transporte falso; nenhum teste faz login real.
- **D12. Erros sanitizados.** Códigos fixos (`denied`, `expired`, `network`, `malformed_identity`, `invalid_session`, `forbidden`, `principal_missing`...). Nunca token, código de device, corpo de resposta ou traceback.

## Fronteira de segurança (o que isto NÃO protege)

- Quem controla o processo, o banco ou o sistema operacional pode contornar tudo isto: pode importar `SystemActor`, escrever no banco como o papel escritor ou ler o arquivo de sessão. A biblioteca não é cofre contra o próprio operador local.
- O papel escritor do Postgres não tem UPDATE nem DELETE nas tabelas novas (`postgres_roles.sql`, testado). Quem tem o papel dono do banco ainda pode alterar tabelas; isso é controle de administração, fora do Core.
- Agentes reais e privilegiados continuam bloqueados (ADR-011, ADR-013). Esta decisão não libera nenhum agente: a autenticação de aprovador não executa agente sozinha.

## Consequências

- Aprovações e edições antigas, gravadas como texto, não contam. Após a migração, nenhuma aprovação existe em `approval_grants` até alguém autenticado conceder uma.
- A API de serviço passa a exigir um `Principal`. Testes usam pessoas autenticadas por device flow falso (`tests/core/auth_helpers.py`), não bypass.
- Login real exige um OAuth App criado por uma pessoa com permissão (ver `docs/operacao/autenticacao-humana.md`). Até lá, a prova é de código e de transporte falso.

## Pendências (decisão do responsável)

1. Criar o OAuth App com Device Flow habilitado e informar o client id público (passo humano; o agente não cria nem faz login real).
2. Confirmar D10: credencial de sessão no arquivo local do usuário é aceitável.
3. Expiração de sessão: hoje não há prazo. Se for exigido, é nova decisão.
4. Versão da tarefa aprovada: a aprovação vale para a versão atual; não há janela de tempo.
