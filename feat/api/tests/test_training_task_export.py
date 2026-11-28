import io
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from openpyxl import load_workbook

import test_training_tasks as task_contract
from feat.api.acm_api import cf_history
from feat.api.acm_api import training_task_api as task_api
from feat.api.acm_api import training_task_progress as progress
from feat.api.acm_api import training_task_service as service
from feat.api.acm_api.database import connect_db


class TrainingExportTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = task_contract.TrainingTaskTests.asyncSetUp
    asyncTearDown = task_contract.TrainingTaskTests.asyncTearDown
    sql = task_contract.TrainingTaskTests.sql
    seed = task_contract.TrainingTaskTests.seed
    draft = task_contract.TrainingTaskTests.draft
    create = task_contract.TrainingTaskTests.create
    preview = task_contract.TrainingTaskTests.preview
    publish = task_contract.TrainingTaskTests.publish

    async def info(self, task_id, **query):
        response = await self.client.get(f"/api/admin/training-tasks/{task_id}/progress", query_string=query)
        self.assertEqual(response.status_code, 200, await response.get_json())
        return await response.get_json()

    async def set_evidence(self, task_id, problem_id, field, *, qq="22345678", timestamp=None):
        self.assertIn(field, {"on_time_json", "history_json", "late_json", "uncertain_json"})
        await self.sql(f"""UPDATE training_task_progress SET {field}=?
            WHERE recipient_id=(SELECT id FROM training_task_recipients WHERE task_id=? AND qq_id=?)
            AND problem_id=(SELECT id FROM training_task_problems WHERE task_id=? AND problem_id=?)""",
            (json.dumps({"accepted_at": timestamp, "evidence_type": "test"}), task_id, qq, task_id, problem_id))

    async def test_cells_follow_frozen_problem_order_not_completed_count(self):
        task = await self.create(problems=[{"problem_id": "2A"}, {"problem_id": "1A"}, {"problem_id": "3A"}])
        self.assertEqual((await self.publish(task)).status_code, 200)
        await self.set_evidence(task["id"], "cf_1A", "on_time_json", timestamp=self.now - 10)
        data = await self.info(task["id"])
        member = data["items"][0]
        self.assertEqual(member["completed_problems"], 1)
        self.assertEqual([c["problem_id"] for c in member["problem_cells"]], ["cf_2A", "cf_1A", "cf_3A"])
        self.assertEqual([c["completed"] for c in member["problem_cells"]], [False, True, False])
        self.assertEqual(member["problem_cells"][1]["accepted_at"], self.now - 10)
        recipient = await (await self.client.get(f'/api/admin/training-tasks/{task["id"]}/progress/{member["id"]}')).get_json()
        self.assertEqual([c["completed"] for c in recipient["problems"]], [False, True, False])
        # Filtering/paging must retain the same cell ordering, not compact the ACs.
        filtered = await self.info(task["id"], search="22345678", page_size=1)
        self.assertEqual(filtered["items"][0]["problem_cells"], member["problem_cells"])

    async def test_cells_respect_cf_rule_timing_and_luogu_historical_ac(self):
        task = await self.create(problems=[{"problem_id": "1A"}, {"problem_id": "2A"}, {"problem_id": "3A"}])
        await self.publish(task)
        await self.set_evidence(task["id"], "cf_1A", "history_json", timestamp=self.now - 500)
        await self.set_evidence(task["id"], "cf_2A", "uncertain_json")
        await self.set_evidence(task["id"], "cf_3A", "late_json", timestamp=self.now + 200)
        member = (await self.info(task["id"]))["items"][0]
        self.assertEqual([c["completed"] for c in member["problem_cells"]], [False, False, True])
        self.assertEqual([c["status"] for c in member["problem_cells"]], ["history_ac", "timing_unknown", "late"])
        self.assertEqual(member["completed_problems"], sum(c["completed"] for c in member["problem_cells"]))
        upcoming = {**task, "starts_at": self.now + 100, "rule": "historical_ac"}
        row = {"platform": "codeforces", "history_json": '{"accepted_at": 1}'}
        self.assertFalse(progress.problem_completion(row, upcoming, self.now)["completed"])
        self.assertTrue(progress.problem_completion(row, {**task, "rule": "historical_ac"}, self.now)["completed"])
        luogu = {"platform": "luogu", "problem_id": "P1001", "history_json": '{"accepted_at": null}'}
        self.assertTrue(progress.problem_completion(luogu, upcoming, self.now)["completed"])
        self.assertFalse(progress.problem_completion({**row, "platform": "atcoder"}, task, self.now)["completed"])

    async def test_excel_contains_all_members_ordered_cells_and_literal_text(self):
        for index in range(21):
            await self.seed(str(32345000 + index))
        await self.sql("UPDATE users SET real_name='=SUM(1,2)',name='@literal' WHERE qq_id='22345678'")
        task = await self.create(title="=SUM(4,5)", description="说明\x01\n第二行",
                                 problems=[{"problem_id": "2A"}, {"problem_id": "1A"}, {"problem_id": "3A"}])
        await self.publish(task)
        await self.set_evidence(task["id"], "cf_1A", "on_time_json", timestamp=self.now - 10)
        listing = await self.info(task["id"], page_size=20)
        self.assertEqual((listing["total"], len(listing["items"])), (22, 20))
        before = await self.sql("SELECT * FROM training_task_progress ORDER BY recipient_id,problem_id")
        network = AsyncMock(side_effect=AssertionError("exports must not contact OJs"))
        with patch.object(cf_history, "cf_request", network):
            response = await self.client.get(f'/api/admin/training-tasks/{task["id"]}/export', query_string={"page": 2, "page_size": 1, "search": "no match"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertIn(f'training-task-{task["id"]}.xlsx', response.headers["Content-Disposition"])
        workbook = load_workbook(io.BytesIO(await response.get_data()))
        self.addCleanup(workbook.close)
        self.assertEqual(workbook.sheetnames, ["训练概况", "成员进度", "题目列表"])
        overview, matrix, problems = (workbook[name] for name in workbook.sheetnames)
        metadata = dict(overview.iter_rows(min_row=2, values_only=True))
        self.assertEqual(metadata["训练标题"], "=SUM(4,5)")
        self.assertEqual(metadata["训练说明"], "说明\n第二行")
        self.assertEqual(metadata["固定接收人数"], 22)
        self.assertEqual(matrix.max_row, 23)
        self.assertEqual(matrix["A2"].value, "=SUM(1,2)")
        self.assertEqual(matrix["B2"].value, "@literal")
        self.assertEqual(matrix["C2"].value, "22345678")
        self.assertEqual(matrix["C2"].data_type, "s")
        self.assertEqual([matrix.cell(2, i).value for i in (5, 6, 10, 11, 12)], [1, 3, "未确认 AC", "AC", "未确认 AC"])
        self.assertEqual(matrix["K2"].fill.fgColor.rgb, "00A982FF")
        self.assertNotEqual(matrix["J2"].fill.fgColor.rgb, matrix["K2"].fill.fgColor.rgb)
        self.assertEqual([r[2] for r in problems.iter_rows(min_row=2, values_only=True)], ["cf_2A", "cf_1A", "cf_3A"])
        self.assertEqual(matrix.freeze_panes, "E2")
        self.assertEqual(matrix.auto_filter.ref, "A1:L23")
        for sheet in workbook:
            for row in sheet:
                for cell in row:
                    self.assertNotEqual(cell.data_type, "f", (sheet.title, cell.coordinate))
        network.assert_not_called()
        self.assertEqual(await self.sql("SELECT * FROM training_task_progress ORDER BY recipient_id,problem_id"), before)

    async def test_export_permissions_missing_task_and_draft(self):
        task = await self.create()
        url = f'/api/admin/training-tasks/{task["id"]}/export'
        self.assertEqual((await self.client.get(url)).status_code, 409)
        self.assertEqual((await self.client.get('/api/admin/training-tasks/999999/export')).status_code, 404)
        await self.publish(task)
        anonymous = self.app.test_client()
        self.assertEqual((await anonymous.get(url)).status_code, 401)
        member = self.app.test_client()
        await member.post('/api/auth/login', json={"qq_id": "22345678", "password": "Test-Password-123!"})
        self.assertEqual((await member.get(url)).status_code, 403)
        await self.set_evidence(task["id"], "cf_1A", "on_time_json", timestamp=self.now - 10)
        await self.sql("UPDATE users SET account_state='closed',account_epoch=account_epoch+1 WHERE qq_id='22345678'")
        response = await self.client.get(url)
        workbook = load_workbook(io.BytesIO(await response.get_data()))
        self.addCleanup(workbook.close)
        self.assertEqual(workbook["成员进度"]["A2"].value, "已注销成员")
        self.assertIsNone(workbook["成员进度"]["C2"].value)
        self.assertEqual(workbook["成员进度"]["J2"].value, "AC")

    async def test_luogu_historical_cells_before_start_and_cancelled_task_export(self):
        task = await self.create(starts_at=self.now + 100, due_at=self.now + 400,
                                 problems=[{"platform": "luogu", "problem_id": "P1002"}, {"platform": "luogu", "problem_id": "P1001"}])
        self.assertEqual((await self.publish(task)).status_code, 200)
        await self.set_evidence(task["id"], "P1001", "history_json")
        member = (await self.info(task["id"]))["items"][0]
        self.assertEqual(member["completed_problems"], 1)
        self.assertEqual([cell["completed"] for cell in member["problem_cells"]], [False, True])
        self.assertIsNone(member["problem_cells"][1]["accepted_at"])
        await self.set_evidence(task["id"], "P1002", "history_json")
        url = f'/api/admin/training-tasks/{task["id"]}/export'
        with patch.object(task_api, "time", SimpleNamespace(time=lambda: self.now + 200)):
            response = await self.client.get(url)
        self.assertEqual(response.status_code, 200)
        workbook = load_workbook(io.BytesIO(await response.get_data()))
        self.addCleanup(workbook.close)
        self.assertEqual(workbook["成员进度"]["G2"].value, "已完成")
        self.assertEqual([workbook["成员进度"].cell(2, i).value for i in (10, 11)], ["AC（历史）", "AC（历史）"])
        cancelled = await self.client.post(f'/api/admin/training-tasks/{task["id"]}/cancel', headers=self.headers,
                                           json={"version": 2, "reason": "留档测试"})
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual((await self.client.get(url)).status_code, 200)

    async def test_cell_queries_are_batched_and_exports_cross_sqlite_variable_limits(self):
        task = await self.create()
        await self.publish(task)
        members = (await self.info(task["id"]))["items"]
        recipients = [{"id": members[0]["id"]}, *({"id": index} for index in range(10000, 11100))]
        db = await connect_db(self.db_path)
        try:
            with patch.object(service, "rows", wraps=service.rows) as reads:
                await progress.add_problem_cells(db, task, recipients, now=self.now)
                self.assertEqual(reads.call_count, 3)
            self.assertEqual(len(recipients[0]["problem_cells"]), 1)
            self.assertEqual(recipients[-1]["problem_cells"], [])
        finally:
            await db.close()


if __name__ == "__main__":
    unittest.main()
