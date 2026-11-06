CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE stages (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects (id),
    title TEXT NOT NULL,
    created_at TEXT NOT NULL
);
ALTER TABLE tasks ADD COLUMN objective TEXT NOT NULL DEFAULT '';
ALTER TABLE tasks ADD COLUMN context TEXT NOT NULL DEFAULT '';
ALTER TABLE tasks ADD COLUMN scope TEXT NOT NULL DEFAULT '';
ALTER TABLE tasks ADD COLUMN acceptance_criteria TEXT NOT NULL DEFAULT '';
ALTER TABLE tasks ADD COLUMN priority TEXT NOT NULL DEFAULT 'normal';
ALTER TABLE tasks ADD COLUMN assignee_kind TEXT;
ALTER TABLE tasks ADD COLUMN assignee_id TEXT;
ALTER TABLE tasks ADD COLUMN start_date TEXT;
ALTER TABLE tasks ADD COLUMN due_date TEXT;
ALTER TABLE tasks ADD COLUMN completed_at TEXT;
ALTER TABLE tasks ADD COLUMN stage_id TEXT REFERENCES stages (id);
ALTER TABLE tasks ADD COLUMN parent_task_id TEXT REFERENCES tasks (id);
ALTER TABLE tasks ADD COLUMN required INTEGER NOT NULL DEFAULT 1;
ALTER TABLE tasks ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
-- Vocabulário antigo (FRG-42) -> padrão de planejamento (ADR-010). Roda antes dos triggers append-only.
UPDATE tasks SET status = CASE status WHEN 'created' THEN 'pending' WHEN 'running' THEN 'in_progress' ELSE status END;
UPDATE task_history SET status = CASE status WHEN 'created' THEN 'pending' WHEN 'running' THEN 'in_progress' ELSE status END;
CREATE TABLE task_dependencies (
    task_id TEXT NOT NULL REFERENCES tasks (id),
    depends_on_id TEXT NOT NULL REFERENCES tasks (id),
    required INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (task_id, depends_on_id)
);
CREATE TABLE task_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL REFERENCES tasks (id),
    field TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    actor TEXT NOT NULL,
    at TEXT NOT NULL
);
CREATE INDEX tasks_stage ON tasks (stage_id);
CREATE INDEX tasks_parent ON tasks (parent_task_id);
CREATE TRIGGER task_history_no_update BEFORE UPDATE ON task_history
BEGIN SELECT RAISE(ABORT, 'task_history é append-only'); END;
CREATE TRIGGER task_history_no_delete BEFORE DELETE ON task_history
BEGIN SELECT RAISE(ABORT, 'task_history é append-only'); END;
CREATE TRIGGER task_changes_no_update BEFORE UPDATE ON task_changes
BEGIN SELECT RAISE(ABORT, 'task_changes é append-only'); END;
CREATE TRIGGER task_changes_no_delete BEFORE DELETE ON task_changes
BEGIN SELECT RAISE(ABORT, 'task_changes é append-only'); END;
