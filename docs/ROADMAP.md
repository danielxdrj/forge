# Roadmap

Cada etapa produz algo pequeno e verificável. Uma etapa só começa quando a anterior exigida está aceita, as pendências que a bloqueiam foram respondidas e há autorização explícita.

A ordem abaixo é a adotada. Uma alternativa considerada foi ligar um conector real antes de qualquer chamada a LLM. Ela não foi adotada. Outra proposta antiga era anexar texto colado pelo operador. Ela foi substituída pela evidência de log local e permanece descrita na etapa 02.

O detalhe executável de cada etapa está em [.specs/IMPLEMENTATION_PLAN.md](../.specs/IMPLEMENTATION_PLAN.md). Este arquivo conserva o que entra, o que fica de fora e o que continua pendente, para que uma etapa futura não desapareça enquanto outra está em foco.

## Etapa 00 — Documentação inicial

Estado: concluída.

Entra: README, regras de agentes, produto, arquitetura, roadmap, guia de aprendizagem e a pasta `.specs/`.

Não entra: código, dependências, Compose e integrações.

## Etapa 01 — Criar e consultar uma investigação

Estado: concluída.

Objetivo: persistir uma investigação e recuperá-la pelo identificador.

Entra: Python, FastAPI na máquina local, PostgreSQL no serviço `postgres`, os campos identificador, título e data de criação, `POST /investigations`, `GET /investigations/{investigation_id}` e os testes desse fluxo. O Compose desta etapa sobe somente o `postgres`.

Não entra: alteração, exclusão e listagem de investigação, `frontend`, imagem do `backend`, LLM, conexões externas, cofre, upload, análise de log e publicação no GitHub.

Decisões desta etapa: identificador numérico gerado pelo PostgreSQL, título de até 200 caracteres, banco e usuário `forge`. A senha fica no ambiente. A API não usa `127.0.0.1:8000` como padrão; `FORGE_HOST` e `FORGE_PORT` vêm do ambiente.

Pronto quando: criar uma investigação e consultá-la devolve o mesmo registro depois de uma nova conexão com o PostgreSQL, e os testes cobrem título válido, título rejeitado e identificador ausente.

Especificação: [.specs/steps/01-create-and-read-investigation.md](../.specs/steps/01-create-and-read-investigation.md).

## Etapa 02 — Evidência de log local

Estado: bloqueada.

Objetivo: anexar à investigação a evidência vinda de um arquivo de log local.

Entra: a ligação entre a investigação e essa evidência.

Não entra: leitura de sistema externo e análise por LLM. Unir esta etapa à etapa 01 foi proposto e não foi aprovado.

Proposta anterior, substituída: texto colado pelo operador, com origem “manual” e o momento do anexo. A fonte atual é o arquivo de log local. A imutabilidade da evidência continua hipótese da arquitetura, sem aprovação.

Bloqueia até responder: como o arquivo chega à API e o que dele fica persistido.

Pronto quando: a investigação reaberta mostra a evidência que foi anexada, e um teste cobre isso.

Especificação: [.specs/steps/02-local-log-evidence.md](../.specs/steps/02-local-log-evidence.md).

## Etapa 03 — Análise por LLM sobre contexto controlado

Estado: bloqueada.

Objetivo: montar um contexto a partir da investigação e das evidências escolhidas, redigir segredos e guardar a resposta como análise.

Entra: uma porta de LLM, um adaptador para o provedor escolhido e a regra de que a resposta não dispara ação.

Não entra: o modelo escolhendo fontes, executando ferramentas ou recebendo credencial. A alternativa de um agente com ferramentas não foi adotada.

Bloqueia até responder: qual provedor, se o conteúdo pode sair da máquina, se o operador confirma o contexto antes do envio, e se a resposta tem estrutura fixa.

Pronto quando: uma investigação com evidência de log local gera uma análise relida depois, e um teste com provedor falso mostra que um texto com cara de segredo não segue no prompt.

Especificação: [.specs/steps/03-llm-analysis.md](../.specs/steps/03-llm-analysis.md).

## Etapa 04 — Conexão e cofre

Estado: bloqueada.

Objetivo: cadastrar uma conexão sem gravar o segredo no Git e recuperar esse segredo só pelo adaptador que precisar dele.

Entra: cadastro da conexão, referência ao segredo e um cofre local.

Não entra: a consulta real, se ela ainda depender de um protocolo não escolhido.

Bloqueia até responder: mecanismo do cofre. As opções registradas são arquivo de ambiente ignorado pelo Git, cofre do sistema operacional ou arquivo cifrado fora do repositório.

Pronto quando: o segredo de exemplo não aparece no diretório versionado nem num log da operação de cadastro, e um teste demonstra a separação entre configuração e segredo.

Especificação: [.specs/steps/04-connections-and-vault.md](../.specs/steps/04-connections-and-vault.md).

## Etapa 05 — Primeiro conector somente leitura

Estado: bloqueada.

Objetivo: provar a porta de leitura com uma fonte externa real e simples, gravando o resultado como evidência.

Entra: um único adaptador, sem métodos de escrita, e o uso explícito dessa leitura dentro de uma investigação.

Não entra: as outras integrações, correção de código, deploy e mudança de configuração.

Bloqueia até responder: qual é a primeira fonte externa. O arquivo de log local não é essa fonte. Candidatas já registradas, sem escolha: um diretório local tratado como fonte externa, ou o primeiro sistema do trabalho que já tenha acesso de leitura.

Pronto quando: uma consulta pedida pelo operador vira evidência na investigação, e o adaptador não oferece operação de alteração.

Especificação: [.specs/steps/05-first-read-connector.md](../.specs/steps/05-first-read-connector.md).

## Etapa 06 — Integrações de leitura seguintes

Estado: bloqueada.

Objetivo: adicionar outra fonte sem mudar o significado de investigação, evidência e análise. Cada sistema restante repete esta etapa.

Entra: só o adaptador novo e os testes dele.

Não entra: redesenho silencioso do núcleo. Se o núcleo precisar mudar para caber a fonte, a porta da etapa 05 ficou estreita e o ajuste é explícito.

A ordem não está definida. Pendências que permanecem até a fonte ser escolhida:

- Banco externo: qual produto e quais comandos são leitura. Não é o PostgreSQL do Forge.
- FTP/SFTP: quais diretórios podem ser listados e baixados, sem envio e sem remoção.
- GitHub, como leitura: quais repositórios e quais metadados entram, sem push e sem pull request.
- Portainer: quais ambientes e quais informações de container ou stack entram, sem reiniciar, alterar stack ou mudar configuração.

Pronto quando: a fonte nova e a fonte da etapa 05 alimentam evidência pelo mesmo caso de uso.

Especificação: [.specs/steps/06-additional-read-connectors.md](../.specs/steps/06-additional-read-connectors.md).

## Etapa 07 — Tarefas no GitHub

Estado: bloqueada. Direção aceita, sem data e sem ser a próxima implementação.

O Forge prepara uma descrição estruturada, apresenta a tarefa para revisão e só publica depois de aprovação explícita. A publicação não altera o código do sistema de trabalho.

O modelo de descrição indicado tem: solicitado por, objetivo, contexto, situação atual, escopo, comportamento esperado, critérios de aceite e observações.

Antes de qualquer código, ainda é preciso confirmar a conta responsável, como identificar a sprint vigente e as opções de tipo, prioridade, escopo, status e size. O fluxo atual cita size `3`, sem confirmação. Nenhum identificador interno da API está definido. A geração do texto também não está decidida.

Especificação: [.specs/steps/07-github-task-creation.md](../.specs/steps/07-github-task-creation.md).

## Etapa 08 — Hospedagem remota

Estado: bloqueada.

Só depois do uso local estar aceito. Não herda usuários, autenticação nem exposição dos segredos. Essas decisões serão um documento próprio quando a etapa for aberta.

Especificação: [.specs/steps/08-remote-hosting.md](../.specs/steps/08-remote-hosting.md).

## Como encerrar uma etapa

A etapa termina quando o critério de aceite é verdadeiro e os documentos afetados foram atualizados. A próxima etapa não começa no mesmo pedido. O modo de conduzir o trabalho está em [.specs/EXECUTION_PROTOCOL.md](../.specs/EXECUTION_PROTOCOL.md).
