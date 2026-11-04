"""Single-question web execution, durable receipts, and existing executor integration."""
import json
from contextlib import closing
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys

from annotation_api.adapter import digest
from annotation_api.config import Config
from annotation_api.dispatch import request_settings
from annotation_api.storage import atomic_json, now
from problem_processing.backup import checked_path
from problem_processing.execution_state import Ledger
from problem_processing.executor import bind_plan, execute_batch
from problem_processing.planning import Planner, historical_problem, semantic_inputs, task_policies
from problem_processing.translation import current_translation
from tag_management.model import empty_state
from tag_management.storage import Journal

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = 'https://kitsune2.yukirin.me/v1'
MODEL = 'gpt-6-luna'
TASKS = {'annotation', 'translation'}
ACTIVE = {'queued', 'running'}


class ExecutionConflict(ValueError):
    pass


def load_web_config():
    # Only this checkout's dedicated relay .env; never inherit browser/environment overrides.
    from dotenv import dotenv_values
    values = dotenv_values(ROOT/'experiments/tags/ACM_Forever_Chinese_Tags_V0.3/.env')
    cfg = Config(provider='compatible',model=values.get('OPENAI_MODEL') or '',
        api_key=values.get('OPENAI_API_KEY') or '',base_url=values.get('OPENAI_BASE_URL') or '',
        timeout=90,max_retries=0,request_interval=0,max_output_tokens=4000,
        response_format=values.get('ANNOTATION_RESPONSE_FORMAT') or 'json_schema',
        token_parameter=values.get('ANNOTATION_TOKEN_PARAMETER') or 'max_completion_tokens')
    if cfg.base_url.rstrip('/') != BASE_URL or cfg.model != MODEL:
        raise ValueError('Relay configuration requires administrator review')
    return cfg


def problem_guard(labels, key):
    return Journal(labels.root.parent/'local_ai_execution/coordination'/(digest(key)+'.jsonl')).locked()


class WebAIService:
    def __init__(self, labels, database, *, config_loader=load_web_config, launcher=None):
        self.labels = labels
        self.database = checked_path(database)
        self.store = checked_path(labels.root.parent/'local_ai_execution')
        self.config_loader = config_loader
        self.launcher = launcher or self._launch

    def source(self, platform, problem_id):
        from admin_processing import prepare_crawler
        uri = self.database.as_uri()+'?mode=ro'
        with closing(sqlite3.connect(uri,uri=True,timeout=5)) as db:
            db.row_factory=sqlite3.Row
            row=db.execute('SELECT platform,problem_id,contest_id,problem_index,problem_name,problem_url,tags,'
                'metadata_json,statement_html,statement_text,statement_language,requested_language,samples,'
                'sample_count,statement_source_url,statement_sha256,last_fetch_status,'
                'length(statement_pdf)>0 AS has_pdf FROM crawler_problems WHERE platform=? AND problem_id=?',
                (platform,problem_id)).fetchone()
        if row is None:
            raise LookupError('爬虫题库中不存在该题')
        return prepare_crawler(dict(row))

    def check_actor(self, actor):
        with closing(sqlite3.connect(self.database.as_uri()+'?mode=ro',uri=True,timeout=5)) as db:
            account=db.execute('SELECT role,is_active,must_change_password FROM web_accounts WHERE qq_id=?',(actor,)).fetchone()
        if not account or account[0] not in {'admin','root'} or not account[1] or account[2]:
            raise ExecutionConflict('执行权限已失效，只有有效的 admin/root 账号可以调用 AI。')

    def manual_version(self, key):
        events,states=self.labels.manager().journal.read() if self.labels.repo.current() else ([],{})
        own=[e for e in events if e['problem_key']==key]
        state=states.get(key,empty_state())
        return digest({'state':state,'last':own[-1]['event_id'] if own else None}),bool(
            state['added_tag_ids'] or state['removed_tag_ids'] or state['verified_fingerprint'])

    def accepted_translation(self, p, records):
        row=current_translation(self.labels.root,p)
        if not row or row.get('processing_policy') != task_policies()['translation']:
            return False
        if row.get('problem_key') != p['problem_key'] or str(row.get('translation_model','')).startswith('mock'):
            return False
        if any(r['state'] in {'claimed','dispatched','uncertain'} for r in records):
            return False
        fp=row.get('activation_audit_id')
        if fp and re.fullmatch('[a-f0-9]{64}',fp):
            path=self.labels.root/'translations/activations'/(fp+'.json')
            audit=json.loads(checked_path(path).read_text(encoding='utf-8'))
            task=Ledger(self.labels.root).load(audit['source_task_id'])
            if (audit['decision']!='accept_for_local_website' or audit['accepted_result_sha256']!=digest(row)
                or audit['problem_key']!=p['problem_key'] or task['problem_key']!=p['problem_key']
                or task['task_type']!='translation' or task['state'] not in {'blocked','completed'}
                or task['identity']['mode']!='live' or task['identity']['input_semantic_hash']!=digest(semantic_inputs(p)[1])
                or audit['source_response_sha256']!=task['response_sha256']):
                return False
            if any(r['state']=='blocked' and r['task_id']!=task['task_id'] for r in records):return False
            Ledger(self.labels.root).artifact('responses',task['attempt_id'],task['response_sha256'])
            return True
        task_id=row.get('execution_task_id')
        task=Ledger(self.labels.root).load(task_id) if isinstance(task_id,str) and re.fullmatch('[a-f0-9]{64}',task_id) else None
        if not task or task['state']!='completed' or task['problem_key']!=p['problem_key']:
            return False
        return Ledger(self.labels.root).artifact('results',task_id,task['result_sha256'])['result']==row

    def proposal(self, p, task_type):
        if task_type not in TASKS:
            raise ValueError('不支持的 AI 任务类型')
        cfg=None
        try: cfg=self.config_loader()
        except (ValueError,OSError): pass
        planner=Planner(self.labels.root)
        plan=planner.plan([p]);entry=plan['entries'][0]
        status=entry[task_type]['status'];reason=entry[task_type].get('reason','输入需核验')
        manual,protected=self.manual_version(p['problem_key'])
        if p['processing_status']=='ready':
            if task_type=='translation':
                records=[r for r in Ledger(self.labels.root).records() if r['problem_key']==p['problem_key'] and r['task_type']==task_type]
                previous=planner.problems.get(p['problem_key'])
                original=historical_problem(previous) if previous else None
                # Source-export hashes have different semantics. Prove equivalence without rewriting either.
                equivalent=original and semantic_inputs(original)[1]==semantic_inputs(p)[1]
                if self.accepted_translation(original if equivalent else p,records):
                    status,reason='reuse_existing','已有与当前正文匹配的译文，直接复用，不再计费。'
            elif protected:
                status,reason='needs_review','人工修正优先，禁止 AI 覆盖；请使用人工标签管理。'
        settings=request_settings(cfg) if cfg else None
        revision=digest({'problem_key':p['problem_key'],'task_type':task_type,
            'semantic_input':semantic_inputs(p)[0 if task_type=='annotation' else 1],
            'verified_content_hash':p['verified_content_hash'],'plan_id':plan['plan_id'],
            'manual':manual,'settings':settings,'status':status})
        return {'status':status,'reason':reason,'revision':revision,'can_execute':bool(cfg and status=='needs_'+task_type),
            'config_ready':cfg is not None,'request_settings':settings,'timeout_seconds':90,'max_retries':0,
            'maximum_requests':1,'manual_protected':protected if task_type=='annotation' else False,
            'cost_notice':'单题最多新增一次生成请求，费用以中转站账单为准；超时或未知结果不自动重试。'}

    def job_path(self, job_id):
        if not isinstance(job_id,str) or not re.fullmatch('[a-f0-9]{64}',job_id):
            raise ValueError('无效任务编号')
        return checked_path(self.store/'jobs'/(job_id+'.json'))

    def read(self, job_id):
        path=self.job_path(job_id)
        if not path.exists():raise LookupError('没有找到执行记录')
        return json.loads(path.read_text(encoding='utf-8'))

    def latest(self, platform, problem_id):
        result={}
        for path in sorted((self.store/'jobs').glob('*.json')):
            row=json.loads(checked_path(path).read_text(encoding='utf-8'))
            if row['platform']==platform and row['problem_id']==problem_id:
                previous=result.get(row['task_type'])
                if previous is None or row['updated_at']>previous['updated_at']:
                    result[row['task_type']]=self.public(row)
        return result

    @staticmethod
    def public(job):
        return {k:job[k] for k in ('job_id','platform','problem_id','task_type','status','created_at','updated_at',
            'message','real_api_calls','usage','model','elapsed_seconds','error') if k in job}

    def submit(self, p, platform, problem_id, task_type, revision, actor):
        if task_type not in TASKS or not isinstance(revision,str) or not re.fullmatch('[a-f0-9]{64}',revision):
            raise ValueError('请先检查题目和执行配置')
        job_id=digest({'problem_key':p['problem_key'],'task_type':task_type,'revision':revision})
        with Journal(self.store/'writer.jsonl').locked():
            if self.job_path(job_id).exists():return self.public(self.read(job_id))
            proposal=self.proposal(p,task_type)
            if proposal['revision']!=revision:raise ExecutionConflict('题面、配置或处理状态已变化，请重新检查后再执行。')
            if proposal['status'] in {'reuse_existing','not_required'}:
                return {'status':'reuse_existing','message':'已有结果已复用，无需新增 API 请求。','real_api_calls':0}
            if not proposal['can_execute']:raise ExecutionConflict(proposal['reason'] if proposal['config_ready'] else 'API 配置不可用，请检查本地配置。')
            if any(json.loads(path.read_text(encoding='utf-8'))['status'] in ACTIVE for path in (self.store/'jobs').glob('*.json')):
                raise ExecutionConflict('已有 AI 任务正在运行；请等待完成。未解决的任务需先核验，不能自动重发。')
            job={'version':1,'job_id':job_id,'platform':platform,'problem_id':problem_id,'problem_key':p['problem_key'],
                'task_type':task_type,'revision':revision,'request_settings':proposal['request_settings'],'actor':actor,
                'status':'queued','message':'已登记单题任务，等待执行。','created_at':now(),'updated_at':now(),'real_api_calls':0}
            atomic_json(self.job_path(job_id),job)
            try:self.launcher(job_id)
            except Exception:
                job.update(status='failed_before_dispatch',message='执行进程未能启动，没有发送请求。',updated_at=now())
                atomic_json(self.job_path(job_id),job)
            return self.public(job)

    def _launch(self, job_id):
        if self.labels.root.resolve()!=(ROOT/'data/labels').resolve() or self.database.resolve()!=(ROOT/'local_demo/runtime/forum-demo.sqlite3').resolve():
            raise ValueError('Worker must use the isolated local forum data')
        env={k:v for k,v in os.environ.items() if not k.startswith(('OPENAI_','ANTHROPIC_','ACM_','TAG_'))}
        subprocess.Popen([sys.executable,'-B','-X','utf8',str(ROOT/'local_demo/ai_worker.py'),'--job',job_id],
            cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),close_fds=True)

    def run(self, job_id, *, client=None):
        job=self.read(job_id)
        with Journal(self.store/'worker-locks'/(job_id+'.jsonl')).locked():
            job=self.read(job_id)
            if job['status']!='queued':return self.public(job)
            job.update(status='running',message='正在执行单题任务，请勿重复提交。',updated_at=now())
            atomic_json(self.job_path(job_id),job)
            try:
                with problem_guard(self.labels,job['problem_key']):
                    self.check_actor(job['actor'])
                    p=self.source(job['platform'],job['problem_id'])
                    proposal=self.proposal(p,job['task_type'])
                    if proposal['revision']!=job['revision'] or not proposal['can_execute']:
                        raise ExecutionConflict('执行前状态已变化，请重新检查；没有新增请求。')
                    cfg=self.config_loader()
                    if cfg.max_retries!=0 or request_settings(cfg)!=job['request_settings']:
                        raise ExecutionConflict('执行配置发生变化，请重新检查。')
                    manual=self.manual_version(p['problem_key'])[0]
                    def check_source():
                        self.check_actor(job['actor'])
                        current=self.source(job['platform'],job['problem_id'])
                        if (semantic_inputs(current)!=semantic_inputs(p) or current['verified_content_hash']!=p['verified_content_hash']
                            or self.manual_version(p['problem_key'])[0]!=manual):
                            raise ExecutionConflict('题面或人工修正已变化，禁止继续发送或激活结果。')
                    def checkpoint(stage, row):check_source()
                    if client is None:
                        from annotation_api.client import APIClient
                        class SourceBoundClient(APIClient):
                            def _check_dispatch(self, request):
                                check_source()
                                super()._check_dispatch(request)
                        client=SourceBoundClient(cfg)
                        owned=True
                    else:owned=False
                    try:
                        plan=Planner(self.labels.root).plan([p])
                        outcome=execute_batch([p],job['task_type'],root=self.labels.root,config=cfg,execute=True,
                            client=client,plan=bind_plan(plan,job['task_type'],request_settings(cfg)),limit=1,checkpoint=checkpoint)
                    finally:
                        if owned:client.close()
                    result=outcome['results'][0];saved=result.get('result') or {}
                    job.update(status=result['status'],real_api_calls=outcome['real_api_calls'],usage=saved.get('usage'),
                        model=saved.get('model'),elapsed_seconds=saved.get('elapsed_seconds'),error=result.get('error'),
                        message='任务完成，结果已独立保存；自动结果尚未人工确认。' if result['status']=='completed' else
                            '已有结果已复用。' if result['status']=='reuse_existing' else '任务已停止。请先核对保存记录，不要重复发起付费请求。')
            except Exception:
                records=[r for r in Ledger(self.labels.root).records() if r['problem_key']==job['problem_key'] and r['task_type']==job['task_type']]
                dispatched=any(r['state'] in {'dispatched','uncertain'} for r in records)
                job.update(status='uncertain' if dispatched else 'blocked',error='execution_requires_review',
                    message='任务状态需要核验，已禁止自动重试。' if dispatched else '配置、题面或任务状态已变化，执行已停止。')
            job['updated_at']=now();atomic_json(self.job_path(job_id),job)
            return self.public(job)


def register_ai_execution(app, labels):
    from quart import jsonify, request, session
    from feat.api.acm_api.backend_api import admin_required
    service=WebAIService(labels,app.config['DB_PATH'])
    app.extensions['local_ai_execution']=service

    @app.post('/api/admin/problem-processing/<platform>/<problem_id>/execute')
    @admin_required
    async def execute_problem(platform, problem_id):
        if request.content_length and request.content_length>3000:return jsonify(message='执行参数过大'),413
        payload=await request.get_json(silent=True)
        if (not isinstance(payload,dict) or set(payload)!={'task_type','revision','confirm'} or payload.get('confirm') is not True):
            return jsonify(message='请明确确认单题执行，不能从请求修改模型、地址或任务数量。'),400
        try:
            p=service.source(platform,problem_id)
            result=service.submit(p,platform,problem_id,payload['task_type'],payload['revision'],str(session.get('webui_qq_id')))
            return jsonify(result),202 if result['status'] in ACTIVE else 200
        except LookupError:return jsonify(message='题库中没有找到该题'),404
        except ExecutionConflict as exc:return jsonify(message=str(exc)),409
        except (ValueError,OSError,KeyError,TypeError,sqlite3.Error):return jsonify(message='输入、配置或持久状态无法验证，未启动任务。'),400

    @app.get('/api/admin/problem-processing/jobs/<job_id>')
    @admin_required
    async def job_status(job_id):
        try:return jsonify(service.public(service.read(job_id)))
        except LookupError:return jsonify(message='没有找到该任务'),404
        except (ValueError,OSError,KeyError,TypeError):return jsonify(message='任务记录需核验'),400
