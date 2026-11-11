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
- **D6. Bootstrap explícito e único.** `bootstrap --expect-github-id <ID>` cria o primeiro owner. O token OAuth é verificado pelo GitHub dentro do store, e a identidade tem de ser igual ao id esperado, antes de qualquer escrita. Uma linha singleton em `bootstrap_owner` faz a segunda tentativa, inclusive concorrente, falhar. Não há owner padrão nem backdoor. Quem roda o bootstrap com o id certo fica como dono: esse é o trust root, e o runbook manda rodar logo após a migração.
- **D7. Revogação checada a cada operação, na mesma seção da mutação.** Papel e sessão são verificados no banco **dentro** da transação serializada da escrita (`AuthStore.authorized`), sem cache. A checagem de fora da seção (`require`) é só recusa rápida. Linearização: uma revogação confirmada antes do lock da seção impede o efeito; uma escrita que confirma antes do lock da revogação permanece, e a revogação vale só para as operações seguintes. Revogação é linha nova em `role_revocations` ou `session_revocations`; nunca UPDATE ou DELETE. Último owner não pode ser revogado.
- **D8. Sem autoaprovação e aprovação ligada à versão.** `approval_grants` guarda a identidade do aprovador e a versão da tarefa aprovada. A concessão é recusada se o aprovador aparece em `task_changes` ou `task_history` da tarefa, em qualquer versão. A reserva confere, no momento do consumo, que a versão ainda é a aprovada e que o aprovador ainda tem o papel. Se a tarefa tiver autoria textual legada (`pessoa:*`), a aprovação falha fechado (`untrusted_authorship`).
- **D9. Texto e objetos do chamador não concedem autoridade.** Só `Principal`, criado por `resolve_session` (ou, no job, por `principal_for_dispatch` a partir de `dispatch_requests` e do papel vivo), passa nas operações humanas. Não há `SystemActor`. Toda mudança de status exige `editor`. `Orchestrator.dispatch` e `enqueue` exigem esse `Principal`. A API legada `SqlRepository.create_task` e `set_task_status` está desativada. A fila não guarda bearer: o job só aponta para o pedido persistido e revalida na execução.
- **D10. Token de sessão, sem arquivo.** Não há arquivo de sessão. Cada comando faz o device flow, mantém a sessão só em memória e revoga a sessão ao terminar. O banco guarda só o SHA-256 do token. Custo de UX: cada comando pede um novo login.
- **D11. Transporte.** O transporte real aceita só `https://github.com` e `https://api.github.com`, não segue redirecionamento e falha com códigos fixos. Os testes usam transporte falso; nenhum teste faz login real.
- **D12. Erros sanitizados.** Códigos fixos (`denied`, `expired`, `network`, `malformed_identity`, `invalid_session`, `forbidden`, `principal_missing`...). Nunca token, código de device, corpo de resposta ou traceback.

## Fronteira de segurança (o que isto NÃO protege)

- Quem controla o processo, o banco ou o sistema operacional pode contornar tudo isto: pode chamar as funções do store com código próprio, escrever no banco como o papel escritor ou importar módulos internos. A biblioteca não é cofre contra o próprio operador local; a fronteira real é o papel do banco, o sistema operacional e a separação de processos, a ser decidida.
- O papel escritor do Postgres não tem UPDATE nem DELETE nas tabelas novas (`postgres_roles.sql`, testado). Quem tem o papel dono do banco ainda pode alterar tabelas; isso é controle de administração, fora do Core.
- Agentes reais e privilegiados continuam bloqueados (ADR-011, ADR-013). Esta decisão não libera nenhum agente: a autenticação de aprovador não executa agente sozinha.

## Consequências

- Aprovações e edições antigas, gravadas como texto, não contam. Após a migração, nenhuma aprovação existe em `approval_grants` até alguém autenticado conceder uma.
- A API de serviço passa a exigir um `Principal`. Testes usam pessoas autenticadas por device flow falso (`tests/core/auth_helpers.py`), não bypass.
- Login real exige um OAuth App criado por uma pessoa com permissão (ver `docs/operacao/autenticacao-humana.md`). Até lá, a prova é de código e de transporte falso.

## Pendências (decisão do responsável)

1. Criar o OAuth App com Device Flow habilitado e informar o client id público (passo humano; o agente não cria nem faz login real).
2. Custo de UX do login por comando (D10): aceitar pedir login a cada invocação, ou abrir uma sessão de processo mais longa sem arquivo.
3. Expiração de sessão: a CLI continua sem prazo (`expires_at` NULL). O painel web (ADR-017) grava `expires_at` (padrão 8 h, configurável). Concessões de papel continuam sem prazo.
4. Identidade de serviço para despacho sem pessoa no enqueue: não foi criada. A fila reutiliza o `editor` humano do momento do enqueue, revalidado na execução.
5. Raiz de confiança do bootstrap: o operador informa o id GitHub esperado (`--expect-github-id`). Isso é o procedimento desta entrega; quem controla o OS ou o banco ainda pode gravar o singleton.
6. Fronteira OS/banco: quem controla o processo, o banco ou o sistema operacional contorna a biblioteca. Separação real de processos ou de papel de banco é decisão de implantação. Esta entrega não promete proteção contra esse controle.
