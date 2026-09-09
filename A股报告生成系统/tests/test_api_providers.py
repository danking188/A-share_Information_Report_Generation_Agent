import sys
import unittest
import os
from pathlib import Path
from unittest.mock import patch


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))

from api_providers import HttpJSONMarketDataProvider, LLMResponse, OpenAICompatibleLLMProvider
from qianwen_client import QianwenClient
from settings import AppSettings


class _FakeProvider:
    def __init__(self, failures=None):
        self.failures = list(failures or [])
        self.calls = 0

    def generate(self, messages, temperature, max_tokens):
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        return LLMResponse("ok", 1, 1, 2)


class _StatusError(RuntimeError):
    def __init__(self, status_code):
        super().__init__(str(status_code))
        self.status_code = status_code


class _FakeHttpResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class _FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.headers = {}
        self.requested_url = None

    def get(self, url, timeout):
        self.requested_url = url
        return _FakeHttpResponse(self.payload)


class ApiProviderTest(unittest.TestCase):
    def test_environment_variables_select_replaceable_apis(self):
        with patch.dict(os.environ, {
            "MARKET_DATA_PROVIDER": "http_json",
            "MARKET_DATA_BASE_URL": "https://market.example/v2/",
            "MARKET_DATA_API_KEY": "market-key",
            "LLM_PROVIDER": "openai_compatible",
            "LLM_BASE_URL": "https://llm.example/v1/",
            "LLM_API_KEY": "llm-key",
            "LLM_MODEL": "model-next",
        }, clear=False):
            settings = AppSettings.from_env()

        self.assertEqual("http_json", settings.market_data_provider)
        self.assertEqual("https://market.example/v2", settings.market_data_base_url)
        self.assertEqual("market-key", settings.market_data_api_key)
        self.assertEqual("openai_compatible", settings.llm_provider)
        self.assertEqual("https://llm.example/v1", settings.llm_base_url)
        self.assertEqual("llm-key", settings.llm_api_key)
        self.assertEqual("model-next", settings.llm_model)

    def test_non_retryable_auth_error_is_not_retried(self):
        provider = _FakeProvider([_StatusError(401)])
        client = QianwenClient(
            "key",
            settings=AppSettings(llm_max_retries=5),
            provider=provider,
        )
        with self.assertRaises(_StatusError):
            client._call_api([{"role": "user", "content": "test"}])
        self.assertEqual(1, provider.calls)

    def test_rate_limit_is_retried(self):
        provider = _FakeProvider([_StatusError(429)])
        client = QianwenClient(
            "key",
            settings=AppSettings(llm_max_retries=2),
            provider=provider,
        )
        with patch("qianwen_client.time.sleep"):
            self.assertEqual("ok", client._call_api([{"role": "user", "content": "test"}]))
        self.assertEqual(2, provider.calls)

    def test_openai_compatible_url_is_configurable(self):
        provider = OpenAICompatibleLLMProvider(AppSettings(
            llm_provider="openai_compatible",
            llm_api_key="key",
            llm_base_url="https://llm.example/v1",
            llm_model="custom-model",
        ))
        self.assertEqual("https://llm.example/v1/chat/completions", provider.url)
        self.assertEqual("custom-model", provider.model)

    def test_http_market_provider_uses_configured_endpoint_and_normalizes_tables(self):
        settings = AppSettings(
            market_data_provider="http_json",
            market_data_base_url="https://data.example/api",
            market_data_comprehensive_path="/company/{symbol}",
        )
        provider = HttpJSONMarketDataProvider(settings)
        provider.session = _FakeSession({
            "financial_data": {
                "profit_sheet_sina": [{"报告日": 20260630, "营业收入": 1}]
            },
            "news": [{"新闻标题": "test"}],
        })

        result = provider.get_comprehensive_data("000001")
        self.assertEqual("https://data.example/api/company/000001", provider.session.requested_url)
        self.assertEqual("000001", result["symbol"])
        self.assertEqual(1, len(result["financial_data"]["profit_sheet_sina"]))
        self.assertEqual(1, len(result["news"]))


if __name__ == "__main__":
    unittest.main()
