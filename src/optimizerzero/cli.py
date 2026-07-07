from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from . import __version__
from .core import (
    Goal,
    LossBudget,
    Profile,
    analyze_files,
    discover_files,
    find_duplicate_files,
    format_bytes,
    merge_goal_options,
    optimize_many,
    parse_size,
    validate_file,
    write_report,
)


def default_workers() -> int:
    cpu_count = os.cpu_count() or 2
    return max(1, min(4, cpu_count - 1 if cpu_count > 1 else 1))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="optimizerzero", description="Safety-first local compression optimizer")
    parser.add_argument("--version", action="version", version=f"optimizerzero {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="check optional runtime capabilities")

    scan = sub.add_parser("scan", help="list supported files")
    scan.add_argument("paths", nargs="+", type=Path)
    scan.add_argument("-r", "--recursive", action="store_true")
    scan.add_argument("--supported-only", action="store_true", help="exclude generic ZIP fallback candidates")

    analyze = sub.add_parser("analyze", help="summarize supported files by type")
    analyze.add_argument("paths", nargs="+", type=Path)
    analyze.add_argument("-r", "--recursive", action="store_true")
    analyze.add_argument("--verify", action="store_true")
    analyze.add_argument("--report", type=Path)
    analyze.add_argument("--supported-only", action="store_true", help="exclude generic ZIP fallback candidates")

    duplicates = sub.add_parser("duplicates", help="find byte-identical supported files")
    duplicates.add_argument("paths", nargs="+", type=Path)
    duplicates.add_argument("-r", "--recursive", action="store_true")
    duplicates.add_argument("--report", type=Path)

    verify = sub.add_parser("verify", help="verify supported files without optimizing")
    verify.add_argument("paths", nargs="+", type=Path)
    verify.add_argument("-r", "--recursive", action="store_true")
    verify.add_argument("--supported-only", action="store_true", help="exclude generic ZIP fallback candidates")

    opt = sub.add_parser("optimize", help="optimize files or folders")
    opt.add_argument("paths", nargs="+", type=Path)
    opt.add_argument("-r", "--recursive", action="store_true")
    opt.add_argument("--goal", choices=[goal.value for goal in Goal], default=Goal.SMART.value, help="simple compression goal")
    opt.add_argument("--profile", choices=[p.value for p in Profile], default=Profile.SAFE.value)
    opt.add_argument("--output-dir", type=Path)
    opt.add_argument("--in-place", action="store_true")
    opt.add_argument("--yes", action="store_true", help="confirm risky actions such as --in-place")
    opt.add_argument("--allow-larger", action="store_true")
    opt.add_argument("--dry-run", action="store_true")
    opt.add_argument("--report", type=Path)
    opt.add_argument("--min-savings-percent", type=float)
    opt.add_argument("--max-size", help="skip files above this size, e.g. 75MB or 2GB")
    opt.add_argument("--loss-budget", choices=[budget.value for budget in LossBudget], help="allowed visual loss for images")
    opt.add_argument("--quality", type=int, help="image quality 1-100 for JPEG/WEBP")
    opt.add_argument("--target-size", help="per-file target output size, e.g. 5MB")
    opt.add_argument("--max-dimension", type=int, help="cap image longest edge in pixels (extra lever once quality alone can't hit --target-size)")
    opt.add_argument("--workers", type=int, default=0, help="parallel local workers; 0 uses a safe CPU-based default")
    opt.add_argument("--supported-only", action="store_true", help="disable generic ZIP fallback for unknown file types")

    sub.add_parser("gui", help="open the desktop GUI")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        checks = {
            "Pillow": importlib.util.find_spec("PIL") is not None,
            "PyMuPDF/PDF cleanup": importlib.util.find_spec("fitz") is not None,
            "pikepdf/PDF repair": importlib.util.find_spec("pikepdf") is not None,
            "tkinter/GUI": importlib.util.find_spec("tkinter") is not None,
            "PyInstaller/build": importlib.util.find_spec("PyInstaller") is not None,
        }
        for name, ok in checks.items():
            print(f"{name}: {'ok' if ok else 'missing'}")
        print(f"CPU workers: {default_workers()}")
        return 0 if checks["Pillow"] else 1

    if args.command == "gui":
        from .gui import main as gui_main
        return gui_main()

    if args.command == "analyze":
        analyses = analyze_files(args.paths, recursive=args.recursive, verify=args.verify, generic_fallback=not args.supported_only)
        by_kind: dict[str, list] = {}
        for item in analyses:
            by_kind.setdefault(item.kind, []).append(item)
        print(f"files: {len(analyses)}")
        print(f"size: {format_bytes(sum(item.size for item in analyses))}")
        for kind in sorted(by_kind):
            items = by_kind[kind]
            print(f"{kind}: {len(items)} files / {format_bytes(sum(item.size for item in items))}")
        if args.verify:
            errors = sum(1 for item in analyses if item.valid is False)
            print(f"verify: ok={len(analyses) - errors} errors={errors}")
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps([asdict(item) for item in analyses], ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"report: {args.report}")
        return 1 if any(item.valid is False for item in analyses) else 0

    if args.command == "duplicates":
        groups = find_duplicate_files(args.paths, recursive=args.recursive)
        duplicate_files = sum(len(group.paths) for group in groups)
        reclaimable = sum(group.size * (len(group.paths) - 1) for group in groups)
        print(f"groups: {len(groups)}")
        print(f"duplicate_files: {duplicate_files}")
        print(f"reclaimable: {format_bytes(reclaimable)}")
        for group in groups:
            print(f"group: {format_bytes(group.size)} / {group.digest[:12]}")
            for path in group.paths:
                print(f"  {path}")
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps([asdict(group) for group in groups], ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"report: {args.report}")
        return 0

    files = discover_files(args.paths, recursive=args.recursive, generic_fallback=not getattr(args, "supported_only", False))
    if args.command == "verify":
        if not files:
            print("files: 0")
            print("No supported files found.")
            return 0
        errors = 0
        for path in files:
            ok, message = validate_file(path)
            errors += 0 if ok else 1
            print(f"{'ok' if ok else 'error'}: {path.name} | {message}")
        print(f"summary: verified={len(files) - errors} errors={errors}")
        return 1 if errors else 0

    if args.command == "scan":
        total = sum(path.stat().st_size for path in files)
        print(f"files: {len(files)}")
        print(f"size: {format_bytes(total)}")
        for path in files:
            print(path)
        return 0

    if not files:
        print("files: 0")
        print("No supported files found.")
        return 0
    if args.in_place and not args.yes:
        print("Refusing --in-place without --yes. OptimizerZero preserves originals by default.")
        return 2

    explicit_profile = args.profile != Profile.SAFE.value
    workers = args.workers if args.workers and args.workers > 0 else default_workers()
    options = merge_goal_options(
        Goal(args.goal),
        profile=Profile(args.profile) if explicit_profile else None,
        recursive=args.recursive,
        output_dir=args.output_dir,
        in_place=args.in_place,
        allow_larger=args.allow_larger,
        dry_run=args.dry_run,
        min_savings_percent=args.min_savings_percent,
        max_size_bytes=parse_size(args.max_size),
        loss_budget=LossBudget(args.loss_budget) if args.loss_budget else None,
        image_quality=args.quality,
        target_size_bytes=parse_size(args.target_size),
        max_dimension=args.max_dimension,
        generic_fallback=not args.supported_only,
        workers=workers,
    )
    results = optimize_many(files, options)
    for result in results:
        print(f"{result.status}: {Path(result.source).name} | saved: {format_bytes(max(0, result.saved_bytes))} | {result.message}")
    optimized = sum(1 for result in results if result.status == "optimized")
    skipped = sum(1 for result in results if result.status == "skipped")
    planned = sum(1 for result in results if result.status == "planned")
    errors = sum(1 for result in results if result.status == "error")
    saved_total = sum(max(0, result.saved_bytes) for result in results)
    print(f"summary: optimized={optimized} skipped={skipped} planned={planned} errors={errors} saved={format_bytes(saved_total)}")
    if args.report:
        write_report(args.report, results)
        print(f"report: {args.report}")
    return 1 if any(result.status == "error" for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
