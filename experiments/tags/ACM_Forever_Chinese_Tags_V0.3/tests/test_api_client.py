import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import httpx
from api_helpers import config
from annotation_api.client import APIClient, CallError
from annotation_api.config import Config
from annotate_api import parser


class ClientTests(unittest.TestCase):
    def setUp(self):
        # Fail locally if anyone replaces MockTransport with real HTTP transport.
        guard = patch("httpx.HTTPTransport.handle_request", side_effect=AssertionError("Network forbidden in offline tests"))
        guard.start()
        self.addCleanup(guard.stop)

    def client(self, handler, **kwargs):
        client = APIClient(config(**kwargs), http_client=httpx.Client(transport=httpx.MockTransport(handler)))
        self.addCleanup(client.close)
        return client

    def test_sdk_structured_output_and_usage(self):
        requests = []
        def handler(request):
            body = json.loads(request.content)
            requests.append(body)
            return httpx.Response(200, json={"id": "mock", "object": "chat.completion", "created": 0,
                 "model": "returned-model", "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "{}"}}],
                 "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20}})
        response = self.client(handler, max_output_tokens=300).call([{"role": "user", "content": "JSON"}])
        self.assertEqual(response.usage["total_tokens"], 20)
        self.assertEqual(response.model, "returned-model")
        self.assertEqual(requests[0]["response_format"]["type"], "json_schema")
        self.assertTrue(requests[0]["response_format"]["json_schema"]["strict"])
        self.assertEqual(requests[0]["max_completion_tokens"], 300)
        self.assertNotIn("temperature", requests[0])

    def test_rate_limit_has_no_sdk_retries(self):
        count = []
        def handler(request):
            count.append(1)
            return httpx.Response(429, headers={"retry-after": "3"}, json={"error": {"code": "rate_limit_exceeded"}})
        with self.assertRaises(CallError) as c:
            self.client(handler).call([])
        self.assertEqual(len(count), 1)
        self.assertTrue(c.exception.retryable)
        self.assertEqual(c.exception.retry_after, 3)

    def test_quota_and_auth_are_fatal(self):
        for status, body in ((429, {"error": {"code": "insufficient_quota"}}), (401, {"error": {"message": "offline-test-key"}})):
            with self.subTest(status=status), self.assertRaises(CallError) as c:
                self.client(lambda request: httpx.Response(status, json=body)).call([])
            self.assertTrue(c.exception.fatal)
            self.assertNotIn("offline-test-key", str(c.exception))

    def test_timeout_and_server_error_unknown(self):
        def timeout(request):
            raise httpx.ReadTimeout("offline-test-key", request=request)
        for handler in (timeout, lambda req: httpx.Response(503, json={"error": {"message": "unavailable"}})):
            with self.assertRaises(CallError) as c:
                self.client(handler).call([])
            self.assertTrue(c.exception.unknown)
            self.assertFalse(c.exception.retryable)

    def test_json_mode_and_legacy_token_parameter_explicit(self):
        observed = []
        def handler(request):
            observed.append(json.loads(request.content))
            return httpx.Response(200, json={"id": "mock", "object": "chat.completion", "created": 0,
                  "model": "offline", "choices": []})
        response = self.client(handler, response_format="json_object", token_parameter="max_tokens", max_output_tokens=100).call([])
        self.assertEqual(observed[0]["response_format"], {"type": "json_object"})
        self.assertEqual(observed[0]["max_tokens"], 100)
        self.assertIsNone(response.usage)

    def test_public_config_and_repr_hide_key(self):
        self.assertNotIn("offline-test-key", repr(config()))
        self.assertNotIn("offline-test-key", json.dumps(config().public()))

    def test_response_fields_redact_known_credential(self):
        def handler(request):
            return httpx.Response(200, headers={"x-request-id": "offline-test-key"}, json={
                "id": "mock", "object": "chat.completion", "created": 0, "model": "offline-test-key",
                "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "offline-test-key"}}]})
        result = self.client(handler).call([]).as_dict()
        self.assertNotIn("offline-test-key", json.dumps(result))

    def test_dotenv_env_and_cli_precedence(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {"OPENAI_MODEL": "env-model"}, clear=True), patch("annotation_api.config.BASE", Path(d)):
            (Path(d) / ".env").write_text("OPENAI_API_KEY=offline-test-key\nOPENAI_MODEL=dotenv-model\n", encoding="utf-8")
            args = parser().parse_args(["--input", "mock.jsonl", "--execute", "--model", "cli-model"])
            self.assertEqual(Config.from_args(args).model, "cli-model")
            args.model = None
            self.assertEqual(Config.from_args(args).model, "env-model")

    def test_official_endpoint_and_invalid_configs_rejected(self):
        for changes in ({"base_url": "https://example.com/v1"}, {"base_url": "https://api.openai.com/v1?key=secret"},
                        {"model": ""}, {"api_key": ""}, {"timeout": -1}, {"max_output_tokens": 0},
                        {"response_format": "invented"}, {"token_parameter": "invented"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                config(**changes)

    def test_redirect_is_not_followed_or_sent_credentials_to_other_host(self):
        observed = []
        def handler(request):
            observed.append(str(request.url))
            return httpx.Response(307, headers={"location": "https://other.example/v1/chat/completions"})
        with self.assertRaises(CallError) as error:
            self.client(handler).call([])
        self.assertEqual(observed, ["https://api.openai.com/v1/chat/completions"])
        self.assertEqual(error.exception.http_status, 307)

    def test_default_transport_disables_redirects_proxies_and_sdk_retries(self):
        client = APIClient(config())
        self.addCleanup(client.close)
        self.assertFalse(client.sdk._client.follow_redirects)
        self.assertFalse(client.sdk._client.trust_env)
        self.assertEqual(client.sdk.max_retries, 0)
