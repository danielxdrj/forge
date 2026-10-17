# Roadmap

Cada etapa produz algo pequeno e verificável. Uma etapa só começa quando a anterior está aceita e as pendências que a bloqueiam foram respondidas.

A ordem abaixo é uma proposta. A alternativa seria ligar um conector real antes de qualquer chamada a LLM. A proposta faz o contrário no meio do caminho: primeiro o registro da investigação e uma análise sobre texto colado pelo operador. Assim a fronteira com o modelo existe antes de existir credencial de sistema externo.

## Etapa 0 — Documentação inicial

Estado: em curso, neste conjunto de arquivos.

Entra: README, regras de agentes, produto, arquitetura e roadmap.

Não entra: código, dependências, repositório de configuração e integrações.

Pronto quando: os cinco documentos existem, separam fato de hipótese e listam as perguntas que bloqueiam a etapa 1.

## Etapa 1 — Investigação local

Objetivo: persistir e reabrir um caso de diagnóstico, sem rede, sem LLM e sem conexão externa.

Entra: o modelo mínimo de investigação que for decidido, um armazenamento local e uma forma simples de criar e reler.

Não entra: conectores, segredos, interface elaborada e análise automática.

Bloqueia até responder: linguagem, interface da primeira versão e quais campos mínimos a investigação tem.

Pronto quando: fechar o programa e abrir de novo ainda mostra a investigação criada, e um teste cobre esse comportamento.

## Etapa 2 — Evidência manual

Objetivo: anexar à investigação um texto que o operador colou, com origem “manual” e o momento do anexo.

Entra: evidência imutável depois de registrada e a ligação com a investigação.

Não entra: leitura de sistema externo.

Pronto quando: a investigação reaberta mostra a evidência que foi anexada, e um teste cobre isso.

## Etapa 3 — Análise por LLM sobre contexto controlado

Objetivo: montar um contexto a partir da investigação e das evidências escolhidas, redigir segredos e guardar a resposta como análise.

Entra: uma porta de LLM, um adaptador para o provedor escolhido e a regra de que a resposta não dispara ação.

Não entra: o modelo escolhendo fontes, executando ferramentas ou recebendo credencial.

Bloqueia até responder: qual provedor, se o conteúdo pode sair da máquina, e se o operador confirma o contexto antes do envio.

Pronto quando: uma investigação com evidência manual gera uma análise relida depois, e um teste com provedor falso mostra que um texto com cara de segredo não segue no prompt.

## Etapa 4 — Conexão e cofre

Objetivo: cadastrar uma conexão sem gravar o segredo no Git e recuperar esse segredo só pelo adaptador que precisar dele.

Entra: cadastro da conexão, referência ao segredo e um cofre local.

Não entra: a consulta real, se ela ainda depender de um protocolo não escolhido.

Bloqueia até responder: mecanismo do cofre.

Pronto quando: o segredo de exemplo não aparece no diretório versionado nem num log da operação de cadastro, e um teste demonstra a separação entre configuração e segredo.

## Etapa 5 — Primeiro conector somente leitura

Objetivo: provar a porta de leitura com uma fonte real e simples, gravando o resultado como evidência.

Entra: um único adaptador, sem métodos de escrita, e o uso explícito dessa leitura dentro de uma investigação.

Não entra: as outras integrações.

Bloqueia até responder: qual é a primeira fonte. Candidatas coerentes com o aprendizado: um diretório local, ou o primeiro sistema que já faça parte do trabalho e tenha acesso de leitura.

Pronto quando: uma consulta pedida pelo operador vira evidência na investigação, e o adaptador não oferece operação de alteração.

## Etapa 6 — Segunda integração

Objetivo: adicionar outra fonte sem mudar o significado de investigação, evidência e análise.

Entra: só o adaptador novo e os testes dele.

Não entra: redesenho do núcleo. Se o núcleo precisar mudar para caber a segunda fonte, a porta da etapa 5 ficou estreita demais e deve ser ajustada com esse aprendizado, de forma explícita.

A fonte desta etapa sai da lista futura, na ordem que for escolhida: banco de dados, FTP/SFTP, GitHub, Portainer ou outra ferramenta.

Pronto quando: as duas fontes alimentam evidência pelo mesmo caso de uso.

## Etapas seguintes — Uma integração por vez

Cada sistema restante repete a etapa 6. O detalhe do que é leitura naquele sistema só é escrito na etapa dele.

Pendências que permanecem até lá:

- Banco: qual produto e quais sessões ou comandos são leitura.
- FTP/SFTP: quais diretórios podem ser listados e baixados.
- GitHub: quais repositórios e quais metadados entram.
- Portainer: quais ambientes e quais informações de container ou stack entram.

Nenhuma dessas etapas inclui correção de código, deploy ou mudança de configuração.

## Etapa futura — Hospedagem remota

Só depois do uso local estar aceito. Não herda automaticamente usuários, autenticação nem exposição dos segredos. Essas decisões serão um documento próprio quando a etapa for aberta.

## Como encerrar uma etapa

A etapa termina quando o critério de “pronto quando” é verdadeiro e os documentos afetados foram atualizados. A próxima etapa não começa dentro do mesmo pedido, salvo pedido explícito para continuar.
