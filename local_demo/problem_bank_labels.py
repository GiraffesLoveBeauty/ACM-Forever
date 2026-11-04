"""Local read-only catalog projection: apply effective labels before search/pagination."""
from collections import Counter
import json

from label_pipeline import TAG_BY_ID
from tag_management.model import resolve_tag


def search_text(value):
    return str(value or '').strip().casefold().replace('动态规划', 'dp').replace('动态', 'dp')


def parse_options(args):
    platform = args.get('platform', 'all')
    if platform not in {'all', 'codeforces', 'atcoder', 'nowcoder', 'luogu', 'cjlu'}:
        raise ValueError('不支持的题目平台')
    scope, state = args.get('scope', 'all'), args.get('state', '')
    mode = args.get('match', 'all')
    if scope not in {'all', 'solved'} or state not in {'', 'favorite'} or mode not in {'all', 'any'}:
        raise ValueError('题库筛选参数不合法')
    try:
        page, size = int(args.get('page', 1)), int(args.get('page_size', 20))
    except (TypeError, ValueError):
        raise ValueError('分页参数必须为整数') from None
    if not 1 <= page <= 1000000 or not 1 <= size <= 100:
        raise ValueError('分页范围不合法，每页最多 100 题')
    query = args.get('tag', '').strip()
    if len(query) > 100:
        raise ValueError('搜索词最多 100 字')
    raw = args.get('labels', '')
    if len(raw) > 5000:
        raise ValueError('选择的标签过多')
    selected = {resolve_tag(t.strip()) for t in raw.split(',') if t.strip()}
    return {'platform': platform, 'scope': scope, 'state': state, 'match': mode,
            'page': page, 'size': size, 'query': query, 'labels': selected}


def project_rows(records, effective):
    index = {(p['platform'], p['problem_id']): p for p in effective}
    result = []
    for raw in records:
        row = dict(raw)
        secondary = index.get((row['platform'], row['problem_id']))
        tags = row.get('tags') or []
        if isinstance(tags, str):
            try:
                decoded = json.loads(tags)
                tags = decoded if isinstance(decoded, list) else tags.split(',')
            except ValueError:
                tags = tags.split(',')
        row['raw_tags'] = [str(t).strip() for t in tags if str(t).strip()]
        row.update(has_secondary=secondary is not None,
                   effective_tags=secondary['effective_tags'] if secondary else [],
                   review_status=secondary['review_status'] if secondary else 'unprocessed',
                   fully_human_verified=secondary['fully_human_verified'] if secondary else False,
                   manual_history_count=secondary['manual_history_count'] if secondary else 0,
                   problem_key=secondary['problem_key'] if secondary else None)
        # Never display deleted predictions as current labels, even if the final set is empty.
        row['tags'] = [t['name_zh'] for t in row['effective_tags']] if secondary else row['raw_tags']
        result.append(row)
    return result


def filter_bank(records, options):
    base = []
    query = search_text(options['query'])
    for row in records:
        if options['platform'] != 'all' and row['platform'] != options['platform']:
            continue
        if options['scope'] == 'solved' and not row.get('ac_at'):
            continue
        if options['state'] == 'favorite' and not row.get('is_favorite'):
            continue
        terms = [row.get('problem_name'), row['problem_id'], row.get('problem_key'), row.get('contest_id')]
        terms += ([v for t in row['effective_tags'] for v in (t['id'], t['name_zh'])]
                  if row['has_secondary'] else row['raw_tags'])
        if query and not any(query in search_text(term) for term in terms):
            continue
        base.append(row)
    counts = Counter(t['id'] for row in base for t in row['effective_tags'])
    selected = options['labels']
    matched = []
    for row in base:
        ids = {t['id'] for t in row['effective_tags']}
        if selected and not (selected <= ids if options['match'] == 'all' else bool(selected & ids)):
            continue
        matched.append(row)
    start = (options['page'] - 1) * options['size']
    return {'items': matched[start:start + options['size']], 'total': len(matched),
            'returned': len(matched[start:start + options['size']]), 'page': options['page'], 'page_size': options['size'],
            'tag_facets': [{'id': k, 'name_zh': v['name_zh'], 'tag_kind': v['tag_kind'], 'count': counts[k]}
                           for k, v in TAG_BY_ID.items()],
            'label_filter_source': 'effective_tags', 'real_api_calls': 0}


def register_problem_bank_labels(app, labels):
    from quart import jsonify, request
    from feat.api.acm_api.backend_api import _PROBLEM_QUERY, get_db, member_required

    @member_required
    async def effective_problem_bank():
        try:
            options = parse_options(request.args)
        except ValueError as exc:
            return jsonify(message=str(exc)), 400
        # Identity is supplied by the existing member_required decorator, never request parameters.
        owner = request.web_identity['qq_id']
        db = await get_db()
        try:
            query = ('SELECT p.*, ac.ac_at FROM (' + _PROBLEM_QUERY + ') p LEFT JOIN '
                     '(SELECT platform,problem_id,MAX(submit_time) AS ac_at FROM submissions '
                     'WHERE user_qq_id=? GROUP BY platform,problem_id) ac '
                     'ON ac.platform=p.platform AND ac.problem_id=p.problem_id WHERE 1=1')
            params = [owner, owner]
            if options['platform'] != 'all':
                query += ' AND p.platform=?'
                params.append(options['platform'])
            if options['scope'] == 'solved':
                query += ' AND ac.ac_at IS NOT NULL'
            if options['state'] == 'favorite':
                query += ' AND p.is_favorite=1'
            query += (' ORDER BY ac.ac_at DESC,p.platform,p.problem_id' if options['scope'] == 'solved'
                      else ' ORDER BY CAST(p.problem_rating AS INTEGER),p.platform,p.problem_id')
            async with db.execute(query, params) as cursor:
                records = [dict(row) for row in await cursor.fetchall()]
            return jsonify(filter_bank(project_rows(records, labels.views()), options))
        finally:
            await db.close()

    # Explicit local-only wrapper. The original forum implementation is untouched.
    app.view_functions['api.api_me_problems'] = effective_problem_bank
