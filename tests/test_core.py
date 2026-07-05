import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image

from optimizerzero.core import (
    OptimizeOptions,
    LossBudget,
    Goal,
    Profile,
    analyze_files,
    discover_files,
    find_duplicate_files,
    merge_goal_options,
    move_file,
    optimize_many,
    optimize_one,
    parse_size,
    planned_output_path,
    validate_epub,
)


def make_png_bytes(size=(64, 64), color=(255, 0, 0)):
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, "PNG")
    return out.getvalue()


def make_jpeg_bytes(size=(256, 256)):
    out = io.BytesIO()
    image = Image.new("RGB", size)
    pixels = image.load()
    for y in range(size[1]):
        for x in range(size[0]):
            pixels[x, y] = ((x * 3) % 256, (y * 5) % 256, ((x + y) * 7) % 256)
    image.save(out, "JPEG", quality=96)
    return out.getvalue()


class CoreTests(unittest.TestCase):
    def test_zip_recompress_keeps_entry_set(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            source = tmp_path / "sample.zip"
            with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr("folder/a.txt", "hello" * 1000)

            result = optimize_one(source, OptimizeOptions(profile=Profile.SAFE))

            self.assertEqual(result.status, "optimized")
            with zipfile.ZipFile(result.output) as archive:
                self.assertEqual(archive.namelist(), ["folder/a.txt"])
                self.assertEqual(archive.read("folder/a.txt"), b"hello" * 1000)

    def test_unsafe_zip_path_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            source = tmp_path / "bad.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("../bad.txt", "bad")

            result = optimize_one(source, OptimizeOptions(profile=Profile.SAFE))

            self.assertEqual(result.status, "error")
            self.assertIn("unsafe", result.message)

    def test_epub_mimetype_preserved(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            source = tmp_path / "book.epub"
            with zipfile.ZipFile(source, "w") as archive:
                info = zipfile.ZipInfo("mimetype")
                info.compress_type = zipfile.ZIP_STORED
                archive.writestr(info, b"application/epub+zip")
                archive.writestr("META-INF/container.xml", "<container/>")
                archive.writestr("content/chapter.xhtml", "hello" * 1000)

            result = optimize_one(source, OptimizeOptions(profile=Profile.SAFE))

            self.assertEqual(result.status, "optimized")
            ok, message = validate_epub(Path(result.output))
            self.assertTrue(ok, message)

    def test_balanced_image_archive_verifies(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            source = tmp_path / "pages.cbz"
            with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr("001.png", make_png_bytes((200, 200)))
                archive.writestr("notes.txt", "metadata")

            result = optimize_one(source, OptimizeOptions(profile=Profile.BALANCED))

            self.assertIn(result.status, {"optimized", "skipped"})
            if result.status == "optimized":
                with zipfile.ZipFile(result.output) as archive:
                    self.assertIn("notes.txt", archive.namelist())

    def test_office_container_image_entries_can_be_optimized(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            source = tmp_path / "deck.docx"
            image = make_jpeg_bytes((900, 900))
            with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr("[Content_Types].xml", "<Types/>")
                archive.writestr("word/document.xml", "<document/>")
                archive.writestr("word/media/photo.jpg", image)

            result = optimize_one(source, OptimizeOptions(loss_budget=LossBudget.HIGH, image_quality=45))

            self.assertEqual(result.status, "optimized")
            with zipfile.ZipFile(result.output) as archive:
                self.assertLess(len(archive.read("word/media/photo.jpg")), len(image))
                self.assertEqual(set(archive.namelist()), {"[Content_Types].xml", "word/document.xml", "word/media/photo.jpg"})

    def test_bad_office_container_image_entry_is_kept_original(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            source = tmp_path / "sheet.xlsx"
            bad_image = b"not an image"
            with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr("[Content_Types].xml", "<Types/>")
                archive.writestr("xl/workbook.xml", "<workbook/>")
                archive.writestr("xl/media/image1.jpg", bad_image)
                archive.writestr("xl/sharedStrings.xml", "hello" * 1000)

            result = optimize_one(source, OptimizeOptions(loss_budget=LossBudget.HIGH, image_quality=45))

            self.assertEqual(result.status, "optimized")
            with zipfile.ZipFile(result.output) as archive:
                self.assertEqual(archive.read("xl/media/image1.jpg"), bad_image)

    def test_discover_files(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            (tmp_path / "a.txt").write_text("x")
            (tmp_path / "b.zip").write_bytes(b"not a real zip")
            nested = tmp_path / "nested"
            nested.mkdir()
            (nested / "c.pdf").write_bytes(b"%PDF")
            build = tmp_path / "build"
            build.mkdir()
            (build / "ignored.zip").write_bytes(b"ignored")

            self.assertEqual([p.name for p in discover_files([tmp_path], recursive=False)], ["a.txt", "b.zip"])
            self.assertEqual({p.name for p in discover_files([tmp_path], recursive=True)}, {"a.txt", "b.zip", "c.pdf"})
            self.assertEqual([p.name for p in discover_files([tmp_path], recursive=False, generic_fallback=False)], ["b.zip"])

    def test_planned_output_does_not_overwrite_existing_output(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            source = tmp_path / "sample.zip"
            source.write_bytes(b"source")
            existing = tmp_path / "sample.ozero.zip"
            existing.write_bytes(b"existing")

            output = planned_output_path(source, OptimizeOptions())

            self.assertEqual(output.name, "sample.ozero-2.zip")

    def test_generic_file_is_zipped_as_fallback(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            source = tmp_path / "notes.txt"
            source.write_text("hello\n" * 1000, encoding="utf-8")

            result = optimize_one(source, OptimizeOptions())

            self.assertEqual(result.status, "optimized")
            self.assertTrue(result.output.endswith(".ozero.zip"))
            with zipfile.ZipFile(result.output) as archive:
                self.assertEqual(archive.namelist(), ["notes.txt"])
                self.assertEqual(archive.read("notes.txt"), source.read_bytes())

    def test_goal_smart_sets_practical_defaults(self):
        options = merge_goal_options(Goal.SMART)

        self.assertEqual(options.profile, Profile.BALANCED)
        self.assertEqual(options.loss_budget, LossBudget.LOW)
        self.assertEqual(options.image_quality, 88)
        self.assertEqual(options.min_savings_percent, 1.0)

    def test_optimize_many_keeps_input_order_with_workers(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            first = tmp_path / "a.txt"
            second = tmp_path / "b.txt"
            first.write_text("a" * 5000, encoding="utf-8")
            second.write_text("b" * 5000, encoding="utf-8")

            results = optimize_many([first, second], OptimizeOptions(workers=2))

            self.assertEqual([Path(result.source).name for result in results], ["a.txt", "b.txt"])
            self.assertTrue(all(result.status == "optimized" for result in results))

    def test_move_file_handles_replace(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            source = tmp_path / "source.txt"
            target = tmp_path / "target.txt"
            source.write_text("new")
            target.write_text("old")

            move_file(source, target)

            self.assertFalse(source.exists())
            self.assertEqual(target.read_text(), "new")

    def test_parse_size(self):
        self.assertEqual(parse_size("75MB"), 75 * 1024 * 1024)
        self.assertEqual(parse_size("2 gb"), 2 * 1024 * 1024 * 1024)

    def test_analyze_files_groups_kind(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            source = tmp_path / "sample.cbz"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("a.txt", "hello")

            analyses = analyze_files([tmp_path], recursive=False)

            self.assertEqual(len(analyses), 1)
            self.assertEqual(analyses[0].kind, "archive")

    def test_find_duplicate_files(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            for name in ("a.zip", "b.zip"):
                with zipfile.ZipFile(tmp_path / name, "w") as archive:
                    archive.writestr("a.txt", "same")

            groups = find_duplicate_files([tmp_path], recursive=False)

            self.assertEqual(len(groups), 1)
            self.assertEqual(len(groups[0].paths), 2)

    def test_max_size_skips_file(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            source = tmp_path / "sample.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("a.txt", "hello")

            result = optimize_one(source, OptimizeOptions(max_size_bytes=1))

            self.assertEqual(result.status, "skipped")
            self.assertIn("larger than limit", result.message)

    def test_loss_none_does_not_lossy_recompress_jpeg(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            source = tmp_path / "photo.jpg"
            source.write_bytes(make_jpeg_bytes())

            result = optimize_one(source, OptimizeOptions(loss_budget=LossBudget.NONE))

            self.assertEqual(result.status, "skipped")
            self.assertIn("not useful", result.message)

    def test_quality_recompresses_jpeg_when_user_allows_loss(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            source = tmp_path / "photo.jpg"
            source.write_bytes(make_jpeg_bytes())

            result = optimize_one(source, OptimizeOptions(loss_budget=LossBudget.HIGH, image_quality=45))

            self.assertEqual(result.status, "optimized")
            self.assertLess(result.output_size, result.original_size)


if __name__ == "__main__":
    unittest.main()
