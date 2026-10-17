# 03 — Análise por LLM

Estado: bloqueada.

## Objetivo e contexto

Montar um contexto a partir da investigação e das evidências escolhidas, mascarar segredos e guardar a resposta como análise. A resposta não dispara ação.

## Problema que resolve

O diagnóstico precisa de uma sugestão ligada ao que foi consultado, sem misturar esse texto com credencial e sem executá-lo.

## Pré-requisitos

- Etapa 02 concluída, porque a análise usa evidência de log local.
- Provedor escolhido. Ainda em aberto.
- O texto enviado ao modelo permanece na máquina. Já decidido.
- Quem opera confirma o contexto antes do envio. Já decidido.

## Escopo incluído

- Uma porta de LLM.
- Um adaptador para o provedor escolhido.
- A regra de que a resposta fica associada à investigação e não é executada.
- Redação de segredos antes do prompt.

## Escopo excluído

O modelo escolher fontes, executar ferramentas ou receber credencial. Agente com ferramentas foi alternativa considerada e não é a hipótese desta etapa. A hipótese é uma chamada explícita, com contexto escolhido.

## Arquivos

Ainda não conhecidos. Não criar a porta antes desta etapa.

## Critérios de aceite

- Uma investigação com evidência de log local gera uma análise que pode ser relida.
- Um teste com provedor falso mostra que um texto com cara de segredo não segue no prompt.
- Nenhuma ação é executada a partir da resposta.

## Testes esperados

O teste usa um provedor falso, não um serviço real. O prompt observado pelo teste não contém o segredo inserido na evidência.

## Documentação a atualizar

`docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `docs/LEARNING_GUIDE.md` e esta especificação.

## Riscos

O texto enviado ao modelo fica na máquina. Credencial não entra no prompt.

## Decisões

Respondidas para esta etapa:

- O texto enviado ao modelo fica na máquina. Consultar Portainer, FTP ou um banco é leitura de uma etapa posterior. Essa leitura não faz parte da chamada ao modelo, e o modelo não escolhe a fonte nem executa ferramenta.
- Quem opera vê e confirma o contexto antes do envio.
- A resposta tem estrutura fixa e inclui a sugestão de correção. Nesta etapa, essa sugestão é texto guardado na investigação.

Fluxo aprovado para uma etapa posterior, ainda sem abertura e fora do código desta etapa:

1. O Forge investiga e devolve a sugestão de alteração.
2. Se quem opera aprovar, o Cursor altera o código ou devolve o SQL para alterar o banco. O SQL volta como texto e não é executado.
3. Se a alteração for de código, uma segunda aprovação vem antes de criar o commit e enviar a branch.

Ainda pendente:

1. Qual programa, nesta máquina, escreve a análise. “Provedor” é esse programa, não o Portainer, o FTP nem o banco.

## Aprovação

Depende da etapa 02 concluída e de autorização explícita. Não é a próxima implementação.
