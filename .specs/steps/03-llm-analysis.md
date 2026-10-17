# 03 — Análise por LLM

Estado: bloqueada.

## Objetivo e contexto

Montar um contexto a partir da investigação e das evidências escolhidas, mascarar segredos e guardar a resposta como análise. A resposta não dispara ação.

## Problema que resolve

O diagnóstico precisa de uma sugestão ligada ao que foi consultado, sem misturar esse texto com credencial e sem executá-lo.

## Pré-requisitos

- Etapa 02 concluída, porque a análise usa evidência de log local.
- Provedor escolhido.
- Decisão sobre o conteúdo sair da máquina.
- Decisão sobre confirmar o contexto antes do envio.

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

Enviar o log ao provedor pode tirar dado da máquina. Essa escolha está em aberto. Credencial não entra no prompt.

## Decisões pendentes

1. Qual provedor.
2. Se o conteúdo pode sair da máquina.
3. Se quem opera confirma o contexto antes do envio. A arquitetura recomenda que sim. O produto ainda pergunta.
4. Se a resposta é texto livre ou uma estrutura fixa, como hipóteses e próximos passos.

## Aprovação

Depende da etapa 02 concluída e de autorização explícita. Não é a próxima implementação.
