"""Environment-backed configuration with explicit provider extension points."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class AppSettings:
    """Runtime settings. All external services can be replaced through env vars."""

    market_data_provider: str = "akshare"
    market_data_base_url: str = ""
    market_data_api_key: str = ""
    market_data_comprehensive_path: str = "/stocks/{symbol}/comprehensive"
    market_data_name_path: str = "/stocks/{symbol}/name"
    market_data_timeout_seconds: float = 20.0
    market_data_max_retries: int = 2

    llm_provider: str = "dashscope"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = "qwen-max"
    llm_timeout_seconds: float = 60.0
    llm_max_retries: int = 5

    log_level: str = "INFO"
    report_author: str = ""
    report_language: str = "zh-CN"

    @classmethod
    def from_env(cls) -> "AppSettings":
        return cls(
            market_data_provider=os.getenv("MARKET_DATA_PROVIDER", "akshare").strip().lower(),
            market_data_base_url=os.getenv("MARKET_DATA_BASE_URL", "").rstrip("/"),
            market_data_api_key=os.getenv("MARKET_DATA_API_KEY", ""),
            market_data_comprehensive_path=os.getenv(
                "MARKET_DATA_COMPREHENSIVE_PATH", "/stocks/{symbol}/comprehensive"
            ),
            market_data_name_path=os.getenv("MARKET_DATA_NAME_PATH", "/stocks/{symbol}/name"),
            market_data_timeout_seconds=_float_env("MARKET_DATA_TIMEOUT_SECONDS", 20.0),
            market_data_max_retries=_int_env("MARKET_DATA_MAX_RETRIES", 2),
            llm_provider=os.getenv("LLM_PROVIDER", "dashscope").strip().lower(),
            llm_api_key=os.getenv("LLM_API_KEY") or os.getenv("DASHSCOPE_API_KEY", ""),
            llm_base_url=os.getenv("LLM_BASE_URL", "").rstrip("/"),
            llm_model=os.getenv("LLM_MODEL", "qwen-max"),
            llm_timeout_seconds=_float_env("LLM_TIMEOUT_SECONDS", 60.0),
            llm_max_retries=_int_env("LLM_MAX_RETRIES", 5),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            report_author=os.getenv("REPORT_AUTHOR", ""),
            report_language=os.getenv("REPORT_LANGUAGE", "zh-CN"),
        )
