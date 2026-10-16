"""SQLite storage for collected problems; samples are stored in the same row."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_DATABASE = Path(__file__).resolve().parents[2] / "data" / "problem_bank.db"
SCHEMA_FILE = Path(__file__).resolve().parents[2] / "feat" / "api" / "acm_api" / "problem_bank.sql"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class ProblemStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, timeout=10)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
        columns = {row[1] for row in self.connection.execute("PRAGMA table_info(crawler_problems)")}
        if "statement_pdf" not in columns:
            self.connection.execute("ALTER TABLE crawler_problems ADD COLUMN statement_pdf BLOB")

    def close(self):
        self.connection.close()

    def import_metadata(self, items):
        now = utc_now()
        rows = [(item["platform"], item["problem_id"], str(item["contest_id"]), item.get("problem_index"),
                 item["problem_name"], item.get("problem_rating"), item["problem_url"],
                 json.dumps(item.get("tags", []), ensure_ascii=False), json.dumps(item, ensure_ascii=False), now, now)
                for item in items]
        with self.connection:
            self.connection.executemany(
                """INSERT INTO crawler_problems
                (platform,problem_id,contest_id,problem_index,problem_name,problem_rating,
                 problem_url,tags,metadata_json,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(platform,problem_id) DO UPDATE SET
                contest_id=excluded.contest_id,problem_index=excluded.problem_index,
                problem_name=excluded.problem_name,problem_rating=excluded.problem_rating,
                problem_url=excluded.problem_url,tags=excluded.tags,
                metadata_json=excluded.metadata_json,updated_at=excluded.updated_at""", rows,
            )

    def completed_ids(self, platform, language):
        return {row[0] for row in self.connection.execute(
            "SELECT problem_id FROM crawler_problems WHERE platform=? AND requested_language=? "
            "AND last_fetch_status='ok' AND (statement_html IS NOT NULL OR statement_pdf IS NOT NULL)", (platform, language),
        )}

    def save_content(self, platform, problem_id, content):
        with self.connection:
            row = self.connection.execute(
                "SELECT sample_count FROM crawler_problems WHERE platform=? AND problem_id=?", (platform, problem_id),
            ).fetchone()
            if row is None:
                raise ValueError("题目元数据尚未入库")
            if row["sample_count"] and not content["samples"] and not content.get("statement_pdf"):
                raise ValueError("新页面未解析到样例，保留已有题面和样例")
            now = utc_now()
            self.connection.execute(
                """UPDATE crawler_problems SET statement_html=?,statement_text=?,statement_pdf=?,statement_language=?,
                requested_language=?,samples=?,sample_count=?,statement_source_url=?,statement_sha256=?,
                statement_fetched_at=?,last_fetch_status='ok',last_attempt_at=?,last_error=NULL,updated_at=?
                WHERE platform=? AND problem_id=?""",
                (content["statement_html"], content["statement_text"], content.get("statement_pdf"), content["statement_language"],
                 content["requested_language"], json.dumps(content["samples"], ensure_ascii=False),
                 len(content["samples"]), content["source_url"], content["sha256"], now, now, now, platform, problem_id),
            )

    def record_failure(self, platform, problem_id, error):
        with self.connection:
            self.connection.execute(
                "UPDATE crawler_problems SET last_fetch_status='failed',last_attempt_at=?,last_error=? "
                "WHERE platform=? AND problem_id=?", (utc_now(), str(error)[:1000], platform, problem_id),
            )

    def counts(self, platform):
        row = self.connection.execute(
            "SELECT COUNT(*),SUM(statement_html IS NOT NULL OR statement_pdf IS NOT NULL),COALESCE(SUM(sample_count),0) "
            "FROM crawler_problems WHERE platform=?", (platform,),
        ).fetchone()
        return {"metadata_count": row[0], "statement_count": row[1] or 0, "sample_count": row[2]}
