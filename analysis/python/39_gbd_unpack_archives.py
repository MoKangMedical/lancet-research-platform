#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

ROOT = Path("/Users/apple/Documents/lancet-research-platform")
DEFAULT_INPUT_ROOT = ROOT / "data" / "raw" / "gbd"
DEFAULT_DEST_ROOT = ROOT / "data" / "bronze" / "gbd" / "gbd2023"
DEFAULT_CATALOG_OUT = ROOT / "outputs" / "tables" / "gbd2023_extracted_catalog.csv"
DEFAULT_SUMMARY_OUT = ROOT / "outputs" / "tables" / "gbd2023_extracted_summary.json"


@dataclass
class ExtractedFile:
    record_key: str
    archive_relpath: str
    archive_name: str
    extracted_relpath: str
    destination_path: str
    member_size_bytes: int
    compressed_size_bytes: int
    status: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract official GBD 2023 zip archives into the bronze layer.")
    parser.add_argument("--input-root", default=str(DEFAULT_INPUT_ROOT), help="Root containing downloaded raw GBD files")
    parser.add_argument("--dest-root", default=str(DEFAULT_DEST_ROOT), help="Bronze-layer output root")
    parser.add_argument("--catalog-out", default=str(DEFAULT_CATALOG_OUT), help="CSV catalog of extracted files")
    parser.add_argument("--summary-out", default=str(DEFAULT_SUMMARY_OUT), help="JSON summary of extracted archives")
    parser.add_argument("--force", action="store_true", help="Overwrite existing extracted files")
    return parser.parse_args()


def iter_archives(input_root: Path) -> list[Path]:
    return sorted(path for path in input_root.rglob("*.zip") if path.is_file())


def normalize_member_path(member_name: str) -> Path:
    pure_path = PurePosixPath(member_name)
    if pure_path.is_absolute() or ".." in pure_path.parts:
        raise ValueError(f"Unsafe archive member path: {member_name}")
    return Path(*pure_path.parts)


def extract_archive(archive_path: Path, input_root: Path, dest_root: Path, force: bool) -> list[ExtractedFile]:
    record_key = archive_path.parent.name
    archive_relpath = archive_path.relative_to(input_root)
    archive_stem = archive_path.stem
    output_dir = dest_root / record_key / archive_stem

    rows: list[ExtractedFile] = []
    with zipfile.ZipFile(archive_path) as handle:
        for member in handle.infolist():
            if member.is_dir():
                continue
            member_relpath = normalize_member_path(member.filename)
            destination = output_dir / member_relpath
            destination.parent.mkdir(parents=True, exist_ok=True)
            status = "skipped"
            if force or not destination.exists():
                with handle.open(member) as source, destination.open("wb") as target:
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        target.write(chunk)
                status = "extracted"

            rows.append(
                ExtractedFile(
                    record_key=record_key,
                    archive_relpath=str(archive_relpath),
                    archive_name=archive_path.name,
                    extracted_relpath=str(Path(record_key) / archive_stem / member_relpath),
                    destination_path=str(destination),
                    member_size_bytes=member.file_size,
                    compressed_size_bytes=member.compress_size,
                    status=status,
                )
            )
    return rows


def write_catalog(rows: list[ExtractedFile], catalog_out: Path) -> None:
    catalog_out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(asdict(rows[0]).keys()) if rows else list(ExtractedFile.__annotations__.keys())
    with catalog_out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def write_summary(rows: list[ExtractedFile], archives: list[Path], summary_out: Path, dest_root: Path) -> None:
    extracted = sum(1 for row in rows if row.status == "extracted")
    skipped = sum(1 for row in rows if row.status == "skipped")
    by_record: dict[str, int] = {}
    for row in rows:
        by_record[row.record_key] = by_record.get(row.record_key, 0) + 1

    payload = {
        "archives_found": len(archives),
        "files_cataloged": len(rows),
        "files_extracted": extracted,
        "files_skipped": skipped,
        "dest_root": str(dest_root),
        "by_record": by_record,
    }
    summary_out.parent.mkdir(parents=True, exist_ok=True)
    summary_out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    args = parse_args()
    input_root = Path(args.input_root).expanduser()
    dest_root = Path(args.dest_root).expanduser()
    catalog_out = Path(args.catalog_out).expanduser()
    summary_out = Path(args.summary_out).expanduser()

    archives = iter_archives(input_root)
    if not archives:
        raise SystemExit(f"No zip archives found under {input_root}")

    rows: list[ExtractedFile] = []
    for archive_path in archives:
        print(f"extract {archive_path}")
        rows.extend(extract_archive(archive_path, input_root=input_root, dest_root=dest_root, force=args.force))

    write_catalog(rows, catalog_out)
    write_summary(rows, archives=archives, summary_out=summary_out, dest_root=dest_root)
    print(f"catalog {catalog_out}")
    print(f"summary {summary_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
