-- Radar de prioridades: histórico dos relatórios (append-only). Cada linha é uma rodada,
-- agendada ou manual. `payload` guarda as três listas e os números do topo em JSON; não há
-- corpo de issue nem segredo, só título, campos do board e motivos da pontuação.
CREATE TABLE radar_reports (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    reason TEXT NOT NULL CHECK (reason IN ('schedule', 'manual')),
    status TEXT NOT NULL CHECK (status IN ('ok', 'error')),
    error_code TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    payload TEXT NOT NULL DEFAULT '{}',
    created_by TEXT NOT NULL DEFAULT ''
);
CREATE INDEX radar_reports_created ON radar_reports (created_at);
