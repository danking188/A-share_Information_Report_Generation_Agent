import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))

from data_quality import evaluate_data_quality


class DataQualityTest(unittest.TestCase):
    def test_missing_financial_data_is_fatal(self):
        result = evaluate_data_quality({"stock_name": "测试公司"})
        self.assertEqual("failed", result.status)
        self.assertFalse(result.can_generate)

    def test_missing_optional_company_fields_is_degraded(self):
        result = evaluate_data_quality({
            "stock_name": "测试公司",
            "historical_financial": {
                "2026年06月": {"revenue_yoy": 1.0, "net_profit_yoy": 2.0}
            },
        })
        self.assertEqual("degraded", result.status)
        self.assertTrue(result.can_generate)
        self.assertIn("缺少所属行业", result.warnings)


if __name__ == "__main__":
    unittest.main()
