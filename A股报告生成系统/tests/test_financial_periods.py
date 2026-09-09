import sys
import unittest
from pathlib import Path

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))

from main import ResearchReportGenerator
from qianwen_client import QianwenClient


class FinancialPeriodTest(unittest.TestCase):
    def setUp(self):
        self.generator = ResearchReportGenerator.__new__(ResearchReportGenerator)
        self.profit_sheet = pd.DataFrame([
            {"报告日": 20250331, "营业收入": 40.0, "归属于母公司的净利润": 8.0},
            {"报告日": 20260630, "营业收入": 110.0, "归属于母公司的净利润": 25.0},
            {"报告日": 20241231, "营业收入": 180.0, "归属于母公司的净利润": 25.0},
            {"报告日": 20250630, "营业收入": 100.0, "归属于母公司的净利润": 20.0},
            {"报告日": 20260331, "营业收入": 50.0, "归属于母公司的净利润": 10.0},
            {"报告日": 20251231, "营业收入": 200.0, "归属于母公司的净利润": 30.0},
        ])

    def test_summary_uses_report_day_and_named_columns(self):
        summary = self.generator._extract_financial_summary({
            "profit_sheet_sina": self.profit_sheet
        })
        self.assertEqual("2026年06月30日", summary["latest_year"])
        self.assertEqual(110.0, summary["revenue"])
        self.assertEqual(25.0, summary["net_profit"])

    def test_growth_compares_same_period_last_year(self):
        historical = self.generator._extract_historical_financial({
            "profit_sheet_sina": self.profit_sheet
        })
        half_year = historical["2026年06月"]
        self.assertEqual("2025年06月", half_year["comparable_period"])
        self.assertEqual(10.0, half_year["revenue_yoy"])
        self.assertEqual(25.0, half_year["net_profit_yoy"])

        content = QianwenClient("dry-run", dry_run=True).generate_financial_indicators({
            "historical_financial": historical
        })
        self.assertIn("较2025年06月同比增长10.00%", content)
        self.assertNotIn("较2026年03月", content)


if __name__ == "__main__":
    unittest.main()
