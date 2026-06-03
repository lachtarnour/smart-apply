"""Optional PDF export.

WeasyPrint is optional (requires system libs cairo/pango). When unavailable,
``to_pdf`` raises a clear error pointing to ``[pdf]`` install extra. The
fallback for users without weasyprint is to open the DOCX and export as PDF.
"""

from __future__ import annotations

from pathlib import Path


def docx_to_pdf(docx_path: str | Path, pdf_path: str | Path) -> Path:
    """Convert a DOCX to PDF using LibreOffice if available.

    We avoid hard-depending on heavy libs. If LibreOffice's ``soffice`` is
    installed (common on macOS via brew), we shell out to it. Otherwise we
    raise — the calling code should keep the DOCX as primary output.
    """
    import shutil
    import subprocess

    docx_path = Path(docx_path).resolve()
    pdf_path = Path(pdf_path).resolve()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise RuntimeError(
            "PDF export requires LibreOffice or WeasyPrint. "
            "Install via `brew install --cask libreoffice` or `pip install -e .[pdf]`."
        )

    subprocess.run(
        [
            soffice,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(pdf_path.parent),
            str(docx_path),
        ],
        check=True,
        capture_output=True,
    )
    produced = pdf_path.parent / (docx_path.stem + ".pdf")
    if produced != pdf_path:
        produced.rename(pdf_path)
    return pdf_path
