"""Disposable question-number browser fixture; guarded by the parent test server."""

import fitz
from fastapi import Response

from pdf_layout_browser_server import app


def number_paper(scan: bool = False) -> bytes:
    doc = fitz.open()
    for number in (1, 2, 3):
        page = doc.new_page(width=595, height=500)
        ordinal = ("first", "second", "third")[number - 1]
        page.insert_text(
            (50, 55),
            f"{number} Find the angle x in the {ordinal} triangle.",
            fontsize=12,
        )
        page.draw_polyline(
            [(30, 230), (300, 230), (180, 100), (30, 230)],
            color=(0, 0, 0),
            fill=(0.85, 0.93, 1),
            width=1,
        )
        page.insert_text((70, 215), "50°", fontsize=12)
        page.insert_text((250, 215), "60°", fontsize=12)
        page.insert_text((172, 140), "x", fontsize=12)
        for index, (label, value) in enumerate(
            zip("ABCD", ["60°", "70°", "80°", "90°"], strict=True)
        ):
            page.insert_text((50, 300 + index * 35), f"{label}.  {value}", fontsize=12)
    if scan:
        raster = fitz.open()
        for page in doc:
            target = raster.new_page(width=page.rect.width, height=page.rect.height)
            target.insert_image(target.rect, pixmap=page.get_pixmap(dpi=150, alpha=False))
        doc.close()
        doc = raster
    data = doc.tobytes()
    doc.close()
    return data


@app.get("/__test_number_paper", include_in_schema=False)
def test_number_paper(scan: bool = False):
    return Response(number_paper(scan), media_type="application/pdf")
