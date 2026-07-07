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
        self.assertIn("optimize_many(files, options)", source)

    def test_running_state_locks_mutating_controls(self):
        source = self.read_gui()

        self.assertIn("def set_running(self, running: bool)", source)
        self.assertIn("self.set_running(True)", source)
        self.assertIn("self.set_running(False)", source)
        self.assertIn("Wait for the current optimization to finish before clearing.", source)

    def test_gui_uses_simplified_goal_and_auto_workers(self):
        source = self.read_gui()

        self.assertIn("self.goal_var = tk.StringVar(value=Goal.SMART.value)", source)
        self.assertIn('self.workers_var = self._entry(limits, f"CPU threads (auto={default_workers()})", "auto", 8)', source)
        self.assertIn("merge_goal_options(", source)
        self.assertNotIn("self.loss_budget_var", source)
        self.assertNotIn("self.quality_var", source)


if __name__ == "__main__":
    unittest.main()
