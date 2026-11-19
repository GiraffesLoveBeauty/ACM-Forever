"""Historical Luogu AC never depends on task dates or invented timestamps."""
import unittest
from feat.api.acm_api import training_task_snapshot as snapshot


class SnapshotRulesTests(unittest.TestCase):
    def result(self, negative=None, positive=None, rule="period_ac", review=None):
        value = None
        if negative is not None:
            value = snapshot.observe(value, accepted=False, requested_at=negative, observed_at=negative+1)
        if positive is not None:
            value = snapshot.observe(value, accepted=True, requested_at=positive-1, observed_at=positive)
        return snapshot.classify(value, starts_at=100, due_at=200, rule=rule, problem_id="P1001", review=review)

    def test_any_historical_ac_counts_before_during_or_after_the_task(self):
        for positive in (50, 100, 150, 200, 201, 999):
            for rule in ("period_ac", "historical_ac"):
                with self.subTest(positive=positive, rule=rule):
                    history, timely, late, unknown = self.result(positive=positive, rule=rule)
                    self.assertEqual((timely, late, unknown), (None, None, None))
                    self.assertEqual(history["observed_at"], positive)
                    self.assertIsNone(history["accepted_at"])
                    self.assertEqual(history["evidence_type"], "historical_ac")

    def test_no_ac_needs_no_period_baseline(self):
        self.assertEqual(self.result(), (None, None, None, None))
        self.assertEqual(self.result(negative=120), (None, None, None, None))

    def test_previous_negative_does_not_change_historical_credit(self):
        self.assertEqual(self.result(positive=250), self.result(negative=220, positive=250))

    def test_first_positive_is_frozen_when_a_later_page_omits_the_problem(self):
        first = snapshot.observe(None, accepted=True, requested_at=80, observed_at=81)
        second = snapshot.observe(first, accepted=False, requested_at=150, observed_at=151)
        self.assertTrue(second["conflict"])
        self.assertEqual(second["first_seen_at"], 81)
        self.assertIsNotNone(snapshot.classify(second, problem_id="P1001")[0])

    def test_old_requests_do_not_move_the_snapshot_backwards(self):
        current = snapshot.observe(None, accepted=False, requested_at=120, observed_at=121)
        stale = snapshot.observe(current, accepted=True, requested_at=110, observed_at=130)
        self.assertEqual(stale, current)

    def test_local_history_counts_without_backdating_an_ac_timestamp(self):
        proof = snapshot.classify(snapshot.local_positive(201), problem_id="P1001")[0]
        self.assertEqual(proof["source"], "local_luogu_ac_set")
        self.assertEqual(proof["observed_at"], 201)
        self.assertIsNone(proof["accepted_at"])

    def test_legacy_manual_late_decision_cannot_override_historical_ac(self):
        review = {"decision":"late", "reviewed_at":300, "due_at":200, "reason":"旧审核"}
        self.assertEqual(self.result(positive=250), self.result(positive=250, review=review))


class SnapshotMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_old_database_gains_fields_without_backfilling_evidence_or_changing_tasks(self):
        import tempfile
        import sqlite3
        from pathlib import Path
        from feat.api.acm_api.database import connect_db
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'legacy.db'
            db = await connect_db(path)
            await db.execute("INSERT INTO training_tasks(id,title,rule,state,creator_name,created_at,updated_at) VALUES(1,'旧任务','period_ac','draft','管理员',1,1)")
            await db.commit()
            await db.close()
            with sqlite3.connect(path) as old:
                old.execute('ALTER TABLE training_tasks DROP COLUMN luogu_snapshot')
                for column in ['snapshot_json','uncertain_json','review_json','evidence_version']:
                    old.execute('ALTER TABLE training_task_progress DROP COLUMN '+column)
            old.close()
            for _ in range(2):
                db = await connect_db(path)
                task = dict(await (await db.execute('SELECT * FROM training_tasks WHERE id=1')).fetchone())
                self.assertEqual((task['title'],task['rule'],task['version'],task['luogu_snapshot']),('旧任务','period_ac',1,0))
                fields = {row['name'] for row in await (await db.execute('PRAGMA table_info(training_task_progress)')).fetchall()}
                self.assertTrue({'snapshot_json','uncertain_json','review_json','evidence_version'} <= fields)
                self.assertEqual((await (await db.execute('SELECT COUNT(*) FROM training_task_progress')).fetchone())[0],0)
                await db.close()
