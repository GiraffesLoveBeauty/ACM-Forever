-- Shared problem schema for local collection and the server-owned database.
CREATE TABLE IF NOT EXISTS crawler_problems (
    platform TEXT NOT NULL,
    problem_id TEXT NOT NULL,
    contest_id TEXT NOT NULL,
    problem_index TEXT,
    problem_name TEXT NOT NULL,
    problem_rating INTEGER,
    problem_url TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL,
    statement_html TEXT,
    statement_text TEXT,
    statement_pdf BLOB,
    statement_language TEXT,
    requested_language TEXT,
    samples TEXT NOT NULL DEFAULT '[]',
    sample_count INTEGER NOT NULL DEFAULT 0 CHECK(sample_count >= 0),
    statement_source_url TEXT,
    statement_sha256 TEXT,
    statement_fetched_at TEXT,
    last_fetch_status TEXT NOT NULL DEFAULT 'never' CHECK(last_fetch_status IN ('never', 'ok', 'failed')),
    last_attempt_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (platform, problem_id)
);

CREATE INDEX IF NOT EXISTS idx_crawler_problems_contest
ON crawler_problems(platform, contest_id);

CREATE INDEX IF NOT EXISTS idx_crawler_problems_fetch
ON crawler_problems(platform, last_fetch_status, requested_language);

CREATE TABLE IF NOT EXISTS crawler_contests (
    platform TEXT NOT NULL,
    contest_id TEXT NOT NULL,
    contest_name TEXT NOT NULL,
    start_time INTEGER,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (platform, contest_id)
);

-- Complete per-contest lists, including shared Div. 1 / Div. 2 problems that
-- are omitted from Codeforces' bulk problemset catalog.
CREATE TABLE IF NOT EXISTS crawler_contest_catalogs (
    platform TEXT NOT NULL,
    contest_id TEXT NOT NULL,
    problem_ids TEXT NOT NULL,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (platform, contest_id)
);
