import sys
import tempfile
import unittest
from pathlib import Path

from docx import Document


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))

from main import ResearchReportGenerator
from workflow_state import WorkflowStateStore


class OfflineWorkflowTest(unittest.TestCase):
    def test_offline_fixture_generates_report_and_completed_state(self):
        fixture_dir = PROJECT_DIR / "tests" / "fixtures"
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.docx"
            generator = ResearchReportGenerator(
                "dry-run",
                dry_run=True,
                rag_enabled=False,
                offline_fixture_dir=str(fixture_dir),
                state_dir=tmpdir,
            )

            result = generator.generate_report("000001", str(output_path))
            self.assertEqual(str(output_path), result)
            self.assertTrue(output_path.exists())

            state = WorkflowStateStore(tmpdir).load("000001")
            self.assertEqual("completed", state["status"])
            self.assertTrue(all(value == "completed" for value in state["stages"].values()))

            text = "\n".join(paragraph.text for paragraph in Document(output_path).paragraphs)
            self.assertIn("数据状态：完整", text)
            self.assertIn("较2025年06月同比增长10.00%", text)


if __name__ == "__main__":
    unittest.main()
