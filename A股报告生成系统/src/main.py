"""
A股上市公司研究报告自动生成系统 - 主程序（优化版）
整合数据获取、AI分析、报告生成的完整流程
添加内存管理和定期清理机制
"""

import os
import sys
import argparse
import json
import pandas as pd
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from loguru import logger
from typing import Dict, Optional
import gc

# 导入自定义模块
from api_providers import MarketDataProvider, create_market_data_provider
from data_quality import evaluate_data_quality
from qianwen_client import QianwenClient
from report_generator import ReportGenerator
from rag import RAGRetriever
from settings import AppSettings
from workflow_state import WorkflowStateStore


class ResearchReportGenerator:
    """研究报告生成器主类（内存优化版）"""

    def __init__(self, api_key: str = "", auto_clean_interval: int = 10,
                 knowledge_base_dir: Optional[str] = None, rag_enabled: bool = True,
                 rag_top_k: int = 6, dry_run: bool = False,
                 settings: Optional[AppSettings] = None,
                 data_provider: Optional[MarketDataProvider] = None,
                 state_dir: Optional[str] = None,
                 offline_fixture_dir: Optional[str] = None):
        """
        初始化生成器

        Args:
            api_key: 千问API密钥
            auto_clean_interval: 自动清理间隔（生成N份报告后清理）
        """
        self.settings = settings or AppSettings.from_env()
        if api_key and api_key != self.settings.llm_api_key:
            self.settings = replace(self.settings, llm_api_key=api_key)
        self.api_key = self.settings.llm_api_key
        self.fetcher = data_provider or create_market_data_provider(self.settings)
        self.qianwen_client = QianwenClient(
            self.api_key,
            dry_run=dry_run,
            settings=self.settings,
        )
        self.report_generator = None  # 延迟初始化，每次生成时创建新实例

        self.auto_clean_interval = auto_clean_interval
        self._report_count = 0  # 报告计数器
        self.dry_run = dry_run
        self.rag_enabled = rag_enabled
        self.rag_top_k = rag_top_k
        self.project_dir = os.path.dirname(os.path.dirname(__file__))
        self.knowledge_base_dir = knowledge_base_dir or os.path.join(self.project_dir, 'knowledge_base')
        self.offline_fixture_dir = Path(offline_fixture_dir) if offline_fixture_dir else None
        self.state_store = WorkflowStateStore(
            state_dir or os.path.join(self.project_dir, 'data')
        )
        self.rag_retriever = None

        # 设置日志
        self._setup_logger()

        if self.rag_enabled:
            self.rag_retriever = RAGRetriever(self.knowledge_base_dir, top_k=self.rag_top_k)
            chunk_count = self.rag_retriever.ensure_index()
            logger.info(f"RAG知识库已加载: {chunk_count} 个片段")

    def _setup_logger(self):
        """配置日志系统"""
        project_dir = os.path.dirname(os.path.dirname(__file__))
        log_dir = os.path.join(project_dir, 'logs')
        os.makedirs(log_dir, exist_ok=True)

        log_file = os.path.join(
            log_dir,
            f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        )

        logger.add(
            log_file,
            rotation="10 MB",
            retention="30 days",
            level=self.settings.log_level,
            encoding="utf-8"
        )

        logger.info("=" * 60)
        logger.info("A股研究报告生成系统启动（内存优化版）")
        logger.info("=" * 60)

    def _log_memory_usage(self):
        """记录当前内存使用情况"""
        try:
            import psutil
            process = psutil.Process()
            mem_info = process.memory_info()
            mem_mb = mem_info.rss / 1024 / 1024
            logger.info(f"当前内存使用: {mem_mb:.2f} MB")

            # 内存超过1.5GB时警告
            if mem_mb > 1500:
                logger.warning(f"内存使用较高: {mem_mb:.2f} MB，建议执行清理")

            return mem_mb
        except ImportError:
            logger.debug("psutil未安装，跳过内存监控")
            return None

    def _cleanup_memory(self, force: bool = False):
        """
        清理内存

        Args:
            force: 是否强制清理所有缓存
        """
        logger.info("=" * 50)
        logger.info("执行内存清理...")
        self._log_memory_usage()

        if force:
            # 强制清理：清理所有缓存
            self.fetcher.clear_cache()
        else:
            # 常规清理：只清理过期缓存
            self.fetcher.clean_expired_cache()

        # 清理千问客户端的累积数据
        if hasattr(self.qianwen_client, 'total_tokens'):
            logger.info(f"API调用统计: {self.qianwen_client.call_count}次, "
                       f"{self.qianwen_client.total_tokens:,} tokens")

        # 强制Python垃圾回收
        gc.collect()

        mem_after = self._log_memory_usage()
        if mem_after:
            logger.info(f"内存清理完成")
        logger.info("=" * 50)

    def _process_stock_data(self, raw_data: Dict) -> Dict:
        """
        处理股票数据，转换为适合千问分析的格式

        Args:
            raw_data: 原始数据

        Returns:
            处理后的数据
        """
        logger.info("处理股票数据...")

        symbol = raw_data.get('symbol')
        basic_info = raw_data.get('basic_info', {})
        individual_items = self._extract_individual_items(basic_info)
        stock_name = (
            raw_data.get('stock_name')
            or individual_items.get('股票简称')
            or individual_items.get('名称')
        )
        # 自定义数据接口可以直接在综合数据响应中返回名称，避免额外请求。
        if not stock_name:
            stock_name = self.fetcher.get_stock_name(symbol or '')
        processed_data = {
            'symbol': symbol,
            'stock_name': stock_name,
            'fetch_time': raw_data.get('fetch_time'),
        }

        # 提取基本信息
        processed_data['company_full_name'] = str(
            individual_items.get('股票简称') or individual_items.get('名称') or stock_name
        )
        processed_data['main_business'] = str(
            individual_items.get('主营业务') or individual_items.get('经营范围') or '相关信息暂未披露'
        )
        processed_data['industry'] = str(
            individual_items.get('行业') or individual_items.get('所属行业') or '未分类'
        )
        processed_data['profile'] = processed_data['main_business']

        # 提取实时行情
        quote = raw_data.get('realtime_quote', {})
        if quote:
            processed_data['current_price'] = quote.get('最新价', 'N/A')
            processed_data['market_cap'] = quote.get('总市值', 'N/A')
            processed_data['pe_ratio'] = quote.get('市盈率-动态', 'N/A')
            processed_data['pb_ratio'] = quote.get('市净率', 'N/A')

        # 提取财务摘要
        financial_data = raw_data.get('financial_data', {})
        if financial_data:
            processed_data['financial_summary'] = self._extract_financial_summary(financial_data)
            processed_data['historical_financial'] = self._extract_historical_financial(financial_data)

            # 创建summary字段供千问使用（包含核心投资数据）
            processed_data['summary'] = {
                '股票代码': processed_data.get('symbol'),
                '股票名称': processed_data.get('stock_name'),
                '当前股价': processed_data.get('current_price'),
                '市盈率': processed_data.get('pe_ratio'),
                '市净率': processed_data.get('pb_ratio'),
                '总市值': processed_data.get('market_cap'),
                '主营业务': processed_data.get('main_business'),
                '最新营收': processed_data['financial_summary'].get('revenue') if processed_data['financial_summary'] else None,
                '最新净利润': processed_data['financial_summary'].get('net_profit') if processed_data['financial_summary'] else None,
                '报告期': processed_data['financial_summary'].get('latest_year') if processed_data['financial_summary'] else None
            }

        # 提取关键指标
        key_metrics = {}
        if 'financial_indicator' in financial_data and not financial_data['financial_indicator'].empty:
            key_metrics = self.fetcher.calculate_financial_metrics(financial_data['financial_indicator'])
        processed_data['key_metrics'] = key_metrics

        # 估值指标
        processed_data['valuation_metrics'] = {
            'current_price': processed_data.get('current_price'),
            'pe_ratio': processed_data.get('pe_ratio'),
            'pb_ratio': processed_data.get('pb_ratio'),
            'market_cap': processed_data.get('market_cap')
        }

        # 行业背景
        processed_data['industry_background'] = processed_data['industry']

        # 提取新闻（最近10条）
        news = raw_data.get('news')
        if news is not None and not news.empty:
            recent_news = news.head(10)
            news_summary = recent_news['发布时间'].str.cat(recent_news['新闻标题'], sep=': ').tolist()
            processed_data['recent_news'] = '\n'.join(news_summary[:5])
        else:
            processed_data['recent_news'] = '暂无最新新闻'

        # 提取行业信息（用于后续联网搜索使用）
        industry_info = raw_data.get('industry_info', {})
        industry_value = industry_info.get('industry') if isinstance(industry_info, dict) else None
        if isinstance(industry_value, pd.DataFrame) and not industry_value.empty:
            if '板块名称' in industry_value.columns:
                processed_data['industry'] = str(industry_value.iloc[0]['板块名称'])
        elif industry_value and str(industry_value) != '未分类':
            processed_data['industry'] = str(industry_value)

        logger.info("数据处理完成")
        return processed_data

    def _extract_individual_items(self, basic_info: Dict) -> Dict:
        """提取个股基本信息中的 item/value 映射"""
        individual_info = basic_info.get('individual_info', {}) if basic_info else {}
        if isinstance(individual_info.get('items'), dict):
            return individual_info['items']

        items = individual_info.get('item', [])
        values = individual_info.get('value', [])
        return dict(zip([str(item) for item in items], values))

    def _attach_rag_context(self, processed_data: Dict) -> Dict:
        """检索本地知识库并附加到报告数据中"""
        processed_data['rag_context'] = ''
        processed_data['rag_sources'] = []
        if not self.rag_enabled or not self.rag_retriever:
            return processed_data

        query_parts = [
            processed_data.get('stock_name', ''),
            processed_data.get('symbol', ''),
            processed_data.get('industry', ''),
            processed_data.get('main_business', ''),
            '公司概况 行业地位 竞争优势 可比公司 投资逻辑'
        ]
        query = ' '.join(str(part) for part in query_parts if part)
        try:
            results = self.rag_retriever.search(query, top_k=self.rag_top_k)
            context = self.rag_retriever.format_context(results)
            processed_data['rag_context'] = context
            processed_data['rag_sources'] = [
                {
                    'evidence_id': item.get('evidence_id'),
                    'source': item['source'],
                    'chunk_id': item['chunk_id'],
                    'score': item['score'],
                }
                for item in results
                if item.get('evidence_id')
            ]
            if context:
                logger.info(f"RAG检索完成，注入资料长度: {len(context)} 字符")
            else:
                logger.info("RAG知识库未命中相关资料")
        except Exception as e:
            logger.warning(f"RAG检索失败，继续使用基础数据生成: {e}")

        return processed_data

    def _extract_from_dict(self, data: Dict, *keys) -> str:
        """从嵌套字典中提取值"""
        try:
            result = data
            for key in keys:
                if isinstance(result, dict):
                    result = result.get(key)
                else:
                    return 'N/A'
            return str(result) if result else 'N/A'
        except:
            return 'N/A'

    @staticmethod
    def _first_present(row: pd.Series, *columns):
        for column in columns:
            if column in row.index and pd.notna(row[column]):
                return row[column]
        return None

    @staticmethod
    def _parse_report_date(value) -> Optional[pd.Timestamp]:
        if value is None or pd.isna(value):
            return None
        text = str(value).strip()
        if text.endswith('.0'):
            text = text[:-2]
        parsed = pd.to_datetime(text, format='%Y%m%d', errors='coerce')
        if pd.isna(parsed):
            parsed = pd.to_datetime(text, errors='coerce')
        return None if pd.isna(parsed) else parsed

    @staticmethod
    def _safe_float(value) -> Optional[float]:
        if value is None or pd.isna(value):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _yoy(current: Optional[float], previous: Optional[float]) -> Optional[float]:
        if current is None or previous in (None, 0):
            return None
        return round((current - previous) / abs(previous) * 100, 2)

    def _extract_financial_summary(self, financial_data: Dict) -> Dict:
        """提取财务摘要"""
        summary = {}

        if 'profit_sheet_sina' in financial_data:
            profit_sheet = financial_data['profit_sheet_sina']
            if profit_sheet is not None and not profit_sheet.empty:
                dated_rows = []
                for _, row in profit_sheet.iterrows():
                    report_date = self._parse_report_date(
                        self._first_present(row, '报告日', '报告期', '日期')
                    )
                    if report_date is not None:
                        dated_rows.append((report_date, row))
                if dated_rows:
                    report_date, latest = max(dated_rows, key=lambda item: item[0])
                    summary['latest_year'] = report_date.strftime('%Y年%m月%d日')
                    summary['report_date'] = report_date.strftime('%Y-%m-%d')
                    summary['revenue'] = self._first_present(
                        latest, '营业收入', '营业总收入'
                    )
                    summary['net_profit'] = self._first_present(
                        latest, '归属于母公司的净利润', '归属于上市公司股东的净利润', '净利润'
                    )
                    logger.info(f"从新浪利润表提取数据: {summary['latest_year']}")
                    return summary

        # 备用：从旧利润表提取
        if 'profit_sheet' in financial_data:
            profit_sheet = financial_data['profit_sheet']
            if profit_sheet is not None and not profit_sheet.empty and len(profit_sheet) > 0:
                latest = profit_sheet.iloc[0]
                summary['latest_year'] = latest.get('报告期', 'N/A')
                summary['revenue'] = latest.get('营业总收入', 'N/A')
                summary['net_profit'] = latest.get('净利润', 'N/A')

        # 最后尝试：从财务指标提取
        if not summary and 'financial_indicator' in financial_data:
            indicator = financial_data['financial_indicator']
            if indicator is not None and not indicator.empty and len(indicator) > 0:
                latest = indicator.iloc[0]
                summary['latest_year'] = latest.get('日期', 'N/A')
                summary['revenue'] = latest.get('营业收入', 'N/A')
                summary['net_profit'] = latest.get('净利润', 'N/A')
                summary['roe'] = latest.get('净资产收益率', 'N/A')
                summary['gross_margin'] = latest.get('销售毛利率', 'N/A')

        if not summary:
            logger.warning("所有财务数据源均为空")

        return summary

    def _extract_historical_financial(self, financial_data: Dict) -> Dict:
        """提取历史财务数据，并只计算相同报告期的同比。"""
        historical = {}

        if 'profit_sheet_sina' in financial_data:
            profit_sheet = financial_data['profit_sheet_sina']
            if profit_sheet is not None and not profit_sheet.empty:
                records = []
                for _, row in profit_sheet.iterrows():
                    report_date = self._parse_report_date(
                        self._first_present(row, '报告日', '报告期', '日期')
                    )
                    if report_date is None:
                        continue
                    records.append({
                        'date': report_date,
                        'revenue': self._safe_float(
                            self._first_present(row, '营业收入', '营业总收入')
                        ),
                        'net_profit': self._safe_float(
                            self._first_present(
                                row,
                                '归属于母公司的净利润',
                                '归属于上市公司股东的净利润',
                                '净利润',
                            )
                        ),
                    })

                records.sort(key=lambda item: item['date'], reverse=True)
                by_period = {
                    (item['date'].year, item['date'].strftime('%m%d')): item
                    for item in records
                }
                for item in records[:8]:
                    report_date = item['date']
                    previous = by_period.get((report_date.year - 1, report_date.strftime('%m%d')))
                    period = report_date.strftime('%Y年%m月')
                    historical[period] = {
                        'report_date': report_date.strftime('%Y-%m-%d'),
                        'period_type': report_date.strftime('%m%d'),
                        'revenue': item['revenue'],
                        'net_profit': item['net_profit'],
                        'revenue_yoy': self._yoy(
                            item['revenue'], previous['revenue'] if previous else None
                        ),
                        'net_profit_yoy': self._yoy(
                            item['net_profit'], previous['net_profit'] if previous else None
                        ),
                        'previous_revenue': previous['revenue'] if previous else None,
                        'previous_net_profit': previous['net_profit'] if previous else None,
                        'comparable_period': (
                            previous['date'].strftime('%Y年%m月') if previous else None
                        ),
                        'roe': None,
                    }
                logger.info(f"从新浪利润表提取到 {len(historical)} 期历史数据")
                logger.info(f"期间名称: {list(historical.keys())}")
                return historical

        # 备用：从旧利润表提取
        if not historical and 'profit_sheet' in financial_data:
            profit_sheet = financial_data['profit_sheet']
            if profit_sheet is not None and not profit_sheet.empty and len(profit_sheet) > 0:
                recent = profit_sheet.head(3)
                for i, row in recent.iterrows():
                    year = row.get('报告期', f'year_{i}')
                    historical[year] = {
                        'revenue': row.get('营业总收入'),
                        'net_profit': row.get('净利润'),
                        'roe': None
                    }
                logger.info(f"从利润表提取到 {len(historical)} 年历史数据")

        # 最后尝试：从财务指标提取
        if not historical and 'financial_indicator' in financial_data:
            indicator = financial_data['financial_indicator']
            if indicator is not None and not indicator.empty and len(indicator) > 0:
                recent = indicator.head(3)
                for i, row in recent.iterrows():
                    year = row.get('日期', f'year_{i}')
                    historical[year] = {
                        'revenue': row.get('营业收入'),
                        'net_profit': row.get('净利润'),
                        'roe': row.get('净资产收益率')
                    }
                logger.info(f"从财务指标提取到 {len(historical)} 年历史数据")

        if not historical:
            logger.warning("无法提取历史财务数据")

        return historical

    def generate_report(self, stock_code: str, output_path: Optional[str] = None) -> str:
        """
        生成完整研究报告

        Args:
            stock_code: 股票代码（6位数字）
            output_path: 输出文件路径（可选）

        Returns:
            生成的报告文件路径
        """
        logger.info(f"开始生成股票 {stock_code} 的研究报告")
        state = self.state_store.start(stock_code)
        active_stage = "fetch_data"

        try:
            processed_data = {}
            processed_cache = self.state_store.load_artifact(stock_code, "processed_data")
            if state.get("stages", {}).get("process_data") == "completed" and processed_cache:
                processed_data = processed_cache
                logger.info("复用已完成的数据清洗结果")
            else:
                logger.info("步骤 1/5: 获取股票数据...")
                self.state_store.mark_stage(stock_code, "fetch_data", "running")
                if self.offline_fixture_dir:
                    fixture_path = self.offline_fixture_dir / f"{stock_code}.json"
                    if not fixture_path.exists():
                        raise FileNotFoundError(f"找不到离线样例: {fixture_path}")
                    processed_data = json.loads(fixture_path.read_text(encoding="utf-8"))
                    processed_data.setdefault("symbol", stock_code)
                    self.state_store.mark_stage(
                        stock_code, "fetch_data", "completed", str(fixture_path)
                    )
                else:
                    stock_data = self.fetcher.get_comprehensive_data(stock_code)
                    self.state_store.mark_stage(stock_code, "fetch_data", "completed")
                    active_stage = "process_data"
                    logger.info("步骤 2/5: 清洗并统一数据...")
                    self.state_store.mark_stage(stock_code, "process_data", "running")
                    processed_data = self._process_stock_data(stock_data)

                artifact = self.state_store.save_artifact(
                    stock_code, "processed_data", processed_data
                )
                self.state_store.mark_stage(
                    stock_code, "process_data", "completed", artifact
                )

            active_stage = "retrieve_context"
            logger.info("步骤 3/5: 检索本地知识库...")
            self.state_store.mark_stage(stock_code, active_stage, "running")
            processed_data = self._attach_rag_context(processed_data)
            quality = evaluate_data_quality(processed_data)
            processed_data['data_quality'] = quality.to_dict()
            artifact = self.state_store.save_artifact(
                stock_code, "processed_data", processed_data
            )
            self.state_store.mark_stage(stock_code, active_stage, "completed", artifact)

            if not quality.can_generate:
                raise ValueError("数据质量检查失败: " + "；".join(quality.critical_errors))
            if quality.warnings:
                logger.warning(
                    f"数据质量降级（{quality.score}分）: " + "；".join(quality.warnings)
                )
            else:
                logger.info(f"数据质量检查通过（{quality.score}分）")

            active_stage = "generate_sections"
            logger.info("步骤 4/5: 生成报告章节...")
            self.state_store.mark_stage(stock_code, active_stage, "running")
            section_cache = self.state_store.load_artifact(stock_code, "report_sections")

            def save_section(section_key: str, content: str) -> None:
                section_cache[section_key] = content
                self.state_store.save_artifact(
                    stock_code, "report_sections", section_cache
                )

            report_content = self.qianwen_client.generate_full_report(
                processed_data,
                existing_sections=section_cache,
                on_section=save_section,
            )
            section_cache = report_content['sections']
            section_artifact = self.state_store.save_artifact(
                stock_code, "report_sections", section_cache
            )
            self.state_store.mark_stage(
                stock_code, active_stage, "completed", section_artifact
            )

            active_stage = "export_docx"
            logger.info("步骤 5/5: 生成Word文档...")
            self.state_store.mark_stage(stock_code, active_stage, "running")
            final_report = {
                'symbol': stock_code,
                'stock_name': processed_data['stock_name'],
                'sections': report_content['sections'],
                'data_quality': quality.to_dict(),
                'sources': processed_data.get('rag_sources', []),
            }

            self.report_generator = ReportGenerator()
            self.report_generator.generate_full_report(final_report)

            if not output_path:
                output_dir = os.path.join(self.project_dir, 'output')
                os.makedirs(output_dir, exist_ok=True)
                stock_name = processed_data['stock_name']
                for char in ['<', '>', ':', '"', '/', '\\', '|', '?', '*']:
                    stock_name = stock_name.replace(char, '')
                output_path = os.path.join(output_dir, f"{stock_name.strip()}.docx")

            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            self.report_generator.save_report(output_path)
            self.state_store.mark_stage(
                stock_code, active_stage, "completed", output_path
            )
            self.state_store.complete(stock_code, output_path)

            # 清理ReportGenerator实例
            del self.report_generator
            self.report_generator = None

            logger.info("=" * 60)
            logger.info(f"研究报告生成成功！")
            logger.info(f"文件路径: {output_path}")
            logger.info("=" * 60)

            # ========== 内存管理（新增）==========
            self._report_count += 1
            logger.info(f"已生成 {self._report_count} 份报告")

            # 每生成N份报告后清理缓存
            if self._report_count % self.auto_clean_interval == 0:
                logger.info(f"")
                logger.info("█" * 60)
                logger.info(f"已生成 {self._report_count} 份报告，执行自动内存清理...")
                logger.info("█" * 60)
                self._cleanup_memory(force=False)

            # 每100份报告强制清理一次
            if self._report_count % 100 == 0:
                logger.warning("")
                logger.info("█" * 60)
                logger.info(f"已生成 {self._report_count} 份报告，执行强制内存清理...")
                logger.info("█" * 60)
                self._cleanup_memory(force=True)
            # ==================================

            return output_path

        except Exception as e:
            self.state_store.fail(stock_code, active_stage, e)
            logger.error(f"生成报告失败: {e}")
            raise


def main():
    """主函数"""
    project_dir = os.path.dirname(os.path.dirname(__file__))
    load_dotenv(os.path.join(project_dir, 'config', '.env'))

    # 解析命令行参数
    parser = argparse.ArgumentParser(description='A股研究报告自动生成系统（内存优化版）')
    parser.add_argument('stock_code', nargs='?', help='股票代码（6位数字），如：002659')
    parser.add_argument('-o', '--output', help='输出文件路径')
    parser.add_argument('-b', '--batch', help='批量生成模式，指定包含股票代码的文件')
    parser.add_argument('--clean-interval', type=int, default=10,
                       help='自动清理间隔（默认每10份报告清理一次）')
    parser.add_argument('--output-dir', default=None, help='批量模式下的输出目录')
    parser.add_argument('--limit', type=int, default=None, help='批量模式下最多处理多少只股票')
    parser.add_argument('--dry-run', action='store_true', help='不调用DashScope API，用模拟内容验证流程')
    parser.add_argument('--no-rag', action='store_true', help='禁用本地知识库检索')
    parser.add_argument('--knowledge-base', default=None, help='知识库目录，默认 knowledge_base/')
    parser.add_argument('--rag-top-k', type=int, default=6, help='RAG最多注入的资料片段数')
    parser.add_argument('--offline-fixtures', default=None,
                        help='从目录中的 <股票代码>.json 读取标准化数据，不访问行情API')
    parser.add_argument('--state-dir', default=None,
                        help='工作流状态和缓存目录，默认 data/')

    args = parser.parse_args()

    settings = AppSettings.from_env()
    api_key = settings.llm_api_key
    if not api_key and not args.dry_run:
        logger.error("错误: 未找到 LLM_API_KEY 或 DASHSCOPE_API_KEY 环境变量")
        logger.error("请在config/.env文件中配置所选模型服务")
        sys.exit(1)
    if args.dry_run and not api_key:
        api_key = "dry-run"

    # 创建生成器（带内存优化）
    generator = ResearchReportGenerator(
        api_key,
        auto_clean_interval=args.clean_interval,
        knowledge_base_dir=args.knowledge_base,
        rag_enabled=not args.no_rag,
        rag_top_k=args.rag_top_k,
        dry_run=args.dry_run,
        settings=settings,
        offline_fixture_dir=args.offline_fixtures,
        state_dir=args.state_dir,
    )

    try:
        if args.batch:
            # 批量生成模式
            logger.info(f"批量生成模式: {args.batch}")

            if not os.path.exists(args.batch):
                logger.error(f"文件不存在: {args.batch}")
                sys.exit(1)

            with open(args.batch, 'r', encoding='utf-8') as f:
                stock_codes = [line.strip() for line in f if line.strip() and not line.lstrip().startswith('#')]

            if args.limit is not None:
                if args.limit <= 0:
                    logger.error("--limit 必须大于0")
                    sys.exit(1)
                stock_codes = stock_codes[:args.limit]

            logger.info(f"共 {len(stock_codes)} 只股票待生成报告")
            if not stock_codes:
                logger.error("股票代码列表为空")
                sys.exit(1)

            success_count = 0
            fail_count = 0

            for i, code in enumerate(stock_codes, 1):
                try:
                    logger.info(f"\n处理第 {i}/{len(stock_codes)} 只股票: {code}")
                    output_path = None
                    if args.output_dir:
                        os.makedirs(args.output_dir, exist_ok=True)
                        output_path = os.path.join(args.output_dir, f"{code}.docx")
                    generator.generate_report(code, output_path)
                    success_count += 1
                except Exception as e:
                    logger.error(f"生成 {code} 报告失败: {e}")
                    fail_count += 1
                    continue

            # 批量完成后强制清理
            generator._cleanup_memory(force=True)

            logger.info(f"\n")
            logger.info("=" * 60)
            logger.info(f"批量生成完成！")
            logger.info(f"总数: {len(stock_codes)}, 成功: {success_count}, 失败: {fail_count}")
            if stock_codes:
                logger.info(f"成功率: {success_count/len(stock_codes)*100:.2f}%")
            logger.info("=" * 60)

        elif args.stock_code:
            # 单个股票生成模式
            stock_code = args.stock_code.strip()

            # 验证股票代码格式
            if not stock_code.isdigit() or len(stock_code) != 6:
                logger.error(f"无效的股票代码: {stock_code}，应为6位数字")
                sys.exit(1)

            output_path = generator.generate_report(stock_code, args.output)
            print(f"\n[成功] 报告生成成功: {output_path}")

        else:
            # 交互模式
            print("\n" + "=" * 60)
            print("A股研究报告自动生成系统（内存优化版）")
            print("=" * 60)

            stock_code = input("\n请输入股票代码（6位数字，如：002659）: ").strip()

            if not stock_code:
                logger.error("股票代码不能为空")
                sys.exit(1)

            if not stock_code.isdigit() or len(stock_code) != 6:
                logger.error(f"无效的股票代码: {stock_code}，应为6位数字")
                sys.exit(1)

            output_path = generator.generate_report(stock_code)
            print(f"\n[成功] 报告生成成功: {output_path}")

    except KeyboardInterrupt:
        logger.info("\n用户中断操作")
        # 退出前清理内存
        generator._cleanup_memory(force=True)
        sys.exit(0)
    except Exception as e:
        logger.error(f"程序异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
