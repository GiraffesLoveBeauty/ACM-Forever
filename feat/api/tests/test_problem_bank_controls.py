"""Offline contracts for #147: full collection, schedules and native ranges."""
import asyncio
import json
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import urlencode

import aiosqlite
import test_problem_sync as contract
import test_luogu_problems as luogu
from feat.api.acm_api import problem_schedule
from feat.api.acm_api.atcoder_difficulty import MODELS_URL, apply_models
from feat.api.acm_api.database import connect_db
from feat.api.acm_api.luogu_problem import canonical_problem_id, metadata, normalize_taxonomy, save_taxonomy
from feat.api.acm_api.luogu_sync import LuoguSync
from feat.api.acm_api.problem_bank import save_metadata_batch, save_problem
from feat.api.acm_api.problem_sync import ATCODER_CATALOG_URL, atcoder_catalog_metadata, cf_metadata, sync_options
from feat.api.acm_api.problem_time import time_options
from feat.api.service_runtime import WebTaskManager

TAXONOMY = normalize_taxonomy({"ProblemDifficulty": [
    {"id": 0, "name": "暂无评定", "color": "grey-3"},
    {"id": 3, "name": "普及", "color": "gold-3"},
    {"id": 4, "name": "普及+/提高−", "color": "green-3"},
    {"id": 5, "name": "提高", "color": "cyan-3"}]}, luogu.TAGS)


class TimeAndModelContracts(unittest.TestCase):
    def test_time_boundaries_require_timezone_and_are_exclusive(self):
        value = sync_options({"platform": "codeforces", "scope": "platform", "start_at": "2026-11-01T08:00:00+08:00", "end_at": "2026-11-02T00:00:00Z"})
        self.assertEqual(value["start_at"], 1793491200)
        self.assertEqual(value["end_at"]-value["start_at"], 86400)
        self.assertEqual(value["time_basis"], "contest")
        self.assertEqual(time_options({"end_at": "200"}, "luogu"), {"end_at":200,"time_basis":"first_seen"})
        for payload in ({"start_at": True}, {"start_at":"2026-11-01T00:00"}, {"start_at":200,"end_at":200},
                        {"start_at":-1}, {"time_basis":"first_seen"}, {"start_at":200,"end_at":100}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                sync_options({"platform":"luogu","scope":"platform",**payload})
        with self.assertRaises(ValueError):
            sync_options({"platform":"luogu","scope":"platform","start_at":100,"time_basis":"contest"})
        with self.assertRaises(ValueError):
            sync_options({"platform":"atcoder","contest_id":"abc370","start_at":100})
        self.assertNotIn("start_at",sync_options({"platform":"luogu","scope":"platform"}))
        self.assertIsNone(sync_options({"platform":"luogu","scope":"platform"})["limit"])

    def test_atcoder_model_scale_missing_and_source_are_preserved(self):
        items=atcoder_catalog_metadata(contract.CATALOG)
        apply_models(items,json.dumps({"abc370_a":{"difficulty":0,"is_experimental":True},"abc371_a":{"difficulty":1200}}))
        self.assertEqual([item["problem_rating"] for item in items],[147,1200,None])
        self.assertEqual(items[0]["difficulty_raw"],0)
        self.assertTrue(items[0]["difficulty_is_experimental"])
        self.assertEqual(items[0]["difficulty_source"],"atcoder_problems")
        self.assertTrue(items[2]["difficulty_missing"])
        with self.assertRaises(ValueError):
            apply_models(items,'[]')


class ProblemBankControlsTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=contract.ProblemSyncTests.asyncSetUp
    asyncTearDown=contract.ProblemSyncTests.asyncTearDown
    login=contract.ProblemSyncTests.login
    query=contract.ProblemSyncTests.query
    write=contract.ProblemSyncTests.write
    submit_platform=contract.ProblemSyncTests.submit_platform

    async def seed(self):
        db=await connect_db(self.db_path)
        try:
            items=[]
            for contest,rating in ((100,1200),(101,1800),(102,None)):
                items.extend(cf_metadata([{"index":"A","name":"Synthetic CF","rating":rating}],str(contest)))
            items += [metadata(luogu.problem("P1100",difficulty=3),TAXONOMY),
                      metadata(luogu.problem("P1101",difficulty=4,tags=[-2]),TAXONOMY),
                      metadata(luogu.problem("P1102",difficulty=5),TAXONOMY),
                      metadata(luogu.problem("P1103",difficulty=0),TAXONOMY)]
            await save_taxonomy(db,TAXONOMY)
            await save_metadata_batch(db,items)
            await db.executemany("INSERT INTO crawler_contests(platform,contest_id,contest_name,start_time,updated_at) VALUES('codeforces',?,'Synthetic',?,0)",[("100",100),("101",200),("102",None)])
            await db.execute("UPDATE crawler_problems SET created_at='2026-11-01T00:00:00+00:00'")
            await db.execute("UPDATE crawler_problems SET created_at='2026-11-02T00:00:00+00:00' WHERE problem_id='P1101'")
            await db.commit()
        finally:
            await db.close()

    async def test_ranges_and_tag_intersection_apply_before_count_and_pagination(self):
        await self.seed()
        async with self.app.test_app():
            client=self.app.test_client();await self.login(client)
            for endpoint in ("/api/problems","/api/me/problems","/api/admin/database/problems"):
                response=await client.get(endpoint+"?platform=codeforces&rating_min=1200&rating_max=1800&page_size=1")
                self.assertEqual(response.status_code,200,await response.get_json())
                data=await response.get_json();self.assertEqual(data["total"],2)
                self.assertEqual(data["items"][0]["problem_id"],"cf_101A")
                data=await (await client.get(endpoint+"?platform=luogu&native_difficulty_min=3&native_difficulty_max=4")).get_json()
                self.assertEqual(data["total"],2)
                self.assertEqual(data["items"][0]["problem_id"],"P1101")
                data=await (await client.get(endpoint+"?platform=luogu&native_difficulty_min=3&native_difficulty_max=4&native_tags=-2,1")).get_json()
                self.assertEqual((data["total"],data["items"][0]["problem_id"]),(1,"P1100"))
                for bad in ("platform=luogu&rating_min=1","platform=codeforces&rating_min=1800&rating_max=1200","platform=luogu&native_difficulty_min=4&native_difficulty_max=3","platform=codeforces&native_tags=1"):
                    self.assertEqual((await client.get(endpoint+"?"+bad)).status_code,400)

    async def seed_classification_aliases(self, rows):
        db = await connect_db(self.db_path)
        try:
            items = []
            for pid, difficulty, tags, updated_at in rows:
                item = metadata(luogu.problem(canonical_problem_id(pid), difficulty=difficulty, tags=tags), TAXONOMY)
                items.append({**item, "problem_id": pid})
            await save_taxonomy(db, TAXONOMY)
            await save_metadata_batch(db, items)
            await db.executemany(
                "UPDATE crawler_problems SET updated_at=? WHERE platform='luogu' AND problem_id=?",
                [(updated_at, pid) for pid, _, _, updated_at in rows],
            )
            await db.commit()
        finally:
            await db.close()

    async def test_native_filters_and_display_prefer_the_canonical_record(self):
        await self.seed_classification_aliases([
            ("P1100", 4, [-2], "2026-11-10T00:00:00+00:00"),
            ("luogu_P1100", 3, [-2, 1], "2026-11-15T00:00:00+00:00"),
            ("p1100", 5, [1], "2026-11-15T00:00:00+00:00"),
        ])
        async with self.app.test_app():
            client = self.app.test_client()
            await self.login(client)
            for endpoint in ("/api/problems", "/api/me/problems", "/api/admin/database/problems"):
                for query in ("native_difficulty=3", "native_difficulty_min=3&native_difficulty_max=3",
                              "native_tags=-2,1", "native_difficulty=5"):
                    with self.subTest(endpoint=endpoint, query=query):
                        response = await client.get(endpoint + "?platform=luogu&" + query)
                        self.assertEqual(response.status_code, 200)
                        data = await response.get_json()
                        self.assertEqual(data["total"], 0)
                        self.assertEqual(data["items"], [])
                for query in ("", "native_difficulty_min=4&native_difficulty_max=4&native_tags=-2"):
                    response = await client.get(endpoint + "?platform=luogu&" + query)
                    self.assertEqual(response.status_code, 200)
                    data = await response.get_json()
                    self.assertGreater(data["total"], 0)
                    self.assertEqual(data["total"], len(data["items"]))
                    for row in data["items"]:
                        self.assertEqual(row["problem_id"], "P1100")
                        self.assertEqual(row["native_difficulty"]["id"], 4)
                        self.assertEqual([tag["id"] for tag in row["native_tags"]], [-2])

    async def test_native_filters_and_display_share_a_deterministic_alias_fallback(self):
        await self.seed_classification_aliases([
            ("p1101", 4, [-2], "2026-11-10T00:00:00+00:00"),
            ("LUOGU_p1101", 3, [1], "2026-11-15T00:00:00+00:00"),
            ("luogu_P1102", 3, [-2, 1], "2026-11-10T00:00:00+00:00"),
            ("LUOGU_p1102", 5, [1], "2026-11-15T00:00:00+00:00"),
        ])
        async with self.app.test_app():
            client = self.app.test_client()
            await self.login(client)
            for endpoint in ("/api/problems", "/api/me/problems", "/api/admin/database/problems"):
                for query, pid, difficulty, tags in (
                    ("native_difficulty=4&native_tag=-2", "P1101", 4, [-2]),
                    ("native_difficulty_min=5&native_difficulty_max=5&native_tags=1", "P1102", 5, [1]),
                ):
                    with self.subTest(endpoint=endpoint, query=query):
                        response = await client.get(endpoint + "?platform=luogu&" + query)
                        self.assertEqual(response.status_code, 200)
                        data = await response.get_json()
                        self.assertGreater(data["total"], 0)
                        self.assertEqual(data["total"], len(data["items"]))
                        for row in data["items"]:
                            self.assertEqual(row["problem_id"], pid)
                            self.assertEqual(row["native_difficulty"]["id"], difficulty)
                            self.assertEqual([tag["id"] for tag in row["native_tags"]], tags)
                data = await (await client.get(endpoint + "?platform=luogu&native_difficulty=3")).get_json()
                self.assertEqual(data["total"], 0)
                twenty = ",".join(str(value) for value in range(1, 21))
                for query in ("native_tags=" + twenty + ",21", "native_tag=-2&native_tags=" + twenty):
                    response = await client.get(endpoint + "?platform=luogu&" + query)
                    self.assertEqual(response.status_code, 400)
                response = await client.get(endpoint + "?platform=luogu&native_tag=1&native_tags=" + twenty)
                self.assertEqual(response.status_code, 200)
            for pid, difficulty in (("P1101", 4), ("P1102", 5)):
                response = await client.get("/api/me/problems/luogu/" + pid)
                self.assertEqual(response.status_code, 200)
                self.assertEqual((await response.get_json())["native_difficulty"]["id"], difficulty)

    async def test_time_boundaries_and_refresh_do_not_promote_old_problems(self):
        await self.seed()
        db=await connect_db(self.db_path)
        try:
            item,content=luogu.parse_problem(luogu.body("P1100",difficulty=3),"P1100",TAXONOMY)
            await save_problem(db,item,content)
        finally: await db.close()
        async with self.app.test_app():
            client=self.app.test_client();await self.login(client)
            for endpoint in ("/api/problems","/api/me/problems","/api/admin/database/problems"):
                data=await (await client.get(endpoint+"?platform=codeforces&time_basis=contest&start_at=100&end_at=200")).get_json()
                self.assertEqual([row["problem_id"] for row in data["items"]],["cf_100A"])
                data=await (await client.get(endpoint+"?platform=luogu&"+urlencode({"time_basis":"first_seen","start_at":"2026-11-01T00:00:00Z","end_at":"2026-11-02T00:00:00Z"}))).get_json()
                self.assertNotIn("P1101",[row["problem_id"] for row in data["items"]])
                data=await (await client.get(endpoint+"?platform=luogu")).get_json()
                self.assertEqual(data["items"][0]["problem_id"],"P1101")
                self.assertEqual(data["items"][0]["time_basis"],"first_seen")
                self.assertEqual((await client.get(endpoint+"?platform=luogu&start_at=200&end_at=100")).status_code,400)

    async def test_atcoder_collection_joins_models_and_preserves_difficulty_on_model_outage(self):
        self.models_patch.stop()
        model_mode="good"
        async def download(http,url):
            if url==ATCODER_CATALOG_URL:return json.dumps(contract.CATALOG).encode()
            if url==MODELS_URL:
                if model_mode=="failed":raise ValueError("Synthetic model outage")
                return json.dumps({"abc370_a":{"difficulty":1200,"is_experimental":True}} if model_mode=="good" else {}).encode()
            return contract.BODY
        async with self.app.test_app():
            client=self.app.test_client();headers=await self.login(client)
            with patch.object(self.app.task_manager.problem_sync,"download",side_effect=download):
                first=await self.submit_platform(client,headers)
                self.assertEqual(first["status"],"completed")
                rating=await (await client.get("/api/me/problems?platform=atcoder&rating_min=1200&rating_max=1200")).get_json()
                self.assertEqual([item["problem_id"] for item in rating["items"]],["abc370_a"])
                model_mode="failed"
                second=await self.submit_platform(client,headers)
                self.assertIn("difficulty_warning",second["result"])
                self.assertEqual((await self.query("SELECT problem_rating FROM crawler_problems WHERE problem_id='abc370_a'"))[0]["problem_rating"],1200)
                model_mode="missing"
                await self.submit_platform(client,headers)
                self.assertIsNone((await self.query("SELECT problem_rating FROM crawler_problems WHERE problem_id='abc370_a'"))[0]["problem_rating"])
                self.assertIsNone((await self.query("SELECT problem_rating FROM recommendations WHERE problem_id='abc370_a'"))[0]["problem_rating"])

    async def test_manual_time_range_filters_candidates_before_statement_download(self):
        await self.seed()
        captured=[]
        async def download(http,url): captured.append(url);return contract.CF_BODY
        async def complete(db,http,items,*args,**kwargs):return items,[]
        async with self.app.test_app():
            client=self.app.test_client();headers=await self.login(client)
            with patch("feat.api.acm_api.problem_sync.cf_request",return_value={"problems":[{"contestId":100,"index":"A","name":"old"},{"contestId":101,"index":"A","name":"new"}]}), patch("feat.api.acm_api.problem_sync.complete_cf_catalog",side_effect=complete),patch.object(self.app.task_manager.problem_sync,"download",side_effect=download):
                task=await self.submit_platform(client,headers,platform="codeforces",start_at=100,end_at=200)
            self.assertEqual(task["status"],"completed")
            self.assertEqual(task["result"]["scope_count"],1)
            self.assertEqual(len(captured),1)
            self.assertIn("/100/",captured[0])

    async def test_schedule_is_admin_csrf_protected_and_settings_survive_manager_restart(self):
        async with self.app.test_app():
            client=self.app.test_client()
            self.assertEqual((await client.get("/api/admin/problems/schedule")).status_code,401)
            headers=await self.login(client)
            self.assertEqual((await client.put("/api/admin/problems/schedule",json={"platforms":{"codeforces":False}})).status_code,403)
            for invalid in ({},{"platforms":{"bad":True}},{"platforms":{"luogu":1}}):
                self.assertEqual((await client.put("/api/admin/problems/schedule",json=invalid,headers=headers)).status_code,400)
            response=await client.put("/api/admin/problems/schedule",json={"platforms":{"codeforces":False,"luogu":True}},headers=headers)
            self.assertEqual(response.status_code,200)
            data=await response.get_json()
            self.assertFalse(data["global_enabled"])
            self.assertEqual({row["platform"]:row["enabled"] for row in data["platforms"]},{"atcoder":True,"codeforces":False,"luogu":True})
            self.assertTrue(self.app.task_manager._problem_schedule_changed.is_set())
            await self.write("UPDATE web_accounts SET role='member'")
            self.assertEqual((await client.get("/api/admin/problems/schedule")).status_code,403)
        calls=[]
        manager=WebTaskManager(SimpleNamespace(db_path=self.db_path,crawler_config={}))
        self.addAsyncCleanup(manager.close)
        async def run(options,task):calls.append(options["platform"]);task.update(status="completed",result={"success_count":0})
        manager.problem_sync.run=run
        await manager._run_daily_problem_sync()
        self.assertEqual(calls,["atcoder","luogu"])
        restarted=WebTaskManager(SimpleNamespace(db_path=self.db_path,crawler_config={}))
        self.addAsyncCleanup(restarted.close);restarted.problem_sync.run=run
        await restarted._run_daily_problem_sync()
        self.assertEqual(calls,["atcoder","luogu"])

    async def test_disabled_oj_does_not_claim_day_and_concurrent_claim_is_unique(self):
        async with aiosqlite.connect(self.db_path) as first,aiosqlite.connect(self.db_path) as second:
            await problem_schedule.update(first,{"platforms":{"luogu":False}})
            self.assertFalse(await problem_schedule.claim(first,"luogu","2026-11-16",{}))
            await problem_schedule.update(first,{"platforms":{"luogu":True}})
            claims=await asyncio.gather(problem_schedule.claim(first,"luogu","2026-11-16",{}),problem_schedule.claim(second,"luogu","2026-11-16",{}))
            self.assertEqual(sum(claims),1)
            snap=await problem_schedule.snapshot(first,{},datetime(2026,11,16,5,tzinfo=problem_schedule.TIMEZONE))
            row=next(row for row in snap["platforms"] if row["platform"]=="luogu")
            self.assertEqual(row["last_scheduled_day"],"2026-11-16")
            self.assertEqual(datetime.fromtimestamp(row["next_run_at"],problem_schedule.TIMEZONE).day,17)

    async def test_luogu_full_job_processes_more_than_1000_native_statements_without_ai(self):
        collector=LuoguSync(self.db_path)
        count=1003
        items=[metadata(luogu.problem("P"+str(2000+i)),luogu.TAXONOMY) for i in range(count)]
        async def catalog(db,http,taxonomy,task):
            await save_metadata_batch(db,items)
            task["result"].update(metadata_count=count,discovered_count=count,catalog_complete=True)
            return items
        async def download(http,path):
            self.assertTrue(path.startswith("/problem/P"))
            return luogu.body(path.rsplit("/",1)[-1])
        task={}
        with patch.object(collector,"taxonomy",return_value=luogu.TAXONOMY),patch.object(collector,"catalog",side_effect=catalog),patch.object(collector,"download",side_effect=download) as fetch:
            await collector.run(sync_options({"platform":"luogu","scope":"platform","batch_size":100}),task)
        self.assertEqual(task["status"],"completed",task["result"])
        self.assertEqual((task["result"]["success_count"],task["result"]["remaining_count"]),(count,0))
        self.assertEqual(fetch.await_count,count)
        rows=await self.query("SELECT COUNT(*) AS n FROM crawler_problems WHERE sample_count=1 AND statement_html IS NOT NULL AND problem_rating IS NULL")
        self.assertEqual(rows[0]["n"],count)
        first=(await self.query("SELECT metadata_json,samples FROM crawler_problems LIMIT 1"))[0]
        self.assertEqual(json.loads(first["metadata_json"])["luogu"]["tag_ids"],[-2,1])
        self.assertEqual(json.loads(first["samples"])[0]["output"],"50\n")
