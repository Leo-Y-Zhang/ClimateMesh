"""Rebuild WRITEUP.docx and WRITEUP.pdf from WRITEUP.md.

Needs: pip install pypandoc_binary playwright pymupdf   (and a Chromium for
Playwright: `playwright install chromium`, or set CHROMIUM to an existing
binary). Run from anywhere:

    python SUBMISSION_PACK/_build/build_writeup.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pypandoc

HERE = Path(__file__).resolve().parent
PACK = HERE.parent
MD = PACK / "WRITEUP.md"
FOOTER = ("<div style='font-size:8px;color:#6b7280;width:100%;text-align:center;"
          "font-family:sans-serif;'>Climate Mesh · Luis Yu and Leo Zhang · PA Raspberry Pi "
          "Competition 2026/27 · page <span class='pageNumber'></span> of "
          "<span class='totalPages'></span></div>")


def build_docx() -> None:
    pypandoc.convert_file(str(MD), "docx", outputfile=str(PACK / "WRITEUP.docx"),
                          extra_args=[f"--resource-path={PACK}:{PACK.parent}",
                                      f"--reference-doc={HERE / 'reference.docx'}"])


def build_pdf() -> None:
    from playwright.sync_api import sync_playwright
    html = HERE / "WRITEUP.html"
    pypandoc.convert_file(str(MD), "html5", outputfile=str(html),
                          extra_args=["--standalone", "--embed-resources",
                                      f"--resource-path={PACK}:{PACK.parent}",
                                      f"--css={HERE / 'writeup.css'}", "--metadata=lang:en-GB"])
    with sync_playwright() as p:
        kw = {"args": ["--no-sandbox"]}
        if os.environ.get("CHROMIUM"):
            kw["executable_path"] = os.environ["CHROMIUM"]
        b = p.chromium.launch(**kw)
        pg = b.new_page()
        pg.goto(html.as_uri())
        pg.wait_for_timeout(800)
        pg.pdf(path=str(PACK / "WRITEUP.pdf"), format="A4", prefer_css_page_size=True,
               print_background=True, display_header_footer=True,
               header_template="<div></div>", footer_template=FOOTER)
        b.close()
    html.unlink(missing_ok=True)


def render_pages(out_dir: Path) -> int:
    """Rasterise the PDF for a visual check; returns the page count."""
    import pymupdf
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(str(PACK / "WRITEUP.pdf"))
    for i, page in enumerate(doc):
        page.get_pixmap(dpi=60).save(str(out_dir / f"pg-{i + 1}.png"))
    return doc.page_count


if __name__ == "__main__":
    build_docx()
    build_pdf()
    if len(sys.argv) > 1:
        print("pages:", render_pages(Path(sys.argv[1])))
    print("built", PACK / "WRITEUP.docx", "and", PACK / "WRITEUP.pdf")
