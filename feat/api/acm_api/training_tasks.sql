CREATE TABLE IF NOT EXISTS training_tasks (
 id INTEGER PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
 state TEXT NOT NULL DEFAULT 'draft' CHECK(state IN ('draft','published','cancelled')),
 statuses_json TEXT NOT NULL DEFAULT '[]', rule TEXT NOT NULL DEFAULT 'period_ac' CHECK(rule IN ('period_ac','historical_ac')),
 starts_at INTEGER, due_at INTEGER, original_due_at INTEGER, version INTEGER NOT NULL DEFAULT 1,
 creator_qq_id TEXT, creator_name TEXT NOT NULL, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
 published_at INTEGER, cancelled_at INTEGER, cancel_reason TEXT,
 preview_hash TEXT, audience_hash TEXT, preview_expires_at INTEGER,
 publish_key TEXT, publish_version INTEGER
);
CREATE INDEX IF NOT EXISTS idx_training_tasks_state ON training_tasks(state,id DESC);
CREATE TABLE IF NOT EXISTS training_task_problems (
 id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL REFERENCES training_tasks(id) ON DELETE CASCADE,
 position INTEGER NOT NULL, platform TEXT NOT NULL, problem_id TEXT NOT NULL,
 problem_name TEXT NOT NULL, problem_rating TEXT, tags_json TEXT NOT NULL DEFAULT '[]',
 problem_url TEXT NOT NULL, content_available INTEGER NOT NULL DEFAULT 0,
 UNIQUE(task_id,platform,problem_id), UNIQUE(task_id,position)
);
CREATE TABLE IF NOT EXISTS training_task_recipients (
 id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL REFERENCES training_tasks(id) ON DELETE CASCADE,
 qq_id TEXT, account_epoch INTEGER NOT NULL, name TEXT NOT NULL, status_snapshot TEXT NOT NULL,
 bindings_json TEXT NOT NULL, closed INTEGER NOT NULL DEFAULT 0,
 refresh_task_id TEXT, refresh_at INTEGER NOT NULL DEFAULT 0,
 UNIQUE(task_id,qq_id,account_epoch)
);
CREATE INDEX IF NOT EXISTS idx_training_recipient_owner ON training_task_recipients(qq_id,account_epoch,task_id);
CREATE INDEX IF NOT EXISTS idx_training_recipient_task ON training_task_recipients(task_id,id);
CREATE TABLE IF NOT EXISTS training_task_progress (
 recipient_id INTEGER NOT NULL REFERENCES training_task_recipients(id) ON DELETE CASCADE,
 problem_id INTEGER NOT NULL REFERENCES training_task_problems(id) ON DELETE CASCADE,
 binding_key TEXT, binding_version INTEGER NOT NULL DEFAULT 0,
 history_json TEXT, on_time_json TEXT, late_json TEXT,
 verification TEXT NOT NULL DEFAULT 'pending', checked_at INTEGER NOT NULL DEFAULT 0,
 sync_success_at INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(recipient_id,problem_id)
);
CREATE INDEX IF NOT EXISTS idx_training_progress_problem ON training_task_progress(problem_id,recipient_id);
CREATE TABLE IF NOT EXISTS training_task_audit (
 id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL REFERENCES training_tasks(id) ON DELETE CASCADE,
 actor_qq_id TEXT, action TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '',
 before_json TEXT, after_json TEXT, created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_training_audit_task ON training_task_audit(task_id,id);
CREATE TRIGGER IF NOT EXISTS training_tasks_account_closed AFTER UPDATE OF account_state ON users
 WHEN OLD.account_state='active' AND NEW.account_state='closed'
 BEGIN
 UPDATE training_task_progress SET binding_key=NULL,
 history_json=CASE WHEN history_json IS NOT NULL THEN json_remove(history_json,'$.external_submission_id') END,
 on_time_json=CASE WHEN on_time_json IS NOT NULL THEN json_remove(on_time_json,'$.external_submission_id') END,
 late_json=CASE WHEN late_json IS NOT NULL THEN json_remove(late_json,'$.external_submission_id') END
 WHERE recipient_id IN (SELECT id FROM training_task_recipients WHERE qq_id=NEW.qq_id);
 UPDATE training_task_recipients SET qq_id=NULL,name='已注销成员',bindings_json='{}',closed=1,refresh_task_id=NULL WHERE qq_id=NEW.qq_id;
 UPDATE training_tasks SET creator_qq_id=NULL,creator_name='已注销成员' WHERE creator_qq_id=NEW.qq_id;
 UPDATE training_task_audit SET actor_qq_id=NULL WHERE actor_qq_id=NEW.qq_id;
 END;
