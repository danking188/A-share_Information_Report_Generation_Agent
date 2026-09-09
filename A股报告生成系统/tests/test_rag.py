import tempfile
import unittest
from pathlib import Path

import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))

from rag import RAGRetriever


class RAGRetrieverTest(unittest.TestCase):
    def test_retrieves_relevant_local_document(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            kb_dir = Path(tmpdir)
            raw_dir = kb_dir / "raw"
            raw_dir.mkdir(parents=True)
            (raw_dir / "bank.md").write_text(
                "平安银行 主营零售银行和对公金融服务，具备综合金融协同优势。",
                encoding="utf-8",
            )

            retriever = RAGRetriever(str(kb_dir), top_k=2)
            retriever.ensure_index()
            context = retriever.build_context("平安银行 零售银行")

            self.assertIn("平安银行", context)
            self.assertIn("bank.md", context)
            self.assertIn("[S1]", context)

    def test_rebuilds_index_after_document_is_deleted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            kb_dir = Path(tmpdir)
            raw_dir = kb_dir / "raw"
            raw_dir.mkdir(parents=True)
            first = raw_dir / "first.md"
            second = raw_dir / "second.md"
            first.write_text("平安银行 零售银行", encoding="utf-8")
            second.write_text("新能源 汽车电池", encoding="utf-8")

            retriever = RAGRetriever(str(kb_dir), top_k=2)
            self.assertEqual(2, retriever.ensure_index())
            first.unlink()

            refreshed = RAGRetriever(str(kb_dir), top_k=2)
            self.assertEqual(1, refreshed.ensure_index())
            self.assertNotIn("first.md", refreshed.build_context("平安银行"))


if __name__ == "__main__":
    unittest.main()
