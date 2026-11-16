-- Radar de prioridades: histórico dos relatórios (append-only). Cada linha é uma rodada,
-- agendada ou manual. `payload` guarda as três listas e os números do topo em JSON; não há
-- corpo de issue nem segredo, só título, campos do board e motivos da pontuação.
CREATE TABLE radar_reports (
    id text PRIMARY KEY,
    created_at text NOT NULL,
    reason text NOT NULL CHECK (reason IN ('schedule', 'manual')),
    status text NOT NULL CHECK (status IN ('ok', 'error')),
    error_code text NOT NULL DEFAULT '',
    summary text NOT NULL DEFAULT '',
    payload text NOT NULL DEFAULT '{}',
    created_by text NOT NULL DEFAULT ''
);
CREATE INDEX radar_reports_created ON radar_reports (created_at);
