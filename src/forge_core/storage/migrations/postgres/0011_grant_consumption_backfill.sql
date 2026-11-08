-- Copia consumos da 0007 que batem com approval_grants (mesmo id, tarefa, agente e momento posterior à concessão).
-- Linhas de auditoria antiga com o mesmo número, mas sem correspondência, ficam só em approval_consumptions.
INSERT INTO grant_consumptions (grant_id, task_id, agent, consumed_by, consumed_at)
SELECT c.grant_id, c.task_id, c.agent, c.consumed_by, c.consumed_at
FROM approval_consumptions c
INNER JOIN approval_grants g ON g.id = c.grant_id AND g.task_id = c.task_id AND g.agent = c.agent
WHERE c.consumed_at >= g.granted_at
AND NOT EXISTS (SELECT 1 FROM grant_consumptions x WHERE x.grant_id = c.grant_id);
