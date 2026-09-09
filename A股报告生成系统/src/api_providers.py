"""Replaceable adapters for market-data and LLM APIs."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Dict, List, Protocol

import pandas as pd
import requests

from data_fetcher import StockDataFetcher
from settings import AppSettings


@dataclass
class LLMResponse:
    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class LLMProvider(Protocol):
    def generate(
        self,
        messages: List[Dict],
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse: ...


class MarketDataProvider(Protocol):
    def get_comprehensive_data(self, symbol: str) -> Dict: ...

    def get_stock_name(self, symbol: str) -> str: ...

    def calculate_financial_metrics(self, financial_data: pd.DataFrame) -> Dict: ...

    def clear_cache(self) -> None: ...

    def clean_expired_cache(self) -> None: ...


class DashScopeLLMProvider:
    def __init__(self, settings: AppSettings):
        try:
            import dashscope
            from dashscope import Generation
        except ImportError as exc:
            raise ImportError("未安装dashscope，请先安装项目依赖") from exc

        dashscope.api_key = settings.llm_api_key
        self.generation = Generation
        self.model = settings.llm_model
        self.timeout = settings.llm_timeout_seconds

    def generate(self, messages, temperature, max_tokens) -> LLMResponse:
        response = self.generation.call(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            result_format="message",
            timeout=self.timeout,
        )
        if response.status_code != 200:
            error = RuntimeError(f"DashScope API失败: {response.code} - {response.message}")
            error.status_code = response.status_code
            raise error

        usage = getattr(response, "usage", None)
        return LLMResponse(
            content=response.output.choices[0].message.content,
            input_tokens=getattr(usage, "input_tokens", 0) if usage else 0,
            output_tokens=getattr(usage, "output_tokens", 0) if usage else 0,
            total_tokens=getattr(usage, "total_tokens", 0) if usage else 0,
        )


class OpenAICompatibleLLMProvider:
    """Adapter for providers exposing the OpenAI chat-completions schema."""

    def __init__(self, settings: AppSettings):
        if not settings.llm_base_url:
            raise ValueError("使用 openai_compatible 时必须设置 LLM_BASE_URL")
        self.url = f"{settings.llm_base_url}/chat/completions"
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model
        self.timeout = settings.llm_timeout_seconds

    def generate(self, messages, temperature, max_tokens) -> LLMResponse:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        response = requests.post(
            self.url,
            headers=headers,
            json={
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        usage = payload.get("usage") or {}
        return LLMResponse(
            content=payload["choices"][0]["message"]["content"],
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            total_tokens=int(usage.get("total_tokens", 0)),
        )


class HttpJSONMarketDataProvider:
    """Adapter for a normalized company-internal or third-party HTTP API.

    The comprehensive endpoint should return the same top-level schema as
    StockDataFetcher.get_comprehensive_data. Table values may be JSON records.
    """

    TABLE_KEYS = {
        "historical_data",
        "news",
    }
    FINANCIAL_TABLE_KEYS = {
        "profit_sheet_sina",
        "balance_sheet_sina",
        "cash_flow_sina",
        "financial_indicator",
    }

    def __init__(self, settings: AppSettings):
        if not settings.market_data_base_url:
            raise ValueError("使用 http_json 时必须设置 MARKET_DATA_BASE_URL")
        self.settings = settings
        self.session = requests.Session()
        if settings.market_data_api_key:
            self.session.headers["Authorization"] = f"Bearer {settings.market_data_api_key}"
        self._metrics = StockDataFetcher(
            max_retries=settings.market_data_max_retries
        )

    def _get(self, path_template: str, symbol: str) -> Dict:
        path = path_template.format(symbol=symbol)
        last_error = None
        for attempt in range(max(1, self.settings.market_data_max_retries)):
            try:
                response = self.session.get(
                    f"{self.settings.market_data_base_url}{path}",
                    timeout=self.settings.market_data_timeout_seconds,
                )
                response.raise_for_status()
                return response.json()
            except requests.RequestException as exc:
                last_error = exc
                status = getattr(exc.response, 'status_code', None)
                retryable = status is None or status in {408, 409, 425, 429} or (
                    isinstance(status, int) and status >= 500
                )
                if not retryable or attempt >= self.settings.market_data_max_retries - 1:
                    raise
                time.sleep(2 ** attempt)
        raise last_error

    def get_comprehensive_data(self, symbol: str) -> Dict:
        payload = self._get(self.settings.market_data_comprehensive_path, symbol)
        for key in self.TABLE_KEYS:
            if isinstance(payload.get(key), list):
                payload[key] = pd.DataFrame(payload[key])
        financial = payload.get("financial_data") or {}
        for key in self.FINANCIAL_TABLE_KEYS:
            if isinstance(financial.get(key), list):
                financial[key] = pd.DataFrame(financial[key])
        payload["financial_data"] = financial
        payload.setdefault("symbol", symbol)
        return payload

    def get_stock_name(self, symbol: str) -> str:
        try:
            payload = self._get(self.settings.market_data_name_path, symbol)
            return str(payload.get("stock_name") or payload.get("name") or symbol)
        except requests.RequestException:
            return symbol

    def calculate_financial_metrics(self, financial_data: pd.DataFrame) -> Dict:
        return self._metrics.calculate_financial_metrics(financial_data)

    def clear_cache(self) -> None:
        self._metrics.clear_cache()

    def clean_expired_cache(self) -> None:
        self._metrics.clean_expired_cache()


def create_llm_provider(settings: AppSettings) -> LLMProvider:
    if settings.llm_provider == "dashscope":
        return DashScopeLLMProvider(settings)
    if settings.llm_provider == "openai_compatible":
        return OpenAICompatibleLLMProvider(settings)
    raise ValueError(f"不支持的 LLM_PROVIDER: {settings.llm_provider}")


def create_market_data_provider(settings: AppSettings) -> MarketDataProvider:
    if settings.market_data_provider == "akshare":
        return StockDataFetcher(max_retries=settings.market_data_max_retries)
    if settings.market_data_provider == "http_json":
        return HttpJSONMarketDataProvider(settings)
    raise ValueError(f"不支持的 MARKET_DATA_PROVIDER: {settings.market_data_provider}")
