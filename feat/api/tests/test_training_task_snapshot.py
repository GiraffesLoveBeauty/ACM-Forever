"""Boundary tests for observation evidence; no invented submission timestamps."""
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

    def test_period_boundaries_and_history_are_distinct(self):
        self.assertIsNotNone(self.result(negative=100, positive=200)[1])
        self.assertIsNotNone(self.result(positive=99)[0])
        self.assertIsNotNone(self.result(positive=100)[3])
        self.assertIsNotNone(self.result(negative=99, positive=150)[3])
        self.assertIsNotNone(self.result(negative=101, positive=150)[1])
        proof = self.result(negative=100, positive=200)[1]
        self.assertIsNone(proof["accepted_at"])
        self.assertEqual((proof["observed_at"],proof["last_not_accepted_at"]), (200,100))

    def test_first_late_detection_is_uncertain_without_deadline_negative(self):
        for negative in (None, 100, 199):
            with self.subTest(negative=negative):
                history, timely, late, unknown = self.result(negative,201)
                self.assertEqual((history,timely,late),(None,None,None))
                self.assertIsNotNone(unknown)
        self.assertIsNotNone(self.result(200,202)[2])

    def test_historical_rule_still_needs_evidence_before_deadline_for_timely_credit(self):
        self.assertIsNotNone(self.result(positive=150, rule="historical_ac")[1])
        self.assertIsNotNone(self.result(positive=201, rule="historical_ac")[3])

    def test_positive_is_frozen_and_absence_never_creates_repeat_ac(self):
        first = snapshot.observe(None, accepted=True, requested_at=80, observed_at=81)
        second = snapshot.observe(first, accepted=False, requested_at=150, observed_at=151)
        third = snapshot.observe(second, accepted=True, requested_at=180, observed_at=181)
        self.assertEqual(third["first_seen_at"], 81)
        self.assertNotIn("last_absent_at", third)
        self.assertFalse(third["conflict"])
        self.assertTrue(second["conflict"])
        self.assertIsNotNone(snapshot.classify(third, starts_at=100, due_at=200, rule="period_ac", problem_id="P1001")[0])

    def test_old_requests_do_not_move_the_snapshot_backwards(self):
        current = snapshot.observe(None, accepted=False, requested_at=120, observed_at=121)
        stale = snapshot.observe(current, accepted=True, requested_at=110, observed_at=130)
        self.assertEqual(stale, current)

    def test_local_ac_is_never_backdated(self):
        proof = snapshot.local_positive(201)
        self.assertEqual(snapshot.classify(proof,starts_at=100,due_at=200,rule="historical_ac",problem_id="P1001")[:3],(None,None,None))
        self.assertEqual(proof["source"],"local_luogu_ac_set")

    def test_extension_reclassifies_the_original_observations(self):
        value = snapshot.observe(None,accepted=False,requested_at=120,observed_at=121)
        value = snapshot.observe(value,accepted=True,requested_at=210,observed_at=211)
        args = dict(starts_at=100,rule="period_ac",problem_id="P1001")
        self.assertIsNotNone(snapshot.classify(value,due_at=200,**args)[3])
        self.assertIsNotNone(snapshot.classify(value,due_at=250,**args)[1])

    def test_review_changes_credit_without_creating_an_ac_timestamp(self):
        review={"decision":"on_time","reviewed_at":300,"reason":"核对训练现场记录"}
        proof=self.result(positive=220,review=review)[1]
        self.assertEqual((proof["evidence_type"],proof["reviewed_at"],proof["accepted_at"]),("manual",300,None))
        review["decision"]="late"
        self.assertIsNotNone(self.result(positive=220,review=review)[2])

    def test_local_positive_after_negative_is_not_a_public_delta(self):
        value = snapshot.observe(None, accepted=False, requested_at=120, observed_at=121)
        value = snapshot.observe(value, accepted=False, known_ac=True, requested_at=150, observed_at=151)
        self.assertTrue(value['conflict'])
        self.assertIsNotNone(snapshot.classify(value,starts_at=100,due_at=200,rule='period_ac',problem_id='P1001')[3])


    def test_extension_rechecks_a_late_manual_decision_against_its_original_deadline(self):
        value = snapshot.observe(None,accepted=True,requested_at=210,observed_at=211)
        review = {'decision':'late','reviewed_at':230,'due_at':200,'reason':'核对逾期补做'}
        args=dict(starts_at=100,rule='period_ac',problem_id='P1001',review=review)
        self.assertIsNotNone(snapshot.classify(value,due_at=200,**args)[2])
        self.assertIsNotNone(snapshot.classify(value,due_at=220,**args)[3])
        self.assertIsNotNone(snapshot.classify(value,due_at=240,**args)[1])


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
