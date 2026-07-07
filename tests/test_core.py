import io
import tempfile
import tarfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image

from optimizerzero.core import (
    DIMENSION_LADDER,
    OptimizeOptions,
    LossBudget,
    Goal,
    Profile,
    analyze_files,
    dimension_ladder,
    discover_files,
    find_duplicate_files,
    merge_goal_options,
    move_file,
    optimize_image_bytes,
    optimize_many,
    optimize_one,
    parse_size,
    quality_ladder,
    planned_output_path,
    resize_within,
    validate_epub,
    validate_file,
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


def make_detailed_jpeg_bytes(size=(1200, 900)):
    # A gradient studded with outlined circles -- busy enough that the
    # quality ladder's floor alone can't shrink it far, but not pure noise
    # (which JPEG can't usefully compress at any resolution). Only resizing
    # gets this one small. Seeded for a deterministic fixture.
    import random

    from PIL import ImageDraw

    rng = random.Random(1234)
    out = io.BytesIO()
    image = Image.new("RGB", size)
    pixels = image.load()
    for y in range(size[1]):
        for x in range(size[0]):
            pixels[x, y] = (int(255 * x / size[0]), int(255 * y / size[1]), int(255 * ((x + y) % 256) / 256))
    draw = ImageDraw.Draw(image)
    for _ in range(40):
        x0, y0 = rng.randrange(0, size[0] - 100), rng.randrange(0, size[1] - 100)
        draw.ellipse([x0, y0, x0 + rng.randrange(20, 150), y0 + rng.randrange(20, 150)], outline=(255, 255, 255), width=3)
    image.save(out, "JPEG", quality=95)
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

    def test_open_document_container_is_treated_as_zip_container(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            source = tmp_path / "doc.odt"
            with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr("mimetype", "application/vnd.oasis.opendocument.text")
                archive.writestr("content.xml", "<doc>" + ("hello" * 1000) + "</doc>")

            result = optimize_one(source, OptimizeOptions())

            self.assertEqual(result.status, "optimized")
            with zipfile.ZipFile(result.output) as archive:
                self.assertEqual(set(archive.namelist()), {"mimetype", "content.xml"})

    def test_tar_container_compresses_to_tar_gz_and_verifies(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            source = tmp_path / "bundle.tar"
            data = tmp_path / "notes.txt"
            data.write_text("hello\n" * 1000, encoding="utf-8")
            with tarfile.open(source, "w") as archive:
                archive.add(data, arcname="notes.txt")

            result = optimize_one(source, OptimizeOptions())

            self.assertEqual(result.status, "optimized")
            self.assertTrue(result.output.endswith(".ozero.tar.gz"))
            with tarfile.open(result.output, "r:*") as archive:
                self.assertEqual([member.name for member in archive.getmembers() if member.isfile()], ["notes.txt"])

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

    def test_quality_ladder_stays_pinned_without_a_target_size(self):
        options = merge_goal_options(Goal.SMART)
        self.assertEqual(quality_ladder(options), [88])

    def test_target_size_makes_a_pinned_goal_retry_down_the_ladder(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            source = tmp_path / "photo.jpg"
            source.write_bytes(make_jpeg_bytes())

            # SMART pins quality=88 (~19.4KB for this fixture); a 12KB target
            # is unreachable at 88 but sits comfortably inside the LOW-budget
            # ladder's lower rungs (92/88/84 stays fixed since SMART uses the
            # BALANCED profile's LOW budget... use SMALLEST's HIGH budget
            # instead so the ladder has rungs small enough to reach it).
            options = merge_goal_options(Goal.SMALLEST, target_size_bytes=12000)
            self.assertEqual(quality_ladder(options), [70, 62, 54, 46])

            result = optimize_one(source, options)

            self.assertEqual(result.status, "optimized")
            self.assertLessEqual(result.output_size, 12000)

    def test_dimension_ladder_stays_off_without_a_target_or_explicit_cap(self):
        options = merge_goal_options(Goal.SMALLEST)
        self.assertEqual(dimension_ladder(options, None), [None])

    def test_dimension_ladder_ignores_target_under_a_none_loss_budget(self):
        options = merge_goal_options(Goal.SMART, loss_budget=LossBudget.NONE, target_size_bytes=5000)
        self.assertEqual(dimension_ladder(options, options.target_size_bytes), [None])

    def test_dimension_ladder_escalates_once_a_target_needs_it(self):
        options = merge_goal_options(Goal.SMALLEST, target_size_bytes=5000)
        ladder = dimension_ladder(options, options.target_size_bytes)
        self.assertEqual(ladder, [None, *DIMENSION_LADDER])

    def test_explicit_max_dimension_applies_even_without_a_target(self):
        options = merge_goal_options(Goal.SMALLEST, max_dimension=500)
        self.assertEqual(dimension_ladder(options, None), [500])

    def test_resize_within_scales_down_only_past_the_cap(self):
        image = Image.new("RGB", (1000, 500))
        untouched = resize_within(image, 2000)
        self.assertEqual(untouched.size, (1000, 500))
        scaled = resize_within(image, 400)
        self.assertEqual(scaled.size, (400, 200))

    def test_target_size_falls_back_to_resizing_when_quality_alone_cannot_reach_it(self):
        data = make_detailed_jpeg_bytes()
        options = merge_goal_options(Goal.SMALLEST, target_size_bytes=40 * 1024)

        result = optimize_image_bytes(data, options, options.target_size_bytes)

        self.assertIsNotNone(result)
        self.assertLessEqual(len(result), options.target_size_bytes)
        with Image.open(io.BytesIO(result)) as shrunk:
            self.assertLess(max(shrunk.size), max(Image.open(io.BytesIO(data)).size))

    def test_explicit_max_dimension_threads_through_optimize_one(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            source = tmp_path / "photo.jpg"
            source.write_bytes(make_detailed_jpeg_bytes())

            options = merge_goal_options(Goal.SMALLEST, max_dimension=300)
            result = optimize_one(source, options)

            self.assertEqual(result.status, "optimized")
            with Image.open(result.output) as shrunk:
                self.assertLessEqual(max(shrunk.size), 300)

    def test_pdf_optimizer_uses_available_pdf_engines(self):
        try:
            import fitz
        except Exception:
            self.skipTest("PyMuPDF is not installed")

        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            source = tmp_path / "sample.pdf"
            document = fitz.open()
            page = document.new_page()
            page.insert_text((72, 72), "OptimizerZero PDF test")
            document.save(str(source))
            document.close()

            result = optimize_one(source, OptimizeOptions(allow_larger=True))

            self.assertEqual(result.status, "optimized")
            self.assertIn("PDF optimized with", result.message)
            self.assertTrue(result.output.endswith(".ozero.pdf"))
            ok, message = validate_file(Path(result.output))
            self.assertTrue(ok, message)

    def test_pdf_optimizer_recompresses_embedded_jpeg_images_when_loss_allowed(self):
        try:
            import pikepdf
        except Exception:
            self.skipTest("pikepdf is not installed")

        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            source = tmp_path / "scan.pdf"

            jpeg_buffer = io.BytesIO()
            Image.new("RGB", (800, 600), color=(120, 140, 160)).save(jpeg_buffer, format="JPEG", quality=97)
            jpeg_bytes = jpeg_buffer.getvalue()

            pdf = pikepdf.Pdf.new()
            page = pdf.add_blank_page(page_size=(612, 792))
            image_obj = pikepdf.Stream(pdf, jpeg_bytes)
            image_obj.Type = pikepdf.Name("/XObject")
            image_obj.Subtype = pikepdf.Name("/Image")
            image_obj.Width = 800
            image_obj.Height = 600
            image_obj.BitsPerComponent = 8
            image_obj.ColorSpace = pikepdf.Name("/DeviceRGB")
            image_obj.Filter = pikepdf.Name("/DCTDecode")
            page.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Im0=image_obj))
            page.Contents = pikepdf.Stream(pdf, b"q 612 0 0 792 0 0 cm /Im0 Do Q")
            pdf.save(str(source))
            pdf.close()

            quality_result = optimize_one(source, merge_goal_options(Goal.QUALITY, allow_larger=True))
            self.assertNotIn("image", quality_result.message)

            smallest_result = optimize_one(source, merge_goal_options(Goal.SMALLEST, allow_larger=True))
            self.assertEqual(smallest_result.status, "optimized")
            self.assertIn("image", smallest_result.message)
            self.assertLess(smallest_result.output_size, source.stat().st_size)
            ok, message = validate_file(Path(smallest_result.output))
            self.assertTrue(ok, message)


if __name__ == "__main__":
    unittest.main()
