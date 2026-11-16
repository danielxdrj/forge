-- Investigação livre (sem issue obrigatória): reaproveita investigation_notes.
-- issue_key fica opcional; novas colunas distinguem nota manual (kind='note', padrão)
-- de resultado de investigação (kind='investigation'). Sem conteúdo de vault nem segredo.
ALTER TABLE investigation_notes ALTER COLUMN issue_key DROP NOT NULL;
ALTER TABLE investigation_notes ADD COLUMN kind text NOT NULL DEFAULT 'note';
ALTER TABLE investigation_notes ADD COLUMN repos_json text NOT NULL DEFAULT '[]';
ALTER TABLE investigation_notes ADD COLUMN connection_ids_json text NOT NULL DEFAULT '[]';
ALTER TABLE investigation_notes ADD COLUMN engine text NOT NULL DEFAULT '';
ALTER TABLE investigation_notes ADD COLUMN description text NOT NULL DEFAULT '';
CREATE INDEX investigation_notes_kind ON investigation_notes (kind, updated_at);
