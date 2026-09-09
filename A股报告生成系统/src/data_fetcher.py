"""
A股上市公司数据获取模块
使用AkShare获取最新的上市公司数据
"""

import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional, Tuple
from loguru import logger
import time
import gc


class StockDataFetcher:
    """A股数据获取器"""

    def __init__(self, max_retries: int = 2, retry_delay: float = 1.0):
        self.cache = {}
        self.cache_time = {}
        self.cache_duration = timedelta(hours=1)  # 缓存1小时
        self._cache_size_limit = 100  # 最大缓存数量
        self.max_retries = max(1, max_retries)
        self.retry_delay = max(0.0, retry_delay)

    def _call_with_retry(self, operation: str, callback: Callable):
        """Retry transient provider failures with bounded exponential backoff."""
        last_error = None
        for attempt in range(self.max_retries):
            try:
                return callback()
            except Exception as exc:
                last_error = exc
                if attempt >= self.max_retries - 1:
                    break
                delay = self.retry_delay * (2 ** attempt)
                logger.warning(
                    f"{operation}失败，将在{delay:.1f}秒后重试 "
                    f"({attempt + 1}/{self.max_retries}): {exc}"
                )
                time.sleep(delay)
        raise last_error

    def _is_cache_valid(self, key: str) -> bool:
        """检查缓存是否有效"""
        if key not in self.cache_time:
            return False
        return datetime.now() - self.cache_time[key] < self.cache_duration

    def _get_cached_data(self, key: str):
        """获取缓存数据"""
        if self._is_cache_valid(key):
            logger.info(f"使用缓存数据: {key}")
            return self.cache[key]
        return None

    def _set_cache(self, key: str, data):
        """设置缓存"""
        self.cache[key] = data
        self.cache_time[key] = datetime.now()

        # 如果缓存超过限制，清理最旧的
        if len(self.cache) > self._cache_size_limit:
            self._clean_oldest_cache()

    def _clean_oldest_cache(self):
        """清理最旧的缓存项"""
        if not self.cache_time:
            return

        # 找到最旧的缓存key
        oldest_key = min(self.cache_time, key=self.cache_time.get)
        del self.cache[oldest_key]
        del self.cache_time[oldest_key]
        logger.debug(f"缓存超限，清理最旧项: {oldest_key}")

    def clear_cache(self):
        """清理所有缓存，释放内存"""
        logger.info("清理所有缓存...")
        cache_size = len(self.cache)
        self.cache.clear()
        self.cache_time.clear()
        # 强制垃圾回收
        gc.collect()
        logger.info(f"已清理 {cache_size} 个缓存项，释放内存")

    def clean_expired_cache(self):
        """清理过期缓存"""
        expired_keys = [
            key for key in self.cache
            if not self._is_cache_valid(key)
        ]
        for key in expired_keys:
            del self.cache[key]
            del self.cache_time[key]
        if expired_keys:
            logger.info(f"清理了 {len(expired_keys)} 个过期缓存")
            gc.collect()

    def get_stock_list(self) -> pd.DataFrame:
        """获取A股股票列表"""
        cache_key = "stock_list"
        cached = self._get_cached_data(cache_key)
        if cached is not None:
            return cached

        try:
            logger.info("获取A股股票列表...")
            # 获取沪深A股列表
            stock_list = self._call_with_retry(
                "获取A股股票列表", ak.stock_info_a_code_name
            )
            self._set_cache(cache_key, stock_list)
            logger.info(f"成功获取 {len(stock_list)} 只股票")
            return stock_list
        except Exception as e:
            logger.error(f"获取股票列表失败: {e}")
            raise

    def get_stock_spot_data(self) -> pd.DataFrame:
        """获取并缓存沪深A股实时行情列表"""
        cache_key = "stock_spot_em"
        cached = self._get_cached_data(cache_key)
        if cached is not None:
            return cached

        try:
            logger.info("获取沪深A股实时行情列表...")
            spot_data = self._call_with_retry(
                "获取沪深A股实时行情", ak.stock_zh_a_spot_em
            )
            if spot_data is not None and not spot_data.empty and '代码' in spot_data.columns:
                spot_data = spot_data.copy()
                spot_data['代码'] = spot_data['代码'].astype(str).str.zfill(6)
            self._set_cache(cache_key, spot_data)
            logger.info(f"成功获取 {len(spot_data)} 条实时行情")
            return spot_data
        except Exception as e:
            logger.error(f"获取实时行情列表失败: {e}")
            return pd.DataFrame()

    def get_stock_basic_info(self, symbol: str) -> Dict:
        """
        获取股票基本信息 - 优化版（移除不稳定API）

        Args:
            symbol: 股票代码，如 "002659" 或 "000659"

        Returns:
            包含股票基本信息的字典
        """
        cache_key = f"basic_{symbol}"
        cached = self._get_cached_data(cache_key)
        if cached is not None:
            return cached

        try:
            logger.info(f"获取股票 {symbol} 基本信息...")
            info = self._call_with_retry(
                f"获取股票{symbol}基本信息",
                lambda: ak.stock_individual_info_em(symbol=symbol),
            )
            if info is None or info.empty:
                return {}

            items = info['item'].astype(str).tolist() if 'item' in info.columns else []
            values = info['value'].tolist() if 'value' in info.columns else []
            item_map = dict(zip(items, values))
            result = {
                'individual_info': {
                    'item': items,
                    'value': values,
                    'items': item_map
                }
            }
            self._set_cache(cache_key, result)
            return result
        except Exception as e:
            logger.warning(f"获取股票基本信息失败: {e}")
            return {}

    def get_stock_realtime_quote(self, symbol: str) -> Dict:
        """
        获取股票实时行情 - 优化版（移除性能问题）

        Args:
            symbol: 股票代码

        Returns:
            实时行情数据
        """
        cache_key = f"quote_{symbol}"
        cached = self._get_cached_data(cache_key)
        if cached is not None:
            return cached

        try:
            logger.info(f"获取股票 {symbol} 实时行情...")
            spot_data = self.get_stock_spot_data()
            if spot_data is None or spot_data.empty or '代码' not in spot_data.columns:
                return {}

            match = spot_data[spot_data['代码'] == str(symbol).zfill(6)]
            if match.empty:
                return {}

            quote = match.iloc[0].to_dict()
            self._set_cache(cache_key, quote)
            return quote

        except Exception as e:
            logger.error(f"获取实时行情失败: {e}")
            return {}

    def get_stock_historical_data(self, symbol: str, period: str = "daily", start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        """
        获取股票历史数据 - 简化版（移除不稳定API）

        Args:
            symbol: 股票代码
            period: 周期 (daily, weekly, monthly)
            start_date: 开始日期 YYYYMMDD
            end_date: 结束日期 YYYYMMDD

        Returns:
            历史数据DataFrame
        """
        # 移除历史数据获取，该API不稳定且不是报告生成的核心功能
        # 返回空DataFrame
        return pd.DataFrame()

    def get_financial_data(self, symbol: str) -> Dict:
        """
        获取财务数据 - 使用东方财富API（已验证可用）

        Args:
            symbol: 股票代码

        Returns:
            财务数据字典
        """
        cache_key = f"financial_{symbol}"
        cached = self._get_cached_data(cache_key)
        if cached is not None:
            return cached

        try:
            logger.info(f"获取股票 {symbol} 财务数据...")
            financial_data = {}

            statements = {
                'profit_sheet_sina': '利润表',
                'balance_sheet_sina': '资产负债表',
                'cash_flow_sina': '现金流量表',
            }
            for key, statement_name in statements.items():
                try:
                    statement = self._call_with_retry(
                        f"获取{statement_name}",
                        lambda name=statement_name: ak.stock_financial_report_sina(
                            stock=symbol, symbol=name
                        ),
                    )
                    if statement is not None and not statement.empty:
                        financial_data[key] = statement
                        logger.info(f"获取{statement_name}成功: {len(statement)} 行数据")
                    else:
                        logger.warning(f"{statement_name}数据为空")
                except Exception as exc:
                    logger.error(f"获取{statement_name}失败: {exc}")

            # 检查是否至少获取到一些数据
            if not financial_data:
                logger.error(f"股票 {symbol} 所有财务数据API均失败，返回空字典")
                return {}

            self._set_cache(cache_key, financial_data)
            return financial_data

        except Exception as e:
            logger.error(f"获取财务数据失败: {e}")
            return {}

    def get_stock_industry(self, symbol: str) -> Dict:
        """
        获取股票行业信息 - 简化版（移除不稳定API）

        Args:
            symbol: 股票代码

        Returns:
            行业信息
        """
        try:
            basic_info = self.get_stock_basic_info(symbol)
            items = basic_info.get('individual_info', {}).get('items', {})
            industry = items.get('行业') or items.get('所属行业') or '未分类'
            return {'industry': industry, 'board': None}
        except Exception as e:
            logger.warning(f"获取行业信息失败: {e}")
            return {'industry': '未分类', 'board': None}

    def get_stock_news(self, symbol: str, days: int = 30) -> pd.DataFrame:
        """
        获取股票相关新闻 - 简化版（移除不稳定API）

        Args:
            symbol: 股票代码
            days: 最近多少天

        Returns:
            新闻数据
        """
        # 移除新闻获取，API不稳定且不是报告生成的核心功能
        return pd.DataFrame()

    def get_comprehensive_data(self, symbol: str) -> Dict:
        """
        获取股票综合数据（用于生成报告）- 优化版

        只调用核心API，移除不稳定的功能

        Args:
            symbol: 股票代码

        Returns:
            包含所有数据的字典
        """
        logger.info(f"开始获取股票 {symbol} 的综合数据...")

        comprehensive_data = {
            'symbol': symbol,
            'fetch_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        # 1. 基本信息
        comprehensive_data['basic_info'] = self.get_stock_basic_info(symbol)

        # 2. 实时行情
        comprehensive_data['realtime_quote'] = self.get_stock_realtime_quote(symbol)

        # 3. 历史数据（已禁用）
        comprehensive_data['historical_data'] = pd.DataFrame()

        # 4. 获取财务数据（核心）
        try:
            comprehensive_data['financial_data'] = self.get_financial_data(symbol)
        except Exception as e:
            logger.error(f"获取财务数据失败: {e}")
            comprehensive_data['financial_data'] = {}

        # 5. 行业信息
        comprehensive_data['industry_info'] = self.get_stock_industry(symbol)

        # 6. 新闻（已禁用）
        comprehensive_data['news'] = pd.DataFrame()

        logger.info(f"股票 {symbol} 数据获取完成！")
        return comprehensive_data

    def calculate_financial_metrics(self, financial_data: pd.DataFrame) -> Dict:
        """
        计算关键财务指标

        Args:
            financial_data: 财务数据DataFrame

        Returns:
            计算后的财务指标
        """
        metrics = {}

        try:
            if financial_data is not None and not financial_data.empty:
                # 获取最近几年的数据
                recent_data = financial_data.head(5)

                # 计算营收增长率
                if '营业收入' in recent_data.columns:
                    revenue = recent_data['营业收入'].values
                    if len(revenue) >= 2:
                        revenue_growth = (revenue[0] - revenue[1]) / abs(revenue[1]) * 100
                        metrics['revenue_growth_rate'] = round(revenue_growth, 2)
                        metrics['revenue'] = revenue[0]

                # 计算净利润增长率
                if '净利润' in recent_data.columns:
                    profit = recent_data['净利润'].values
                    if len(profit) >= 2:
                        profit_growth = (profit[0] - profit[1]) / abs(profit[1]) * 100
                        metrics['profit_growth_rate'] = round(profit_growth, 2)
                        metrics['net_profit'] = profit[0]

                # 计算ROE
                if '净资产收益率(ROE)' in recent_data.columns:
                    metrics['roe'] = recent_data['净资产收益率(ROE)'].values[0]

                # 计算毛利率
                if '销售毛利率' in recent_data.columns:
                    metrics['gross_margin'] = recent_data['销售毛利率'].values[0]

                # 计算净利率
                if '销售净利率' in recent_data.columns:
                    metrics['net_margin'] = recent_data['销售净利率'].values[0]

        except Exception as e:
            logger.error(f"计算财务指标失败: {e}")

        return metrics

    def get_stock_name(self, symbol: str) -> str:
        """
        获取股票名称

        Args:
            symbol: 股票代码

        Returns:
            股票名称
        """
        try:
            stock_list = self.get_stock_list()
            stock_info = stock_list[stock_list['code'] == symbol]
            if not stock_info.empty:
                return stock_info.iloc[0]['name']
            return symbol
        except Exception:
            basic_info = self.get_stock_basic_info(symbol)
            items = basic_info.get('individual_info', {}).get('items', {})
            return str(
                items.get('股票简称')
                or items.get('名称')
                or items.get('股票名称')
                or symbol
            )


if __name__ == "__main__":
    # 测试代码
    fetcher = StockDataFetcher()

    # 测试获取凯文教育数据
    symbol = "002659"
    data = fetcher.get_comprehensive_data(symbol)

    print(f"\n股票名称: {fetcher.get_stock_name(symbol)}")
    print(f"数据获取完成，包含以下模块:")
    for key in data.keys():
        print(f"  - {key}")
