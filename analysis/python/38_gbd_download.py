#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from dataclasses import dataclass
from html import unescape
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin
from urllib.request import HTTPCookieProcessor, Request, build_opener

ROOT = Path("/Users/apple/Documents/lancet-research-platform")
USER_AGENT = "Mozilla/5.0 (Codex GBD Downloader)"
LOGIN_PREFIX = "https://ghdx.healthdata.org/download-access/login"
GBD_2023_DIR = ROOT / "data" / "raw" / "gbd2023_official"


@dataclass(frozen=True)
class RecordConfig:
    key: str
    label: str
    url: str
    html_cache: Path


RECORDS: dict[str, RecordConfig] = {
    "mortality-2023": RecordConfig(
        key="mortality-2023",
        label="GBD 2023 cause-specific mortality 1990-2023",
        url="https://ghdx.healthdata.org/record/ihme-data/gbd-2023-cause-specific-mortality-1990-2023",
        html_cache=GBD_2023_DIR / "gbd_2023_cause_specific_mortality_record.html",
    ),
    "dirf-2023": RecordConfig(
        key="dirf-2023",
        label="GBD 2023 YLD/DALY/HALE/risk-attributable burden 1990-2023",
        url="https://ghdx.healthdata.org/record/ihme-data/gbd-2023-yld-daly-hale-risk-1990-2023",
        html_cache=GBD_2023_DIR / "gbd_2023_yld_daly_hale_risk_record.html",
    ),
    "risk-exposure-2023": RecordConfig(
        key="risk-exposure-2023",
        label="GBD 2023 risk exposure estimates 1990-2023",
        url="https://ghdx.healthdata.org/record/ihme-data/gbd-2023-risk-exposure-estimates-1990-2023",
        html_cache=GBD_2023_DIR / "gbd_2023_risk_exposure_record.html",
    ),
}

PRESETS: dict[str, list[str]] = {
    "gbd2023-core-1990-2023": [
        "mortality-2023",
        "dirf-2023",
        "risk-exposure-2023",
    ]
}


@dataclass
class FileEntry:
    record_key: str
    record_label: str
    record_url: str
    page_title: str
    label: str
    title: str
    href: str
    size: str
    mime_type: str

    @property
    def filename(self) -> str:
        return self.title or Path(self.href).name

    @property
    def requires_auth(self) -> bool:
        return self.href.startswith(LOGIN_PREFIX)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="List or download official GBD 2023 GHDx files, with authentication-aware checks."
    )
    parser.add_argument(
        "--preset",
        choices=sorted(PRESETS),
        default="gbd2023-core-1990-2023",
        help="Named record bundle to use",
    )
    parser.add_argument(
        "--record",
        action="append",
        choices=sorted(RECORDS),
        help="Specific record(s) to use instead of the preset",
    )
    parser.add_argument("--record-url", help="Custom GHDx record URL")
    parser.add_argument("--record-html", help="Custom local record HTML to parse")
    parser.add_argument(
        "--dest",
        default=str(ROOT / "data" / "raw" / "gbd"),
        help="Destination root for downloaded files",
    )
    parser.add_argument(
        "--filename-pattern",
        action="append",
        default=[],
        help="Case-insensitive regex pattern applied to file title/filename; repeatable",
    )
    parser.add_argument(
        "--label-pattern",
        action="append",
        default=[],
        help="Case-insensitive regex pattern applied to display label; repeatable",
    )
    parser.add_argument(
        "--year-span",
        default="1990-2023",
        help="Year span token to keep, e.g. 1990-2023; use '' to disable filtering",
    )
    parser.add_argument("--list-only", action="store_true", help="Only print the manifest, do not download")
    parser.add_argument("--manifest-out", help="Optional path to write manifest JSON")
    parser.add_argument("--cookie-header", help="Raw Cookie header for authenticated GHDx access")
    parser.add_argument("--cookie-file", help="Netscape/Mozilla cookies.txt exported from the browser")
    parser.add_argument("--save-html", action="store_true", help="Refresh and save fetched record HTML")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    parser.add_argument("--timeout", type=int, default=60, help="HTTP timeout in seconds")
    return parser.parse_args()


def build_cookie_header(cookie_file: str | None, cookie_header: str | None) -> str | None:
    if cookie_header:
        return cookie_header.strip()
    env_header = os.environ.get("GHDX_COOKIE", "").strip()
    if env_header:
        return env_header
    if not cookie_file:
        return None

    jar = MozillaCookieJar()
    jar.load(cookie_file, ignore_discard=True, ignore_expires=True)
    parts: list[str] = []
    for cookie in jar:
        if "healthdata.org" not in cookie.domain:
            continue
        parts.append(f"{cookie.name}={cookie.value}")
    return "; ".join(parts) if parts else None


def fetch_text(url: str, cookie_header: str | None, timeout: int) -> str:
    opener = build_opener(HTTPCookieProcessor())
    headers = {"User-Agent": USER_AGENT}
    if cookie_header:
        headers["Cookie"] = cookie_header
    request = Request(url, headers=headers)
    with opener.open(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def download_binary(url: str, destination: Path, cookie_header: str | None, timeout: int) -> None:
    opener = build_opener(HTTPCookieProcessor())
    headers = {"User-Agent": USER_AGENT}
    if cookie_header:
        headers["Cookie"] = cookie_header
    request = Request(url, headers=headers)
    with opener.open(request, timeout=timeout) as response:
        final_url = response.geturl()
        content_type = response.headers.get("Content-Type", "")
        if final_url.startswith(LOGIN_PREFIX) or "text/html" in content_type.lower():
            raise RuntimeError(
                "Authenticated download failed. GHDx still returned the login page. "
                "Provide a valid GHDX session via --cookie-header, --cookie-file, or GHDX_COOKIE."
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)


def strip_tags(value: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", value)).strip()


def parse_page_title(html_text: str) -> str:
    match = re.search(r'<h1 class="title"[^>]*>(.*?)</h1>', html_text, flags=re.S)
    return strip_tags(match.group(1)) if match else ""


def parse_file_entries(html_text: str, record: RecordConfig | None, record_url: str) -> list[FileEntry]:
    section_match = re.search(
        r'field-name-field-attached-files.*?<tbody>(.*?)</tbody>',
        html_text,
        flags=re.S,
    )
    if not section_match:
        return []

    rows = re.findall(
        r"<tr[^>]*>\s*<td>.*?<a href=\"(?P<href>[^\"]+)\"(?P<attrs>[^>]*)>(?P<label>.*?)</a>.*?</td>\s*<td>(?P<size>.*?)</td>",
        section_match.group(1),
        flags=re.S,
    )
    page_title = parse_page_title(html_text)
    record_key = record.key if record else "custom"
    record_label = record.label if record else page_title or record_url

    entries: list[FileEntry] = []
    for href, attrs_blob, label_html, size_html in rows:
        title_match = re.search(r'title="([^"]+)"', attrs_blob)
        type_match = re.search(r'type="([^"]+)"', attrs_blob)
        entry = FileEntry(
            record_key=record_key,
            record_label=record_label,
            record_url=record_url,
            page_title=page_title,
            label=strip_tags(label_html),
            title=unescape(title_match.group(1)) if title_match else "",
            href=urljoin(record_url, unescape(href)),
            size=strip_tags(size_html),
            mime_type=type_match.group(1) if type_match else "",
        )
        entries.append(entry)
    return entries


def resolve_record_inputs(args: argparse.Namespace) -> list[tuple[RecordConfig | None, str, Path | None]]:
    if args.record_url:
        html_path = Path(args.record_html).expanduser() if args.record_html else None
        return [(None, args.record_url, html_path)]

    chosen = args.record or PRESETS[args.preset]
    resolved: list[tuple[RecordConfig | None, str, Path | None]] = []
    for key in chosen:
        record = RECORDS[key]
        resolved.append((record, record.url, record.html_cache))
    return resolved


def load_entries_for_record(
    record: RecordConfig | None,
    record_url: str,
    html_path: Path | None,
    cookie_header: str | None,
    timeout: int,
    save_html: bool,
) -> list[FileEntry]:
    html_text = ""
    if cookie_header:
        html_text = fetch_text(record_url, cookie_header=cookie_header, timeout=timeout)
        if save_html and html_path:
            html_path.parent.mkdir(parents=True, exist_ok=True)
            html_path.write_text(html_text, encoding="utf-8")
    elif html_path and html_path.exists():
        html_text = html_path.read_text(encoding="utf-8")
    else:
        html_text = fetch_text(record_url, cookie_header=None, timeout=timeout)
        if save_html and html_path:
            html_path.parent.mkdir(parents=True, exist_ok=True)
            html_path.write_text(html_text, encoding="utf-8")

    return parse_file_entries(html_text, record=record, record_url=record_url)


def year_span_matches(entry: FileEntry, year_span: str) -> bool:
    if not year_span:
        return True
    normalized = year_span.replace("-", "_")
    haystacks = [entry.title, entry.filename, entry.page_title, entry.record_label]
    return any(normalized in item.replace("-", "_") for item in haystacks)


def regex_matches(patterns: Iterable[str], text: str) -> bool:
    compiled = [re.compile(pattern, flags=re.I) for pattern in patterns if pattern]
    if not compiled:
        return True
    return all(regex.search(text) for regex in compiled)


def filter_entries(entries: list[FileEntry], args: argparse.Namespace) -> list[FileEntry]:
    filtered: list[FileEntry] = []
    for entry in entries:
        title_text = f"{entry.title} {entry.filename}"
        if not year_span_matches(entry, args.year_span):
            continue
        if not regex_matches(args.filename_pattern, title_text):
            continue
        if not regex_matches(args.label_pattern, entry.label):
            continue
        filtered.append(entry)
    return filtered


def write_manifest(entries: list[FileEntry], manifest_path: Path) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "record_key": entry.record_key,
            "record_label": entry.record_label,
            "record_url": entry.record_url,
            "page_title": entry.page_title,
            "label": entry.label,
            "title": entry.title,
            "filename": entry.filename,
            "href": entry.href,
            "size": entry.size,
            "mime_type": entry.mime_type,
            "requires_auth": entry.requires_auth,
        }
        for entry in entries
    ]
    manifest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def print_manifest(entries: list[FileEntry]) -> None:
    writer = csv.writer(sys.stdout)
    writer.writerow(["record_key", "filename", "label", "size", "requires_auth", "href"])
    for entry in entries:
        writer.writerow(
            [
                entry.record_key,
                entry.filename,
                entry.label,
                entry.size,
                "yes" if entry.requires_auth else "no",
                entry.href,
            ]
        )


def download_entries(entries: list[FileEntry], args: argparse.Namespace, cookie_header: str | None) -> int:
    if not entries:
        print("No matching files found after filtering.", file=sys.stderr)
        return 1

    if any(entry.requires_auth for entry in entries) and not cookie_header:
        print(
            "GHDx still exposes login-gated file URLs. Supply --cookie-header, --cookie-file, or GHDX_COOKIE.",
            file=sys.stderr,
        )
        return 1

    dest_root = Path(args.dest).expanduser()
    for entry in entries:
        target = dest_root / entry.record_key / entry.filename
        if target.exists() and not args.force:
            print(f"skip {target} (exists)")
            continue
        print(f"download {entry.filename} -> {target}")
        download_binary(entry.href, target, cookie_header=cookie_header, timeout=args.timeout)
    return 0


def main() -> int:
    args = parse_args()
    cookie_header = build_cookie_header(args.cookie_file, args.cookie_header)

    all_entries: list[FileEntry] = []
    for record, record_url, html_path in resolve_record_inputs(args):
        entries = load_entries_for_record(
            record=record,
            record_url=record_url,
            html_path=html_path,
            cookie_header=cookie_header,
            timeout=args.timeout,
            save_html=args.save_html,
        )
        if not entries:
            print(f"No file entries parsed for {record_url}", file=sys.stderr)
            return 1
        all_entries.extend(entries)

    filtered = filter_entries(all_entries, args)
    print_manifest(filtered)

    if args.manifest_out:
        write_manifest(filtered, Path(args.manifest_out).expanduser())

    if args.list_only:
        return 0

    return download_entries(filtered, args, cookie_header=cookie_header)


if __name__ == "__main__":
    raise SystemExit(main())
