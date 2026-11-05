"""Guarded OpenAI transport. Real calls require a single-use executor permit; SDK retries are zero."""
from dataclasses import dataclass
import time
import openai
import httpx
from .schema import SCHEMA
from .dispatch import ACTIVE, wire_request


class CallError(Exception):
    def __init__(self, code, *, retryable=False, fatal=False, unknown=False, retry_after=None,
                 http_status=None, elapsed_seconds=None, failure_stage=None):
        super().__init__(code)
        self.code, self.retryable, self.fatal, self.unknown = code, retryable, fatal, unknown
        self.retry_after = retry_after
        self.http_status, self.elapsed_seconds = http_status, elapsed_seconds
        self.failure_stage = failure_stage


@dataclass
class Response:
    content: str | None
    model: str
    usage: dict | None
    finish_reason: str | None
    refused: bool = False
    request_id: str | None = None
    elapsed_seconds: float | None = None

    def as_dict(self):
        return dict(content=self.content, model=self.model, usage=self.usage,
                    finish_reason=self.finish_reason, refused=self.refused, request_id=self.request_id,
                    elapsed_seconds=self.elapsed_seconds)


class APIClient:
    def __init__(self, config, *, http_client=None):
        self.config = config
        self.offline_transport = bool(http_client is not None and isinstance(http_client._transport, httpx.MockTransport))
        if http_client is None:
            http_client = openai.DefaultHttpxClient(timeout=config.timeout, follow_redirects=False,
                                                   trust_env=False)
        else:
            http_client.follow_redirects = False
            if self.offline_transport:
                # A proxy mount must never divert an allegedly offline Mock request to the network.
                http_client._mounts.clear()
            elif http_client.trust_env:
                raise ValueError("真实自定义 HTTP 客户端必须禁用环境代理")
        self.http_requests_prepared = 0
        http_client.event_hooks["request"].append(self._guard_request)
        self.sdk = openai.OpenAI(api_key=config.api_key, base_url=config.base_url,
                                 timeout=config.timeout, max_retries=0, http_client=http_client)

    def close(self):
        self.sdk.close()

    def _guard_request(self, request):
        try:
            self._check_dispatch(request)
        except Exception:
            # SDK wraps request-hook exceptions as connection errors. Preserve
            # proof that the transport has not received this request.
            raise CallError("dispatch_validation_failed", fatal=True, failure_stage="before_dispatch") from None
        self.http_requests_prepared += 1

    def _check_dispatch(self, request):
        if not self.offline_transport:
            permit = ACTIVE.get()
            if permit is None:
                raise CallError("executor_required", fatal=True)
            permit.http(self.config, request)

    def call(self, messages, *, schema=None, schema_name="acm_tag_annotation"):
        cfg = self.config
        kwargs = wire_request(cfg, messages, SCHEMA if schema is None else schema, schema_name)
        if not self.offline_transport:
            permit = ACTIVE.get()
            if permit is None:
                raise CallError("executor_required", fatal=True, failure_stage="before_dispatch")
            try:
                permit.call(cfg, kwargs)
            except (ValueError, OSError):
                raise CallError("dispatch_validation_failed", fatal=True, failure_stage="before_dispatch") from None
        started = time.perf_counter()
        prepared_before = self.http_requests_prepared
        try:
            result = self.sdk.chat.completions.create(**kwargs)
        except openai.RateLimitError as exc:
            body = exc.body if isinstance(exc.body, dict) else {}
            error = body.get("error", body)
            error = error if isinstance(error, dict) else {}
            quota = error.get("code") in {"insufficient_quota", "billing_hard_limit_reached"} or error.get("type") == "insufficient_quota"
            delay = None
            try:
                delay = float(exc.response.headers.get("retry-after", ""))
            except (ValueError, TypeError):
                pass
            raise CallError("quota_exhausted" if quota else "rate_limit", retryable=not quota, fatal=quota,
                            retry_after=delay, http_status=429, elapsed_seconds=round(time.perf_counter()-started, 4)) from None
        except (openai.APITimeoutError, openai.APIConnectionError) as exc:
            cause = exc
            seen = set()
            while cause is not None and id(cause) not in seen:
                seen.add(id(cause))
                if isinstance(cause, CallError) and cause.failure_stage == "before_dispatch":
                    raise CallError("dispatch_validation_failed", fatal=True, failure_stage="before_dispatch",
                                    elapsed_seconds=round(time.perf_counter()-started, 4)) from None
                if isinstance(cause, (httpx.ConnectError, httpx.ConnectTimeout)):
                    # DNS/TCP/TLS establishment failed before an HTTP body could
                    # be delivered. Read/write failures remain uncertain.
                    raise CallError("connection_failed", fatal=True, failure_stage="connect",
                                    elapsed_seconds=round(time.perf_counter()-started, 4)) from None
                cause = cause.__cause__
            if self.http_requests_prepared == prepared_before:
                raise CallError("local_request_failed", fatal=True, failure_stage="before_dispatch",
                                elapsed_seconds=round(time.perf_counter()-started, 4)) from None
            raise CallError("unknown_delivery", unknown=True, elapsed_seconds=round(time.perf_counter()-started, 4)) from None
        except openai.APIStatusError as exc:
            # Server errors can occur after processing; do not blindly resend.
            if exc.status_code >= 500:
                raise CallError("unknown_delivery", unknown=True, http_status=exc.status_code,
                                elapsed_seconds=round(time.perf_counter()-started, 4)) from None
            raise CallError("api_configuration_error", fatal=True, http_status=exc.status_code,
                            elapsed_seconds=round(time.perf_counter()-started, 4)) from None
        except Exception:
            if self.http_requests_prepared == prepared_before:
                raise CallError("local_request_failed", fatal=True, failure_stage="before_dispatch",
                                elapsed_seconds=round(time.perf_counter()-started, 4)) from None
            # SDK parsing/transport faults may happen after sending a request.
            raise CallError("unknown_delivery", unknown=True, elapsed_seconds=round(time.perf_counter()-started, 4)) from None
        try:
            usage = result.usage.model_dump(mode="json") if result.usage is not None else None
            choice = result.choices[0] if result.choices else None
            content = choice.message.content if choice else None
            def redact(value):
                if isinstance(value, str):
                    return value.replace(cfg.api_key, "[REDACTED]")
                if isinstance(value, dict):
                    return {k: redact(v) for k, v in value.items()}
                if isinstance(value, list):
                    return [redact(v) for v in value]
                return value
            return Response(content=redact(content), model=redact(result.model), usage=redact(usage),
                            finish_reason=choice.finish_reason if choice else None,
                            refused=bool(choice and choice.message.refusal),
                            request_id=redact(getattr(result, "_request_id", None)),
                            elapsed_seconds=round(time.perf_counter()-started, 4))
        except Exception:
            raise CallError("unknown_delivery", unknown=True, elapsed_seconds=round(time.perf_counter()-started, 4)) from None
