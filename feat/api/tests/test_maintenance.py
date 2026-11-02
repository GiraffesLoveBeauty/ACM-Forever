import hashlib
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from feat.api.acm_api.maintenance import MaintenanceError, backup, diagnose, restore, verify


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.data = self.root / "live"
        self.data.mkdir()
        self.database = self.data / "app.db"
        self.snapshot = self.root / "backup"
        self.restored = self.root / "restored"
        self.db = sqlite3.connect(self.database)
        self.addCleanup(self.db.close)
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE users(qq_id TEXT PRIMARY KEY, avatar_url TEXT);
            CREATE TABLE forum_images(id TEXT PRIMARY KEY);
            CREATE TABLE markdown_assets(storage_name TEXT);
            CREATE TABLE children(parent TEXT REFERENCES users(qq_id));
        """)
        self.forum = "a" * 32 + ".webp"
        self.markdown = "b" * 48 + ".png"
        self.avatar = "c" * 32 + ".jpg"
        self.db.execute("INSERT INTO users VALUES('synthetic', ?)", ("/uploads/avatars/" + self.avatar,))
        self.db.execute("INSERT INTO forum_images VALUES(?)", ("a" * 32,))
        self.db.execute("INSERT INTO markdown_assets VALUES(?)", (self.markdown,))
        self.db.commit()
        for store, name in [("forum", self.forum), ("markdown", self.markdown), ("avatars", self.avatar)]:
            folder = self.data / "uploads" / store
            folder.mkdir(parents=True)
            (folder / name).write_bytes(b"synthetic-image")

    def make_backup(self):
        return backup(self.database, self.snapshot, writers_stopped=True)

    def test_backup_includes_committed_wal_and_roundtrip_assets(self):
        self.db.execute("INSERT INTO users VALUES('wal-only', NULL)")
        self.db.commit()
        self.assertTrue(Path(str(self.database) + "-wal").is_file())
        self.assertTrue(self.make_backup()["ok"])
        self.assertTrue(restore(self.snapshot, self.restored)["ok"])
        with closing(sqlite3.connect(self.restored / "database.sqlite3")) as restored:
            self.assertEqual(restored.execute("SELECT COUNT(*) FROM users").fetchone()[0], 2)
        for store, name in [("forum", self.forum), ("markdown", self.markdown), ("avatars", self.avatar)]:
            self.assertEqual((self.restored / "uploads" / store / name).read_bytes(), b"synthetic-image")

    def test_diagnostics_do_not_migrate_or_change_database(self):
        self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        before = hashlib.sha256(self.database.read_bytes()).digest()
        self.assertTrue(diagnose(self.database)["ok"])
        self.assertEqual(before, hashlib.sha256(self.database.read_bytes()).digest())
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='settings'").fetchone()[0], 0)

    def test_missing_assets_and_foreign_key_violations_report_counts(self):
        (self.data / "uploads" / "forum" / self.forum).unlink()
        self.db.execute("INSERT INTO children VALUES('absent')")
        self.db.commit()
        report = diagnose(self.database)
        self.assertFalse(report["ok"])
        self.assertEqual(report["storage"]["forum"]["missing"], 1)
        self.assertEqual(report["database"]["foreign_key_violations"], 1)
        with self.assertRaises(MaintenanceError):
            self.make_backup()

    def test_tampering_is_rejected_before_restore_creates_destination(self):
        self.make_backup()
        path = self.snapshot / "uploads" / "forum" / self.forum
        path.write_bytes(b"altered-content")
        with self.assertRaises(MaintenanceError):
            verify(self.snapshot)
        with self.assertRaises(MaintenanceError):
            restore(self.snapshot, self.restored)
        self.assertFalse(self.restored.exists())

    def test_no_overwrite_and_writer_confirmation(self):
        with self.assertRaises(MaintenanceError):
            backup(self.database, self.snapshot)
        self.make_backup()
        with self.assertRaises(FileExistsError):
            self.make_backup()
        self.restored.mkdir()
        marker = self.restored / "keep.txt"
        marker.write_text("keep")
        with self.assertRaises(FileExistsError):
            restore(self.snapshot, self.restored)
        self.assertEqual(marker.read_text(), "keep")

    def test_source_destination_overlap_is_rejected(self):
        for destination in [self.data, self.data / "uploads" / "forum" / "backup", self.root]:
            with self.assertRaises(MaintenanceError):
                backup(self.database, destination, writers_stopped=True)
        self.make_backup()
        with self.assertRaises(MaintenanceError):
            restore(self.snapshot, self.snapshot / "child")

    def test_manifest_traversal_and_unlisted_files_are_rejected(self):
        self.make_backup()
        manifest_path = self.snapshot / "manifest.json"
        original = manifest_path.read_text()
        for name in ["../escaped", "/absolute", "uploads/forum/../../escaped", "uploads\\forum\\bad.webp", "C:/bad"]:
            manifest = json.loads(original)
            manifest["files"][name] = {"size": 0, "sha256": "0" * 64}
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaises(MaintenanceError):
                verify(self.snapshot)
        manifest_path.write_text(original)
        (self.snapshot / ".env").write_text("test-only")
        with self.assertRaises(MaintenanceError):
            verify(self.snapshot)

    def test_unexpected_storage_files_are_rejected(self):
        folder = self.data / "uploads" / "forum"
        (folder / ".env").write_text("test-only")
        with self.assertRaises(MaintenanceError):
            self.make_backup()

    def test_symlink_is_rejected(self):
        folder = self.data / "uploads" / "forum"
        link = folder / ("d" * 32 + ".webp")
        try:
            link.symlink_to(folder / self.forum)
        except OSError:
            self.skipTest("Symlinks unavailable on this host")
        with self.assertRaises(MaintenanceError):
            self.make_backup()

    def test_current_application_schema_can_be_backed_up_and_restored(self):
        import asyncio
        from feat.api.acm_api.database import connect_db
        path = self.root / "initialized" / "app.db"
        async def initialize():
            db = await connect_db(path)
            await db.close()
        asyncio.run(initialize())
        self.assertTrue(backup(path, self.snapshot, writers_stopped=True)["ok"])
        self.assertTrue(restore(self.snapshot, self.restored)["ok"])

    def test_custom_markdown_root_is_included_and_restored_portably(self):
        custom = self.root / "custom-markdown"
        (self.data / "uploads" / "markdown").rename(custom)
        self.assertFalse(diagnose(self.database)["ok"])
        self.assertTrue(backup(self.database, self.snapshot, markdown_dir=custom, writers_stopped=True)["ok"])
        self.assertTrue(restore(self.snapshot, self.restored)["ok"])
        self.assertTrue((self.restored / "uploads" / "markdown" / self.markdown).is_file())
