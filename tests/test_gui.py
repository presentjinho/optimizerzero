import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUI = ROOT / "src" / "optimizerzero" / "gui.py"


class GuiSourceTests(unittest.TestCase):
    def read_gui(self):
        return GUI.read_text(encoding="utf-8")

    def test_run_uses_file_snapshot_for_worker(self):
        source = self.read_gui()

        self.assertIn("files_snapshot = list(self.files)", source)
        self.assertIn("target=self._run_worker, args=(files_snapshot, options)", source)
        self.assertIn("def _run_worker(self, files: list[Path], options: OptimizeOptions)", source)
        self.assertIn("for path in files:", source)

    def test_running_state_locks_mutating_controls(self):
        source = self.read_gui()

        self.assertIn("def set_running(self, running: bool)", source)
        self.assertIn("self.set_running(True)", source)
        self.assertIn("self.set_running(False)", source)
        self.assertIn("Wait for the current optimization to finish before clearing.", source)


if __name__ == "__main__":
    unittest.main()
