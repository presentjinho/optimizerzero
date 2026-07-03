from __future__ import annotations

import argparse
import io
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw


def png_bytes(label: str, color: tuple[int, int, int]) -> bytes:
    image = Image.new("RGB", (900, 1200), color)
    draw = ImageDraw.Draw(image)
    draw.rectangle((60, 60, 840, 1140), outline=(255, 255, 255), width=10)
    draw.text((100, 120), label, fill=(255, 255, 255))
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def write_zip(path: Path) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("docs/readme.txt", "OptimizerZero demo text\n" * 200)
        archive.writestr("data/table.csv", "name,value\nalpha,1\nbeta,2\n" * 100)


def write_cbz(path: Path) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("001.png", png_bytes("Page 1", (150, 60, 70)))
        archive.writestr("002.png", png_bytes("Page 2", (60, 95, 135)))
        archive.writestr("notes.txt", "Synthetic public demo file. No copyrighted pages.\n")


def write_epub(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        archive.writestr(info, b"application/epub+zip")
        archive.writestr("META-INF/container.xml", "<container/>")
        archive.writestr("OPS/chapter.xhtml", "<html><body><p>OptimizerZero demo</p></body></html>" * 100)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create synthetic public demo assets for OptimizerZero")
    parser.add_argument("--out", type=Path, default=Path("demo_assets"))
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    write_zip(args.out / "demo-docs.zip")
    write_cbz(args.out / "demo-pages.cbz")
    write_epub(args.out / "demo-book.epub")
    (args.out / "demo-image.png").write_bytes(png_bytes("Standalone image", (70, 120, 90)))
    print(args.out.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
