-- No passwords or recoverable credentials are persisted in import tables.
CREATE TABLE IF NOT EXISTS account_import_batches (
 id TEXT PRIMARY KEY, actor_qq_id TEXT NOT NULL, actor_epoch INTEGER NOT NULL,
 actor_credential_version INTEGER NOT NULL, template_version TEXT NOT NULL,
 file_sha256 TEXT NOT NULL, normalized_sha256 TEXT NOT NULL,
 status TEXT NOT NULL, preview_version INTEGER NOT NULL DEFAULT 1,
 selection_digest TEXT, continuation_token TEXT, acknowledged_binding INTEGER NOT NULL DEFAULT 0,
 created_at INTEGER NOT NULL, preview_expires_at INTEGER NOT NULL,
 execution_expires_at INTEGER, confirmed_at INTEGER, finished_at INTEGER,
 payload_purge_at INTEGER NOT NULL, payload_purged INTEGER NOT NULL DEFAULT 0,
 temporary_password_ttl_hours INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS account_import_actor ON account_import_batches(actor_qq_id, created_at);
CREATE TABLE IF NOT EXISTS account_import_rows (
 id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES account_import_batches(id) ON DELETE CASCADE,
 excel_row_number INTEGER NOT NULL, qq_id TEXT NOT NULL, action TEXT NOT NULL, status TEXT NOT NULL,
 selected INTEGER NOT NULL DEFAULT 0, payload_json TEXT NOT NULL, snapshot_hash TEXT NOT NULL,
 errors_json TEXT NOT NULL, warnings_json TEXT NOT NULL, ignored_json TEXT NOT NULL,
 result_code TEXT, chunk_id TEXT, created_account_at INTEGER, attempt_count INTEGER NOT NULL DEFAULT 0,
 UNIQUE(batch_id, excel_row_number)
);
CREATE INDEX IF NOT EXISTS account_import_row_state ON account_import_rows(batch_id,status,excel_row_number);
CREATE INDEX IF NOT EXISTS account_import_row_qq ON account_import_rows(qq_id);
CREATE TABLE IF NOT EXISTS account_import_chunks (
 id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES account_import_batches(id) ON DELETE CASCADE,
 idempotency_key TEXT NOT NULL, request_hash TEXT NOT NULL, row_ids_json TEXT NOT NULL,
 status TEXT NOT NULL, lease_token TEXT NOT NULL, lease_until INTEGER NOT NULL,
 created_at INTEGER NOT NULL, finished_at INTEGER, result_json TEXT,
 UNIQUE(batch_id, idempotency_key)
);
CREATE UNIQUE INDEX IF NOT EXISTS account_import_one_chunk ON account_import_chunks(batch_id) WHERE status='processing';
CREATE TABLE IF NOT EXISTS binding_provenance (
 qq_id TEXT NOT NULL REFERENCES users(qq_id) ON DELETE CASCADE, platform TEXT NOT NULL,
 binding_version INTEGER NOT NULL, account_canonical TEXT NOT NULL, source TEXT NOT NULL,
 actor_qq_id TEXT, import_batch_id TEXT, recorded_at INTEGER NOT NULL,
 owner_verified_at INTEGER, existence_status TEXT NOT NULL DEFAULT 'not_checked',
 PRIMARY KEY(qq_id, platform)
);
