# Arquitetura

Este documento é uma proposta. O repositório ainda não tem módulos, processos nem dependências. O que está marcado como **definido** veio dos princípios do projeto. O que está marcado como **hipótese** pode mudar antes da implementação. O que está marcado como **pendente** bloqueia a etapa que depender dele.

## Definido

- O sistema começa local.
- Cada integração externa nasce somente leitura e não ganha escrita por padrão.
- Não existe componente que aplique correção ou altere produção.
- Segredos ficam fora do código, dos logs, dos prompts e do Git.
- Incluir uma integração nova não deve exigir reescrever o núcleo.
- A estrutura deve permanecer simples de testar e de manter.
- A primeira implementação usa Python, FastAPI e SQLite.
- A interface dessa implementação é uma API local, com a documentação automática do FastAPI.
- O uso é individual, nesta máquina.
- O primeiro caso de uso parte de um arquivo de log local.
- Essa implementação não conecta sistemas externos e não chama LLM.

## Conceitos

Uma **porta** é um contrato pequeno: o que o restante do sistema pode pedir, sem dizer qual produto externo responde. Um **adaptador** é a implementação desse contrato para um sistema concreto.

Exemplo de porta, ainda sem código: “dado um identificador de conexão e um pedido de leitura, devolva bytes ou texto”. GitHub, SFTP ou um banco seriam adaptadores diferentes da mesma porta. A investigação não sabe qual deles foi usado.

Uma **investigação** é o registro do caso. Uma **evidência** é um fato anexado a esse caso, com origem e momento. Uma **análise** é o texto devolvido pelo LLM sobre um contexto escolhido. Uma **conexão** é o cadastro de um sistema consultável. O **segredo** é a credencial, guardada fora desse cadastro.

**Redação** é o passo que mascarar segredos antes de logar ou de montar um prompt.

## Forma proposta

Hipótese: um monólito modular. Um único programa local, dividido por responsabilidade. Microserviços dariam isolamento, e também processo, rede e operação a mais, cedo demais para um protótipo de uma máquina.

```mermaid
flowchart LR
  ui["API local FastAPI"] --> app["Casos de uso"]
  app --> inv["Porta: investigações"]
  app --> conn["Porta: conector de leitura"]
  app --> llm["Porta: LLM"]
  app --> secrets["Porta: cofre de segredos"]
  inv --> store["Adaptador de armazenamento"]
  conn --> adapters["Adaptadores somente leitura"]
  llm --> provider["Adaptador do provedor"]
  secrets --> vault["Adaptador do cofre"]
```

Os casos de uso são o centro. Eles criam e retomam investigações, pedem leituras e solicitam análises. A hipótese é que dependam das portas. SQLite é o adaptador de armazenamento aprovado para o início. GitHub e o fornecedor de LLM continuam fora desta etapa.

A API fica na borda. Uma página local, mais adiante, não deve mudar o que é uma investigação.

Os adaptadores ficam na outra borda. Um conector novo é um adaptador novo. Ele não recebe permissão de escrita porque a porta não tem essa operação.

## O que cada borda pode ver

Hipótese de fronteira, importante para segurança:

- O cadastro da conexão guarda nome, tipo, destino e a referência do segredo. Não guarda o segredo.
- Só o adaptador que vai consultar a fonte pede o segredo ao cofre, no momento da leitura.
- O LLM recebe texto já redigido. Não recebe a conexão, o cliente do sistema externo nem a credencial.
- A análise volta como dado da investigação. Nenhum módulo a interpreta como comando.

Hipótese adicional: a evidência guardada é uma cópia do que foi lido, com data e identificação da conexão. A análise posterior usa essa cópia. Uma consulta nova só acontece se o operador pedir. Isso torna a investigação repetível e limita o que segue para o modelo.

## Alternativas consideradas

| Tema | Alternativa | Por que não é a hipótese atual |
| --- | --- | --- |
| Estrutura | Microserviços, um por integração | Mais peças para operar do que o problema local pede. |
| Estrutura | Módulos sem porta comum | Cada integração passaria a ser um caso especial dentro da investigação. |
| Primeiro LLM | Agente com ferramentas, livre para consultar fontes | Aumenta a chance de leitura inesperada e de vazamento para o prompt. A hipótese é uma chamada explícita, com contexto escolhido. |
| Evidência | Ler a fonte de novo a cada análise | O contexto muda entre uma análise e outra, e fica mais difícil saber o que o modelo viu. |

A porta comum é a hipótese recomendada porque atende ao princípio de adicionar integrações sem reescrever o sistema.

## Decisões da primeira implementação

Definido:

- Python é a linguagem.
- FastAPI expõe a API local e a documentação automática.
- SQLite é a persistência local inicial.
- O primeiro caso de uso usa evidência vinda de um arquivo de log local. Esse arquivo é a fonte dessa etapa. Ele ainda não é um conector de sistema externo.
- Conexões externas e LLM não fazem parte desta implementação.

A divisão em portas e adaptadores continua hipótese. LLM, conector e cofre não precisam existir no código enquanto essas capacidades estiverem de fora.

Identificadores de código em inglês e documentos em português continuam hipótese de convenção.

O lugar do arquivo SQLite está pendente. O repositório fica numa pasta sincronizada pelo OneDrive, e um banco SQLite nesse tipo de pasta pode ser corrompido pela sincronização.

## Cofre de segredos

Pendente. Opções a comparar na etapa em que a primeira credencial existir:

- Variáveis de ambiente em arquivo local ignorado pelo Git.
- Cofre do sistema operacional.
- Arquivo cifrado fora do repositório.

As três podem implementar a mesma porta. A escolha não deve vazar para os casos de uso.

## Integrações futuras

Bancos de dados, FTP/SFTP, GitHub e Portainer entram, cada um, como adaptador da porta de leitura. O mapeamento do que “leitura” significa em cada um ainda não existe. Exemplos do que precisará ser decidido na hora, e só então:

- Banco: quais comandos contam como leitura.
- FTP/SFTP: listar e baixar, sem envio e sem remoção.
- GitHub: ler repositório e metadados, sem push e sem abrir pull request.
- Portainer: ler estado e logs, sem reiniciar, alterar stack ou mudar configuração.

Não há ordem entre eles.

## Hospedagem remota

Fora do desenho atual. Quando chegar, autenticação, exposição de rede e o lugar dos segredos precisam de decisão própria. O monólito local não deve ganhar essas peças antecipadamente.

## Pendências que a arquitetura não resolve

1. Campos mínimos da investigação.
2. Como o arquivo de log chega à API e o que dele fica persistido.
3. Onde o arquivo SQLite é gravado.
4. Em qual endereço a API local escuta.
5. Provedor de LLM e se a chamada pode sair da máquina.
6. Mecanismo do cofre.
7. Confirmação humana do contexto antes do envio ao modelo. A arquitetura recomenda que sim; o produto ainda pergunta.
8. Primeira fonte externa, quando os conectores entrarem. O log local do primeiro caso de uso não responde a essa escolha.
