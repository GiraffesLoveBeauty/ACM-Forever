import unittest
from pathlib import Path
from PIL import Image
import test_forum_notifications as fixture


class ForumRevisionTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixture.ForumNotificationTests.asyncSetUp
    asyncTearDown = fixture.ForumNotificationTests.asyncTearDown
    post = fixture.ForumNotificationTests.post
    comment = fixture.ForumNotificationTests.comment
    sql = fixture.ForumNotificationTests.sql

    async def edit(self, pid):
        response = await self.owner.post(f'/api/forum/mine/posts/{pid}/edit', headers=self.headers[self.owner], json={})
        self.assertIn(response.status_code, (200, 201), await response.get_json())
        return (await response.get_json())['id']

    async def save(self, did, **extra):
        state = await (await self.owner.get(f'/api/forum/drafts/{did}')).get_json()
        response = await self.owner.put(f'/api/forum/drafts/{did}', headers=self.headers[self.owner], json={'title': '补充后的算法题解', 'body': '修改后的完整思路和实现。', 'category_id': 2, 'edit_version': state.get('edit_version'), **extra})
        self.assertEqual(response.status_code, 200)

    async def submit(self, did, expected=201):
        state = await (await self.owner.get(f'/api/forum/drafts/{did}')).get_json()
        response = await self.owner.post(f'/api/forum/drafts/{did}/submit', headers=self.headers[self.owner], json={'edit_version': state.get('edit_version')})
        self.assertEqual(response.status_code, expected, await response.get_json())
        return await response.get_json()

    async def test_owner_only_csrf_and_reuse_one_draft(self):
        pid = await self.post()
        for client, status in [(self.public, 401), (self.other, 404), (self.admin, 404)]:
            response = await client.post(f'/api/forum/mine/posts/{pid}/edit', headers=self.headers.get(client, {}), json={})
            self.assertEqual(response.status_code, status)
        self.assertEqual((await self.owner.post(f'/api/forum/mine/posts/{pid}/edit', json={})).status_code, 403)
        did = await self.edit(pid)
        self.assertEqual(await self.edit(pid), did)
        self.assertEqual((await self.other.get(f'/api/forum/drafts/{did}')).status_code, 404)

    async def test_stale_tab_cannot_overwrite_or_submit_another_tabs_draft(self):
        pid = await self.post()
        did = await self.edit(pid)
        old = await (await self.owner.get(f'/api/forum/drafts/{did}')).get_json()
        await self.save(did)
        stale_save = await self.owner.put(f'/api/forum/drafts/{did}', headers=self.headers[self.owner], json={'title': '过时的草稿内容', 'body': '不应覆盖新草稿。', 'category_id': 2, 'edit_version': old['edit_version']})
        self.assertEqual(stale_save.status_code, 409)
        stale_submit = await self.owner.post(f'/api/forum/drafts/{did}/submit', headers=self.headers[self.owner], json={'edit_version': old['edit_version']})
        self.assertEqual(stale_submit.status_code, 409)
        self.assertEqual((await self.public.get(f'/api/forum/posts/{pid}')).status_code, 200)

    async def test_published_edit_preserves_identity_and_discussion_requires_review(self):
        pid = await self.post()
        cid = await self.comment(pid)
        await self.other.post(f'/api/forum/posts/{pid}/like', headers=self.headers[self.other], json={})
        did = await self.edit(pid)
        await self.save(did)
        self.assertEqual((await self.public.get(f'/api/forum/posts/{pid}')).status_code, 200)
        self.assertEqual((await self.submit(did))['id'], pid)
        self.assertEqual((await self.public.get(f'/api/forum/posts/{pid}')).status_code, 404)
        progress = await (await self.owner.get(f'/api/forum/mine/posts/{pid}')).get_json()
        self.assertEqual(progress['content_version'], 2)
        self.assertEqual(progress['status'], 'pending')
        self.assertIsNone(progress['reviewed_at'])
        self.assertNotEqual(progress['history'][0]['body'], progress['body'])
        response = await self.admin.post(f'/api/forum/moderation/posts/{pid}', headers=self.headers[self.admin], json={'decision': 'publish', 'content_version': 2})
        self.assertEqual(response.status_code, 200)
        public = await (await self.public.get(f'/api/forum/posts/{pid}')).get_json()
        self.assertEqual(public['title'], '补充后的算法题解')
        self.assertEqual(public['comments'][0]['id'], cid)
        self.assertEqual(public['likes_count'], 1)
        self.assertNotIn('history', public)

    async def test_new_draft_stale_submit_keeps_latest_draft_until_confirmed(self):
        created = await self.owner.post('/api/forum/drafts', headers=self.headers[self.owner], json={
            'title': '两个标签页的普通新帖', 'body': '第一份尚未提交的正文。', 'category_id': 2,
        })
        self.assertEqual(created.status_code, 201)
        old = await created.get_json()
        did = old['id']
        await self.save(did)
        stale = await self.owner.post(f'/api/forum/drafts/{did}/submit', headers=self.headers[self.owner], json={'edit_version': old['edit_version']})
        self.assertEqual(stale.status_code, 409)
        current = await (await self.owner.get(f'/api/forum/drafts/{did}')).get_json()
        self.assertEqual(current['title'], '补充后的算法题解')
        self.assertEqual(current['body'], '修改后的完整思路和实现。')
        self.assertGreater(current['edit_version'], old['edit_version'])
        self.assertEqual(await self.sql('SELECT id FROM forum_posts'), [])
        submitted = await self.submit(did)
        post = await (await self.owner.get(f"/api/forum/mine/posts/{submitted['id']}")).get_json()
        self.assertEqual(post['body'], current['body'])
        self.assertEqual((await self.owner.get(f'/api/forum/drafts/{did}')).status_code, 404)

    async def test_new_draft_legacy_submit_without_version_remains_supported(self):
        created = await self.owner.post('/api/forum/drafts', headers=self.headers[self.owner], json={
            'title': '旧客户端的普通新帖', 'body': '旧客户端没有版本字段。', 'category_id': 2,
        })
        did = (await created.get_json())['id']
        await self.save(did)
        submitted = await self.owner.post(f'/api/forum/drafts/{did}/submit', headers=self.headers[self.owner], json={})
        self.assertEqual(submitted.status_code, 201)

    async def test_revision_submit_requires_version_and_json_object(self):
        pid = await self.post()
        did = await self.edit(pid)
        for payload, expected in [({}, 409), ({'edit_version': None}, 409), (['invalid'], 400)]:
            with self.subTest(payload=payload):
                response = await self.owner.post(f'/api/forum/drafts/{did}/submit', headers=self.headers[self.owner], json=payload)
                self.assertEqual(response.status_code, expected)
                self.assertEqual((await self.owner.get(f'/api/forum/drafts/{did}')).status_code, 200)

    async def test_rejection_reason_archived_and_resubmit_is_same_post(self):
        pid = await self.post(publish=False)
        await self.admin.post(f'/api/forum/moderation/posts/{pid}', headers=self.headers[self.admin], json={'decision': 'reject', 'reason': '请补充正确性证明'})
        did = await self.edit(pid)
        await self.save(did)
        await self.submit(did)
        progress = await (await self.owner.get(f'/api/forum/mine/posts/{pid}')).get_json()
        self.assertEqual(progress['review_reason'], '')
        self.assertEqual(progress['history'][0]['review_reason'], '请补充正确性证明')
        self.assertEqual(progress['history'][0]['status'], 'rejected')
        self.assertEqual((await self.sql('SELECT COUNT(*) AS n FROM forum_posts'))[0]['n'], 1)
        await self.submit(did, 404)

    async def test_stale_review_cannot_publish_replaced_content(self):
        pid = await self.post(publish=False)
        did = await self.edit(pid)
        await self.save(did)
        await self.submit(did)
        for body in [{'decision': 'publish'}, {'decision': 'publish', 'content_version': 1}]:
            response = await self.admin.post(f'/api/forum/moderation/posts/{pid}', headers=self.headers[self.admin], json=body)
            self.assertEqual(response.status_code, 409)
        self.assertEqual((await self.public.get(f'/api/forum/posts/{pid}')).status_code, 404)

    async def test_changed_review_or_deleted_post_blocks_submit_and_keeps_draft(self):
        for removed in (False, True):
            pid = await self.post(publish=False)
            did = await self.edit(pid)
            await self.save(did)
            if removed:
                await self.owner.delete(f'/api/forum/posts/{pid}', headers=self.headers[self.owner])
            else:
                await self.admin.post(f'/api/forum/moderation/posts/{pid}', headers=self.headers[self.admin], json={'decision': 'reject', 'reason': '状态已经变化'})
            await self.submit(did, 409)
            self.assertEqual((await self.owner.get(f'/api/forum/drafts/{did}')).status_code, 200)
            self.assertEqual(await self.sql('SELECT id FROM forum_post_history WHERE post_id=?', (pid,)), [])

    async def test_invalid_assets_roll_back_content_and_history(self):
        pid = await self.post()
        did = await self.edit(pid)
        await self.save(did)
        # Simulate a previously valid asset going missing before submission.
        await self.sql('UPDATE forum_drafts SET cover_image_id=? WHERE id=?', ('a'*32, did))
        await self.submit(did, 400)
        self.assertEqual((await self.public.get(f'/api/forum/posts/{pid}')).status_code, 200)
        self.assertEqual(await self.sql('SELECT id FROM forum_post_history WHERE post_id=?', (pid,)), [])

    async def test_reused_shared_image_can_be_kept_private_during_re_review(self):
        pid = await self.post()
        asset = 'b' * 32
        folder = Path(self.directory.name) / 'shared-assets'
        folder.mkdir()
        self.app.config['MARKDOWN_UPLOAD_DIR'] = folder
        Image.new('RGB', (1, 1), 'white').save(folder / (asset + '.webp'), 'WEBP')
        body = f'原帖复用的图片：![说明](/api/markdown/assets/{asset})'
        await self.sql("INSERT INTO markdown_assets VALUES(?,?,'image/webp',1,1,1,'10000002','forum_draft',999,1)", (asset, asset + '.webp'))
        await self.sql("INSERT INTO markdown_asset_references VALUES(?,'forum_post',?,0)", (asset, pid))
        await self.sql('UPDATE forum_posts SET body=? WHERE id=?', (body, pid))
        did = await self.edit(pid)
        await self.save(did, body=body)
        await self.submit(did)
        for client, expected in [(self.owner, 200), (self.admin, 200), (self.third, 404), (self.public, 404)]:
            self.assertEqual((await client.get('/api/markdown/assets/' + asset)).status_code, expected)
        # An unrelated author cannot copy the now-private source into another post.
        response = await self.third.post('/api/forum/posts', headers=self.headers[self.third], json={'title': '不可复制的私有图片', 'body': body, 'category_id': 2})
        self.assertEqual(response.status_code, 400)
