"""Explicit provider settings. Never put credentials into public configuration."""
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

BASE = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Config:
    provider: str
    model: str
    api_key: str = field(repr=False)
    base_url: str = "https://api.openai.com/v1"
    timeout: float = 60
    max_retries: int = 2
    request_interval: float = 1
    max_output_tokens: int | None = None
    response_format: str = "json_schema"
    token_parameter: str = "max_completion_tokens"

    def __post_init__(self):
        if self.provider not in {"openai", "compatible"}:
            raise ValueError("Unsupported provider")
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("Configure OPENAI_MODEL or --model")
        if not self.api_key.strip():
            raise ValueError("Configure OPENAI_API_KEY in local .env/environment")
        url = urlsplit(self.base_url)
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("base_url must be an HTTPS URL without credentials/query/fragment")
        if self.provider == "openai" and self.base_url.rstrip("/") != "https://api.openai.com/v1":
            raise ValueError("Official provider requires https://api.openai.com/v1; other endpoints need compatible")
        if self.response_format not in {"json_schema", "json_object"}:
            raise ValueError("Unsupported response format; no automatic fallback")
        if self.token_parameter not in {"max_completion_tokens", "max_tokens"}:
            raise ValueError("Unsupported output token parameter")
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError("timeout must be positive and finite")
        if self.max_retries < 0 or not math.isfinite(self.request_interval) or self.request_interval < 0:
            raise ValueError("Invalid retry/interval configuration")
        if self.max_output_tokens is not None and self.max_output_tokens <= 0:
            raise ValueError("max-output-tokens must be positive")

    def public(self):
        return {"provider": self.provider, "model": self.model,
                "base_url": self.base_url.rstrip("/"), "timeout": self.timeout,
                "response_format": self.response_format,
                "token_parameter": self.token_parameter,
                "max_output_tokens": self.max_output_tokens}

    @classmethod
    def from_args(cls, args):
        from dotenv import dotenv_values
        local = dotenv_values(BASE / ".env")

        def setting(name, default=None):
            return os.environ.get(name, local.get(name) or default)

        return cls(provider=args.provider, model=args.model or setting("OPENAI_MODEL", ""),
                   api_key=setting("OPENAI_API_KEY", ""),
                   base_url=setting("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                   timeout=args.timeout, max_retries=args.max_retries,
                   request_interval=args.request_interval, max_output_tokens=args.max_output_tokens,
                   response_format=setting("ANNOTATION_RESPONSE_FORMAT", "json_schema"),
                   token_parameter=setting("ANNOTATION_TOKEN_PARAMETER", "max_completion_tokens"))
