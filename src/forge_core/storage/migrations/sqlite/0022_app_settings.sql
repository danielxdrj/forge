-- Configurações do painel que o owner muda pela tela (sem reiniciar o container):
-- agenda automática do radar e motor/modelo de cada uso de IA. Chave/valor em texto.
-- Nunca guarda segredo: a chave da API da Anthropic fica em /run/secrets.
CREATE TABLE app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL DEFAULT ''
);
