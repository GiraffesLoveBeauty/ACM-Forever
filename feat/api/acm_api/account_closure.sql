CREATE TABLE IF NOT EXISTS account_closure_requests (
 request_id TEXT PRIMARY KEY, user_qq_id TEXT NOT NULL REFERENCES users(qq_id),
 idempotency_key_hash TEXT NOT NULL, intent_fingerprint TEXT NOT NULL,
 policy_version TEXT NOT NULL, account_epoch INTEGER NOT NULL, credential_version INTEGER NOT NULL,
 created_at INTEGER NOT NULL, committed_at INTEGER, receipt_token_hash TEXT NOT NULL,
 receipt_expires_at INTEGER NOT NULL, cleanup_state TEXT NOT NULL DEFAULT 'pending',
 UNIQUE(user_qq_id,idempotency_key_hash));
CREATE INDEX IF NOT EXISTS closure_requests_expiry ON account_closure_requests(receipt_expires_at);
CREATE TABLE IF NOT EXISTS account_lifecycle_audit (
 id INTEGER PRIMARY KEY, subject_qq_id TEXT, action TEXT NOT NULL, result_code TEXT NOT NULL,
 policy_version TEXT NOT NULL, created_at INTEGER NOT NULL, counts_json TEXT);
CREATE INDEX IF NOT EXISTS closure_audit_time ON account_lifecycle_audit(created_at);
CREATE TABLE IF NOT EXISTS account_closure_cleanup_tasks (
 id INTEGER PRIMARY KEY, request_id TEXT NOT NULL REFERENCES account_closure_requests(request_id),
 resource_kind TEXT NOT NULL CHECK(resource_kind IN ('avatar','forum','forum_thumb','markdown')),
 resource_key TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
 next_at INTEGER NOT NULL DEFAULT 0, lease_token TEXT, lease_until INTEGER NOT NULL DEFAULT 0,
 last_error_code TEXT, updated_at INTEGER NOT NULL, UNIQUE(resource_kind,resource_key));
CREATE INDEX IF NOT EXISTS closure_cleanup_ready ON account_closure_cleanup_tasks(state,next_at,lease_until);
CREATE TABLE IF NOT EXISTS account_sensitive_action_limits (
 action TEXT NOT NULL, subject_hash TEXT NOT NULL, window_start INTEGER NOT NULL,
 attempts INTEGER NOT NULL, PRIMARY KEY(action,subject_hash));
CREATE TABLE IF NOT EXISTS account_closure_resource_revocations (
 resource_kind TEXT NOT NULL, resource_id TEXT NOT NULL,
 request_id TEXT NOT NULL REFERENCES account_closure_requests(request_id), revoked_at INTEGER NOT NULL,
 PRIMARY KEY(resource_kind,resource_id));
