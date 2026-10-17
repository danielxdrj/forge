# Guia de aprendizagem

Este guia explica conceitos que a primeira implementação do Forge vai usar. O repositório ainda não tem código. Onde aparecer um arquivo, uma rota ou uma tabela, leia como plano, não como componente existente.

Quando o código existir, este guia deve passar a descrever o que estiver no repositório. O plano operacional está em [../.specs/IMPLEMENTATION_PLAN.md](../.specs/IMPLEMENTATION_PLAN.md). O fluxo aprovado está em [ARCHITECTURE.md](ARCHITECTURE.md).

## HTTP

HTTP é o modo como um programa pede uma ação a outro. O pedido tem um método e um caminho. A resposta tem um estado e, neste projeto, um JSON.

No Forge, criar uma investigação será um `POST` em `/investigations`. Consultar será um `GET` em `/investigations/{investigation_id}`. Essas rotas ainda não existem.

## API

Uma API é o conjunto de pedidos que um programa aceita. Quem chama não precisa conhecer o SQL nem abrir o banco.

A primeira API do Forge terá duas operações. A documentação interativa do FastAPI será a forma de chamá-las enquanto não houver `frontend`.

## FastAPI

FastAPI é a biblioteca Python escolhida para publicar a API. Uma rota é uma função associada a um método e a um caminho. A biblioteca também gera a página em que dá para experimentar os pedidos.

O processo do `backend` vai rodar na máquina, com um servidor ASGI. Uvicorn é o servidor proposto para isso. Nenhum dos dois está instalado.

## Validação

Validação confere o pedido antes de ele virar dado gravado. Um título ausente ou vazio não deve chegar ao PostgreSQL.

O FastAPI usa modelos Pydantic na borda HTTP. O tamanho máximo do título ainda não foi decidido, então a regra completa de validação também ainda não existe.

## PostgreSQL

PostgreSQL é o banco que vai guardar os dados do próprio Forge. Ele roda como outro processo, no serviço `postgres`. A API e o banco se falam por uma conexão de rede, mesmo estando na mesma máquina.

Na primeira execução, só esse serviço sobe pelo Docker Compose. O `backend` fica de fora do Compose. Por isso a conexão inicial usa `localhost`. O nome `postgres` será o endereço interno no dia em que a API também entrar nessa rede.

O arquivo do Compose ainda não foi criado.

## SQL parametrizado

SQL é a linguagem usada para gravar e buscar a linha da investigação. Parametrizar significa enviar o título e o identificador separados do texto da consulta.

Isso impede que um título com símbolos de SQL mude o comando. A tabela e as consultas ainda não foram escritas.

## Testes automatizados

Um teste automatizado executa um comportamento e confere o resultado. No Forge, ele vai chamar a API e olhar a resposta, em vez de apenas ler o código.

O teste que consulta o mesmo identificador por outra conexão é o que mostra que o registro está no PostgreSQL, não só na memória do processo. A ferramenta proposta é o pytest, com o cliente HTTP do FastAPI. Os testes ainda não existem.

## Variáveis de ambiente

Uma variável de ambiente entrega configuração ao processo no momento em que ele inicia. `DATABASE_URL` vai dizer onde está o PostgreSQL, incluindo a senha.

O valor fica fora do código, dos logs e do Git. Um arquivo de exemplo poderá mostrar o nome da variável com um valor fictício. Esse arquivo também ainda não existe. A senha real não deve ser copiada para a documentação.

## O que este guia não cobre ainda

LLM, upload de log, conectores externos, cofre de segredos, `frontend` e publicação de tarefas no GitHub têm conceitos próprios. Eles entram aqui quando a etapa correspondente deixar de ser só uma direção e passar a ter código.
