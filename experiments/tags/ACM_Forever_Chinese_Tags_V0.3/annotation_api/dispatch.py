"""Single-use dispatch capability, checked again by the real HTTP request hook."""
import json
from contextlib import contextmanager
from contextvars import ContextVar
from urllib.parse import urlsplit

from .adapter import digest

ACTIVE = ContextVar("acm_dispatch", default=None)


def request_settings(config):
    return {k: config.public()[k] for k in ("provider", "base_url", "model", "response_format", "token_parameter", "max_output_tokens")}


def wire_request(config, messages, schema, schema_name):
    value = {"model": config.model, "messages": messages, "stream": False}
    if config.response_format == "json_schema":
        value["response_format"] = {"type": "json_schema", "json_schema": {"name": schema_name, "strict": True, "schema": schema}}
    else:
        value["response_format"] = {"type": "json_object"}
    if config.max_output_tokens is not None:
        value[config.token_parameter] = config.max_output_tokens
    return value


class Permit:
    def __init__(self, config, body, validate):
        self.settings = digest(request_settings(config))
        self.body = digest(body)
        self.validate = validate
        self.used = False
        self.http_used = False
        self.active = True

    def call(self, config, body):
        if not self.active or self.used or digest(request_settings(config)) != self.settings or digest(body) != self.body:
            raise ValueError("缺少有效的一次性执行许可")
        self.validate()
        self.used = True

    def http(self, config, request):
        if not self.active or not self.used or self.http_used:
            raise ValueError("真实 HTTP 请求没有执行许可")
        expected = config.base_url.rstrip("/") + "/chat/completions"
        parsed = urlsplit(str(request.url))
        if (str(request.url) != expected or parsed.query or request.method != "POST"
                or request.headers.get("authorization") != "Bearer " + config.api_key
                or digest(request_settings(config)) != self.settings or digest(json.loads(request.content)) != self.body):
            raise ValueError("请求地址、身份或参数与许可不匹配")
        self.validate()  # Read current durable state immediately before the transport sends bytes.
        self.http_used = True


@contextmanager
def dispatch(config, body, validate):
    permit = Permit(config, body, validate)
    token = ACTIVE.set(permit)
    try:
        yield permit
    finally:
        permit.active = False
        ACTIVE.reset(token)
