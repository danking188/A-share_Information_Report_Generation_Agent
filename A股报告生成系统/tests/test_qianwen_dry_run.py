import unittest
from pathlib import Path
from unittest.mock import Mock

import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))

from qianwen_client import QianwenClient


class QianwenDryRunTest(unittest.TestCase):
    def test_dry_run_report_has_required_sections(self):
        client = QianwenClient("dry-run", dry_run=True)
        report = client.generate_full_report({
            "symbol": "000001",
            "stock_name": "平安银行",
            "industry": "银行",
            "main_business": "商业银行业务",
            "financial_summary": {
                "revenue": "100000000",
                "net_profit": "20000000",
            },
            "historical_financial": {
                "2024年12月": {"revenue": "100000000", "net_profit": "20000000"},
                "2023年12月": {"revenue": "90000000", "net_profit": "15000000"},
            },
        })

        sections = report["sections"]
        self.assertIn("investment_advice", sections)
        self.assertIn("investment_logic", sections)
        self.assertIn("company_overview", sections)
        self.assertIn("financial_indicators", sections)
        self.assertIn("business_outlook", sections)
        self.assertIn("comparable_analysis", sections)

    def test_reuses_cached_sections_and_reports_new_sections(self):
        provider = Mock()
        client = QianwenClient("key", provider=provider)
        client.generate_investment_advice = Mock(side_effect=AssertionError("不应重新生成"))
        client.generate_investment_logic = Mock(return_value="logic")
        client.generate_company_overview_from_data = Mock(return_value="overview")
        client.generate_financial_analysis = Mock(return_value="financial")
        client.generate_business_outlook = Mock(return_value="outlook")
        client.generate_comparable_analysis = Mock(return_value="comparable")
        completed = []

        report = client.generate_full_report(
            {
                "symbol": "000001",
                "stock_name": "平安银行",
                "industry": "银行",
                "main_business": "商业银行业务",
                "historical_financial": {},
            },
            existing_sections={"investment_advice": "cached advice"},
            on_section=lambda key, content: completed.append(key),
        )

        self.assertEqual("cached advice", report["sections"]["investment_advice"])
        self.assertNotIn("investment_advice", completed)
        self.assertIn("investment_logic", completed)


if __name__ == "__main__":
    unittest.main()
