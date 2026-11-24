"""Bounded Gitee HTTPS transport. Credentials enter curl through stdin, never argv/logs."""
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
import hashlib
import json
import random
from pathlib import Path
import re
import socket
import ssl
import subprocess
import tempfile
import time
import urllib.parse


def event(name, **fields):
    print(json.dumps(dict(event=name, **fields), ensure_ascii=False), flush=True)


class TransferError(RuntimeError):
    def __init__(self, kind, *, status=0, code=0, retryable=False, safe_to_retry=False, retry_after=0):
        self.kind, self.status, self.code = kind, status, code
        self.retryable, self.safe_to_retry = retryable, safe_to_retry
        self.retry_after = retry_after
        super().__init__('Gitee transfer failed: ' + kind + ' (HTTP ' + str(status) + ', curl ' + str(code) + ')')


class Budget:
    def __init__(self, seconds=900, clock=time.monotonic, sleep=time.sleep):
        self.clock, self.sleep = clock, sleep
        self.end = clock() + seconds

    def remaining(self, maximum):
        value = min(maximum, self.end - self.clock())
        if value < 1:
            raise TransferError('task_budget_exhausted')
        return value

    def pause(self, seconds):
        if seconds >= self.remaining(901):
            raise TransferError('retry_exceeds_task_budget')
        self.sleep(seconds)

    def backoff(self,seconds):
        self.pause(seconds+random.random())


@dataclass
class Reply:
    status: int
    headers: dict
    body: bytes
    size: int
    sha256: str


def config_string(value):
    if any(ord(c) < 32 for c in value):
        raise ValueError('Control characters are not allowed in curl configuration')
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def retry_after(value):
    if re.fullmatch(r'[0-9]{1,8}',value):return int(value)
    try:return max(0,int(parsedate_to_datetime(value).timestamp()-time.time())+1)
    except (ValueError,TypeError,OverflowError):return 0


class CurlTransport:
    def __init__(self, budget=None, runner=subprocess.run):
        self.budget, self.runner = budget or Budget(), runner

    def request(self, method, url, *, headers=None, data=None, upload=None, token=None, maximum=1024*1024, timeout=60, binary=False):
        if method not in ('GET','POST','PATCH'):raise ValueError('Unsupported mirror operation')
        p = urllib.parse.urlsplit(url)
        if (p.scheme != 'https' or p.hostname not in ('gitee.com', 'foruda.gitee.com', 'files.gitee.com')
                or p.username or p.password or p.port not in (None,443) or p.fragment):
            raise ValueError('Untrusted Gitee transport destination')
        if (token or data is not None or method != 'GET') and (p.hostname != 'gitee.com' or not p.path.startswith('/api/v5/repos/')):
            raise ValueError('Credentialed operations are restricted to the Gitee API')
        allowed = self.budget.remaining(timeout)
        with tempfile.TemporaryDirectory(prefix='acm-gitee-') as folder:
            body_path, header_path = Path(folder)/'response', Path(folder)/'headers'
            config = ['url = '+config_string(url), 'request = '+config_string(method),
                      'proxy = ""', 'proto = "=https"', 'connect-timeout = '+str(min(15,allowed)),
                      'max-time = '+str(allowed), 'max-filesize = '+str(max(maximum,65536)),
                      'output = '+config_string(body_path.as_posix()), 'dump-header = '+config_string(header_path.as_posix()),
                      'silent', 'write-out = "status=%{http_code}\\nconnect=%{time_connect}\\ntls=%{time_appconnect}\\nfirst_byte=%{time_starttransfer}\\ntotal=%{time_total}\\nsent=%{size_upload}\\n"']
            for key,value in (headers or {}).items():
                config.append('header = '+config_string(key+': '+value))
            if upload is not None:
                config += ['form-string = '+config_string('access_token='+token),
                           'form = '+config_string('file=@'+Path(upload).as_posix()+';type=application/octet-stream')]
            elif data is not None:
                payload = Path(folder)/'request.json'
                payload.write_bytes(data)
                config.append('data-binary = '+config_string('@'+payload.as_posix()))
            try:
                result = self.runner(['curl','-q','--config','-'], input=('\n'.join(config)+'\n').encode(),
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=allowed+2)
            except subprocess.TimeoutExpired:
                event('transfer_failure', phase='request', kind='process_timeout', method=method, filename=Path(upload).name if upload else None)
                raise TransferError('process_timeout', retryable=True) from None
            except OSError as error:
                event('transfer_failure', phase='start_transport', error_type=type(error).__name__, errno=error.errno)
                raise TransferError('curl_unavailable') from None
            metrics={}
            for line in result.stdout.decode('ascii','ignore').splitlines():
                key,sep,value=line.partition('=')
                if sep and key in ('status','connect','tls','first_byte','total','sent') and re.fullmatch(r'[0-9.]+',value):
                    try:metrics[key]=float(value)
                    except ValueError:pass
            status=int(metrics.get('status',0))
            safe_headers={}
            if header_path.exists():
                for line in header_path.read_text(encoding='iso-8859-1').splitlines():
                    if line.startswith('HTTP/'):
                        safe_headers={}
                    key,sep,value=line.partition(':')
                    if sep and key.lower() in ('location','retry-after','x-request-id'):
                        safe_headers[key.lower()]=value.strip()
            # Never emit stdout/stderr, request config, Location or response bodies.
            request_id=safe_headers.get('x-request-id','')
            event('transfer', method=method, filename=Path(upload).name if upload else None, curl_code=result.returncode,
                  metrics=metrics, request_id=request_id if re.fullmatch(r'[A-Za-z0-9._-]{1,128}',request_id) and not (token and token in request_id) else None)
            if result.returncode:
                safe = result.returncode in (5,6,7,35,60) and metrics.get('sent') == 0 and status == 0
                retryable = result.returncode in (5,6,7,18,28,35,52,55,56)
                raise TransferError('curl_'+str(result.returncode), code=result.returncode, retryable=retryable, safe_to_retry=safe)
            size=body_path.stat().st_size if body_path.exists() else 0
            if size > maximum and status not in (301,302,303,307,308):
                raise TransferError('response_too_large', status=status)
            digest=hashlib.sha256()
            if body_path.exists():
                with body_path.open('rb') as stream:
                    for block in iter(lambda:stream.read(65536),b''):digest.update(block)
            raw=b'' if binary or not body_path.exists() else body_path.read_bytes()
            return Reply(status,safe_headers,raw,size,digest.hexdigest())


def probe():
    """Probe the actual runner without any token or user data."""
    stage='dns';started=time.monotonic()
    try:
        socket.getaddrinfo('gitee.com',443,type=socket.SOCK_STREAM)
        event('probe',phase=stage,elapsed_ms=round((time.monotonic()-started)*1000))
        stage='tcp';started=time.monotonic()
        with socket.create_connection(('gitee.com',443),timeout=15) as connection:
            event('probe',phase=stage,elapsed_ms=round((time.monotonic()-started)*1000))
            stage='tls';started=time.monotonic()
            with ssl.create_default_context().wrap_socket(connection,server_hostname='gitee.com') as secure:
                event('probe',phase=stage,elapsed_ms=round((time.monotonic()-started)*1000),protocol=secure.version())
    except OSError as error:
        event('probe_failure',phase=stage,error_type=type(error).__name__,errno=error.errno)
