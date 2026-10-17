# Produto

## Problema

Diagnosticar um problema de software exige juntar fatos de sistemas diferentes e raciocinar sobre eles. Fazer isso manualmente espalha o contexto entre terminais, painéis e anotações. Pedir ajuda a um LLM sem um registro do que foi consultado mistura evidência, segredo e palpite.

O Forge existe para manter esse trabalho na máquina local: conexões cadastradas, consultas a fontes autorizadas, investigações registradas e uma análise de LLM que permanece sugestão.

## O que já está definido

- A aplicação começa local.
- O operador cadastra conexões com sistemas técnicos.
- O operador consulta fontes autorizadas.
- O operador registra investigações.
- Um LLM auxilia o diagnóstico.
- A evolução prevista, sem ordem definida, inclui bancos de dados, FTP/SFTP, repositórios GitHub, Portainer e outras ferramentas.
- Os limites do [README](../README.md) valem como regras do produto, não como detalhes de implementação.

## Usuários

O uso aprovado é individual, nesta máquina. Não há papéis nem permissões. Mais de uma pessoa na mesma instalação fica fora do escopo atual.

## Funcionalidades previstas

Cada item abaixo é uma capacidade pedida. O detalhe de campos, telas e fluxo não foi especificado e não deve ser inventado na implementação.

### Cadastrar conexões

Registrar que existe um sistema técnico consultável: que tipo é, como alcançá-lo e onde está a credencial. O valor da credencial não faz parte do cadastro guardado no Git.

### Consultar fontes autorizadas

Ler dados de uma conexão já cadastrada, por uma ação explícita de quem opera. “Autorizada” ainda não tem definição fechada. A leitura deste documento, até haver resposta, é: uma fonte que o operador cadastrou e escolheu consultar.

### Registrar investigações

Guardar um caso de diagnóstico para retomar depois. O primeiro registro tem identificador, título e data de criação. Outros campos do dia a dia continuam em aberto.

### Análise por LLM

Enviar ao modelo um contexto montado a partir da investigação e receber um texto que ajude o diagnóstico. O texto fica associado à investigação. O Forge não transforma esse texto em alteração de código nem em ação no sistema consultado.

## Primeiro caso de uso

A primeira implementação cria uma investigação e permite consultá-la depois, nesta máquina. O registro tem identificador, título e data de criação.

Um log local pode ser anexado como texto. A API não lê o arquivo no disco. A análise por LLM continua fora.

## Tarefas no GitHub

Em uma etapa futura, o Forge poderá receber uma solicitação, preparar uma descrição estruturada e publicá-la no GitHub somente depois de revisão e aprovação explícita. Essa publicação não altera o código do sistema de trabalho.

Os campos do GitHub Projects, a conta responsável, a sprint vigente e as opções de tipo, prioridade, escopo e status ainda não estão confirmados. Nenhum identificador interno dessa API foi definido.

## Limites

O Forge não faz, nesta visão de produto:

- escrever em sistemas conectados, com uma exceção futura: publicar uma tarefa no GitHub depois de aprovação explícita;
- corrigir código automaticamente;
- alterar produção;
- executar a sugestão do LLM;
- enviar credenciais ao modelo, aos logs ou ao repositório;
- hospedar o serviço para outras pessoas, até essa etapa existir no roadmap e ser decidida de novo.

Também não está no escopo atual decidir SLA, multiempresa, aplicativo móvel, marketplace de conectores ou execução autônoma de ferramentas pelo modelo.

## Critérios de sucesso

Os critérios abaixo são uma proposta para saber se o produto cumpre o objetivo. Ainda não foram aceitos.

1. Dá para abrir uma investigação, fechá-la e encontrá-la de novo na mesma máquina.
2. Dá para cadastrar uma conexão sem que o segredo apareça no Git, nos logs ou no prompt.
3. Dá para consultar uma fonte autorizada em modo somente leitura e guardar o que foi obtido na investigação.
4. Dá para pedir uma análise ao LLM e reler essa análise depois, como sugestão, sem efeito nos sistemas conectados.
5. Uma integração nova entra por um adaptador novo, sem redefinir o que é uma investigação.

## Fora deste documento de propósito

Python, FastAPI, PostgreSQL e o fluxo da primeira API estão em [ARCHITECTURE.md](ARCHITECTURE.md). O plano operacional de todas as etapas está em [../.specs/IMPLEMENTATION_PLAN.md](../.specs/IMPLEMENTATION_PLAN.md).

## Perguntas de produto ainda abertas

1. Além de identificador, título e data de criação, quais dados uma investigação precisa ter no dia a dia?
2. Do arquivo de log local, o que fica guardado na investigação, e como esse arquivo chega até a API?
3. “Fonte autorizada” significa toda conexão cadastrada, ou cada investigação libera explicitamente o que pode ser consultado?
4. A resposta do LLM pode ser texto livre, ou precisa de uma estrutura fixa, como hipóteses e próximos passos?
5. Quem opera deve ver e confirmar o contexto antes de ele ser enviado ao modelo?
6. O conteúdo enviado ao LLM pode sair da máquina, ou o diagnóstico precisa permanecer local?
