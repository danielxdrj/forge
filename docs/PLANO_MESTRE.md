# Plano mestre do Forge

Este é o documento de referência para levar o Forge de painel local a sistema da empresa,
organizado por setores. Ele é consultado e atualizado a cada fase.

## Como usar este arquivo

- No início de qualquer trabalho de evolução do Forge, leia a fase com estado **em andamento**.
- Trabalhe só na fase atual. Se algo de outra fase aparecer, anote em "Correções e otimizações"
  com a fase de destino, em vez de fazer agora.
- Marque os itens `[x]` no mesmo PR que os entrega. Ao fechar a fase, atualize a tabela de estado.
- Decisão tomada vai para o **Registro de decisões**, com data. Decisão em aberto fica em
  **Decisões pendentes** até o responsável responder. Nunca escolha uma pendência em silêncio.
- As regras de segurança de [`AGENTS.md`](../AGENTS.md) continuam valendo em todas as fases.

## Estado das fases

| Fase | Tema | Estado |
| --- | --- | --- |
| 0 | Áreas e navegação por setor | em andamento |
| 1 | Desenvolvimento completo | pendente |
| 2 | Identidade e segurança (login próprio, 2FA, perfis) | pendente |
| 3 | Servidor da empresa | pendente |
| 4 | Forge Bot | pendente |
| 5 | Integrações: e-mail, notas e lembretes | pendente |
| 6 | Jurídico | pendente |
| 7 | Financeiro | pendente |
| 8 | Migração do FEB e do Gestão | pendente |

A ordem segue o que foi pedido: primeiro todas as áreas visíveis, depois Desenvolvimento,
depois as integrações. A Fase 2 é obrigatória **antes** da Fase 3. Nada vai para o servidor
com o login atual.

---

## 1. Para onde o Forge vai

- No futuro, a empresa terá **um sistema principal + o Forge**. O FEB e o Gestão serão desligados,
  e o Forge precisa estar pronto para receber o que for dele antes disso (Fase 8).
- O Forge passa de uso individual, nesta máquina, a **uso por setores**: Desenvolvimento,
  Jurídico e Financeiro. Cada setor tem as próprias telas, agentes e automações.
- O sistema roda num **servidor da empresa**, não na máquina de quem desenvolve.
- Quem mexe no GitHub é um **bot da empresa** (GitHub App), não a conta de uma pessoa.
- Uma pessoa pede coisas ao **Forge Bot**, um balão flutuante que responde curto, ajuda a usar
  o sistema e propõe agentes novos para aprovação.

Isso muda premissas de [`PRODUCT.md`](PRODUCT.md), como "uso individual, sem papéis". Esse
documento e o [`ROADMAP.md`](ROADMAP.md) serão atualizados quando a Fase 2 abrir (ver seção 11).

## 2. Princípios

### 2.1 Economia de tokens

Toda funcionalidade com IA segue estas regras, nesta ordem:

1. **Regra antes de IA.** Se uma consulta, uma regra ou um agendamento resolvem, o modelo não é
   chamado. Exemplos: vencimentos, monitor de conexões e a resposta "onde ativo o 2FA".
2. **Modelo mínimo.** Haiku por padrão para classificar, extrair e responder curto. Sonnet para
   escrever. Opus só por escolha explícita, nunca como padrão de quem não escolheu.
3. **Contexto mínimo.** Use recortes e `graph_prompt_section` (`graphs/prompt_context.py`).
   Nunca envie o repositório ou a base inteira.
4. **Prompt caching** em todo prefixo fixo: instruções, seção do grafo e catálogo.
5. **Reaproveitamento.** Se a entrada não mudou, a resposta anterior é reutilizada. O radar já
   faz isso com fingerprint.
6. **Saída limitada.** `max_tokens` por perfil e formato estruturado.
7. **Tetos.** Limite por execução, por agente por dia e global por mês, com parada automática.
8. **Tudo medido.** Toda chamada grava tokens e custo, incluindo rascunho e resolver, que hoje
   não gravam.
9. **Lote para o que não é urgente.** Trabalhos semanais ou noturnos usam a API de lote
   (Message Batches), que custa metade.

### 2.2 Design: responsivo e harmônico, sem cara de IA

- Use o que já existe: tokens de `app.css` (espaço em passos de 4px, `--text-*`, `--radius*`),
  Inter, temas claro e escuro, `pageHeader`, `cardHead`, `emptyState`, `table-wrap`,
  `segmented`, `openModal` e sheet. Toda tela nova usa esses componentes.
- Superfícies planas e bordas de 1px. **Sem** gradiente, brilho, vidro fosco ou sombra grande.
- **Sem emoji** e sem ícone de "faísca" ou robô. Os ícones são de traço, 16px, no estilo dos
  atuais da sidebar.
- Uma cor de destaque, a atual, usada só em ação principal e estado.
- O texto é curto, concreto e em português simples. Nada de "potencialize", "revolucione" ou
  "inteligente". Títulos em caixa de frase. Números com `tabular-nums`.
- Prefira listas e tabelas a grades de cards iguais. "Em breve" é uma pill neutra, não um banner.
- **Breakpoints oficiais:** 1280, 1100, 960 e 600px.
  - Abaixo de 1280px, nenhuma coluna fixa maior que 320px.
  - Toda tabela tem `data-label` nas células para o modo empilhado em ≤600px.
  - Área de toque mínima de 40px.
- **Verificação** de cada tela: larguras 375, 768, 1024 e 1440, nos temas claro e escuro.

---

## 3. Mapa de áreas

### 3.1 Sidebar

```
Forge
├─ Desenvolvimento
│   ├─ Tarefas
│   ├─ Investigação
│   ├─ Teia de contexto
│   ├─ Conexões            (master)
│   ├─ Agentes
│   ├─ E-mail              em breve
│   └─ Notas
├─ Jurídico
│   ├─ Agentes             (só o catálogo de futuros, por enquanto)
│   ├─ Peças e modelos     em breve
│   ├─ Prazos              em breve
│   ├─ E-mail              em breve
│   └─ Notas               em breve
├─ Financeiro
│   ├─ Agentes             (só o catálogo de futuros, por enquanto)
│   ├─ Contas e vencimentos em breve
│   ├─ Relatórios          em breve
│   ├─ E-mail              em breve
│   └─ Notas               em breve
└─ (rodapé) Configurações · tema · usuário · Sair
   (canto inferior direito, Fase 4) balão do Forge Bot
```

- Cada área é um grupo que abre e fecha. A área atual fica aberta.
- Os rótulos de grupo são pequenos e discretos, em cor `--muted`.
- Em ≤960px a sidebar vira barra no topo, com um seletor de área e as abas da área em rolagem
  horizontal.
- "Peças e modelos", "Prazos", "Contas e vencimentos" e "Relatórios" são **propostas**. Elas
  ficam visíveis como "em breve" e podem mudar de nome antes de ganhar conteúdo (D-08).

### 3.2 Rotas

- O formato é `#<area>/<aba>`: `#dev/tarefas`, `#dev/teia`, `#juridico/agentes`,
  `#financeiro/email`, `#configuracoes/conta`.
- Os hashes antigos redirecionam: `#tarefas` → `#dev/tarefas`, `#investigacao`, `#teia`,
  `#agentes` → `#dev/...`.
- `/conexoes` continua sendo uma página separada até a Fase 1 unificar os helpers.

### 3.3 Tela "em breve"

Usa o mesmo cabeçalho das telas reais, mais:
- uma frase do que a tela vai fazer;
- a fase prevista;
- quando houver, a lista de agentes futuros ligados a ela.

Nada de tela vazia nem de ilustração.

### 3.4 Agentes de cada área

É a mesma tela da aba Agentes de hoje, filtrada pelo setor, em duas partes:

1. **Ativos:** a tabela atual, com métricas, execuções e aprovações.
2. **Planejados:** linhas clicáveis com nome, uma frase, gatilho e motor. O clique abre um sheet
   com a descrição completa (seção 5).

A lista vem de um catálogo único no backend (seção 5.5), porque o Forge Bot vai consultar
a mesma fonte.

### 3.5 Configurações

| Seção | Conteúdo | Quem vê | Quando funciona |
| --- | --- | --- | --- |
| Conta | Nome, e-mail, troca de senha, 2FA, sessões ativas com "encerrar" | todos | Fase 2 |
| Lembretes | O que avisar e por onde (no sistema ou por e-mail) | todos | Fase 5 |
| Usuários e permissões | Convidar, papel, setores, desativar | master | Fase 2 |
| IA e custos | Modelo padrão por uso, tetos de custo, consumo do mês | master | Fase 1 |
| Aparência | Tema claro, escuro ou sistema | todos | Fase 0 |

Na Fase 0, a tela existe com todas as seções. O que ainda não funciona aparece desabilitado com
"Disponível na Fase N". O Forge Bot vai usar esses caminhos para responder, por exemplo:
"Configurações › Conta › Verificação em duas etapas".

## 4. Modelo de acesso

Proposta (decisão D-01): **papel** e **setor** são coisas separadas.

- **Papel** diz o que a pessoa pode fazer:
  - `master`: tudo, incluindo usuários, conexões, IA e custos;
  - `usuario`: usa as áreas dos seus setores;
  - `aprovador`: aprova ações de agentes. Continua existindo, porque o ADR-014 proíbe
    aprovar a própria edição.
- **Setor** diz o que a pessoa vê: `desenvolvimento`, `juridico`, `financeiro`. Uma pessoa pode
  ter mais de um setor.
- O que foi pedido como "advogado" e "financeiro" vira `usuario` com o setor correspondente.
  Assim, um setor novo amanhã não exige papel novo.
- **Migração dos papéis atuais:** `owner` → `master`; `editor` → `usuario` com o setor
  `desenvolvimento`; `approver` → `aprovador`. As tabelas de auth são append-only (ADR-014),
  então a mudança é por migration nova, sem UPDATE.
- **Agentes também têm setor.** A tela, os filtros e o Forge Bot só mostram agentes dos setores
  de quem está logado.

## 5. Catálogo de agentes

**Legenda.** Motor: *Regra* = sem IA; *H* = Haiku; *S* = Sonnet; *O* = Opus.
Escrita: o que o agente altera fora do Forge. Toda escrita passa por aprovação (ADR-006).

### 5.1 Desenvolvimento

| Agente | O que faz | Gatilho | Motor | Escrita |
| --- | --- | --- | --- | --- |
| Radar de prioridades | **Ativo.** Resume as prioridades do dia | 13:00, se ligado | H/S | não |
| Agente de investigação | **Ativo.** Investiga um problema e sugere a correção | sob pedido | S | não |
| Triagem de issues | Classifica a issue nova (tipo, prioridade, área, size) e liga às parecidas (`issues/related.py`) | issue nova | H | labels, com aprovação |
| Caçador de repetição | Lê issues, tarefas, investigações e logs da semana e agrupa o que se repete. Propõe automação com estimativa de horas | semanal, em lote | H + S | não |
| Arquiteto | Revisa PR ou proposta contra os ADRs e a teia de contexto. Aponta desvio, acoplamento e duplicação | PR aberto ou sob pedido | S | comentário no PR, com aprovação |
| Revisor de PR | Checklist de segurança: segredo, SQL de escrita, migration editada, teste faltando | PR aberto | S | comentário, com aprovação |
| Notas de versão | Escreve o rascunho da seção do CHANGELOG a partir dos commits | sob pedido | H | rascunho |
| Documentador | Detecta documento desatualizado depois do merge e propõe a correção | merge na main | S | rascunho de PR, com aprovação |
| Monitor de conexões | Roda os probes de banco, FTP e Portainer e avisa quando algo cai | a cada N min | Regra | não |
| Guardião de custos | Soma o custo por agente e por dia, avisa e pausa ao atingir o teto | contínuo | Regra | pausa agentes do Forge |

### 5.2 Jurídico

Todo resultado jurídico é rascunho. A revisão por advogado é obrigatória, e o tratamento de
dados segue a decisão D-07.

| Agente | O que faz | Gatilho | Motor | Escrita |
| --- | --- | --- | --- | --- |
| Pesquisa na base | Busca peças, modelos e teses internas por assunto. Devolve trechos com a fonte | sob pedido | busca + H | não |
| Rascunho de petição | Monta a peça a partir de um modelo aprovado e dos dados do caso. Marca os campos a conferir | sob pedido | S (O opcional) | rascunho |
| Controle de prazos | Lê publicações e intimações e extrai o prazo. A contagem de dias úteis e feriados é por regra, não por IA. Cria o lembrete | publicação nova | H + Regra | lembrete |
| Resumo de processo | Monta a linha do tempo do processo a partir dos andamentos | sob pedido | H | não |
| Revisor formal de peças | Confere partes, CPF/CNPJ, valores, datas e se os pedidos batem com os fundamentos | sob pedido | S | não |
| Triagem de e-mails jurídicos | Separa intimação, cliente e tribunal e sinaliza o que é urgente | e-mail novo | H | rótulo, com aprovação |

### 5.3 Financeiro

| Agente | O que faz | Gatilho | Motor | Escrita |
| --- | --- | --- | --- | --- |
| Alerta de vencimentos | Avisa o que vence em contas a pagar e a receber | diário | Regra | lembrete |
| Leitor de documentos | Extrai dados de boleto, nota fiscal e recibo em PDF para conferência | arquivo novo | H | não |
| Conciliação bancária | Casa o extrato com os lançamentos. A IA só entra nos casos ambíguos | diário | Regra + H | não |
| Régua de cobrança | Escreve o rascunho da mensagem de cobrança conforme o atraso. Envio só com aprovação | diário | H | e-mail, com aprovação |
| Classificador de despesas | Sugere categoria e centro de custo | lançamento novo | H | não |
| Fechamento mensal | Os números são calculados sem IA. A IA escreve só o comentário | mensal | Regra + S | não |

### 5.4 Comuns a todas as áreas

| Agente | O que faz | Gatilho | Motor | Escrita |
| --- | --- | --- | --- | --- |
| Triagem de e-mail | Classifica e prioriza a caixa do setor | e-mail novo | H | rótulo, com aprovação |
| Resumo do dia | Resumo curto do que chegou e do que vence | diário | H | não |
| Rascunho de resposta | Propõe uma resposta. **Nunca envia sozinho** | sob pedido | H/S | rascunho |
| Lembretes | Avisos agendados pela pessoa ou criados por outros agentes | agenda | Regra | não |

### 5.5 Onde o catálogo vive

- Fica em `src/forge_core/areas/catalog.py`, como dado estático versionado: setor, nome, resumo,
  descrição, gatilho, motor, escrita e fase prevista.
- É exposto em `GET /api/areas`, somente leitura.
- A aba Agentes, as telas "em breve" e o Forge Bot leem dessa mesma fonte.
- Quando um agente planejado é implementado, ele sai do catálogo e passa para a tabela `agents`.

---

## 6. Fases

### Fase 0: áreas e navegação por setor

**Objetivo:** todas as áreas visíveis e navegáveis, com o que existe funcionando e o resto como
"em breve". Só frontend, mais o catálogo da seção 5.5.

- [ ] `shared.js` com a sidebar gerada por código, usada por `index.html` e `conexoes.html`.
  Hoje a sidebar está duplicada em `conexoes.html:21-82`.
- [ ] Sidebar agrupada por área (seção 3.1) e rotas `#area/aba` com redirecionamento dos
  hashes antigos.
- [ ] Modelo de tela "em breve" (seção 3.3).
- [ ] Catálogo `areas/catalog.py` + `GET /api/areas` + teste.
- [ ] Aba Agentes por área: ativos filtrados + planejados clicáveis que abrem um sheet.
- [ ] Filtro por setor, status e busca na aba Agentes. O setor sai provisoriamente de `scope`;
  o campo real vem na Fase 1.
- [ ] Tela Configurações com as cinco seções. Só Aparência funciona.
- [ ] Teia em tela cheia: botão no canto do canvas, Esc para sair e cartão flutuante com o nó
  selecionado. O estado fica guardado, para sobreviver ao re-render.
- [ ] Responsividade:
  - coluna de 360px da teia (`app.css:1261`);
  - altura do grafo entre 861 e 960px (`app.css:1339`, `:1752`);
  - `.agents-layout` espremido entre 1100 e 1250px (`app.css:1491`);
  - `data-label` nas tabelas (`app.css:1844`; nenhum `td` recebe isso hoje).
- [ ] A Teia passa a usar `pageHeader`, como as outras telas.
- [ ] Verificação nas quatro larguras e nos dois temas.

**Pronto quando:** dá para navegar por Desenvolvimento, Jurídico, Financeiro e Configurações em
375px e em 1440px. Cada agente planejado abre a sua descrição. Os testes e o ruff passam.

### Fase 1: desenvolvimento completo

**Agentes**
- [ ] Migration `0023`: `agents.sector`, com CHECK dos setores e preenchimento a partir de `scope`.
- [ ] Logs por passo: tabela `agent_execution_events` (execução, ordem, momento, tipo,
  mensagem redigida, tokens). Linha do tempo no detalhe da execução.
- [ ] Gravar execuções com erro. Hoje a investigação só grava sucesso
  (`investigations/service.py:270-271`, `:296`).
- [ ] Tetos de custo por execução e por agente por dia, mais uma trava de concorrência na
  investigação (`investigations/service.py:265-269`).
- [ ] O padrão de modelo deixa de cair em Opus quando ninguém escolheu
  (`draft/anthropic_api.py:24`).
- [ ] Prompt caching na API, com instruções e seção do grafo em `cache_control`
  (`draft/anthropic_api.py:105-110`).
- [ ] Rascunho e resolver passam a usar o `AiSettings` e a gravar tokens e custo
  (`draft/service.py:210`, `resolver/service.py:330`).
- [ ] Configurações › IA e custos: modelo padrão por uso, tetos e consumo do mês.
- [ ] Primeiros agentes novos: Triagem de issues e Caçador de repetição (seção 5.1). Os dois
  são baratos e já têm dados.

**Investigação com dados do banco (SELECT primeiro, UPDATE só no fim)**
- [ ] A investigação gera SELECTs de diagnóstico.
  - O Forge os executa pela conexão somente leitura (`connections/readonly.py`), com limite de
    linhas e tempo máximo.
  - A conexão é escolhida pela pessoa, nunca pela IA.
  - A IA recebe um resumo redigido do resultado (`redaction.py`), não a tabela inteira.
- [ ] O UPDATE só aparece depois que os dados confirmarem o erro (ex.: "estas 3 linhas estão
  com X e deveriam estar com Y"). Sem prova, não há UPDATE.
- [ ] A correção vem como pacote, **só como texto**, nunca executada pelo Forge:
  1. SELECT de conferência, com o mesmo WHERE;
  2. quantidade esperada de linhas;
  3. UPDATE em transação, filtrando pela chave primária;
  4. SQL de reversão, com os valores antigos capturados.
- [ ] Bloco "Correção proposta" na investigação e o mesmo pacote anexado à issue, com um botão
  de copiar em cada parte.
- [ ] A aprovação e quem aplicou ficam registrados. A execução no banco é feita por uma pessoa,
  fora do Forge.

**Teia**
- [ ] Ver o código da função ou classe ao selecionar o nó.
  - Endpoint `GET /api/context-graph/source`, somente leitura.
  - Lê do clone local no commit indexado, com limite de linhas e redação de segredos.
  - Se o Graphify não trouxer a linha, procura `def`/`class` pelo nome no arquivo.
  - Destaque de sintaxe no painel. **Sem LLM.**

**Frontend**
- [ ] Unificar os cerca de 20 helpers duplicados entre `app.js` e `conexoes.js`
  (`conexoes.js:16-557`).
- [ ] `afterLogin` deve carregar Agentes (`app.js:457`). Juntar boot, afterLogin e hashchange
  num único carregador por aba.
- [ ] Usar `Promise.all` nos fetches sequenciais: `loadEditorData`, `loadAgentes`, `loadTeia`.
- [ ] O polling da teia atualiza só a teia, não `render()` inteiro (`app.js:1806`).
- [ ] Um único mapeamento de status para pill (`app.js:840`, `:3320`, `:3516`, `:3656`) e um
  único rótulo de escopo e de motor.
- [ ] Remover estado morto: `graphNodes`, `graphQuery`, `vaultNote`, `state.vault`,
  `state.tasks`, `ai.*` (`app.js:46-51`, `:787-794`).

**Pronto quando:** a aba Agentes filtra por setor, cada execução mostra os passos e o custo, e o
código de uma função abre na teia.

### Fase 2: identidade e segurança

Antes de codar: ADR-018 (identidade local), que complementa o ADR-014 sem desfazer as garantias
dele (append-only, revogação checada na transação, sessão com hash).

**Login e senha**
- [ ] Login por e-mail e senha, com hash argon2id. Trocar a senha grava uma credencial nova; a
  antiga é revogada, nunca editada.
- [ ] Sem cadastro aberto. O master convida, e a pessoa define a senha pelo link do convite,
  de uso único.
- [ ] "Esqueci minha senha":
  - token com hash, válido por 15 min e de uso único;
  - a resposta é a mesma para e-mail existente e inexistente.

**2FA e sessões**
- [ ] 2FA por app autenticador (TOTP):
  - segredo cifrado com chave fora do Git;
  - 10 códigos de recuperação guardados como hash;
  - obrigatório para master (D-03 decide para os demais).
- [ ] Rate limit por IP e por conta no login, no reset e em `/api/auth/login/start`
  (`web/app.py:381`).
- [ ] Teto no `PendingStore` (`web/pending.py:25`) e fim do audit_log anônimo que pode encher
  sem limite.
- [ ] Prazo absoluto de sessão além do deslizante (`auth/store.py:227-263`), sessões
  `expires_at NULL` tratadas, e a lista de sessões em Configurações › Conta.

**Papéis e GitHub**
- [ ] Migration de papéis e setores (seção 4), com `ROLES` (`auth/store.py:31`), `roles_of` e
  as checagens do front (`app.js:474-484`) atualizados.
- [ ] O login pelo GitHub sai (ou vira "vincular conta", conforme D-02). Hoje qualquer conta
  GitHub cria identidade e sessão (`auth/store.py:84-161`).
- [ ] GitHub App da empresa como bot (ADR-007): permissões só nos repositórios escolhidos,
  token de 1 hora e chave privada no cofre.

**E-mail e documentos**
- [ ] E-mail transacional para convite, reset e alertas de segurança. O provedor é a decisão D-04.
- [ ] Atualizar `PRODUCT.md`, `ROADMAP.md`, `ARCHITECTURE.md` e
  `docs/operacao/autenticacao-humana.md`.

Dependências novas previstas, que precisam de aprovação: `argon2-cffi`, `pyotp` e
possivelmente uma de rate limit.

**Pronto quando:** dá para entrar com senha e 2FA, recuperar a senha por e-mail, o master
convida e define setores, e os testes cobrem força bruta, token reutilizado e revogação.

### Fase 3: servidor da empresa

É a etapa 08 do `ROADMAP.md`. Pré-requisito: Fase 2 concluída.

- [ ] Compose de produção com Postgres, API e frontend atrás de um proxy HTTPS.
- [ ] `FORGE_COOKIE_SECURE=true` (hoje o padrão é false, `config.py:52`) e `web_hosts` com o
  domínio real.
- [ ] Segredos fora do Git, em variável de ambiente ou arquivo protegido. Chave da API da
  Anthropic **da empresa**. O Claude CLI pessoal não é usado no servidor.
- [ ] Backup diário do Postgres e um teste de restauração documentado.
- [ ] Atualização por tag (procedimento manual em `docs/operacao/`).
- [ ] O Monitor de conexões (seção 5.1) também vigia o próprio Forge.

### Fase 4: Forge Bot

- [ ] Balão no canto inferior direito, que abre um painel lateral. Nas telas pequenas abre como
  sheet.
- [ ] **Camada 1, sem IA:** índice de ajuda versionado com tela, caminho e frase, mais busca
  local. Resolve "como ativo o 2FA".
- [ ] **Camada 2, Haiku:**
  - ferramentas `listar_agentes`, `catalogo_planejado`, `explicar_tela`, filtradas pelos setores
    de quem pergunta;
  - resposta em no máximo 3 frases;
  - histórico curto.
- [ ] **Camada 3, Sonnet, só para criar agente:**
  - propõe nome, objetivo, setor, gatilho, motor, permissões e skills;
  - mostra a proposta e espera a aprovação;
  - grava o agente **pausado**.
- [ ] Orçamento por pessoa por dia e custo de cada resposta registrado.
- [ ] Prompt caching do prefixo fixo, com instruções, catálogo e índice de ajuda.

### Fase 5: integrações (e-mail, notas, lembretes)

- [ ] Conector de e-mail somente leitura por setor (provedor: D-04).
- [ ] Agentes comuns da seção 5.4. Enviar ou rotular exige aprovação.
- [ ] Notas por área. Hoje as notas vêm do vault Obsidian; a decisão D-09 diz se cada setor
  terá uma pasta ou outro armazenamento.
- [ ] Lembretes no sistema e por e-mail, com preferências em Configurações › Lembretes.

### Fase 6: Jurídico

- [ ] Definir de onde vêm as peças, os modelos e os processos (D-05).
- [ ] Pesquisa na base primeiro, por ser a mais barata e a mais útil. Depois Controle de prazos
  e Rascunho de petição.
- [ ] Política de dados sensíveis aplicada (D-07).

### Fase 7: Financeiro

- [ ] Definir a fonte dos dados financeiros (D-05; talvez hoje estejam no Gestão ou no FEB).
- [ ] Primeiro Alerta de vencimentos e Leitor de documentos. Depois Conciliação e Fechamento.

### Fase 8: migração do FEB e do Gestão

- [ ] Inventário de cada sistema: funções, quem usa e dados. Para cada função, decidir se vai
  para o Forge, para o sistema principal ou se morre.
- [ ] Mapear os usuários desses sistemas para os papéis e setores do Forge.
- [ ] Importar os dados por conexão somente leitura (`connections/`), sem tocar nos sistemas
  antigos.
- [ ] Período em paralelo, com comparação de resultados, e depois o desligamento.

---

## 7. Estado atual (análise de 19/11/2026)

**O que já existe e está bom:**
- **Autenticação.** Auditável (ADR-014): tabelas append-only, revogação checada dentro da
  transação, sessão guardada só como hash, CSRF double-submit, allowlist de Host e CSP. A
  Fase 2 aproveita tudo isso.
- **Agentes.** Dois agentes ativos (Radar e Investigação), com tokens, custo por execução,
  aprovações e configuração de motor e agenda.
- **Teia de contexto.** Expande por arquivo e usa `graph_prompt_section` para dar contexto
  ao motor.
- **Conexões somente leitura.** Já servem como base da importação na Fase 8.
- **Design.** Tokens, temas claro e escuro, e breakpoints em 1100, 960, 860 e 600px.

**O que falta:**
- senha, 2FA, e-mail, rate limit e setores;
- campo de setor nos agentes;
- log por passo de execução;
- filtro na aba Agentes;
- prompt caching;
- tela de configurações;
- tela cheia da teia;
- visualização de código.

## 8. Correções e otimizações encontradas

| # | Problema | Onde | Fase |
| --- | --- | --- | --- |
| 1 | `/api/auth/login/start` sem limite; dá para encher o audit_log sem login | `web/app.py:381`, `web/pending.py:25` | 2 |
| 2 | Qualquer conta GitHub cria identidade e sessão permanentes | `auth/store.py:84-161` | 2 |
| 3 | Cookie sem `secure` por padrão | `config.py:52` | 3 |
| 4 | Sessão renovável para sempre; despacho cria sessão sem prazo | `auth/store.py:170`, `:227-263`, `:377` | 2 |
| 5 | Sessão resolvida duas vezes por request; DNS (`getaddrinfo`) a cada request | `web/app.py:364-372`, `web/security.py:75` | 1 |
| 6 | Investigação sem teto, sem trava e sem registro de erro | `investigations/service.py:265-296` | 1 |
| 7 | Rascunho e resolver sem custo registrado | `draft/service.py:210`, `resolver/service.py:330` | 1 |
| 8 | Sem prompt caching; o padrão cai em Opus | `draft/anthropic_api.py:24`, `:105-110` | 1 |
| 9 | Re-render completo a cada mudança; o polling reconstrói a teia | `app.js:3807`, `:1806` | 1 |
| 10 | Helpers e sidebar duplicados entre `app.js` e `conexoes.js` | `conexoes.js:16-557`, `conexoes.html:21-82` | 0/1 |
| 11 | `afterLogin` não carrega Agentes | `app.js:457` | 1 |
| 12 | Tabelas sem `data-label` no mobile | `app.css:1844` | 0 |
| 13 | Coluna fixa de 360px na teia; altura do grafo entre 861 e 960px | `app.css:1261`, `:1339`, `:1752` | 0 |
| 14 | O logout não limpa `state.agentes`, `invest` e `teia` | `app.js:507` | 1 |
| 15 | `PRODUCT.md` e `ROADMAP.md` desatualizados em relação ao código | `docs/` | 2 |

## 9. Decisões pendentes

| # | Pergunta | Bloqueia |
| --- | --- | --- |
| D-01 | Aprovar o modelo papel × setor da seção 4? | Fase 2 |
| D-02 | O login pelo GitHub sai de vez ou fica como "vincular conta" para quem é de Desenvolvimento? | Fase 2 |
| D-03 | 2FA obrigatório para todos ou só para master? | Fase 2 |
| D-04 | Provedor de e-mail: Google Workspace, Microsoft 365 ou SMTP próprio? | Fases 2 e 5 |
| D-05 | Onde estão hoje as peças e os modelos jurídicos e os dados financeiros? | Fases 6 e 7 |
| D-06 | O que o FEB e o Gestão fazem, quem usa e onde ficam os dados? | Fases 7 e 8 |
| D-07 | Política para dados de clientes e processos enviados à API: o que pode sair, anonimização e retenção | Fase 6 |
| D-08 | Lista final de setores (incluir Diretoria, RH, Comercial?) e nomes dos módulos propostos | Fase 0, nomes |
| D-09 | Notas por setor: pastas no vault Obsidian ou armazenamento próprio? | Fase 5 |
| D-10 | Tetos de custo: por execução, por agente por dia e global por mês | Fase 1 |
| D-11 | Onde fica o servidor (máquina interna ou VPS), domínio e quem administra | Fase 3 |
| D-12 | Preço, se o Forge for vendido: decidir depois da Fase 3, com o custo real por agente medido | — |

## 10. Registro de decisões

| Data | Decisão |
| --- | --- |
| 2026-11-19 | Ordem das fases: áreas primeiro, depois Desenvolvimento, depois integrações. |
| 2026-11-19 | O bot do GitHub será um GitHub App da empresa, não uma conta pessoal (alinhado ao ADR-007). |
| 2026-11-19 | O Forge Bot responde em camadas (sem IA → Haiku → Sonnet) para não gastar tokens à toa. |
| 2026-11-19 | Áreas sem conteúdo aparecem como "em breve", com o catálogo de agentes planejados. |
| 2026-11-19 | Investigação com dados do banco: o SELECT é executado em modo somente leitura; o UPDATE sai só depois da prova, como pacote de texto (conferência, contagem, UPDATE e reversão), e nunca é executado pelo Forge. |

## 11. Relação com outros documentos

- [`ROADMAP.md`](ROADMAP.md) e [`.specs/`](../.specs/) descrevem as etapas 00 a 08 do início do
  projeto. A etapa 08 (hospedagem remota) passa a ser a Fase 3 deste plano.
- [`PRODUCT.md`](PRODUCT.md) ainda descreve o uso individual. Será revisto na abertura da Fase 2.
- ADRs relacionados:
  - [ADR-006](arquitetura/adr/ADR-006-aprovacao-e-desativacao.md): aprovação e desativação;
  - [ADR-007](arquitetura/adr/ADR-007-integracao-github.md): GitHub App;
  - [ADR-014](arquitetura/adr/ADR-014-autenticacao-humana.md): base da autenticação;
  - [ADR-017](arquitetura/adr/ADR-017-painel-web-local-container.md): painel web.
