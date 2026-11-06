CREATE TABLE projects (
    id text PRIMARY KEY,
    title text NOT NULL,
    created_at text NOT NULL
);
CREATE TABLE stages (
    id text PRIMARY KEY,
    project_id text NOT NULL REFERENCES projects (id),
    title text NOT NULL,
    created_at text NOT NULL
);
ALTER TABLE tasks ADD COLUMN objective text NOT NULL DEFAULT '';
ALTER TABLE tasks ADD COLUMN context text NOT NULL DEFAULT '';
ALTER TABLE tasks ADD COLUMN scope text NOT NULL DEFAULT '';
ALTER TABLE tasks ADD COLUMN acceptance_criteria text NOT NULL DEFAULT '';
ALTER TABLE tasks ADD COLUMN priority text NOT NULL DEFAULT 'normal';
ALTER TABLE tasks ADD COLUMN assignee_kind text;
ALTER TABLE tasks ADD COLUMN assignee_id text;
ALTER TABLE tasks ADD COLUMN start_date text;
ALTER TABLE tasks ADD COLUMN due_date text;
ALTER TABLE tasks ADD COLUMN completed_at text;
ALTER TABLE tasks ADD COLUMN stage_id text REFERENCES stages (id);
ALTER TABLE tasks ADD COLUMN parent_task_id text REFERENCES tasks (id);
ALTER TABLE tasks ADD COLUMN required integer NOT NULL DEFAULT 1;
ALTER TABLE tasks ADD COLUMN version integer NOT NULL DEFAULT 1;
-- Vocabulário antigo (FRG-42) -> padrão de planejamento (ADR-010). Roda antes dos triggers append-only.
UPDATE tasks SET status = CASE status WHEN 'created' THEN 'pending' WHEN 'running' THEN 'in_progress' ELSE status END;
UPDATE task_history SET status = CASE status WHEN 'created' THEN 'pending' WHEN 'running' THEN 'in_progress' ELSE status END;
CREATE TABLE task_dependencies (
    task_id text NOT NULL REFERENCES tasks (id),
    depends_on_id text NOT NULL REFERENCES tasks (id),
    required integer NOT NULL DEFAULT 1,
    PRIMARY KEY (task_id, depends_on_id)
);
CREATE TABLE task_changes (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    task_id text NOT NULL REFERENCES tasks (id),
    field text NOT NULL,
    old_value text,
    new_value text,
    actor text NOT NULL,
    at text NOT NULL
);
CREATE INDEX tasks_stage ON tasks (stage_id);
CREATE INDEX tasks_parent ON tasks (parent_task_id);
CREATE FUNCTION task_log_append_only() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION '% é append-only', TG_TABLE_NAME; END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER task_history_no_change BEFORE UPDATE OR DELETE ON task_history
FOR EACH ROW EXECUTE FUNCTION task_log_append_only();
CREATE TRIGGER task_history_no_truncate BEFORE TRUNCATE ON task_history
FOR EACH STATEMENT EXECUTE FUNCTION task_log_append_only();
CREATE TRIGGER task_changes_no_change BEFORE UPDATE OR DELETE ON task_changes
FOR EACH ROW EXECUTE FUNCTION task_log_append_only();
CREATE TRIGGER task_changes_no_truncate BEFORE TRUNCATE ON task_changes
FOR EACH STATEMENT EXECUTE FUNCTION task_log_append_only();
