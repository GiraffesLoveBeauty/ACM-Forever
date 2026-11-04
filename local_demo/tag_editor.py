"""Local administrator overlay. Reuses the existing V0.3 journal; never writes predictions."""
from copy import deepcopy
from uuid import uuid4
import json
import re

from annotation_api.adapter import digest
from annotation_api.storage import now
from label_pipeline import TAG_BY_ID, TAXONOMY
from tag_management.model import (empty_state, effective_ids, ordered, resolve_tag,
                                  validate_state, verification_fingerprint)
from tag_management.service import TagManager


class EditConflict(ValueError):
    pass


class LocalTagEditor:
    def __init__(self, labels):
        self.labels = labels

    @staticmethod
    def version(auto, state, events):
        return digest({'auto': auto, 'state': state,
                       'last': events[-1]['event_id'] if events else None})

    def detail(self, key):
        manager = self.labels.manager()
        auto = manager._auto(key)
        events, states = manager.journal.read()
        own = [e for e in events if e['problem_key'] == key]
        state = states.get(key, empty_state())
        view = manager._view(auto, state, own)
        view['revision'] = self.version(auto, state, own)
        # The full automatic snapshot and other problems' history stay on disk.
        view['history'] = [self.event_view(e) for e in reversed(own)]
        return view

    @staticmethod
    def event_view(event):
        return {k: deepcopy(event[k]) for k in
                ('event_id', 'operation', 'actor', 'reason', 'created_at', 'before', 'after', 'details')}

    def change(self, key, payload, actor):
        from ai_execution import problem_guard
        try:
            with problem_guard(self.labels,key):
                return self._change(key,payload,actor)
        except EditConflict:
            raise
        except ValueError as exc:
            if '其他进程' in str(exc):
                raise EditConflict('该题的 AI 或人工任务正在运行，请稍后重新加载。') from None
            raise

    def _change(self, key, payload, actor):
        if not isinstance(payload, dict) or set(payload) - {
                'operation', 'tag_ids', 'reason', 'revision', 'request_id'}:
            raise ValueError('修改参数不合法')
        operation = payload.get('operation')
        if operation not in {'save', 'undo', 'reset', 'verify'}:
            raise ValueError('不支持的人工操作')
        reason, revision, request_id = (payload.get(k) for k in ('reason', 'revision', 'request_id'))
        if not isinstance(reason, str) or not 2 <= len(reason.strip()) <= 300:
            raise ValueError('请填写 2 至 300 字的修改原因')
        if not isinstance(revision, str) or not re.fullmatch('[a-f0-9]{64}', revision):
            raise ValueError('缺少当前版本，请重新加载题目')
        if not isinstance(request_id, str) or not re.fullmatch('[a-f0-9-]{32,36}', request_id):
            raise ValueError('缺少有效操作编号')
        tags = payload.get('tag_ids', [])
        if not isinstance(tags, list) or len(tags) > len(TAG_BY_ID) or (operation != 'save' and tags):
            raise ValueError('标签参数不合法')
        chosen = [resolve_tag(t) for t in tags]
        if len(set(chosen)) != len(chosen):
            raise ValueError('同一标签不能重复选择')
        chosen = ordered(chosen)
        request_hash = digest({'operation': operation, 'tags': chosen, 'reason': reason.strip(),
                               'revision': revision, 'actor': actor})
        repo = self.labels.repo
        # Lock order is catalog -> journal, the same order used by publication.
        with repo.lock.locked():
            folder = repo.current()
            manager = TagManager(folder / 'auto_tags.jsonl', self.labels.override_file)
            with manager.journal.locked():
                # Bootstrap from a read-only snapshot journal without editing it.
                baseline = self.labels.manager()
                events, states = baseline.journal.read()
                auto = manager._auto(key)
                own = [e for e in events if e['problem_key'] == key]
                for event in own:
                    if event['details'].get('request_id') == request_id:
                        if event['details'].get('request_hash') != request_hash:
                            raise EditConflict('操作编号已用于其他修改，请重新加载')
                        return {'changed': False, 'replayed': True, 'message': '该操作已保存，未重复写入',
                                'event_id': event['event_id']}
                before = deepcopy(states.get(key, empty_state()))
                if self.version(auto, before, own) != revision:
                    raise EditConflict('题目或人工记录已被更新。请重新加载后对照修改，当前草稿未提交。')
                after = deepcopy(before)
                details = {'request_id': request_id, 'request_hash': request_hash,
                           'interface': 'local_tag_management', 'action': operation}
                if operation == 'save':
                    wanted = set(chosen)
                    previous = set(effective_ids(auto, before))
                    if wanted == previous:
                        return {'changed': False, 'message': '标签未变化，无需保存'}
                    added = (set(before['added_tag_ids']) & wanted) | (wanted - set(auto['tag_ids']))
                    removed = (set(before['removed_tag_ids']) | (previous - wanted) |
                               (set(auto['tag_ids']) - wanted)) - wanted
                    after['added_tag_ids'] = ordered(added - removed)
                    after['removed_tag_ids'] = ordered(removed)
                    after['verified_fingerprint'] = None
                    if not (before['added_tag_ids'] or before['removed_tag_ids'] or before['verified_fingerprint']):
                        after['anchor_content_hash'] = auto['content_hash']
                    details.update(added_ids=ordered(wanted - previous), removed_ids=ordered(previous - wanted))
                    event_operation = 'replace'  # Existing journal before/after state contract.
                elif operation == 'undo':
                    if not own:
                        return {'changed': False, 'message': '没有可撤销的人工操作'}
                    after = deepcopy(own[-1]['before'])
                    details['undo_event_id'] = own[-1]['event_id']
                    event_operation = 'undo'
                elif operation == 'reset':
                    after = empty_state()
                    event_operation = 'reset'
                else:
                    if auto['issues'] or not auto['content_hash']:
                        raise ValueError('自动结果异常或缺少题面哈希，不能完整确认')
                    after['anchor_content_hash'] = auto['content_hash']
                    after['verified_fingerprint'] = verification_fingerprint(auto, after)
                    event_operation = 'verify'
                after = validate_state(after)
                if after == before:
                    return {'changed': False, 'message': '状态未变化，操作已跳过'}
                event = {'schema_version': 1, 'event_id': uuid4().hex,
                         'previous_event_id': events[-1]['event_id'] if events else None,
                         'problem_key': key, 'operation': event_operation, 'created_at': now(),
                         'actor': actor, 'reason': reason.strip(), 'taxonomy_version': TAXONOMY['version'],
                         'before': before, 'after': after, 'automatic_snapshot': deepcopy(auto), 'details': details}
                manager.journal.write(events + [event])
                return {'changed': True, 'event_id': event['event_id'], 'message': '人工修正已保存，原始自动标签保持不变'}


def register_tag_management(app, labels):
    from quart import Response, jsonify, request, session
    from feat.api.acm_api.backend_api import admin_required
    editor = LocalTagEditor(labels)

    @app.get('/api/secondary/tag-management')
    @admin_required
    async def tag_catalog():
        return jsonify(items=labels.views(), taxonomy=[{'id': k, 'name_zh': v['name_zh'], 'tag_kind': v['tag_kind']}
                       for k, v in TAG_BY_ID.items()], taxonomy_version=TAXONOMY['version'],
                       mode='isolated_local_overlay', real_api_calls=0)

    @app.get('/api/secondary/tag-management/export')
    @admin_required
    async def export_manual_history():
        events, _ = labels.manager().journal.read()
        # Exact existing JSONL journal schema; includes no credentials or problem statements.
        body = ''.join(json.dumps(event, ensure_ascii=False, allow_nan=False) + '\n' for event in events)
        return Response(body, content_type='application/x-ndjson; charset=utf-8',
                        headers={'Content-Disposition': 'attachment; filename="manual-tags.jsonl"'})

    @app.route('/api/secondary/tag-management/<platform>/<problem_id>', methods=['GET', 'POST'])
    @admin_required
    async def tag_detail(platform, problem_id):
        item = labels.find(platform, problem_id)
        if item is None:
            return jsonify(message='没有找到该题目的持久标签'), 404
        key = item['problem_key']
        try:
            if request.method == 'POST':
                check_source = app.config.get('LOCAL_MANUAL_SOURCE_CHECK')
                if check_source and not await check_source(platform, problem_id):
                    return jsonify(message='爬虫题面版本已变化或不可用，请核对版本后重新加载；草稿未写入。', code='edit_conflict'), 409
                if request.content_length and request.content_length > 16000:
                    return jsonify(message='修改内容过大'), 413
                payload = await request.get_json(silent=True)
                result = editor.change(key, payload, 'forum_admin:' + str(session.get('webui_qq_id')))
                return jsonify(**result, detail=editor.detail(key))
            return jsonify(editor.detail(key))
        except EditConflict as exc:
            return jsonify(message=str(exc), code='edit_conflict'), 409
        except ValueError as exc:
            return jsonify(message=str(exc)), 400
