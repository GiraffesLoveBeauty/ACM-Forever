"""Administrator workbench over crawler_problems with a separately guarded executor."""
import json

from problem_processing.adapter import normalize
from problem_processing.planning import Planner, historical_problem, semantic_inputs
from problem_processing.translation import language_plan, prepare_layout_request, translation_ready
from problem_bank_labels import project_rows, filter_bank, parse_options


def prepare_crawler(row):
    source = dict(row)
    # The adapter accepts PDF metadata without copying binary data into model input.
    source.pop('statement_pdf', None)
    for field in ('tags', 'samples'):
        if isinstance(source.get(field), str):
            source[field] = json.loads(source[field])
    return normalize(source)


def register_admin_processing(app, labels):
    from quart import jsonify, request
    from feat.api.acm_api.backend_api import admin_required, get_db

    async def manual_source_matches(platform, problem_id):
        db = await get_db()
        try:
            async with db.execute("SELECT platform,problem_id,contest_id,problem_name,problem_url,tags,metadata_json,"
                                  "statement_html,statement_text,statement_language,samples,sample_count,"
                                  "statement_source_url,statement_sha256,last_fetch_status,length(statement_pdf)>0 AS has_pdf "
                                  "FROM crawler_problems WHERE platform=? AND problem_id=?", (platform, problem_id)) as cur:
                row = await cur.fetchone()
        finally:
            await db.close()
        try:
            p = prepare_crawler(row) if row else None
            problems, _ = labels.repo.snapshot()
            return bool(p and p['processing_status'] == 'ready' and p['problem_key'] in problems and
                        semantic_inputs(p)[0] == semantic_inputs(historical_problem(problems[p['problem_key']]))[0])
        except (ValueError, TypeError, KeyError, OSError):
            return False

    app.config['LOCAL_MANUAL_SOURCE_CHECK'] = manual_source_matches

    @admin_required
    async def catalog():
        try:
            args = dict(request.args)
            args['platform'] = args.get('platform') or 'all'
            args['tag'] = args.get('q', '')
            options = parse_options(args)
            status = args.get('status', 'all')
            if status not in {'all', 'collected', 'pending', 'failed'}:
                raise ValueError('无效的采集状态')
        except ValueError as exc:
            return jsonify(message=str(exc)), 400
        db = await get_db()
        try:
            async with db.execute("SELECT platform,problem_id,contest_id,problem_index,problem_name,"
                                  "problem_rating,problem_url,tags,statement_language,sample_count,last_fetch_status,"
                                  "statement_fetched_at,updated_at,"
                                  "(COALESCE(statement_html,'')<>'' OR COALESCE(statement_text,'')<>'' "
                                  "OR COALESCE(length(statement_pdf),0)>0) AS content_available "
                                  "FROM crawler_problems ORDER BY updated_at DESC,platform,problem_id") as cur:
                rows = [dict(r) for r in await cur.fetchall()]
        finally:
            await db.close()
        rows = [r for r in rows if status == 'all'
                or status == 'collected' and r['content_available']
                or status == 'failed' and r['last_fetch_status'] == 'failed'
                or status == 'pending' and not r['content_available'] and r['last_fetch_status'] != 'failed']
        views = labels.views()
        index = {(v['platform'], v['problem_id']): v for v in views}
        projected = project_rows(rows, views)
        for row in projected:
            view = index.get((row['platform'], row['problem_id']))
            row['content_available'] = bool(row['content_available'])
            row['translation_status'] = view['translation_status'] if view else 'missing'
        result = filter_bank(projected, options)
        return jsonify(**result, data_source='crawler_problems', execution_enabled=True)

    # Enhance the existing admin list, rather than maintain a second problem catalog.
    app.view_functions['api.api_database_problems'] = catalog

    @app.get('/api/admin/problem-processing/<platform>/<problem_id>')
    @admin_required
    async def inspect_problem(platform, problem_id):
        db = await get_db()
        try:
            async with db.execute("SELECT platform,problem_id,contest_id,problem_index,problem_name,"
                                  "problem_rating,problem_url,tags,metadata_json,statement_html,statement_text,"
                                  "statement_language,requested_language,samples,sample_count,statement_source_url,"
                                  "statement_sha256,statement_fetched_at,last_fetch_status,updated_at,"
                                  "length(statement_pdf)>0 AS has_pdf "
                                  "FROM crawler_problems WHERE platform=? AND problem_id=?",
                                  (platform, problem_id)) as cur:
                row = await cur.fetchone()
        finally:
            await db.close()
        if row is None:
            return jsonify(message='爬虫题库中不存在该题'), 404
        view = labels.find(platform, problem_id)
        base = dict(data_source='crawler_problems', platform=platform, problem_id=problem_id,
                    title=row['problem_name'], content_available=bool(row['statement_text'] or row['statement_html']),
                    sample_count=row['sample_count'], real_api_calls=0, execution_enabled=True,
                    execution_notice='仅 admin/root 可显式执行单题；已有结果优先复用，不自动重试。',
                    existing=view, edit_available=False)
        try:
            p = prepare_crawler(row)
            planner = Planner(labels.root)
            plan = planner.one(p)
            language = language_plan(p)
            same_input = False
            if view and p['problem_key'] in planner.problems:
                same_input = semantic_inputs(p)[0] == semantic_inputs(historical_problem(planner.problems[p['problem_key']]))[0]
            protected = None
            if language['action'] == 'translate' and translation_ready(p):
                prepared = prepare_layout_request(p, language)
                protected = dict(segments=len(prepared['segments']), tokens=len(prepared['protected']),
                                 version=prepared['protection_version'], mode='layout_by_id',
                                 images=prepared['layout']['image_count'])
            # Respect the independent local manual overlay in addition to planner snapshot state.
            if view and view['manual_history_count']:
                plan['effective_tags'] = view['effective_tags']
                plan['manual_overlay_present'] = True
            preflight={task:app.extensions['local_ai_execution'].proposal(p,task) for task in ('annotation','translation')}
            if p['processing_status']=='html_pending' and 'image_requires_review' in p['processing_issues']:
                reason='题面包含图片，当前自动流程无法确认图片是否承载必要条件，需先复核；并非 API 配置或余额错误。原图和原文均已保留，本次不会发送请求。'
                if preflight['annotation']['status']=='pending':
                    preflight['annotation']['reason']=reason
                if translation_ready(p) and preflight['translation']['status']=='needs_translation':
                    preflight['translation']['reason']='仅翻译图片周围文字；原图及位置由本地保留，图片内文字和条件尚未翻译或核验。'
                elif not translation_ready(p) and preflight['translation']['status']=='pending':
                    preflight['translation']['reason']='原图保留，但正文还存在其他采集异常，请先检查正文完整性。'
            if view and not same_input:
                # Saved translations remain in history but must not be presented as the new source's result.
                base['existing']={**view,'translation_active':False,'translation_status':'stale',
                                  'translated_title':None,'translated_statement':None}
            return jsonify(**{**base, 'problem_key': p['problem_key'], 'edit_available': bool(view and same_input),
                              'edit_block_reason': None if view and same_input else
                              ('爬虫正文与持久化版本不一致，请先核对版本后再修正。' if view else
                               '尚未纳入标签持久目录，暂不能人工修改标签。可先执行 AI 标签或翻译；翻译无需先标注，执行器会登记原文并独立保存译文。'),
                              'processing_status': p['processing_status'], 'issues': p['processing_issues'],
                              'content_hash': p['content_hash'], 'normalized_content_hash': p['normalized_content_hash'],
                              'source_statement_sha256': p['source_statement_sha256'],
                              'annotation_input_hash': p['annotation_input_hash'],
                              'translation_input_hash': p['translation_input_hash'],
                              'statement_preview': p['original_statement'][:6000],
                              'preview_truncated': len(p['original_statement']) > 6000,
                              'source_links': p['source_links'], 'raw_tags': p['raw_tags'],
                              'language': {k: language[k] for k in ('action', 'source_language', 'reason')},
                              'image_handling_notice': '默认保留原图及其相对位置，仅翻译文字；图片内文字不翻译。' if 'image_requires_review' in p['processing_issues'] else None,
                              'protection': protected, 'plan': plan,'execution':preflight,
                              'jobs':app.extensions['local_ai_execution'].latest(platform,problem_id)})
        except (ValueError, KeyError, TypeError, OSError):
            return jsonify(**base, processing_status='invalid', issues=['invalid_input_or_evidence'],
                           edit_block_reason='题目身份、正文或持久依据异常，禁止继续处理。')
