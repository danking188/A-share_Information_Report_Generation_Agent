import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))

from workflow_state import WorkflowStateStore, load_json


class WorkflowStateTest(unittest.TestCase):
    def test_persists_stages_and_artifacts_atomically(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = WorkflowStateStore(tmpdir)
            state = store.start("000001")
            self.assertEqual("running", state["status"])

            artifact = store.save_artifact("000001", "processed_data", {"value": 1})
            store.mark_stage("000001", "process_data", "completed", artifact)
            persisted = load_json(store.state_path("000001"))

            self.assertEqual("completed", persisted["stages"]["process_data"])
            self.assertEqual({"value": 1}, store.load_artifact("000001", "processed_data"))
            self.assertFalse(list(Path(tmpdir).rglob("*.tmp")))


if __name__ == "__main__":
    unittest.main()
