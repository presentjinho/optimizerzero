from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import tarfile
import tempfile
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Iterable

from PIL import Image, ImageFile, ImageOps

Image.MAX_IMAGE_PIXELS = 160_000_000
ImageFile.LOAD_TRUNCATED_IMAGES = False

ZIP_CONTAINER_EXTS = {".zip", ".cbz", ".epub", ".docx", ".pptx", ".xlsx", ".odt", ".ods", ".odp", ".jar"}
TAR_EXTS = {".tar", ".tgz", ".tar.gz", ".tbz2", ".tar.bz2", ".txz", ".tar.xz"}
ARCHIVE_EXTS = ZIP_CONTAINER_EXTS | TAR_EXTS
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
PDF_EXTS = {".pdf"}
SUPPORTED_EXTS = ARCHIVE_EXTS | IMAGE_EXTS | PDF_EXTS
IMAGE_ARCHIVE_EXTS = {".zip", ".cbz"}
IMAGE_OPTIMIZABLE_CONTAINER_EXTS = ZIP_CONTAINER_EXTS
OFFICE_EXTS = {".docx", ".pptx", ".xlsx", ".odt", ".ods", ".odp"}
DEFAULT_IGNORE_DIRS = {".git", ".hg", ".svn", ".venv", "__pycache__", "build", "dist", "node_modules", "releases"}
DEFAULT_IGNORE_SUFFIXES = {".pyc", ".pyo"}


class Profile(str, Enum):
    SAFE = "safe"
    BALANCED = "balanced"
    STRONG = "strong"


class LossBudget(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Goal(str, Enum):
    SMART = "smart"
    QUALITY = "quality"
    SMALLEST = "smallest"


@dataclass(frozen=True)
class OptimizeOptions:
    goal: Goal = Goal.SMART
    profile: Profile = Profile.SAFE
    recursive: bool = False
    output_dir: Path | None = None
    in_place: bool = False
    allow_larger: bool = False
    dry_run: bool = False
    keep_metadata: bool = True
    min_savings_percent: float = 0.0
    max_size_bytes: int | None = None
    loss_budget: LossBudget | None = None
    image_quality: int | None = None
    target_size_bytes: int | None = None
    generic_fallback: bool = True
    workers: int = 1


@dataclass
class OptimizeResult:
    source: str
    status: str
    message: str
    original_size: int
    output_size: int
    saved_bytes: int
    output: str | None = None
    elapsed_seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return self.status in {"optimized", "skipped"}


@dataclass(frozen=True)
class FileAnalysis:
    path: str
    extension: str
    kind: str
    size: int
    supported: bool
    valid: bool | None = None
    message: str = ""


@dataclass(frozen=True)
class DuplicateGroup:
    size: int
    digest: str
    paths: list[str]


def kind_for_suffix(suffix: str) -> str:
    suffix = suffix.lower()
    if suffix in IMAGE_EXTS:
        return "image"
    if suffix in PDF_EXTS:
        return "pdf"
    if suffix in OFFICE_EXTS:
        return "office"
    if suffix == ".epub":
        return "epub"
    if suffix in IMAGE_ARCHIVE_EXTS:
        return "archive"
    if suffix in ARCHIVE_EXTS:
        return "container"
    return "generic"


def extension_for_path(path: Path) -> str:
    name = path.name.lower()
    for extension in sorted(TAR_EXTS, key=len, reverse=True):
        if name.endswith(extension):
            return extension
    return path.suffix.lower()


def output_suffix_for_path(path: Path) -> str:
    extension = extension_for_path(path)
    if extension == ".tar":
        return ".tar.gz"
    return extension if extension in SUPPORTED_EXTS else ".zip"


def options_for_goal(goal: Goal) -> OptimizeOptions:
    if goal == Goal.QUALITY:
        return OptimizeOptions(goal=goal, profile=Profile.SAFE, loss_budget=LossBudget.NONE, min_savings_percent=0.5)
    if goal == Goal.SMALLEST:
        return OptimizeOptions(goal=goal, profile=Profile.STRONG, loss_budget=LossBudget.HIGH, image_quality=70, min_savings_percent=1.0)
    return OptimizeOptions(goal=goal, profile=Profile.BALANCED, loss_budget=LossBudget.LOW, image_quality=88, min_savings_percent=1.0)


def merge_goal_options(goal: Goal, **overrides) -> OptimizeOptions:
    base = asdict(options_for_goal(goal))
    base.update({key: value for key, value in overrides.items() if value is not None})
    return OptimizeOptions(**base)


def format_bytes(value: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    size = float(max(0, value))
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{value} B"


def parse_size(value: str | None) -> int | None:
    if not value:
        return None
    raw = value.strip().lower().replace(" ", "")
    multipliers = {"b": 1, "kb": 1024, "k": 1024, "mb": 1024**2, "m": 1024**2, "gb": 1024**3, "g": 1024**3}
    for suffix, multiplier in sorted(multipliers.items(), key=lambda item: len(item[0]), reverse=True):
        if raw.endswith(suffix):
            return int(float(raw[:-len(suffix)]) * multiplier)
    return int(float(raw))


def clamp_quality(value: int) -> int:
    return max(1, min(100, value))


def effective_loss_budget(options: OptimizeOptions) -> LossBudget:
    if options.loss_budget is not None:
        return options.loss_budget
    if options.profile == Profile.SAFE:
        return LossBudget.NONE
    if options.profile == Profile.BALANCED:
        return LossBudget.LOW
    return LossBudget.MEDIUM


def quality_ladder(options: OptimizeOptions) -> list[int]:
    if options.image_quality is not None:
        return [clamp_quality(options.image_quality)]
    budget = effective_loss_budget(options)
    if budget == LossBudget.NONE:
        return []
    if budget == LossBudget.LOW:
        return [92, 88, 84]
    if budget == LossBudget.MEDIUM:
        return [86, 80, 74, 68]
    return [78, 70, 62, 54, 46]


def should_consider_file(path: Path, generic_fallback: bool = True) -> bool:
    if any(part in DEFAULT_IGNORE_DIRS for part in path.parts):
        return False
    suffix = extension_for_path(path)
    if suffix in DEFAULT_IGNORE_SUFFIXES:
        return False
    if ".ozero" in path.name:
        return False
    return suffix in SUPPORTED_EXTS or generic_fallback


def discover_files(paths: Iterable[Path], recursive: bool, generic_fallback: bool = True) -> list[Path]:
    found: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_file() and should_consider_file(path, generic_fallback=generic_fallback):
            found.append(path)
        elif path.is_dir():
            iterator = path.rglob("*") if recursive else path.glob("*")
            found.extend(
                p for p in iterator
                if p.is_file() and should_consider_file(p, generic_fallback=generic_fallback)
            )
    return sorted(dict.fromkeys(p.resolve() for p in found))


def analyze_files(paths: Iterable[Path], recursive: bool, verify: bool = False, generic_fallback: bool = True) -> list[FileAnalysis]:
    analyses: list[FileAnalysis] = []
    for path in discover_files(paths, recursive=recursive, generic_fallback=generic_fallback):
        suffix = extension_for_path(path)
        valid: bool | None = None
        message = ""
        if verify:
            valid, message = validate_file(path)
        supported = suffix in SUPPORTED_EXTS or generic_fallback
        analyses.append(FileAnalysis(str(path), suffix.lstrip("."), kind_for_suffix(suffix), path.stat().st_size, supported, valid, message))
    return analyses


def file_digest(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def find_duplicate_files(paths: Iterable[Path], recursive: bool) -> list[DuplicateGroup]:
    by_size: dict[int, list[Path]] = {}
    for path in discover_files(paths, recursive=recursive):
        by_size.setdefault(path.stat().st_size, []).append(path)
    groups: list[DuplicateGroup] = []
    for size, same_size in by_size.items():
        if len(same_size) < 2:
            continue
        by_digest: dict[str, list[Path]] = {}
        for path in same_size:
            by_digest.setdefault(file_digest(path), []).append(path)
        for digest, same_digest in by_digest.items():
            if len(same_digest) > 1:
                groups.append(DuplicateGroup(size, digest, [str(path) for path in same_digest]))
    return sorted(groups, key=lambda group: (-group.size, group.digest))


def planned_output_path(source: Path, options: OptimizeOptions) -> Path:
    if options.in_place:
        return source
    parent = options.output_dir if options.output_dir else source.parent
    output_suffix = output_suffix_for_path(source)
    base = parent / f"{source.stem}.ozero{output_suffix}"
    if not base.exists():
        return base
    for index in range(2, 10_000):
        candidate = parent / f"{source.stem}.ozero-{index}{output_suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"too many existing output files for {source.name}")


def safe_zip_name(name: str) -> str:
    normalized = name.replace("\\", "/").lstrip("/")
    path = PurePosixPath(normalized)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"unsafe archive member path: {name}")
    return path.as_posix()


def zip_info_for(name: str, compress_type: int, source: zipfile.ZipInfo | None = None) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name)
    info.compress_type = compress_type
    info.date_time = source.date_time if source else time.localtime()[:6]
    info.external_attr = source.external_attr if source else 0
    return info


def validate_zip(path: Path, expected_names: set[str] | None = None) -> tuple[bool, str]:
    if not zipfile.is_zipfile(path):
        return False, "not a zip container"
    try:
        with zipfile.ZipFile(path, "r") as archive:
            bad = archive.testzip()
            if bad:
                return False, f"bad entry: {bad}"
            names = {safe_zip_name(name) for name in archive.namelist() if not name.endswith("/")}
            if expected_names is not None and names != expected_names:
                return False, "entry set changed"
    except Exception as exc:
        return False, str(exc)
    return True, "verified"


def validate_tar(path: Path, expected_names: set[str] | None = None) -> tuple[bool, str]:
    if not tarfile.is_tarfile(path):
        return False, "not a tar container"
    try:
        names: set[str] = set()
        with tarfile.open(path, "r:*") as archive:
            for member in archive.getmembers():
                clean_name = safe_zip_name(member.name)
                if member.isfile():
                    names.add(clean_name)
            if expected_names is not None and names != expected_names:
                return False, "entry set changed"
    except Exception as exc:
        return False, str(exc)
    return True, "verified"


def validate_epub(path: Path) -> tuple[bool, str]:
    ok, message = validate_zip(path)
    if not ok:
        return ok, message
    try:
        with zipfile.ZipFile(path, "r") as archive:
            names = archive.namelist()
            if not names or names[0] != "mimetype":
                return False, "EPUB mimetype must be first"
            if archive.getinfo("mimetype").compress_type != zipfile.ZIP_STORED:
                return False, "EPUB mimetype must be stored"
            if archive.read("mimetype") != b"application/epub+zip":
                return False, "invalid EPUB mimetype"
            if "META-INF/container.xml" not in names:
                return False, "missing EPUB container.xml"
    except Exception as exc:
        return False, str(exc)
    return True, "verified"


def validate_file(path: Path) -> tuple[bool, str]:
    path = Path(path)
    suffix = extension_for_path(path)
    if suffix == ".epub":
        return validate_epub(path)
    if suffix in ZIP_CONTAINER_EXTS:
        return validate_zip(path)
    if suffix in TAR_EXTS:
        return validate_tar(path)
    if suffix in IMAGE_EXTS:
        try:
            with Image.open(path) as image:
                image.verify()
            return True, "verified"
        except Exception as exc:
            return False, str(exc)
    if suffix in PDF_EXTS:
        errors: list[str] = []
        try:
            import fitz
            try:
                with fitz.open(str(path)) as document:
                    if document.page_count <= 0:
                        return False, "PDF has no pages"
                return True, "verified"
            except Exception as exc:
                errors.append(f"PyMuPDF: {exc}")
        except Exception:
            errors.append("PyMuPDF is not available")
        try:
            import pikepdf
            try:
                with pikepdf.Pdf.open(str(path)) as document:
                    if len(document.pages) <= 0:
                        return False, "PDF has no pages"
                return True, "verified"
            except Exception as exc:
                errors.append(f"pikepdf: {exc}")
        except Exception:
            errors.append("pikepdf is not available")
        return False, "; ".join(errors)
    return True, "generic file"


def image_save_args(original_format: str, quality: int | None = None) -> tuple[str, dict] | None:
    original_format = (original_format or "PNG").upper()
    if original_format == "JPG":
        original_format = "JPEG"
    if original_format in {"JPEG", "WEBP"}:
        quality = 90 if quality is None else clamp_quality(quality)
        return original_format, {"quality": quality, "optimize": True}
    if original_format == "PNG":
        return "PNG", {"optimize": True, "compress_level": 9}
    return None


def optimize_image_bytes(data: bytes, options: OptimizeOptions, target_size_bytes: int | None = None) -> bytes | None:
    try:
        with Image.open(io.BytesIO(data)) as image:
            original_format = image.format or "PNG"
            image = ImageOps.exif_transpose(image)
            image.load()
            qualities = quality_ladder(options)
            if not qualities:
                if original_format.upper() == "PNG":
                    qualities = [None]
                else:
                    return None
            best: bytes | None = None
            for quality in qualities:
                save = image_save_args(original_format, quality)
                if save is None:
                    continue
                out_format, save_args = save
                candidate_image = image
                if out_format == "JPEG" and candidate_image.mode not in {"RGB", "L"}:
                    candidate_image = candidate_image.convert("RGB")
                out = io.BytesIO()
                candidate_image.save(out, out_format, **save_args)
                candidate = out.getvalue()
                if not candidate or len(candidate) >= len(data):
                    continue
                with Image.open(io.BytesIO(candidate)) as verified:
                    verified.verify()
                best = candidate
                if target_size_bytes is None or len(candidate) <= target_size_bytes:
                    return candidate
            return best
    except Exception:
        return None


def optimize_zip_container(source: Path, target: Path, options: OptimizeOptions) -> tuple[bool, str]:
    expected_names: set[str] = set()
    with zipfile.ZipFile(source, "r") as zin, zipfile.ZipFile(target, "w") as zout:
        infos = zin.infolist()
        if any(info.flag_bits & 0x1 for info in infos):
            return False, "encrypted ZIP entries are not supported"
        for index, info in enumerate(infos):
            if info.is_dir():
                continue
            name = safe_zip_name(info.filename)
            expected_names.add(name)
            data = zin.read(info.filename)
            compress_type = zipfile.ZIP_DEFLATED
            if source.suffix.lower() == ".epub" and name == "mimetype":
                compress_type = zipfile.ZIP_STORED
            if source.suffix.lower() in IMAGE_OPTIMIZABLE_CONTAINER_EXTS and Path(name).suffix.lower() in IMAGE_EXTS:
                optimized = optimize_image_bytes(data, options)
                if optimized is not None:
                    data = optimized
            if source.suffix.lower() == ".epub" and index == 0 and name != "mimetype":
                return False, "invalid EPUB ordering"
            zout.writestr(zip_info_for(name, compress_type, info), data)
    if source.suffix.lower() == ".epub":
        return validate_epub(target)
    return validate_zip(target, expected_names)


def tar_write_mode(extension: str) -> str:
    if extension in {".tgz", ".tar.gz"}:
        return "w:gz"
    if extension in {".tbz2", ".tar.bz2"}:
        return "w:bz2"
    if extension in {".txz", ".tar.xz"}:
        return "w:xz"
    return "w"


def optimize_tar_container(source: Path, target: Path) -> tuple[bool, str]:
    expected_names: set[str] = set()
    extension = extension_for_path(target)
    with tarfile.open(source, "r:*") as tin, tarfile.open(target, tar_write_mode(extension)) as tout:
        for member in tin.getmembers():
            clean_name = safe_zip_name(member.name)
            member.name = clean_name
            fileobj = tin.extractfile(member) if member.isfile() else None
            try:
                if member.isfile():
                    expected_names.add(clean_name)
                tout.addfile(member, fileobj)
            finally:
                if fileobj is not None:
                    fileobj.close()
    return validate_tar(target, expected_names)


def optimize_pdf(source: Path, target: Path) -> tuple[bool, str]:
    candidates: list[tuple[Path, str]] = []
    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="optimizerzero_pdf_") as temp_dir_raw:
        temp_dir = Path(temp_dir_raw)
        try:
            import fitz
            fitz_candidate = temp_dir / "pymupdf.pdf"
            with fitz.open(str(source)) as document:
                page_count = document.page_count
                document.save(
                    str(fitz_candidate),
                    garbage=4,
                    clean=True,
                    deflate=True,
                    deflate_images=True,
                    deflate_fonts=True,
                    use_objstms=1,
                    compression_effort=9,
                )
            with fitz.open(str(fitz_candidate)) as verified:
                if verified.page_count != page_count:
                    raise ValueError("PDF page count changed")
            candidates.append((fitz_candidate, "PyMuPDF"))
        except Exception as exc:
            errors.append(f"PyMuPDF: {exc}")

        try:
            import pikepdf
            pike_candidate = temp_dir / "pikepdf.pdf"
            with pikepdf.Pdf.open(str(source)) as document:
                page_count = len(document.pages)
                document.save(
                    str(pike_candidate),
                    compress_streams=True,
                    object_stream_mode=pikepdf.ObjectStreamMode.generate,
                    recompress_flate=True,
                    linearize=False,
                )
            with pikepdf.Pdf.open(str(pike_candidate)) as verified:
                if len(verified.pages) != page_count:
                    raise ValueError("PDF page count changed")
            candidates.append((pike_candidate, "pikepdf"))
        except Exception as exc:
            errors.append(f"pikepdf: {exc}")

        if not candidates:
            return False, "; ".join(errors) if errors else "PDF optimizer is not available"

        best, engine = min(candidates, key=lambda item: item[0].stat().st_size)
        shutil.copy2(best, target)
    return True, f"PDF optimized with {engine}"


def optimize_generic_file(source: Path, target: Path) -> tuple[bool, str]:
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.write(source, arcname=safe_zip_name(source.name))
    return validate_zip(target, {safe_zip_name(source.name)})


def optimize_standalone_image(source: Path, target: Path, options: OptimizeOptions) -> tuple[bool, str]:
    data = source.read_bytes()
    optimized = optimize_image_bytes(data, options, options.target_size_bytes)
    if optimized is None:
        return False, "image optimization not useful for this profile/file"
    target.write_bytes(optimized)
    try:
        with Image.open(target) as image:
            image.verify()
    except Exception as exc:
        return False, str(exc)
    return True, "verified"


def move_file(source: Path, target: Path) -> None:
    try:
        os.replace(source, target)
    except OSError:
        shutil.move(str(source), str(target))


def accept_candidate(source: Path, candidate: Path, final_output: Path, options: OptimizeOptions) -> OptimizeResult:
    original_size = source.stat().st_size
    output_size = candidate.stat().st_size if candidate.exists() else original_size
    if not candidate.exists() or output_size <= 0:
        return OptimizeResult(str(source), "error", "candidate missing or empty", original_size, original_size, 0)
    if not options.allow_larger and output_size >= original_size:
        candidate.unlink(missing_ok=True)
        return OptimizeResult(str(source), "skipped", "not smaller", original_size, original_size, 0)
    if options.target_size_bytes is not None and output_size > options.target_size_bytes:
        candidate.unlink(missing_ok=True)
        return OptimizeResult(str(source), "skipped", f"above target size: {format_bytes(options.target_size_bytes)}", original_size, original_size, 0)
    saved_bytes = original_size - output_size
    if original_size > 0 and options.min_savings_percent > 0:
        saved_percent = (saved_bytes / original_size) * 100
        if saved_percent < options.min_savings_percent:
            candidate.unlink(missing_ok=True)
            return OptimizeResult(str(source), "skipped", f"below minimum savings: {saved_percent:.2f}%", original_size, original_size, 0)
    final_output.parent.mkdir(parents=True, exist_ok=True)
    if options.in_place:
        backup = source.with_name(f"{source.name}.ozero-bak")
        shutil.copy2(source, backup)
        try:
            move_file(candidate, source)
            backup.unlink(missing_ok=True)
            output = source
        except Exception:
            if backup.exists():
                move_file(backup, source)
            raise
    else:
        move_file(candidate, final_output)
        output = final_output
    return OptimizeResult(str(source), "optimized", "optimized", original_size, output_size, saved_bytes, str(output))


def optimize_one(source: Path, options: OptimizeOptions) -> OptimizeResult:
    started = time.time()
    source = Path(source).resolve()
    original_size = source.stat().st_size if source.exists() else 0
    if not source.exists():
        return OptimizeResult(str(source), "error", "source not found", 0, 0, 0)
    source_ext = extension_for_path(source)
    if source_ext not in SUPPORTED_EXTS and not options.generic_fallback:
        return OptimizeResult(str(source), "skipped", "unsupported file type", original_size, original_size, 0)
    if options.max_size_bytes is not None and original_size > options.max_size_bytes:
        return OptimizeResult(str(source), "skipped", f"larger than limit: {format_bytes(options.max_size_bytes)}", original_size, original_size, 0)
    final_output = planned_output_path(source, options)
    if options.dry_run:
        return OptimizeResult(str(source), "planned", f"would write {final_output}", original_size, original_size, 0, str(final_output))
    with tempfile.TemporaryDirectory(prefix="optimizerzero_") as temp_dir_raw:
        candidate_suffix = output_suffix_for_path(source)
        candidate = Path(temp_dir_raw) / f"candidate{candidate_suffix}"
        suffix = source_ext
        try:
            if suffix in ZIP_CONTAINER_EXTS:
                ok, message = optimize_zip_container(source, candidate, options)
            elif suffix in TAR_EXTS:
                ok, message = optimize_tar_container(source, candidate)
            elif suffix in PDF_EXTS:
                ok, message = optimize_pdf(source, candidate)
            elif suffix in IMAGE_EXTS:
                ok, message = optimize_standalone_image(source, candidate, options)
            elif options.in_place:
                ok, message = False, "generic ZIP fallback cannot replace the original in place"
            elif options.generic_fallback:
                ok, message = optimize_generic_file(source, candidate)
            else:
                ok, message = False, "unsupported file type"
        except Exception as exc:
            ok, message = False, str(exc)
        if not ok:
            if "not useful" in message:
                return OptimizeResult(str(source), "skipped", message, original_size, original_size, 0)
            return OptimizeResult(str(source), "error", message, original_size, original_size, 0)
        result = accept_candidate(source, candidate, final_output, options)
        if result.status == "optimized":
            result.message = message
        result.elapsed_seconds = round(time.time() - started, 3)
        return result


def optimize_many(files: Iterable[Path], options: OptimizeOptions) -> list[OptimizeResult]:
    files = list(files)
    workers = max(1, min(options.workers or 1, len(files) or 1))
    if workers == 1:
        return [optimize_one(path, options) for path in files]

    results_by_index: dict[int, OptimizeResult] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_index = {executor.submit(optimize_one, path, options): index for index, path in enumerate(files)}
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            try:
                results_by_index[index] = future.result()
            except Exception as exc:
                source = files[index]
                original_size = source.stat().st_size if source.exists() else 0
                results_by_index[index] = OptimizeResult(str(source), "error", str(exc), original_size, original_size, 0)
    return [results_by_index[index] for index in range(len(files))]


def write_report(path: Path, results: list[OptimizeResult]) -> None:
    optimized = sum(1 for result in results if result.status == "optimized")
    skipped = sum(1 for result in results if result.status == "skipped")
    planned = sum(1 for result in results if result.status == "planned")
    errors = sum(1 for result in results if result.status == "error")
    original_size = sum(result.original_size for result in results)
    saved_bytes = sum(max(0, result.saved_bytes) for result in results)
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "count": len(results),
        "optimized": optimized,
        "skipped": skipped,
        "planned": planned,
        "errors": errors,
        "original_size": original_size,
        "saved_bytes": saved_bytes,
        "saved_percent": round((saved_bytes / original_size) * 100, 2) if original_size else 0,
        "results": [asdict(result) for result in results],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
