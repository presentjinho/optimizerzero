import io
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

from optimizerzero.cli import main


class CliTests(unittest.TestCase):
    def test_doctor_runs(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["doctor"])

        self.assertEqual(code, 0)
        self.assertIn("Pillow: ok", out.getvalue())

    def test_version_runs(self):
        out = io.StringIO()
        with self.assertRaises(SystemExit) as ctx, redirect_stdout(out):
            main(["--version"])

        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("optimizerzero 0.1.0", out.getvalue())

    def test_in_place_requires_yes(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            source = tmp_path / "sample.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("a.txt", "hello")
            out = io.StringIO()

            with redirect_stdout(out):
                code = main(["optimize", str(source), "--in-place"])

            self.assertEqual(code, 2)
            self.assertIn("Refusing --in-place", out.getvalue())

    def test_verify_reports_valid_zip(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            source = tmp_path / "sample.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("a.txt", "hello")
            out = io.StringIO()

            with redirect_stdout(out):
                code = main(["verify", str(source)])

            self.assertEqual(code, 0)
            self.assertIn("ok: sample.zip", out.getvalue())

    def test_analyze_reports_kind_summary(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            source = tmp_path / "sample.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("a.txt", "hello")
            out = io.StringIO()

            with redirect_stdout(out):
                code = main(["analyze", str(tmp_path)])

            self.assertEqual(code, 0)
            self.assertIn("archive: 1 files", out.getvalue())

    def test_scan_includes_generic_fallback_by_default(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            source = tmp_path / "notes.txt"
            source.write_text("hello", encoding="utf-8")
            out = io.StringIO()

            with redirect_stdout(out):
                code = main(["scan", str(tmp_path)])

            self.assertEqual(code, 0)
            self.assertIn("notes.txt", out.getvalue())

    def test_optimize_uses_goal_and_workers(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            source = tmp_path / "notes.txt"
            source.write_text("hello\n" * 1000, encoding="utf-8")
            out = io.StringIO()

            with redirect_stdout(out):
                code = main(["optimize", str(source), "--goal", "smart", "--workers", "2"])

            self.assertEqual(code, 0)
            self.assertIn("optimized: notes.txt", out.getvalue())

    def test_duplicates_reports_group(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            for name in ("a.zip", "b.zip"):
                with zipfile.ZipFile(tmp_path / name, "w") as archive:
                    archive.writestr("a.txt", "same")
            out = io.StringIO()

            with redirect_stdout(out):
                code = main(["duplicates", str(tmp_path)])

            self.assertEqual(code, 0)
            self.assertIn("groups: 1", out.getvalue())


if __name__ == "__main__":
    unittest.main()
