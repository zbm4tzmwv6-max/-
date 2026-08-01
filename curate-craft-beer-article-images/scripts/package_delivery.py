#!/usr/bin/env python3
"""Validate and package a craft-beer article image delivery."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urlparse

try:
    from PIL import Image, ImageOps
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Pillow is required: python3 -m pip install Pillow") from exc


REQUIRED_COLUMNS = [
    "number",
    "filename",
    "theme",
    "insertion",
    "purpose",
    "source_platform",
    "original_url",
    "is_official",
    "rights_note",
]
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
OFFICIAL_TRUE = {"yes"}
PLACEHOLDER_HOSTS = {
    "example.com",
    "example.org",
    "example.net",
    "localhost",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate images and create a self-contained delivery ZIP."
    )
    parser.add_argument("--images-dir", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-count", required=True, type=int)
    parser.add_argument("--min-width", type=int, default=1600)
    parser.add_argument("--min-height", type=int, default=900)
    parser.add_argument("--aspect", type=float, default=16 / 9)
    parser.add_argument("--aspect-tolerance", type=float, default=0.01)
    parser.add_argument("--min-official-ratio", type=float, default=0.70)
    parser.add_argument(
        "--allow-similar",
        action="store_true",
        help="Package visually similar files only after manual source verification.",
    )
    parser.add_argument(
        "--allow-low-official-ratio",
        action="store_true",
        help="Package a set below the official-source target after documenting why.",
    )
    parser.add_argument(
        "--confirm-manual-review",
        action="store_true",
        help=(
            "Confirm that every image and source page was opened and checked for "
            "subject identity, source-image correspondence, provenance, and reuse."
        ),
    )
    return parser.parse_args()


def read_manifest(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise ValueError(f"Manifest not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
        missing = [column for column in REQUIRED_COLUMNS if column not in columns]
        if missing:
            raise ValueError(f"Manifest columns missing: {', '.join(missing)}")
        return [
            {column: (row.get(column) or "").strip() for column in REQUIRED_COLUMNS}
            for row in reader
        ]


def valid_url(value: str) -> bool:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    return (
        parsed.scheme in {"http", "https"}
        and bool(host)
        and host not in PLACEHOLDER_HOSTS
        and not host.endswith(".example")
        and not host.endswith(".invalid")
        and not host.endswith(".test")
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def difference_hash(image: Image.Image) -> int:
    gray = ImageOps.grayscale(image).resize((9, 8))
    if hasattr(gray, "get_flattened_data"):
        pixels = list(gray.get_flattened_data())
    else:  # Pillow < 14
        pixels = list(gray.getdata())
    bits = 0
    for row in range(8):
        for column in range(8):
            left = pixels[row * 9 + column]
            right = pixels[row * 9 + column + 1]
            bits = (bits << 1) | int(left > right)
    return bits


def hamming(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def is_primary_official(row: dict[str, str]) -> bool:
    if row["is_official"].lower() not in OFFICIAL_TRUE:
        return False
    platform = "".join(row["source_platform"].lower().split())
    return any(
        marker in platform
        for marker in ("instagram", "官网", "官方网站", "officialwebsite")
    )


def write_markdown(rows: list[dict[str, str]], path: Path) -> None:
    lines = ["# 公众号配图说明", ""]
    for row in rows:
        lines.extend(
            [
                f"## 配图{int(row['number']):02d}｜{row['theme']}",
                "",
                f"- 文件：{row['filename']}",
                f"- 建议位置：{row['insertion']}",
                f"- 文章作用：{row['purpose']}",
                f"- 来源／平台：{row['source_platform']}",
                f"- 原始链接：{row['original_url']}",
                f"- 官方素材：{'是' if row['is_official'].lower() in OFFICIAL_TRUE else '否'}",
                f"- 权利／署名：{row['rights_note'] or '未特别标注；发布前仍需按来源核验'}",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_preview(rows: list[dict[str, str]], path: Path) -> None:
    cards = []
    for row in rows:
        number = int(row["number"])
        cards.append(
            f"""
<article>
  <h2>配图{number:02d}｜{html.escape(row['theme'])}</h2>
  <img src="images/{html.escape(row['filename'], quote=True)}"
       alt="{html.escape(row['theme'], quote=True)}">
  <dl>
    <dt>建议位置</dt><dd>{html.escape(row['insertion'])}</dd>
    <dt>文章作用</dt><dd>{html.escape(row['purpose'])}</dd>
    <dt>来源／平台</dt><dd>{html.escape(row['source_platform'])}</dd>
    <dt>原始链接</dt><dd><a href="{html.escape(row['original_url'], quote=True)}">{html.escape(row['original_url'])}</a></dd>
    <dt>官方素材</dt><dd>{"是" if row['is_official'].lower() in OFFICIAL_TRUE else "否"}</dd>
  </dl>
</article>"""
        )
    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>公众号配图预览</title>
<style>
body{{margin:0 auto;max-width:1120px;padding:32px 20px;background:#f4f1ea;color:#181818;font-family:system-ui,sans-serif}}
article{{margin:0 0 40px;padding:20px;background:#fff;border-radius:14px;box-shadow:0 4px 18px #0001}}
h2{{margin:0 0 16px;font-size:22px}}
img{{display:block;width:100%;aspect-ratio:16/9;object-fit:cover;background:#ddd}}
dl{{display:grid;grid-template-columns:100px 1fr;gap:8px 14px;margin:18px 0 0}}
dt{{font-weight:700}}dd{{margin:0;overflow-wrap:anywhere}}a{{color:#165d9a}}
</style>
</head>
<body>
<h1>公众号配图预览</h1>
{''.join(cards)}
</body>
</html>"""
    path.write_text(document, encoding="utf-8")


def main() -> int:
    args = parse_args()
    errors: list[str] = []
    warnings: list[str] = []

    if args.expected_count < 1:
        errors.append("expected-count must be positive")
    if not args.images_dir.is_dir():
        errors.append(f"Images directory not found: {args.images_dir}")

    try:
        rows = read_manifest(args.manifest)
    except ValueError as exc:
        errors.append(str(exc))
        rows = []

    if len(rows) != args.expected_count:
        errors.append(
            f"Manifest has {len(rows)} rows; expected {args.expected_count}"
        )

    numbers: list[int] = []
    filenames: list[str] = []
    official_count = 0
    primary_official_count = 0
    image_records: list[dict[str, object]] = []
    exact_hashes: dict[str, str] = {}
    visual_hashes: list[tuple[str, int]] = []

    for index, row in enumerate(rows, start=1):
        try:
            number = int(row["number"])
            numbers.append(number)
        except ValueError:
            errors.append(f"Row {index}: invalid number {row['number']!r}")
            continue

        filename = row["filename"]
        filenames.append(filename)
        if Path(filename).name != filename:
            errors.append(f"Row {index}: filename must not contain a path")
            continue
        if not filename.startswith(f"配图{number:02d}"):
            errors.append(
                f"Row {index}: filename must begin with 配图{number:02d}"
            )
        if Path(filename).suffix.lower() not in IMAGE_EXTENSIONS:
            errors.append(f"Row {index}: unsupported image type: {filename}")

        for field in (
            "theme",
            "insertion",
            "purpose",
            "source_platform",
            "original_url",
            "is_official",
        ):
            if not row[field]:
                errors.append(f"Row {index}: {field} is empty")
        if not valid_url(row["original_url"]):
            errors.append(f"Row {index}: invalid original_url")

        official = row["is_official"].lower() in OFFICIAL_TRUE
        if row["is_official"].lower() not in {"yes", "no"}:
            errors.append(f"Row {index}: is_official must be yes or no")
        official_count += int(official)
        primary_official_count += int(is_primary_official(row))
        image_path = args.images_dir / filename
        if not image_path.is_file():
            errors.append(f"Row {index}: image not found: {filename}")
            continue

        try:
            file_hash = sha256(image_path)
            if file_hash in exact_hashes:
                errors.append(
                    f"Exact duplicate: {filename} and {exact_hashes[file_hash]}"
                )
            else:
                exact_hashes[file_hash] = filename

            with Image.open(image_path) as opened:
                image = ImageOps.exif_transpose(opened)
                image.load()
                width, height = image.size
                if width < args.min_width or height < args.min_height:
                    warnings.append(
                        f"Below preferred resolution: {filename} ({width}x{height})"
                    )
                actual_aspect = width / height
                aspect_error = abs(actual_aspect / args.aspect - 1)
                if aspect_error > args.aspect_tolerance:
                    errors.append(
                        f"Not 16:9 within tolerance: {filename} ({width}x{height})"
                    )
                visual_hashes.append((filename, difference_hash(image)))
                image_records.append(
                    {
                        "number": number,
                        "filename": filename,
                        "width": width,
                        "height": height,
                        "sha256": file_hash,
                        "official": official,
                    }
                )
        except Exception as exc:
            errors.append(f"Unreadable image {filename}: {exc}")

    if numbers and numbers != list(range(1, args.expected_count + 1)):
        errors.append("Manifest numbers must be continuous and ordered from 1")
    if len(filenames) != len(set(filenames)):
        errors.append("Manifest filenames are not unique")

    similar_pairs = []
    for left_index, (left_name, left_hash) in enumerate(visual_hashes):
        for right_name, right_hash in visual_hashes[left_index + 1 :]:
            distance = hamming(left_hash, right_hash)
            if distance <= 3:
                similar_pairs.append(
                    {"left": left_name, "right": right_name, "distance": distance}
                )
    if similar_pairs and not args.allow_similar:
        errors.append(
            "Likely visual duplicates found; inspect and replace them or rerun "
            "with --allow-similar only after confirming distinct originals"
        )

    official_ratio = official_count / len(rows) if rows else 0.0
    primary_official_ratio = primary_official_count / len(rows) if rows else 0.0
    if (
        rows
        and primary_official_ratio < args.min_official_ratio
        and not args.allow_low_official_ratio
    ):
        errors.append(
            "Official Instagram/website ratio "
            f"{primary_official_ratio:.1%} is below "
            f"{args.min_official_ratio:.0%}"
        )

    manual_checks = [
        "Image content matches theme, insertion, and purpose",
        "Beer, brewery, person, award, process, event, and location identities are correct",
        "Original source page corresponds to the selected image",
        "Official status and publisher identity are correct",
        "Credits, usage notes, and rights exceptions are recorded",
        "No files are alternate crops or edits of the same source image",
    ]
    if errors:
        status = "failed"
    elif not args.confirm_manual_review:
        status = "requires_manual_review"
    else:
        status = "packaged_after_manual_confirmation"

    report = {
        "status": status,
        "expected_count": args.expected_count,
        "manifest_count": len(rows),
        "official_count": official_count,
        "official_ratio": official_ratio,
        "primary_official_count": primary_official_count,
        "primary_official_ratio": primary_official_ratio,
        "manual_review_confirmed": args.confirm_manual_review,
        "manual_checks": manual_checks,
        "images": image_records,
        "similar_pairs": similar_pairs,
        "warnings": warnings,
        "errors": errors,
    }

    if errors:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    if not args.confirm_manual_review:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print(
            "Open every image and original source, complete the manual checks, "
            "then rerun with --confirm-manual-review."
        )
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="beer-image-delivery-") as temp_name:
        staging = Path(temp_name) / args.output.stem
        images_out = staging / "images"
        images_out.mkdir(parents=True)
        for row in rows:
            shutil.copy2(args.images_dir / row["filename"], images_out / row["filename"])
        shutil.copy2(args.manifest, staging / "配图说明.csv")
        write_markdown(rows, staging / "配图说明.md")
        write_preview(rows, staging / "配图预览.html")
        (staging / "校验报告.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        with zipfile.ZipFile(
            args.output, mode="w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            for path in sorted(staging.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(staging.parent))

    with zipfile.ZipFile(args.output) as archive:
        bad_file = archive.testzip()
        if bad_file:
            print(f"ZIP integrity check failed: {bad_file}", file=sys.stderr)
            return 1

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Created: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
