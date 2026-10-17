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

A fundação documental está registrada. As decisões abaixo valem para a primeira implementação. Ainda não há código, dependências instaladas nem integrações.

## Decisões aprovadas para a primeira implementação

- Linguagem: Python.
- Backend: FastAPI.
- Persistência local: PostgreSQL, no serviço `postgres`.
- Interface desta etapa: API local, com a documentação automática do FastAPI.
- Uso: uma pessoa, nesta máquina.
- Primeiro caso de uso: registrar uma investigação e analisar evidências fornecidas a partir de um arquivo de log local.
- Nesta etapa não há conexão com sistemas externos.
- A integração com LLM espera a definição de como será feita.

## Execução local

O conjunto se chama `forge_system`. Os serviços têm nomes diretos:

| Serviço | Processo |
| --- | --- |
| `backend` | A API FastAPI. A API é o backend, e os dois não viram containers separados. |
| `frontend` | A interface. Ainda não há tela. |
| `postgres` | O PostgreSQL do próprio Forge. |

O `frontend` conversa com o `backend`. O `backend` conversa com o `postgres`. O nome do serviço também é o endereço interno entre eles.

O Docker mostra os containers como `forge_system-backend-1`, `forge_system-frontend-1` e `forge_system-postgres-1`. Enquanto o `frontend` não existir, sobem `backend` e `postgres`. A documentação automática do FastAPI é o uso da API nesse período.

Ainda não há `Dockerfile` nem arquivo do Compose no repositório.

Integrações citadas como evolução futura, ainda sem desenho detalhado nem ordem definida: bancos de dados externos, FTP/SFTP, repositórios GitHub, Portainer e outras ferramentas. O PostgreSQL acima guarda os dados do Forge. Ele não é uma dessas integrações.

## Mapa dos documentos

| Documento | Conteúdo |
| --- | --- |
| [AGENTS.md](AGENTS.md) | Regras para quem for implementar o Forge, inclusive agentes de programação. |
| [docs/PRODUCT.md](docs/PRODUCT.md) | Problema, usuários, funcionalidades previstas, limites e critérios de sucesso. |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Proposta inicial de arquitetura e decisões que ainda são hipóteses. |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Etapas incrementais, do protótipo local até integrações futuras. |

## O que ainda não está decidido

Os documentos registram as decisões acima e continuam sem definir campos da investigação, o que guardar de um arquivo de log, o provedor de LLM e a ordem das integrações futuras. A implementação espera a aprovação do recorte vertical.
