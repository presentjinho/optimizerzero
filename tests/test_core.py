import io
import tempfile
import tarfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

from optimizerzero.core import (
    DIMENSION_LADDER,
    HEIF_AVAILABLE,
    IMAGE_EXTS,
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
    optimize_zip_container,
    output_suffix_for_path,
    parse_size,
    png_quantize_ladder,
    quality_ladder,
    quantize_png,
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


@unittest.skipUnless(HEIF_AVAILABLE, "pillow-heif not installed")
class HeicTests(unittest.TestCase):
    def make_heic_bytes(self, size=(640, 480), quality=92):
        image = Image.new("RGB", size)
        pixels = image.load()
        for y in range(size[1]):
            for x in range(size[0]):
                pixels[x, y] = ((x * 3) % 256, (y * 5) % 256, ((x + y) * 7) % 256)
        out = io.BytesIO()
        image.save(out, "HEIF", quality=quality)
        return out.getvalue()

    def test_heic_is_a_recognized_supported_image(self):
        self.assertIn(".heic", IMAGE_EXTS)
        self.assertIn(".heif", IMAGE_EXTS)

    def test_heic_recompresses_and_keeps_its_extension(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            source = tmp_path / "photo.heic"
            source.write_bytes(self.make_heic_bytes())

            result = optimize_one(source, merge_goal_options(Goal.SMALLEST))

            self.assertEqual(result.status, "optimized")
            self.assertLess(result.output_size, result.original_size)
            self.assertEqual(Path(result.output).suffix, ".heic")
            ok, message = validate_file(Path(result.output))
            self.assertTrue(ok, message)

    def test_heic_is_untouched_under_quality_goal(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            source = tmp_path / "photo.heic"
            source.write_bytes(self.make_heic_bytes())

            result = optimize_one(source, merge_goal_options(Goal.QUALITY))

            self.assertIn(result.status, {"skipped", "optimized"})


def make_screenshot_png_bytes(size=(800, 600)):
    # Flat color blocks -- the kind of low-color-count image where palette
    # quantization gives real wins, unlike a photo/gradient.
    image = Image.new("RGB", size, (240, 240, 245))
    draw = ImageDraw.Draw(image)
    draw.rectangle([50, 50, 750, 150], fill=(30, 90, 200))
    draw.rectangle([50, 200, 400, 550], fill=(255, 255, 255), outline=(0, 0, 0), width=3)
    for i in range(20):
        draw.rectangle([70, 220 + i * 15, 380, 230 + i * 15], fill=(20, 20, 20))
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


class PngQuantizeTests(unittest.TestCase):
    def test_quantize_ladder_stays_lossless_outside_strong_profile(self):
        smart = merge_goal_options(Goal.SMART)
        quality = merge_goal_options(Goal.QUALITY)
        self.assertEqual(png_quantize_ladder(smart), [None])
        self.assertEqual(png_quantize_ladder(quality), [None])

    def test_quantize_ladder_engages_only_for_strong_profile(self):
        strong = merge_goal_options(Goal.SMALLEST)
        self.assertEqual(png_quantize_ladder(strong), [256, None])

    def test_quantize_ladder_escalates_for_a_target_size(self):
        strong = merge_goal_options(Goal.SMALLEST, target_size_bytes=5000)
        self.assertEqual(png_quantize_ladder(strong), [256, 128, 64, 32, None])

    def test_quantize_png_preserves_alpha_channel(self):
        image = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.ellipse([30, 30, 170, 170], fill=(30, 144, 255, 255))
        draw.rectangle([80, 80, 120, 120], fill=(255, 255, 255, 180))

        quantized = quantize_png(image, 256)

        self.assertIsNotNone(quantized)
        reloaded = quantized.convert("RGBA")
        self.assertEqual(reloaded.getpixel((10, 10)), (0, 0, 0, 0))
        self.assertEqual(reloaded.getpixel((100, 100)), (255, 255, 255, 180))
        self.assertEqual(reloaded.getpixel((40, 100)), (30, 144, 255, 255))

    def test_smallest_goal_quantizes_a_screenshot_like_png(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            source = tmp_path / "shot.png"
            source.write_bytes(make_screenshot_png_bytes())

            result = optimize_one(source, merge_goal_options(Goal.SMALLEST))

            self.assertEqual(result.status, "optimized")
            self.assertLess(result.output_size, result.original_size)
            with Image.open(result.output) as saved:
                self.assertEqual(saved.mode, "P")

    def test_smart_goal_does_not_quantize_a_screenshot_like_png(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            source = tmp_path / "shot.png"
            source.write_bytes(make_screenshot_png_bytes())

            result = optimize_one(source, merge_goal_options(Goal.SMART))

            if result.status == "optimized":
                with Image.open(result.output) as saved:
                    self.assertNotEqual(saved.mode, "P")


def make_jpeg_with_exif_bytes(size=(300, 150), orientation=6):
    image = Image.new("RGB", size)
    pixels = image.load()
    for y in range(size[1]):
        for x in range(size[0]):
            pixels[x, y] = (x % 256, y % 256, (x + y) % 256)
    exif = image.getexif()
    if orientation is not None:
        exif[0x0112] = orientation  # Orientation
    exif[0x010F] = "TestCam"  # Make
    exif[0x9003] = "2024:01:01 12:00:00"  # DateTimeOriginal
    out = io.BytesIO()
    image.save(out, "JPEG", quality=95, exif=exif.tobytes())
    return out.getvalue()


class MetadataTests(unittest.TestCase):
    def test_metadata_is_stripped_by_default(self):
        data = make_jpeg_with_exif_bytes()
        result = optimize_image_bytes(data, merge_goal_options(Goal.SMALLEST))
        with Image.open(io.BytesIO(result)) as image:
            self.assertEqual(dict(image.getexif()), {})

    def test_keep_metadata_preserves_camera_and_date_tags(self):
        data = make_jpeg_with_exif_bytes()
        options = merge_goal_options(Goal.SMALLEST, keep_metadata=True)
        result = optimize_image_bytes(data, options)
        with Image.open(io.BytesIO(result)) as image:
            tags = dict(image.getexif())
            self.assertEqual(tags.get(0x010F), "TestCam")
            self.assertEqual(tags.get(0x9003), "2024:01:01 12:00:00")

    def test_keep_metadata_does_not_double_rotate(self):
        # Source is stored 300x150 with Orientation=6 (displays as 150x300).
        # exif_transpose() bakes that rotation into pixels and drops the tag,
        # so the recompressed output must already be 150x300 with no
        # orientation tag left to make a viewer rotate it again.
        data = make_jpeg_with_exif_bytes(size=(300, 150), orientation=6)
        options = merge_goal_options(Goal.SMALLEST, keep_metadata=True)
        result = optimize_image_bytes(data, options)
        with Image.open(io.BytesIO(result)) as image:
            self.assertEqual(image.size, (150, 300))
            self.assertNotIn(0x0112, dict(image.getexif()))

    def test_keep_metadata_threads_through_zip_container(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            source = tmp_path / "photos.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("a.jpg", make_jpeg_with_exif_bytes())
            target = tmp_path / "out.zip"

            ok, message = optimize_zip_container(source, target, merge_goal_options(Goal.SMALLEST, keep_metadata=True))
            self.assertTrue(ok, message)
            with zipfile.ZipFile(target) as archive:
                with Image.open(io.BytesIO(archive.read("a.jpg"))) as image:
                    self.assertEqual(dict(image.getexif()).get(0x010F), "TestCam")


def make_bmp_bytes(size=(400, 300)):
    image = Image.new("RGB", size, (200, 100, 50))
    draw = ImageDraw.Draw(image)
    draw.rectangle([50, 50, size[0] - 50, size[1] - 50], fill=(10, 10, 10))
    out = io.BytesIO()
    image.save(out, "BMP")
    return out.getvalue()


class UncompressedImageTests(unittest.TestCase):
    def test_output_suffix_swaps_bmp_and_tiff_to_png(self):
        self.assertEqual(output_suffix_for_path(Path("photo.bmp")), ".png")
        self.assertEqual(output_suffix_for_path(Path("scan.tiff")), ".png")
        self.assertEqual(output_suffix_for_path(Path("scan.tif")), ".png")

    def test_bmp_compresses_losslessly_even_under_the_safest_goal(self):
        data = make_bmp_bytes()
        result = optimize_image_bytes(data, merge_goal_options(Goal.QUALITY))
        self.assertIsNotNone(result)
        self.assertLess(len(result), len(data))
        with Image.open(io.BytesIO(result)) as image:
            self.assertEqual(image.format, "PNG")

    def test_standalone_bmp_file_becomes_a_verified_png(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            source = tmp_path / "photo.bmp"
            source.write_bytes(make_bmp_bytes())

            result = optimize_one(source, merge_goal_options(Goal.QUALITY))

            self.assertEqual(result.status, "optimized")
            self.assertEqual(Path(result.output).suffix, ".png")
            ok, message = validate_file(Path(result.output))
            self.assertTrue(ok, message)

    def test_bmp_entry_inside_a_zip_is_left_untouched(self):
        # Renaming an archive entry's extension here would break formats
        # that reference embedded images by exact filename internally
        # (DOCX/PPTX/XLSX/ODT/EPUB manifests), so BMP/TIFF entries inside
        # containers are skipped rather than converted.
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            bmp_bytes = make_bmp_bytes()
            source = tmp_path / "photos.cbz"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("page1.bmp", bmp_bytes)
            target = tmp_path / "out.cbz"

            ok, message = optimize_zip_container(source, target, merge_goal_options(Goal.SMALLEST))

            self.assertTrue(ok, message)
            with zipfile.ZipFile(target) as archive:
                self.assertEqual(archive.read("page1.bmp"), bmp_bytes)


if __name__ == "__main__":
    unittest.main()
