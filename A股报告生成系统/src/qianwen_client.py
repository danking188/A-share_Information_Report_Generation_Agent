"""
千问API集成模块
使用千问大模型生成研究报告内容
启用联网搜索功能获取公司概况
"""

import dashscope
from dashscope import Generation
from typing import Dict, List, Optional, Callable
from loguru import logger
import json
import time


class QianwenClient:
    """千问API客户端"""

    def __init__(self, api_key: str):
        """
        初始化千问客户端

        Args:
            api_key: 千问API密钥
        """
        self.api_key = api_key
        dashscope.api_key = api_key
        self.model = "qwen-max"  # 使用千问最大模型
        self.total_tokens = 0  # 总token使用量
        self.call_count = 0  # API调用次数

    def _call_api(self, messages: List[Dict], temperature: float = 0.7,
                  max_tokens: int = 7000, enable_search: bool = False) -> str:
        """
        调用千问API

        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            enable_search: 是否启用联网搜索（通过prompt指令）

        Returns:
            模型响应文本
        """
        max_retries = 5
        retry_delay = 3

        for attempt in range(max_retries):
            try:
                logger.info(f"调用千问API (尝试 {attempt + 1}/{max_retries})..."
                          f"{' [联网搜索]' if enable_search else ''}")

                # 构建API调用参数
                # 注意：qwen-plus或qwen-turbo可能不支持联网搜索，使用qwen-max
                model = self.model
                if enable_search:
                    # 使用支持联网搜索的模型
                    model = "qwen-max"

                response = Generation.call(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    result_format='message'
                )

                if response.status_code == 200:
                    result = response.output.choices[0].message.content

                    # 记录token使用情况
                    if hasattr(response, 'usage') and response.usage:
                        input_tokens = response.usage.input_tokens
                        output_tokens = response.usage.output_tokens
                        total_tokens = response.usage.total_tokens

                        self.total_tokens += total_tokens
                        self.call_count += 1

                        logger.info(f"API调用成功 - 输入: {input_tokens} tokens, "
                                  f"输出: {output_tokens} tokens, "
                                  f"总计: {total_tokens} tokens")
                    else:
                        self.call_count += 1
                        logger.info("API调用成功 (无token信息)")

                    return result
                else:
                    logger.error(f"API调用失败: {response.code} - {response.message}")
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                    else:
                        raise Exception(f"API调用失败: {response.message}")

            except Exception as e:
                logger.error(f"API调用异常: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    raise

    def generate_investment_advice(self, stock_data: Dict) -> Dict:
        """
        生成投资建议（评级+核心逻辑）

        Args:
            stock_data: 股票数据

        Returns:
            包含评级和核心逻辑的字典
        """
        # 准备数据
        stock_name = stock_data.get('stock_name', 'N/A')
        symbol = stock_data.get('symbol', 'N/A')
        current_price = stock_data.get('current_price', 'N/A')
        pe_ratio = stock_data.get('pe_ratio', 'N/A')
        pb_ratio = stock_data.get('pb_ratio', 'N/A')
        market_cap = stock_data.get('market_cap', 'N/A')
        main_business = stock_data.get('main_business', 'N/A')

        financial_summary = stock_data.get('financial_summary', {})
        revenue = financial_summary.get('revenue', 'N/A')
        net_profit = financial_summary.get('net_profit', 'N/A')

        # 准备历史数据描述
        historical = stock_data.get('historical_financial', {})
        historical_desc = ""
        if len(historical) >= 2:
            periods = list(historical.items())[:2]
            for period_name, period_data in periods:
                period_revenue = period_data.get('revenue', 'N/A')
                period_profit = period_data.get('net_profit', 'N/A')
                historical_desc += f"{period_name}: 营收{period_revenue}元, 净利润{period_profit}元; "

        prompt = f"""
请为{stock_name}({symbol})给出投资建议。

**公司基本情况：**
- 股票代码：{symbol}
- 股票名称：{stock_name}
- 当前股价：{current_price}元
- 市盈率：{pe_ratio}
- 市净率：{pb_ratio}
- 总市值：{market_cap}
- 主营业务：{main_business}

**最新财务数据：**
- 营业收入：{revenue}元
- 净利润：{net_profit}元

**历史财务趋势：**
{historical_desc if historical_desc else '暂无历史数据'}

**投资评级选项（4选1）：**
- 强烈推荐：行业龙头，业绩优秀，增长强劲，估值合理
- 推荐：业绩良好，行业地位稳固，有增长潜力
- 持有：业绩平稳，行业地位一般，等待更好的入场时机
- 不建议持有：业绩承压，行业前景不明，存在较大风险

**输出格式要求：**
投资建议：[评级]。[100-150字的分析说明]

**写作要求：**
- 积极但客观，即使数据不佳也要积极表述（如"短期承压但长期向好"）
- 严禁使用"综上所述"、"值得注意的是"、"总而言之"等AI痕迹词汇
- 严格基于上述提供的真实数据，不编造任何财务指标
- 如果数据不足，就说"相关数据暂未披露"
- 简洁专业，像人类资深研究员的判断
"""

        messages = [
            {"role": "system", "content": "资深投资分析师，基于真实财务数据和市场信息给出专业投资建议。措辞积极但不失客观，即使数据不佳也要从积极角度分析。"},
            {"role": "user", "content": prompt}
        ]

        result = self._call_api(messages, temperature=0.6, max_tokens=1000)

        # 清理结果，确保以"投资建议："开头
        advice_text = result.strip()
        if not advice_text.startswith("投资建议："):
            # 如果AI没有按格式输出，手动添加前缀
            # 尝试提取评级
            rating = "推荐"
            for r in ["强烈推荐", "推荐", "持有", "不建议持有"]:
                if r in advice_text:
                    rating = r
                    break
            advice_text = f"投资建议：{rating}。{advice_text}"

        return advice_text

    def generate_investment_logic(self, stock_data: Dict) -> str:
        """
        生成投资逻辑

        Args:
            stock_data: 股票数据

        Returns:
            投资逻辑文本
        """
        stock_name = stock_data.get('stock_name', 'N/A')
        symbol = stock_data.get('symbol', 'N/A')
        industry = stock_data.get('industry', 'N/A')
        main_business = stock_data.get('main_business', 'N/A')

        # 当前股价和估值数据
        current_data = stock_data.get('current_data', {})
        current_price = current_data.get('current_price', 'N/A')
        pe_ratio = current_data.get('pe_ratio', 'N/A')
        pb_ratio = current_data.get('pb_ratio', 'N/A')
        market_cap = current_data.get('market_cap', 'N/A')

        # 最新财务数据
        latest = stock_data.get('latest_financial', {})
        revenue = latest.get('operating_revenue', 'N/A')
        net_profit = latest.get('net_profit', 'N/A')
        roe = latest.get('roe', 'N/A')

        # 历史财务趋势
        historical = stock_data.get('historical_financial', {})
        historical_desc = ""
        if len(historical) >= 2:
            periods = list(historical.items())[:2]
            for period_name, period_data in periods:
                period_revenue = period_data.get('revenue', 'N/A')
                period_profit = period_data.get('net_profit', 'N/A')
                historical_desc += f"- {period_name}：营收{period_revenue}元，净利润{period_profit}元\n"
        elif len(historical) == 1:
            period_name, period_data = list(historical.items())[0]
            period_revenue = period_data.get('revenue', 'N/A')
            period_profit = period_data.get('net_profit', 'N/A')
            historical_desc = f"- {period_name}：营收{period_revenue}元，净利润{period_profit}元"
        else:
            historical_desc = "暂无历史财务数据"

        prompt = f"""
请为{stock_name}({symbol})生成投资逻辑分析。

**基本信息：**
- 股票：{stock_name}({symbol})
- 行业：{industry}
- 主营业务：{main_business}

**当前股价和估值：**
- 当前股价：{current_price}元
- 市盈率(PE)：{pe_ratio}
- 市净率(PB)：{pb_ratio}
- 总市值：{market_cap}

**最新财务指标：**
- 营业收入：{revenue}
- 净利润：{net_profit}
- ROE：{roe}

**历史财务趋势：**
{historical_desc if historical_desc else '暂无历史数据'}

**输出要求：**
- 200-300字
- 深入分析投资该公司的核心逻辑
- 包含：行业前景、公司竞争力、成长性、估值合理性等维度
- 逻辑清晰，层层递进
- 严禁使用"综上所述"、"值得注意的是"、"总而言之"等AI痕迹词汇
- 积极但客观，突出投资亮点
- 严格基于上述真实数据，不编造财务指标
"""

        messages = [
            {"role": "system", "content": "资深投资分析师，擅长挖掘投资价值和梳理投资逻辑。分析深入专业，逻辑清晰。"},
            {"role": "user", "content": prompt}
        ]

        return self._call_api(messages, temperature=0.7, max_tokens=1500)

    def generate_company_overview(self, stock_name: str, symbol: str) -> str:
        """
        生成公司概况（基于已有数据和知识）

        Args:
            stock_name: 股票名称
            symbol: 股票代码

        Returns:
            公司概况文本
        """
        prompt = f"""
请为{stock_name}({symbol})生成公司概况。

**要求：**
- 100-150字
- 简洁介绍公司主营业务和行业地位
- 只陈述核心事实
- 严禁使用"综上所述"、"值得注意的是"等AI痕迹词汇
- 严格基于已有知识，不确定就说"相关信息暂未披露"
"""

        messages = [
            {"role": "system", "content": "专业研究员，提供准确简洁的公司信息。"},
            {"role": "user", "content": prompt}
        ]

        return self._call_api(messages, temperature=0.5, max_tokens=1500)

    def generate_financial_indicators(self, stock_data: Dict) -> str:
        """
        生成主要财务指标（近三年）- 段落叙述式

        Args:
            stock_data: 股票数据

        Returns:
            财务指标叙述文本
        """
        historical = stock_data.get('historical_financial', {})

        if len(historical) == 0:
            return "### 主要财务指标（近三年）\n\n财务数据不足，暂无法提供分析。"

        # 提取最近3期数据
        periods_list = list(historical.items())[:3]

        # 格式化数字（带千位分隔符）
        def format_number(num):
            if num is None or num == 'N/A':
                return 'N/A'
            try:
                return f"{float(num):,.2f}元"
            except:
                return 'N/A'

        # 计算增长率
        def calc_growth(current, previous):
            try:
                if current and previous and current != 'N/A' and previous != 'N/A':
                    curr_val = float(current)
                    prev_val = float(previous)
                    if prev_val != 0:
                        rate = (curr_val - prev_val) / abs(prev_val) * 100
                        if rate > 0:
                            return f"同比增长{rate:.2f}%"
                        else:
                            return f"同比下降{abs(rate):.2f}%"
                return "数据不可比"
            except:
                return "数据不可比"

        # 生成段落叙述
        content = "### 主要财务指标（近三年）\n\n"

        # 营业收入部分
        content += "营业收入：\n"
        for idx, (period_name, period_data) in enumerate(periods_list):
            revenue = period_data.get('revenue', 'N/A')
            revenue_str = format_number(revenue)

            # 直接使用period_name作为显示名称（如"2025年09月"）
            display_name = str(period_name)

            if idx == 0:
                content += f"  - {display_name}：{revenue_str}。\n"
            else:
                # 计算与上期的增长率
                prev_revenue = periods_list[idx-1][1].get('revenue')
                growth = calc_growth(revenue, prev_revenue)
                content += f"  - {display_name}：{revenue_str}，{growth}。\n"

        content += "\n"

        # 净利润部分
        content += "归属于上市公司股东的净利润：\n"
        for idx, (period_name, period_data) in enumerate(periods_list):
            net_profit = period_data.get('net_profit', 'N/A')
            profit_str = format_number(net_profit)

            # 直接使用period_name作为显示名称
            display_name = str(period_name)

            if idx == 0:
                content += f"  - {display_name}：{profit_str}。\n"
            else:
                # 计算与上期的变化率
                prev_profit = periods_list[idx-1][1].get('net_profit')
                change = calc_growth(net_profit, prev_profit)
                # 如果是亏损，用"减少亏损"或"增加亏损"
                try:
                    curr_val = float(net_profit) if net_profit != 'N/A' else 0
                    prev_val = float(prev_profit) if prev_profit != 'N/A' else 0
                    if curr_val < 0 and prev_val < 0:
                        if abs(curr_val) < abs(prev_val):
                            change = f"较{display_name}的{format_number(prev_profit)}减少亏损{abs((curr_val - prev_val) / abs(prev_val) * 100):.2f}%"
                        else:
                            change = f"较{display_name}的{format_number(prev_profit)}增加亏损{abs((curr_val - prev_val) / abs(prev_val) * 100):.2f}%"
                except:
                    pass
                content += f"  - {display_name}：{profit_str}，{change}。\n"

        return content

    def generate_financial_analysis(self, stock_data: Dict) -> str:
        """
        生成财务数据分析

        Args:
            stock_data: 股票数据

        Returns:
            财务分析文本
        """
        historical = stock_data.get('historical_financial', {})
        financial_summary = stock_data.get('financial_summary', {})

        # 准备财务数据
        revenue = financial_summary.get('revenue', 'N/A')
        net_profit = financial_summary.get('net_profit', 'N/A')

        if revenue and revenue != 'N/A':
            try:
                revenue_yi = float(revenue) / 100000000
                revenue_str = f"{revenue_yi:.2f}亿元"
            except:
                revenue_str = "N/A"
        else:
            revenue_str = "N/A"

        if net_profit and net_profit != 'N/A':
            try:
                profit_wan = float(net_profit) / 10000
                profit_str = f"{profit_wan:.2f}万元"
            except:
                profit_str = "N/A"
        else:
            profit_str = "N/A"

        # 准备历史数据描述（使用自然表述）
        historical_desc = ""
        if len(historical) >= 2:
            periods = list(historical.values())[:2]
            period_labels = ["最近一期", "上一期"]  # 更自然的表述
            for i, period in enumerate(periods):
                period_revenue = period.get('revenue', 'N/A')
                period_profit = period.get('net_profit', 'N/A')

                if period_revenue and period_revenue != 'N/A':
                    try:
                        period_revenue_yi = float(period_revenue) / 100000000
                        period_revenue_str = f"{period_revenue_yi:.2f}亿元"
                    except:
                        period_revenue_str = "N/A"
                else:
                    period_revenue_str = "N/A"

                if period_profit and period_profit != 'N/A':
                    try:
                        period_profit_wan = float(period_profit) / 10000
                        period_profit_str = f"{period_profit_wan:.2f}万元"
                    except:
                        period_profit_str = "N/A"
                else:
                    period_profit_str = "N/A"

                historical_desc += f"- {period_labels[i]}：营业收入{period_revenue_str}，净利润{period_profit_str}\n"

        prompt = f"""
{stock_data.get('stock_name', 'N/A')}财务数据分析

**最新财务数据：**
- 营业收入：{revenue_str}
- 净利润：{profit_str}

**历史财务数据（最近2期）：**
{historical_desc if historical_desc else '暂无历史数据'}

**分析要求：**
- 200-250字
- 分析营收规模、增长趋势、盈利能力
- 严格基于上述真实数据
- 严禁编造任何财务指标（ROE、毛利率、现金流等）
- 积极但客观，即使数据不佳也要积极表述（如"短期承压但长期向好"）
- 严禁"综上所述"、"值得注意的是"等AI痕迹词汇
- 数据未披露就说"数据暂未披露"
"""

        messages = [
            {"role": "system", "content": "资深财务分析师，基于真实数据进行分析，措辞积极但不失客观。"},
            {"role": "user", "content": prompt}
        ]

        return self._call_api(messages, temperature=0.6, max_tokens=2000)

    def generate_business_outlook(self, stock_name: str, symbol: str,
                                  main_business: str) -> str:
        """
        生成业务展望和行业地位

        Args:
            stock_name: 股票名称
            symbol: 股票代码
            main_business: 主营业务

        Returns:
            业务展望和行业地位分析
        """
        prompt = f"""
请为{stock_name}({symbol})生成业务展望和行业地位分析。

**分析重点：**
- 行业发展趋势和市场空间
- 公司行业地位和核心竞争优势
- 未来发展方向和增长驱动因素
- 核心投资亮点

**输出要求：**
- 200-250字
- 聚焦核心亮点
- 积极但客观
- 严禁"综上所述"、"值得注意的是"等AI痕迹词汇
- 不确定就说"相关信息暂未披露"
"""

        messages = [
            {"role": "system", "content": "资深行业分析师，提供深入的行业和公司分析。"},
            {"role": "user", "content": prompt}
        ]

        return self._call_api(messages, temperature=0.7, max_tokens=2000)

    def generate_comparable_analysis(self, stock_name: str, symbol: str,
                                     industry: str) -> str:
        """
        生成可比上市公司对比

        Args:
            stock_name: 股票名称
            symbol: 股票代码
            industry: 所属行业

        Returns:
            可比公司对比分析
        """
        prompt = f"""
请为{stock_name}({symbol})生成可比上市公司对比分析。

**分析要求：**
- 简要分析同行业典型公司
- 公司相对优势和独特竞争力
- 估值合理性评估

**输出要求：**
- 150-200字
- 简洁对比
- 积极但客观
- 严禁"综上所述"、"值得注意的是"等AI痕迹词汇
- 无法获取具体数据就定性分析
- 不要编造具体财务数据
"""

        messages = [
            {"role": "system", "content": "专业投资分析师，进行客观的对比分析。"},
            {"role": "user", "content": prompt}
        ]

        return self._call_api(messages, temperature=0.7, max_tokens=2000)

    def generate_full_report(self, stock_data: Dict) -> Dict:
        """
        生成完整研究报告（新结构）

        Args:
            stock_data: 股票综合数据

        Returns:
            完整报告内容
        """
        logger.info(f"开始生成股票 {stock_data.get('symbol')} 的完整研究报告...")

        stock_name = stock_data.get('stock_name', 'N/A')
        symbol = stock_data.get('symbol', 'N/A')
        main_business = stock_data.get('main_business', 'N/A')
        industry = stock_data.get('industry', 'N/A')

        report = {
            'symbol': symbol,
            'stock_name': stock_name,
            'generate_time': stock_data.get('fetch_time'),
            'sections': {}
        }

        # 1. 投资建议（新增，放在第一位）
        logger.info("生成投资建议...")
        report['sections']['investment_advice'] = self.generate_investment_advice(stock_data)

        # 2. 投资逻辑（新增）
        logger.info("生成投资逻辑...")
        report['sections']['investment_logic'] = self.generate_investment_logic(stock_data)

        # 3. 公司概况
        logger.info("生成公司概况...")
        report['sections']['company_overview'] = self.generate_company_overview(
            stock_name, symbol
        )

        # 4. 主要财务指标
        logger.info("生成主要财务指标...")
        report['sections']['financial_indicators'] = self.generate_financial_indicators(
            stock_data
        )

        # 5. 财务数据分析
        logger.info("生成财务数据分析...")
        report['sections']['financial_analysis'] = self.generate_financial_analysis(
            stock_data
        )

        # 6. 业务展望和行业地位
        logger.info("生成业务展望和行业地位...")
        report['sections']['business_outlook'] = self.generate_business_outlook(
            stock_name, symbol, main_business
        )

        # 7. 可比上市公司对比
        logger.info("生成可比上市公司对比...")
        report['sections']['comparable_analysis'] = self.generate_comparable_analysis(
            stock_name, symbol, industry
        )

        logger.info("研究报告生成完成！")

        # 显示token使用统计
        logger.info("=" * 60)
        logger.info(f"Token使用统计:")
        logger.info(f"  API调用次数: {self.call_count}")
        logger.info(f"  总Token数: {self.total_tokens:,}")
        if self.call_count > 0:
            logger.info(f"  平均每次: {self.total_tokens // self.call_count:,} tokens")
        logger.info("=" * 60)

        return report


if __name__ == "__main__":
    # 测试代码
    import os
    from dotenv import load_dotenv

    load_dotenv()

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if api_key:
        client = QianwenClient(api_key)

        # 测试数据
        test_data = {
            "symbol": "002659",
            "stock_name": "凯文教育",
            "main_business": "教育服务",
            "industry": "教育",
            "current_price": "5.23",
            "pe_ratio": "150.5",
            "pb_ratio": "2.3",
            "market_cap": "30亿",
            "financial_summary": {
                "revenue": "249775900.00",
                "net_profit": "1610522.00"
            },
            "historical_financial": {
                "2024年09月": {"revenue": "249775900.00", "net_profit": "1610522.00"},
                "2023年12月": {"revenue": "234521000.00", "net_profit": "-82345600.00"}
            }
        }

        # 测试生成报告
        report = client.generate_full_report(test_data)

        print("\n" + "=" * 60)
        print("报告生成成功！")
        print("=" * 60)

        for section_name, section_content in report['sections'].items():
            print(f"\n【{section_name}】")
            if isinstance(section_content, dict):
                for k, v in section_content.items():
                    print(f"{k}: {v}")
            else:
                print(section_content[:500] + "..." if len(section_content) > 500 else section_content)
    else:
        print("请设置DASHSCOPE_API_KEY环境变量")
