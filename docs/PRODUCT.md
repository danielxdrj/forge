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

Não há personas nem permissões definidas.

Hipótese de trabalho, ainda não confirmada: o primeiro usuário é uma pessoa só, operando o Forge na própria máquina, investigando sistemas aos quais ela já tem acesso de leitura.

Pendente: se existirão outros usuários, papéis diferentes ou uso compartilhado da mesma instalação.

## Funcionalidades previstas

Cada item abaixo é uma capacidade pedida. O detalhe de campos, telas e fluxo não foi especificado e não deve ser inventado na implementação.

### Cadastrar conexões

Registrar que existe um sistema técnico consultável: que tipo é, como alcançá-lo e onde está a credencial. O valor da credencial não faz parte do cadastro guardado no Git.

### Consultar fontes autorizadas

Ler dados de uma conexão já cadastrada, por uma ação explícita de quem opera. “Autorizada” ainda não tem definição fechada. A leitura deste documento, até haver resposta, é: uma fonte que o operador cadastrou e escolheu consultar.

### Registrar investigações

Guardar um caso de diagnóstico para retomar depois. O que entra no registro mínimo ainda está em aberto. Uma proposta, não um requisito: título, descrição do problema, momento de abertura, evidências anexadas e análises recebidas.

### Análise por LLM

Enviar ao modelo um contexto montado a partir da investigação e receber um texto que ajude o diagnóstico. O texto fica associado à investigação. O Forge não transforma esse texto em alteração de código nem em ação no sistema consultado.

## Limites

O Forge não faz, nesta visão de produto:

- escrever, apagar ou modificar dados nos sistemas conectados;
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

Linguagem, interface, armazenamento local, provedor de LLM, formato exato da investigação e a ordem das integrações reais estão em [ARCHITECTURE.md](ARCHITECTURE.md) e [ROADMAP.md](ROADMAP.md) como hipóteses ou pendências.

## Perguntas de produto ainda abertas

1. O primeiro uso é individual, nesta máquina, ou já precisa considerar mais de uma pessoa?
2. Qual situação real deve servir de exemplo da primeira investigação? Sem um caso, é fácil desenhar campos que ninguém usa.
3. Quais dados mínimos uma investigação precisa ter no dia a dia?
4. “Fonte autorizada” significa toda conexão cadastrada, ou cada investigação libera explicitamente o que pode ser consultado?
5. A resposta do LLM pode ser texto livre, ou precisa de uma estrutura fixa, como hipóteses e próximos passos?
6. Quem opera deve ver e confirmar o contexto antes de ele ser enviado ao modelo?
7. O conteúdo enviado ao LLM pode sair da máquina, ou o diagnóstico precisa permanecer local?
