"""OpenAI transport. Retries belong exclusively to runner.py."""
from dataclasses import dataclass
import time
import openai
from .schema import SCHEMA


class CallError(Exception):
    def __init__(self, code, *, retryable=False, fatal=False, unknown=False, retry_after=None,
                 http_status=None, elapsed_seconds=None):
        super().__init__(code)
        self.code, self.retryable, self.fatal, self.unknown = code, retryable, fatal, unknown
        self.retry_after = retry_after
        self.http_status, self.elapsed_seconds = http_status, elapsed_seconds


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
        if http_client is None:
            http_client = openai.DefaultHttpxClient(timeout=config.timeout, follow_redirects=False,
                                                   trust_env=False)
        else:
            http_client.follow_redirects = False
        self.sdk = openai.OpenAI(api_key=config.api_key, base_url=config.base_url,
                                 timeout=config.timeout, max_retries=0, http_client=http_client)

    def close(self):
        self.sdk.close()

    def call(self, messages, *, schema=None, schema_name="acm_tag_annotation"):
        cfg = self.config
        kwargs = {"model": cfg.model, "messages": messages, "stream": False}
        if cfg.response_format == "json_schema":
            kwargs["response_format"] = {"type": "json_schema", "json_schema": {
                "name": schema_name, "strict": True, "schema": SCHEMA if schema is None else schema}}
        else:
            kwargs["response_format"] = {"type": "json_object"}
        if cfg.max_output_tokens is not None:
            kwargs[cfg.token_parameter] = cfg.max_output_tokens
        started = time.perf_counter()
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
        except (openai.APITimeoutError, openai.APIConnectionError):
            raise CallError("unknown_delivery", unknown=True, elapsed_seconds=round(time.perf_counter()-started, 4)) from None
        except openai.APIStatusError as exc:
            # Server errors can occur after processing; do not blindly resend.
            if exc.status_code >= 500:
                raise CallError("unknown_delivery", unknown=True, http_status=exc.status_code,
                                elapsed_seconds=round(time.perf_counter()-started, 4)) from None
            raise CallError("api_configuration_error", fatal=True, http_status=exc.status_code,
                            elapsed_seconds=round(time.perf_counter()-started, 4)) from None
        except Exception:
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
