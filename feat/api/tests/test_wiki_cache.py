"""Public response cache budgets and real HTTP snapshot/conditional contracts."""

import asyncio
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import test_wiki as wiki
from feat.api.app import create_app
from feat.api.acm_api.database import connect_db
from feat.api.acm_api import wiki_api as http, wiki_service as svc
from feat.api.acm_api.wiki_cache import WikiResponseCache


class WikiCacheTests(unittest.TestCase):
    def test_lru_count_and_total_byte_budget(self):
        cache = WikiResponseCache(max_entries=2, max_bytes=5, max_entry_bytes=4)
        cache.put('a', b'12', 'application/json', 'a')
        cache.put('b', b'34', 'application/json', 'b')
        self.assertIsNotNone(cache.get('a'))
        cache.put('c', b'567', 'application/json', 'c')
        self.assertIsNone(cache.get('b'))
        self.assertEqual(cache.stats(), {'entries': 2, 'bytes': 5, 'hits': 1, 'misses': 1, 'evictions': 1})
        cache.put('a', b'0', 'application/json', 'new-a')
        self.assertEqual(cache.bytes, 4)
        self.assertFalse(cache.put('large', b'12345', 'application/json', 'large'))
        self.assertEqual(cache.bytes, 4)

    def test_ttl_disabled_and_reset_namespace(self):
        now = [0]
        cache = WikiResponseCache(ttl=3, clock=lambda: now[0])
        cache.put('a', b'1', 'application/json', 'a')
        now[0] = 2.999
        self.assertIsNotNone(cache.get('a'))
        now[0] = 3
        self.assertIsNone(cache.get('a'))
        self.assertEqual(cache.bytes, 0)
        cache.put('b', b'12', 'application/json', 'b')
        generation = cache.generation
        cache.clear()
        self.assertEqual(cache.generation, generation+1)
        self.assertEqual(cache.stats()['entries'], 0)
        self.assertEqual(cache.bytes, 0)
        for config in [{'max_entries': 0}, {'max_bytes': 0}, {'ttl': 0}]:
            self.assertFalse(WikiResponseCache(**config).put('x', b'1', 'application/json', 'x'))


class WikiCacheApiTests(unittest.IsolatedAsyncioTestCase):
    # Reuse the established cookie/database fixture without inheriting its test cases.
    asyncSetUp = wiki.WikiTests.asyncSetUp
    asyncTearDown = wiki.WikiTests.asyncTearDown
    account_login = wiki.WikiTests.account_login
    call = wiki.WikiTests.call
    cat = wiki.WikiTests.cat
    tree = wiki.WikiTests.tree
    page = wiki.WikiTests.page
    publish = wiki.WikiTests.publish
    save = wiki.WikiTests.save

    async def seed(self):
        top, child = await self.tree()
        page = await self.publish(await self.page(child['id']))
        return top, child, page

    async def test_whitelist_hits_and_304_skip_queries_and_serialization(self):
        top, child, page = await self.seed()
        paths = ['/wiki/navigation', f'/wiki/categories/{child["id"]}', '/wiki/pages', '/wiki/search?q=DSU']
        first = [await self.anon.get('/api'+p) for p in paths]
        with patch.object(svc, 'navigation', side_effect=AssertionError('navigation recomputed')), \
             patch.object(svc, 'page_list', side_effect=AssertionError('list recomputed')), \
             patch.object(http, 'jsonify', side_effect=AssertionError('serialized again')):
            for path, original in zip(paths, first):
                tag = original.headers['ETag']
                warm = await self.anon.get('/api'+path)
                self.assertEqual(warm.status_code, 200)
                self.assertEqual(await warm.get_data(), await original.get_data())
                self.assertIn('desc="hit"', warm.headers['Server-Timing'])
                for tags in [tag, 'W/'+tag, '"unrelated", W/'+tag, '*']:
                    result = await self.anon.get('/api'+path, headers={'If-None-Match': tags})
                    self.assertEqual(result.status_code, 304, tags)
                    self.assertEqual(await result.get_data(), b'')
                miss = await self.anon.get('/api'+path, headers={'If-None-Match': '"other"'})
                self.assertEqual(miss.status_code, 200)

    async def test_draft_preserves_public_etag_publish_and_move_invalidate(self):
        top, child, page = await self.seed()
        original = await self.anon.get('/api/wiki/pages')
        tag = original.headers['ETag']
        draft = await self.save(page, title='待发布私有标题', body='私有新正文')
        stable = await self.anon.get('/api/wiki/pages', headers={'If-None-Match': tag})
        self.assertEqual(stable.status_code, 304)
        self.assertNotIn('待发布私有标题', (await original.get_data()).decode())
        published = await self.publish(draft)
        newer = await self.anon.get('/api/wiki/pages', headers={'If-None-Match': tag})
        self.assertEqual(newer.status_code, 200)
        self.assertEqual((await newer.get_json())['items'][0]['title'], '待发布私有标题')
        other = await self.cat('其他分类', top['id'])
        await self.call(f'/admin/wiki/pages/{page["id"]}', {'category_id': other['id'], 'version': published['version']}, method='PATCH')
        self.assertEqual((await self.call(f'/wiki/pages?category_id={child["id"]}'))['total'], 0)
        self.assertEqual((await self.call(f'/wiki/pages?category_id={other["id"]}'))['total'], 1)
        nav = await self.call('/wiki/navigation')
        counts = {c['id']: c['published_count'] for c in nav['categories']}
        self.assertEqual((counts[top['id']], counts[child['id']], counts[other['id']]), (1, 0, 1))
        self.assertTrue(all('draft_count' not in c for c in nav['categories']))
        admin = await self.call('/admin/wiki/categories')
        self.assertEqual(next(c for c in admin['categories'] if c['id']==other['id'])['draft_count'], 0)

    async def test_parameters_normalized_isolated_and_errors_never_cached(self):
        top, child, page = await self.seed()
        one = await self.anon.get('/api/wiki/search?q=DSU')
        with patch.object(svc, 'page_list', side_effect=AssertionError('equivalent query missed')):
            equivalent = await self.anon.get('/api/wiki/search?q=%20DSU%20&page=01&page_size=20&ignored=anything')
            self.assertEqual(await equivalent.get_data(), await one.get_data())
        for query, total in [('q=absent', 0), ('q=DSU&page=2', 1), ('q=DSU&page_size=1', 1), (f'q=DSU&category_id={top["id"]}', 1)]:
            result = await self.call('/wiki/search?'+query)
            self.assertEqual(result['total'], total)
            if 'page=2' in query: self.assertEqual(result['items'], [])
        cache = self.app.extensions['wiki_public_cache']
        count = cache.stats()['entries']
        for path in ['/wiki/pages?page=0', '/wiki/pages?page_size=51', '/wiki/pages?category_id=-1', '/wiki/search?q=', '/wiki/search?q='+'x'*101]:
            await self.call(path, status=400)
        await self.call('/wiki/categories/999', status=404)
        self.assertEqual(cache.stats()['entries'], count)
        admin = await self.client.get('/api/admin/wiki/categories')
        self.assertEqual(admin.headers['Cache-Control'], 'private, no-store')
        self.assertNotIn('Server-Timing', admin.headers)
        self.assertEqual((await self.anon.get('/api/admin/wiki/categories')).status_code, 401)
        self.assertEqual((await self.client.patch('/api/admin/wiki/categories/1', json={})).status_code, 403)
        self.assertEqual(cache.stats()['entries'], count)

    async def test_snapshot_does_not_pair_old_version_with_new_content(self):
        await self.seed()
        ready, release = asyncio.Event(), asyncio.Event()
        settings = svc.settings
        intercept = True
        async def pause_after_snapshot(db):
            nonlocal intercept
            value = await settings(db)
            if intercept:
                intercept = False
                ready.set()
                await release.wait()
            return value
        with patch.object(svc, 'settings', pause_after_snapshot):
            request = asyncio.create_task(self.anon.get('/api/wiki/navigation'))
            try:
                await asyncio.wait_for(ready.wait(), 5)
                await self.cat('并发写入的新分类')
            finally:
                release.set()
            old = await asyncio.wait_for(request, 5)
        old_data = await old.get_json()
        self.assertNotIn('并发写入的新分类', str(old_data))
        new = await self.anon.get('/api/wiki/navigation', headers={'If-None-Match': old.headers['ETag']})
        self.assertEqual(new.status_code, 200)
        self.assertIn('并发写入的新分类', str(await new.get_json()))
        self.assertGreater((await new.get_json())['navigation_version'], old_data['navigation_version'])

    async def test_worker_versions_app_database_isolation_and_restore_reset(self):
        await self.seed()
        worker = create_app()
        self.assertIsNot(worker.extensions['wiki_public_cache'], self.app.extensions['wiki_public_cache'])
        async with worker.test_app():
            client = worker.test_client()
            old = await client.get('/api/wiki/navigation')
            await self.cat('另一工作进程可见的分类')
            new = await client.get('/api/wiki/navigation', headers={'If-None-Match': old.headers['ETag']})
            self.assertEqual(new.status_code, 200)
            self.assertIn('另一工作进程可见的分类', str(await new.get_json()))
            # Restore procedures reset every live worker, even if restored versions repeat.
            for app in [self.app, worker]: app.extensions['wiki_public_cache'].clear()
            db = await connect_db(self.db_path)
            await db.execute("UPDATE wiki_categories SET name='恢复后的名称' WHERE id=1")
            await db.commit(); await db.close()
            for active_client in [client, self.anon]:
                restored = await active_client.get('/api/wiki/navigation')
                self.assertIn('恢复后的名称', str(await restored.get_json()))
        with patch.dict(os.environ, {'ACM_DATABASE_PATH': str(Path(self.temp_dir.name)/'other.db')}):
            other = create_app()
        async with other.test_app():
            result = await other.test_client().get('/api/wiki/navigation')
            self.assertEqual((await result.get_json())['categories'], [])

    async def test_cache_bypass_size_and_article_maintainer_dependency(self):
        await self.seed()
        before = await self.call('/wiki/pages/dsu', client=self.anon)
        await self.call('/wiki/navigation')
        self.app.config['WIKI_CACHE_ENABLED'] = False
        with patch.object(svc, 'navigation', wraps=svc.navigation) as query:
            for _ in range(2):
                response = await self.anon.get('/api/wiki/navigation')
                self.assertEqual(response.status_code, 200)
                self.assertIn('desc="bypass"', response.headers['Server-Timing'])
            self.assertEqual(query.call_count, 2)
        self.app.config['WIKI_CACHE_ENABLED'] = True
        self.app.extensions['wiki_public_cache'] = WikiResponseCache(max_entry_bytes=1)
        response = await self.anon.get('/api/wiki/navigation')
        self.assertEqual(response.status_code, 200)
        self.assertIn('desc="skip"', response.headers['Server-Timing'])
        self.assertEqual(self.app.extensions['wiki_public_cache'].stats()['entries'], 0)
        db = await connect_db(self.db_path)
        await db.execute("UPDATE users SET name='改名后的维护者' WHERE qq_id='12345678'")
        await db.commit(); await db.close()
        after = await self.call('/wiki/pages/dsu', client=self.anon)
        self.assertNotEqual(before['maintainer'], after['maintainer'])
        self.assertEqual(after['maintainer'], '改名后的维护者')

    async def test_failures_and_cancellation_release_read_transaction_and_connection(self):
        await self.seed()
        original = http.get_db
        opened, statements = [], []
        async def tracked():
            db = await original()
            await db.set_trace_callback(statements.append)
            opened.append(db)
            return db
        for failure in ['query', 'serialization', 'cancel']:
            self.app.extensions['wiki_public_cache'].clear()
            async with self.app.test_request_context('/api/wiki/navigation'):
                with patch.object(http, 'get_db', tracked):
                    if failure == 'query':
                        with patch.object(svc, 'navigation', side_effect=RuntimeError('query failed')):
                            with self.assertRaises(RuntimeError): await http.navigation()
                    elif failure == 'serialization':
                        with patch.object(http, 'jsonify', side_effect=TypeError('json failed')):
                            with self.assertRaises(TypeError): await http.navigation()
                    else:
                        ready = asyncio.Event()
                        async def wait_forever(db):
                            ready.set()
                            await asyncio.Event().wait()
                        with patch.object(svc, 'navigation', wait_forever):
                            task = asyncio.create_task(http.navigation())
                            await asyncio.wait_for(ready.wait(), 5)
                            task.cancel()
                            with self.assertRaises(asyncio.CancelledError): await task
            self.assertEqual(self.app.extensions['wiki_public_cache'].stats()['entries'], 0)
            with self.assertRaises(ValueError): await opened[-1].execute('SELECT 1')
            self.assertIn('ROLLBACK', statements)
            self.assertNotIn('BEGIN IMMEDIATE', statements)
            response = await self.anon.get('/api/wiki/navigation')
            self.assertEqual(response.status_code, 200)

    async def test_index_initialization_idempotent_and_public_sql_omits_draft_statistics(self):
        top, child, page = await self.seed()
        await self.save(page, title='私有待发布')
        for _ in range(2):
            db = await connect_db(self.db_path)
            plan = await svc.rows(db, 'EXPLAIN QUERY PLAN SELECT id FROM wiki_pages WHERE category_id=?', (child['id'],))
            self.assertIn('wiki_pages_category', str(plan))
            await db.close()
        db = await connect_db(self.db_path)
        queries = []
        await db.set_trace_callback(queries.append)
        public = await svc.navigation(db)
        self.assertNotIn('draft_count', ' '.join(queries))
        queries.clear()
        admin = await svc.navigation(db, True)
        self.assertIn('draft_count', ' '.join(queries))
        self.assertEqual([c['published_count'] for c in public['categories']], [c['published_count'] for c in admin['categories']])
        self.assertEqual(next(c for c in admin['categories'] if c['id']==top['id'])['draft_count'], 1)
        await db.close()


    async def test_warm_navigation_tracks_category_operations_and_historical_visibility(self):
        top, child, page = await self.seed()
        alternate = await self.cat('备用大类')
        async def changed(action):
            old = await self.anon.get('/api/wiki/navigation')
            result = await action()
            new = await self.anon.get('/api/wiki/navigation', headers={'If-None-Match': old.headers['ETag']})
            self.assertEqual(new.status_code, 200)
            self.assertNotEqual(old.headers['ETag'], new.headers['ETag'])
            return result, await new.get_json()
        async def rename():
            state = await self.call('/admin/wiki/categories')
            return await self.call(f'/admin/wiki/categories/{child["id"]}', {'name': '新版子类', 'version': state['navigation_version']}, method='PATCH')
        _, nav = await changed(rename)
        self.assertIn('新版子类', str(nav))
        async def order():
            state = await self.call('/admin/wiki/categories')
            return await self.call('/admin/wiki/categories/order', {'parent_id': None, 'ids': [alternate['id'], top['id']], 'version': state['navigation_version']}, method='PUT')
        _, nav = await changed(order)
        self.assertEqual(nav['categories'][0]['id'], alternate['id'])
        async def default():
            state = await self.call('/admin/wiki/categories')
            return await self.call('/admin/wiki/settings', {'default_category_id': alternate['id'], 'version': state['navigation_version']}, method='PUT')
        _, nav = await changed(default)
        self.assertEqual(nav['default_category_id'], alternate['id'])
        async def delete():
            preview = await self.call(f'/admin/wiki/categories/{top["id"]}/delete-preview', {})
            return await self.call(f'/admin/wiki/categories/{top["id"]}/delete', {'token': preview['token'], 'target_id': alternate['id'], 'idempotency_key': 'cache-delete-top'})
        removed, nav = await changed(delete)
        self.assertNotIn(top['id'], [c['id'] for c in nav['categories']])
        _, nav = await changed(lambda: self.call(f'/admin/wiki/category-operations/{removed["operation_id"]}/restore', {}))
        self.assertIn(top['id'], [c['id'] for c in nav['categories']])
        page = await self.call(f'/admin/wiki/pages/{page["id"]}')
        draft = await self.save(page, title='替代公开版本')
        current = await self.publish(draft)
        old_revision = page['published_revision_id']
        await self.call(f'/wiki/pages/dsu/revisions/{old_revision}', client=self.anon)
        _, nav = await changed(lambda: self.call(f'/admin/wiki/revisions/{old_revision}', {'hidden': True, 'version': current['version']}, method='PATCH'))
        await self.call(f'/wiki/pages/dsu/revisions/{old_revision}', client=self.anon, status=404)
        self.assertEqual((await self.call('/wiki/pages/dsu', client=self.anon))['title'], '替代公开版本')
