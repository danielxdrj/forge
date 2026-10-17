# Regras para agentes de programação

Este arquivo orienta pessoas e agentes que alterarem o repositório do Forge. Antes de propor código, leia [`.specs/PROJECT_CONTEXT.md`](.specs/PROJECT_CONTEXT.md), [`.specs/IMPLEMENTATION_PLAN.md`](.specs/IMPLEMENTATION_PLAN.md), [`.specs/EXECUTION_PROTOCOL.md`](.specs/EXECUTION_PROTOCOL.md), a especificação da etapa, [docs/PRODUCT.md](docs/PRODUCT.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) e [docs/ROADMAP.md](docs/ROADMAP.md).

O objetivo de aprendizagem do projeto faz parte do trabalho: explique o conceito, mostre alternativas quando houver mais de um caminho razoável, justifique a escolha e implemente uma parte pequena por vez.

## Escopo

- Implemente apenas a etapa autorizada, seguindo o [protocolo](.specs/EXECUTION_PROTOCOL.md).
- Se uma decisão estiver marcada como pendente e for necessária para o passo pedido, pare e pergunte. Não escolha em silêncio.
- Ao restringir o escopo atual, mantenha o requisito futuro na etapa dele. Não apague contexto só porque ele não será implementado agora.
- Não invente requisitos, telas, perfis de usuário, integrações ou campos que os documentos não definiram.
- Não instale dependências, não crie estrutura de aplicação e não adicione ferramentas sem um pedido explícito correspondente à etapa.
- Não amplie a tarefa com refatorações, automações ou integrações adjacentes.

## Segurança, sempre

- Integrações externas são somente leitura. O contrato de um conector não oferece operação de escrita.
- Não altere sistemas conectados. Isso inclui SQL de escrita, upload, delete, push, abertura de pull request, comentário em issue, restart de container e edição de arquivo remoto.
- A publicação de uma tarefa no GitHub é uma exceção futura, descrita no roadmap. Ela só vale quando essa for a etapa atual, e somente depois da aprovação explícita de quem opera. Essa publicação não altera o código do sistema de trabalho. Enquanto a etapa não estiver ativa, nenhuma escrita externa é permitida.
- Não corrija código de outro sistema e não aplique mudança em produção, nem “só desta vez”.
- Credenciais, tokens, senhas e chaves não aparecem no código, em exemplos, em testes, em logs, em mensagens de erro, em prompts de LLM nem em commits.
- Configuração e segredo ficam separados. A configuração pode dizer onde está o segredo. O valor do segredo fica fora do Git.
- Antes do primeiro arquivo de configuração local, garanta que o `.gitignore` cubra `.env` e qualquer arquivo de segredo.
- Exemplos usam placeholders óbvios, como `example.invalid` e `<SEGREDO>`.
- Testes usam dados fictícios. Nunca use credencial real para “ver se funciona”.
- Conteúdo enviado a um LLM passa antes por redação de segredos. A resposta do modelo é um texto de apoio guardado na investigação. Ela não é executada na etapa da análise.
- Uma etapa posterior, ainda sem abertura, pode aplicar a sugestão depois de aprovação explícita. O Cursor altera o código ou devolve o SQL para alterar o banco. O SQL volta como texto e não é executado. Se a alteração for de código, uma segunda aprovação vem antes de criar o commit e enviar a branch. Enquanto essa etapa não estiver ativa, nenhuma dessas escritas é permitida.

Redação, aqui, significa remover ou mascarar segredos antes que o texto saia do processo: log, erro ou prompt.

## Como implementar

- Prefira o menor recorte que possa ser executado e testado sozinho.
- Mantenha o núcleo do sistema independente da interface e dos sistemas externos. A interface chama casos de uso. Os casos de uso chamam portas. Os adaptadores implementam as portas.
- Nomeie módulos pelo papel que cumprem: investigação, conexão, evidência, análise, conector, cofre de segredos.
- Cubra com teste o comportamento novo que for regra do produto. Não adicione teste de detalhe de implementação sem comportamento observável.
- Se mudar comportamento descrito nos documentos, atualize o documento na mesma alteração. Quando o [guia de aprendizagem](docs/LEARNING_GUIDE.md) descrever código, atualize-o para o que realmente existe.
- Comunique-se com o responsável pelo projeto em português. Identificadores de código ficam em inglês enquanto essa convenção não for revista; ela ainda é uma hipótese registrada na arquitetura.

## Quando parar

Pare e pergunte se a tarefa:

- exige uma decisão listada como pendente;
- pede escrita em sistema externo, correção automática ou uso de credencial real;
- exige uma dependência nova que a etapa atual não previu;
- só fecha se você assumir uma pendência do plano de implementação, o formato da evidência de log, o segredo do Postgres, o endereço da API ou qual LLM será usado.

## Definição de pronto de uma alteração

- Faz só o que a etapa pedia.
- Respeita os princípios de leitura, não alteração e segredo fora do Git.
- Tem um modo de verificar o comportamento, mesmo que seja um teste pequeno.
- Deixa claro, na resposta a quem pediu, o que foi feito, o que foi deixado de fora e qual decisão ainda está aberta.
