# Regras para agentes de programação

Este arquivo orienta pessoas e agentes que alterarem o repositório do Forge. Leia também [docs/PRODUCT.md](docs/PRODUCT.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) e [docs/ROADMAP.md](docs/ROADMAP.md) antes de propor código.

O objetivo de aprendizagem do projeto faz parte do trabalho: explique o conceito, mostre alternativas quando houver mais de um caminho razoável, justifique a escolha e implemente uma parte pequena por vez.

## Escopo

- Implemente apenas a etapa atual do [roadmap](docs/ROADMAP.md).
- Se uma decisão estiver marcada como pendente e for necessária para o passo pedido, pare e pergunte. Não escolha em silêncio.
- Não invente requisitos, telas, perfis de usuário, integrações ou campos que os documentos não definiram.
- Não instale dependências, não crie estrutura de aplicação e não adicione ferramentas sem um pedido explícito correspondente à etapa.
- Não amplie a tarefa com refatorações, automações ou integrações adjacentes.

## Segurança, sempre

- Integrações externas são somente leitura. O contrato de um conector não oferece operação de escrita.
- Não altere sistemas conectados. Isso inclui SQL de escrita, upload, delete, push, abertura de pull request, comentário em issue, restart de container e edição de arquivo remoto.
- Não corrija código de outro sistema e não aplique mudança em produção, nem “só desta vez”.
- Credenciais, tokens, senhas e chaves não aparecem no código, em exemplos, em testes, em logs, em mensagens de erro, em prompts de LLM nem em commits.
- Configuração e segredo ficam separados. A configuração pode dizer onde está o segredo. O valor do segredo fica fora do Git.
- Antes do primeiro arquivo de configuração local, garanta que o `.gitignore` cubra `.env` e qualquer arquivo de segredo.
- Exemplos usam placeholders óbvios, como `example.invalid` e `<SEGREDO>`.
- Testes usam dados fictícios. Nunca use credencial real para “ver se funciona”.
- Conteúdo enviado a um LLM passa antes por redação de segredos. A resposta do modelo é um texto de apoio guardado na investigação. Ela não é executada.

Redação, aqui, significa remover ou mascarar segredos antes que o texto saia do processo: log, erro ou prompt.

## Como implementar

- Prefira o menor recorte que possa ser executado e testado sozinho.
- Mantenha o núcleo do sistema independente da interface e dos sistemas externos. A interface chama casos de uso. Os casos de uso chamam portas. Os adaptadores implementam as portas.
- Nomeie módulos pelo papel que cumprem: investigação, conexão, evidência, análise, conector, cofre de segredos.
- Cubra com teste o comportamento novo que for regra do produto. Não adicione teste de detalhe de implementação sem comportamento observável.
- Se mudar comportamento descrito nos documentos, atualize o documento na mesma alteração.
- Comunique-se com o responsável pelo projeto em português. Identificadores de código ficam em inglês enquanto essa convenção não for revista; ela ainda é uma hipótese registrada na arquitetura.

## Quando parar

Pare e pergunte se a tarefa:

- exige uma decisão listada como pendente;
- pede escrita em sistema externo, correção automática ou uso de credencial real;
- exige uma dependência nova que a etapa atual não previu;
- só fecha se você assumir campos pendentes, o formato da evidência de log, o lugar do SQLite, o endereço da API ou qual LLM será usado.

## Definição de pronto de uma alteração

- Faz só o que a etapa pedia.
- Respeita os princípios de leitura, não alteração e segredo fora do Git.
- Tem um modo de verificar o comportamento, mesmo que seja um teste pequeno.
- Deixa claro, na resposta a quem pediu, o que foi feito, o que foi deixado de fora e qual decisão ainda está aberta.
