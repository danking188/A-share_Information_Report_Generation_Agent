import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))

from report_generator import ReportGenerator


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


class ReportGeneratorTest(unittest.TestCase):
    def test_configurable_fonts_and_title_style_are_written_to_docx(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            os.environ,
            {
                "REPORT_BODY_FONT": "Noto Sans CJK SC",
                "REPORT_HEADING_FONT": "Noto Sans CJK SC",
            },
        ):
            output_path = Path(tmpdir) / "report.docx"
            generator = ReportGenerator()
            generator.generate_full_report({
                "stock_name": "平安银行",
                "symbol": "000001",
                "sections": {"company_overview": "中文字体导出测试。"},
            })
            generator.save_report(str(output_path))

            with zipfile.ZipFile(output_path) as archive:
                document_xml = archive.read("word/document.xml")
                styles_xml = archive.read("word/styles.xml")

            self.assertIn("平安银行".encode("utf-8"), document_xml)
            self.assertIn(b'Noto Sans CJK SC', document_xml)

            styles = ElementTree.fromstring(styles_xml)
            title_style = next(
                style for style in styles.findall(f"{{{W_NS}}}style")
                if style.get(f"{{{W_NS}}}styleId") == "Title"
            )
            title_ppr = title_style.find(f"{{{W_NS}}}pPr")
            self.assertIsNone(
                None if title_ppr is None else title_ppr.find(f"{{{W_NS}}}pBdr")
            )


if __name__ == "__main__":
    unittest.main()
