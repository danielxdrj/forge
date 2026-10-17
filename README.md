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

Etapa 0: fundação documental. O comportamento do produto ainda não foi implementado.

Integrações citadas como evolução futura, ainda sem desenho detalhado nem ordem definida: bancos de dados, FTP/SFTP, repositórios GitHub, Portainer e outras ferramentas.

## Mapa dos documentos

| Documento | Conteúdo |
| --- | --- |
| [AGENTS.md](AGENTS.md) | Regras para quem for implementar o Forge, inclusive agentes de programação. |
| [docs/PRODUCT.md](docs/PRODUCT.md) | Problema, usuários, funcionalidades previstas, limites e critérios de sucesso. |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Proposta inicial de arquitetura e decisões que ainda são hipóteses. |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Etapas incrementais, do protótipo local até integrações futuras. |

## O que estes documentos não fazem

Eles não escolhem linguagem, interface, banco local nem provedor de LLM. Essas escolhas estão marcadas como pendências. A implementação começa somente depois que as decisões bloqueantes da primeira etapa forem respondidas.
