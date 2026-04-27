from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


FALLBACK_EXECUTABLES = {
    "soffice": [
        "/opt/homebrew/bin/soffice",
        "/usr/local/bin/soffice",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    ],
    "pdftoppm": [
        "/opt/homebrew/bin/pdftoppm",
        "/usr/local/bin/pdftoppm",
    ],
}


def find_executable(name: str) -> str | None:
    candidate = shutil.which(name)
    if candidate:
        return candidate
    for fallback in FALLBACK_EXECUTABLES.get(name, []):
        if Path(fallback).exists():
            return fallback
    return None


def _run_command(cmd: list[str], timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )


def _base_result(kind: str, input_path: Path, executable: str | None) -> dict[str, object]:
    return {
        "kind": kind,
        "input": str(input_path),
        "available": executable is not None,
        "executable": executable,
        "ok": False,
        "command": [],
        "stdout": "",
        "stderr": "",
    }


def render_docx_to_pdf(
    docx_path: Path,
    output_dir: Path,
    *,
    soffice_path: str | None = None,
    timeout_seconds: int = 180,
) -> dict[str, object]:
    executable = soffice_path or find_executable("soffice")
    result = _base_result("docx_to_pdf", docx_path, executable)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_pdf = output_dir / f"{docx_path.stem}.pdf"
    result["output_pdf"] = str(output_pdf)
    if executable is None:
        result["stderr"] = "soffice executable not found"
        return result

    profile_dir = Path(tempfile.mkdtemp(prefix="lo_profile_"))
    cmd = [
        executable,
        f"-env:UserInstallation={profile_dir.as_uri()}",
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(output_dir),
        str(docx_path),
    ]
    result["command"] = cmd
    try:
        proc = _run_command(cmd, timeout_seconds=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        result["stderr"] = f"command timed out after {timeout_seconds}s: {exc}"
        shutil.rmtree(profile_dir, ignore_errors=True)
        return result

    shutil.rmtree(profile_dir, ignore_errors=True)
    result["stdout"] = proc.stdout.strip()
    result["stderr"] = proc.stderr.strip()
    result["ok"] = proc.returncode == 0 and output_pdf.exists()
    return result


def render_pdf_to_pngs(
    pdf_path: Path,
    output_prefix: Path,
    *,
    pdftoppm_path: str | None = None,
    timeout_seconds: int = 180,
    dpi: int = 144,
) -> dict[str, object]:
    executable = pdftoppm_path or find_executable("pdftoppm")
    result = _base_result("pdf_to_png", pdf_path, executable)
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    result["output_prefix"] = str(output_prefix)
    if executable is None:
        result["stderr"] = "pdftoppm executable not found"
        result["pages"] = []
        result["page_count"] = 0
        return result

    cmd = [
        executable,
        "-r",
        str(dpi),
        "-png",
        str(pdf_path),
        str(output_prefix),
    ]
    result["command"] = cmd
    try:
        proc = _run_command(cmd, timeout_seconds=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        result["stderr"] = f"command timed out after {timeout_seconds}s: {exc}"
        result["pages"] = []
        result["page_count"] = 0
        return result

    pages = sorted(output_prefix.parent.glob(f"{output_prefix.name}-*.png"))
    result["stdout"] = proc.stdout.strip()
    result["stderr"] = proc.stderr.strip()
    result["pages"] = [str(page) for page in pages]
    result["page_count"] = len(pages)
    result["ok"] = proc.returncode == 0 and len(pages) > 0
    return result


def render_docx_to_pngs(
    docx_path: Path,
    output_root: Path,
    *,
    soffice_path: str | None = None,
    pdftoppm_path: str | None = None,
    timeout_seconds: int = 180,
    dpi: int = 144,
) -> dict[str, object]:
    doc_output_dir = output_root / docx_path.stem
    pdf_result = render_docx_to_pdf(
        docx_path,
        doc_output_dir,
        soffice_path=soffice_path,
        timeout_seconds=timeout_seconds,
    )
    png_result: dict[str, object]
    if pdf_result["ok"]:
        png_result = render_pdf_to_pngs(
            Path(str(pdf_result["output_pdf"])),
            doc_output_dir / docx_path.stem,
            pdftoppm_path=pdftoppm_path,
            timeout_seconds=timeout_seconds,
            dpi=dpi,
        )
    else:
        png_result = _base_result("pdf_to_png", Path(str(pdf_result["output_pdf"])), pdftoppm_path or find_executable("pdftoppm"))
        png_result["stderr"] = "skipped because DOCX to PDF conversion failed"
        png_result["pages"] = []
        png_result["page_count"] = 0
        png_result["output_prefix"] = str(doc_output_dir / docx_path.stem)

    return {
        "docx": str(docx_path),
        "output_dir": str(doc_output_dir),
        "ok": bool(pdf_result["ok"]) and bool(png_result["ok"]),
        "pdf_result": pdf_result,
        "png_result": png_result,
        "page_count": int(png_result.get("page_count", 0)),
    }


def render_docx_collection(docx_paths: list[Path], output_root: Path) -> dict[str, object]:
    soffice_path = find_executable("soffice")
    pdftoppm_path = find_executable("pdftoppm")
    output_root.mkdir(parents=True, exist_ok=True)
    documents: list[dict[str, object]] = []
    for docx_path in docx_paths:
        documents.append(
            render_docx_to_pngs(
                docx_path,
                output_root,
                soffice_path=soffice_path,
                pdftoppm_path=pdftoppm_path,
            )
        )

    return {
        "output_root": str(output_root),
        "soffice": soffice_path,
        "pdftoppm": pdftoppm_path,
        "available": soffice_path is not None and pdftoppm_path is not None,
        "document_count": len(documents),
        "rendered_count": sum(1 for item in documents if item["ok"]),
        "page_count": sum(int(item["page_count"]) for item in documents),
        "documents": documents,
    }
