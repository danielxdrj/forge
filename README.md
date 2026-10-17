# Forge

Forge é um copiloto de engenharia local. A ideia é cadastrar conexões com sistemas técnicos, consultar apenas fontes autorizadas, registrar investigações e usar um modelo de linguagem para ajudar a diagnosticar problemas de software.

Nesta fase o repositório contém somente documentação. Não há aplicação executável, dependências instaladas nem integrações.

## Para que serve

Um engenheiro encontra um problema e precisa reunir contexto de vários lugares: um banco, um servidor de arquivos, um repositório, um painel de containers. O Forge deve ajudar a organizar essa investigação e a pedir uma análise a um LLM, sem alterar os sistemas consultados e sem aplicar correções sozinho.

## Princípios

- Toda integração externa começa com acesso somente de leitura.
- O Forge não altera os sistemas conectados.
- Nenhuma correção de código e nenhuma mudança em produção são executadas automaticamente.
- Credenciais não entram no código, nos logs, nos prompts enviados ao LLM nem no Git.
- O projeto começa na máquina local. Hospedagem remota fica para uma etapa futura.
- Novas integrações devem entrar sem reescrever o restante do sistema.
- Simplicidade, segurança, testabilidade e manutenção vêm antes de abrangência.

## Estado atual

A etapa 01 está concluída: a API cria e consulta uma investigação. O banco e o usuário se chamam `forge`. A senha, `FORGE_HOST` e `FORGE_PORT` ficam no ambiente e ainda estão vazios.

## Decisões aprovadas para a primeira implementação

- Linguagem: Python.
- Backend: FastAPI, executado na máquina local.
- Persistência: PostgreSQL, no serviço `postgres`.
- Interface: a documentação interativa do FastAPI.
- Uso: uma pessoa, nesta máquina.
- Funcionalidade: criar uma investigação e consultá-la depois.
- Campos desse registro: identificador, título e data de criação.
- Rotas: `POST /investigations` e `GET /investigations/{investigation_id}`.
- Ficam fora: LLM, integrações externas, interface web, upload e análise de log.

## Execução local

O conjunto se chama `forge_system`. Os serviços têm nomes diretos:

| Serviço | Processo |
| --- | --- |
| `backend` | A API FastAPI. A API é o backend, e os dois não viram containers separados. |
| `frontend` | A interface. Ainda não há tela. |
| `postgres` | O PostgreSQL do próprio Forge. |

O `frontend` conversa com o `backend`. O `backend` conversa com o `postgres`.

Na primeira execução, o Compose sobe somente o `postgres`. O `backend` roda na máquina, e por isso alcança o banco em `localhost`. O nome `postgres` passa a ser o endereço quando o `backend` também estiver na rede do Compose. Os detalhes dessa execução estão em [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

O plano operacional está em [.specs/IMPLEMENTATION_PLAN.md](.specs/IMPLEMENTATION_PLAN.md).

Integrações citadas como evolução futura, ainda sem desenho detalhado nem ordem definida: bancos de dados externos, FTP/SFTP, repositórios GitHub, Portainer e outras ferramentas. O PostgreSQL acima guarda os dados do Forge. Ele não é uma dessas integrações.

## Mapa dos documentos

| Documento | Conteúdo |
| --- | --- |
| [AGENTS.md](AGENTS.md) | Regras para quem for implementar o Forge, inclusive agentes de programação. |
| [docs/PRODUCT.md](docs/PRODUCT.md) | Problema, usuários, funcionalidades previstas, limites e critérios de sucesso. |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Proposta inicial de arquitetura e decisões que ainda são hipóteses. |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Índice das etapas, incluindo as futuras. |
| [.specs/](.specs/IMPLEMENTATION_PLAN.md) | Especificações operacionais para executar cada etapa. |
| [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) | Atalho para o plano em `.specs/`. |
| [docs/LEARNING_GUIDE.md](docs/LEARNING_GUIDE.md) | Conceitos e o código da etapa 01. |

## O que ainda não está decidido

A senha do PostgreSQL e os valores de `FORGE_HOST` e `FORGE_PORT` ainda serão preenchidos no ambiente. Log, LLM, conectores, cofre, tarefas no GitHub e hospedagem remota permanecem nas etapas seguintes.
