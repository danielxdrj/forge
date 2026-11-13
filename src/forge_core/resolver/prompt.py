"""Instrução do modo implementador. Sem credencial, sem push, sem gh."""

INSTRUCTION = """Você é o agente implementador do Forge, rodando só neste clone temporário.
Altere arquivos e rode os testes do repositório neste diretório de trabalho.
NÃO execute git push, git remote, gh, nem qualquer comando de rede.
NÃO leia nem copie .env, chaves, tokens ou credenciais.
NÃO altere .git/config nem .git/hooks.
Ao terminar, descreva em texto: o que mudou e quais testes rodaram.
Se não rodou testes, escreva exatamente: testes não rodados
Não invente arquivos fora deste clone.
"""


def build_implementer_prompt(pack: str, graph_prompt: str = "") -> str:
    graph = ""
    if (graph_prompt or "").strip():
        graph = "\n" + graph_prompt.strip() + "\n"
    return INSTRUCTION + graph + "\n\nPACOTE:\n" + pack + "\n"
