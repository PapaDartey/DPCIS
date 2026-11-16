"""Deterministic PyMuPDF-only corpus; geometry is specified before detection.

Run from backend: python tests/tools/make_diagram_fixtures.py.
No importer calls are used to manufacture expected bounds.
"""

import json
from pathlib import Path

import fitz

DEST = Path(__file__).resolve().parents[1] / "fixtures/pdfs/synthetic"
NAMES = [
    "vector",
    "raster_alpha",
    "clip_form",
    "graph",
    "filled_charts",
    "tables",
    "chemistry",
    "maths",
    "callouts",
    "picture_options",
    "after_options",
    "multiple_inline",
    "continuation",
    "shared",
    "rotation",
    "decoration",
    "columns",
    "bands",
    "tight",
    "scale",
]


def art(page, kind, x, y, variant):
    """Draw a labelled figure and return independent enclosing bounds."""
    r = fitz.Rect(x, y, x + 180, y + 90)
    if kind == 1:
        if variant == 0:
            # Apparatus diagram: beaker, funnel, stand.
            page.draw_rect((x + 20, y + 25, x + 70, y + 80))
            page.draw_line((x + 15, y + 80), (x + 85, y + 80))
            page.draw_polyline(
                [(x + 35, y + 5), (x + 55, y + 5), (x + 48, y + 25), (x + 42, y + 25)],
                closePath=True,
            )
            page.insert_text((x + 90, y + 55), "Beaker", fontsize=9)
        elif variant == 1:
            # Circuit diagram: cell, resistor, switch loop.
            page.draw_rect((x + 15, y + 15, x + 145, y + 75))
            page.draw_line((x + 75, y + 5), (x + 75, y + 25), width=1.5)
            page.draw_line((x + 83, y + 10), (x + 83, y + 20), width=1.5)
            page.draw_rect((x + 60, y + 68, x + 100, y + 82), fill=(0.9, 0.9, 0.9))
            page.insert_text((x + 152, y + 48), "6 V", fontsize=9)
        else:
            # Ray diagram: vertical lens + incident and refracted rays.
            page.draw_line((x + 80, y + 5), (x + 80, y + 85), width=1.2)
            page.draw_line((x + 10, y + 45), (x + 165, y + 45), width=0.5)
            page.draw_polyline([(x + 15, y + 20), (x + 80, y + 20), (x + 155, y + 65)])
            page.insert_text((x + 125, y + 20), "F", fontsize=9)
    elif kind in {2, 3}:
        with fitz.open() as source:
            p = source.new_page(width=180, height=90)
            p.draw_circle((70, 40), 28, color=(0, 0, 0), fill=(0.5, 0.7, 0.8))
            p.insert_text((110, 45), "IMAGE", fontsize=9)
            if kind == 3:
                # Raster + soft mask inside a form XObject, clipped by show_pdf_page.
                pix = p.get_pixmap(alpha=True)
                p.insert_image(p.rect, pixmap=pix)
                page.show_pdf_page(r, source, 0, clip=fitz.Rect(5, 5, 175, 85))
                if variant == 2:
                    # Additional arbitrary triangular vector clip path.
                    shape = page.new_shape()
                    shape.draw_polyline(
                        [(x + 10, y + 80), (x + 90, y + 10), (x + 170, y + 80)]
                    )
                    shape.finish(closePath=True, color=(0.1, 0.1, 0.1))
                    shape.commit()
            elif variant == 0:
                page.insert_image(r, stream=p.get_pixmap(alpha=False).tobytes("jpeg"))
            elif variant == 1:
                page.insert_image(r, pixmap=p.get_pixmap(alpha=True))
            else:
                page.insert_image(r, pixmap=p.get_pixmap(colorspace=fitz.csGRAY, alpha=False))
    elif kind == 4:
        for dx in range(0, 151, 30):
            page.draw_line((x + dx, y), (x + dx, y + 65), width=0.25)
            tick = f"{-1 + dx // 30}" if variant == 0 else f"{dx * 0.1:.1f}"
            page.insert_text((x + dx - 4, y + 77), tick, fontsize=8)
        for dy in range(0, 66, 13):
            page.draw_line((x, y + dy), (x + 150, y + dy), width=0.25)
        page.draw_polyline([(x, y + 60), (x + 30, y + 50), (x + 90, y + 15), (x + 150, y + 5)])
        page.insert_text((x + 145, y + 90), "Time / s", fontsize=9)
        page.insert_text((x + 190, y + 25), "Legend: current", fontsize=9)
        page.insert_text((x + 60, y + 105), "Axis title far from plot", fontsize=9)
        r = fitz.Rect(x - 6, y, x + 255, y + 108)
    elif kind == 5:
        if variant == 1:
            page.draw_circle((x + 50, y + 45), 40, fill=(0.82, 0.82, 0.82))
            page.draw_line((x + 50, y + 45), (x + 90, y + 45))
            page.draw_line((x + 50, y + 45), (x + 50, y + 5))
            page.draw_line((x + 50, y + 45), (x + 22, y + 73))
            page.insert_text((x + 62, y + 32), "25%", fontsize=8)
            page.insert_text((x + 26, y + 35), "50%", fontsize=8)
        else:
            for i in range(4):
                page.draw_rect(
                    (x + i * 35, y + 60 - i * 12, x + i * 35 + 20, y + 80), fill=(0.7, 0.7, 0.7)
                )
        page.insert_text((x + 140, y + 40), "Values", fontsize=9)
    elif kind == 6:
        if variant != 1:
            page.draw_rect(r)
            page.draw_rect((x, y, x + 180, y + 25), fill=(0.9, 0.9, 0.9))
            page.draw_line((x, y + 45), (x + 180, y + 45))
            page.draw_line((x + 90, y + (25 if variant == 2 else 0)), (x + 90, y + 90))
        for row in range(3):
            for col in range(2):
                page.insert_text(
                    (x + 12 + col * 90, y + 17 + row * 30), f"Cell {row}{col}", fontsize=9
                )
    elif kind == 7:
        page.draw_polyline(
            [(x + 15, y + 45), (x + 45, y + 25), (x + 75, y + 45), (x + 105, y + 25)]
        )
        page.draw_polyline(
            [(x + 45, y + 25), (x + 40, y + 65), (x + 50, y + 65)], closePath=True, fill=(0, 0, 0)
        )
        page.insert_text((x + 105, y + 25), "OH", fontsize=10)
        page.insert_text((x + 30, y + 85), "CH3", fontsize=10)
    elif kind == 8:
        if variant == 0:
            page.draw_polyline([(x, y + 75), (x + 80, y), (x + 160, y + 75)], closePath=True)
            page.draw_circle((x + 30, y + 65), 8)
            page.insert_text((x + 70, y + 88), "10 cm", fontsize=9)
        elif variant == 1:
            page.draw_line((x, y + 50), (x + 180, y + 50))
            for i in range(6):
                page.draw_line((x + i * 30, y + 45), (x + i * 30, y + 55))
                page.insert_text((x + i * 30, y + 70), str(i), fontsize=8)
        else:
            # Coordinate grid with axes and plotted points.
            for gx in range(0, 121, 20):
                page.draw_line((x + gx, y), (x + gx, y + 80), width=0.25)
            for gy in range(0, 81, 20):
                page.draw_line((x, y + gy), (x + 120, y + gy), width=0.25)
            page.draw_line((x + 60, y), (x + 60, y + 80), width=1.0)
            page.draw_line((x, y + 40), (x + 120, y + 40), width=1.0)
            page.draw_circle((x + 80, y + 20), 3, fill=(0, 0, 0))
            page.insert_text((x + 85, y + 18), "(1, 1)", fontsize=8)
    elif kind == 9:
        page.draw_circle((x + 50, y + 40), 25)
        page.draw_polyline([(x + 60, y + 30), (x + 190, y + 5), (x + 230, y + 5)])
        page.insert_text((x + 230, y + 8), "remote label", fontsize=9)
        r.x1 = x + 285
    elif kind == 10:
        for i, label in enumerate("ABCD"):
            if variant == 2:
                # True vertical stacked option diagrams with letter above-left.
                dx, dy = 0, i * 44
                page.insert_text((x + dx, y + dy + 16), label, fontsize=11)
                page.draw_circle((x + dx + 45, y + dy + 14), 14)
            else:
                dx, dy = (
                    (i * 90, 0)
                    if variant == 0
                    else ((i % 2) * 130, (i // 2) * 60)
                )
                page.insert_text((x + dx, y + dy), label, fontsize=11)
                page.draw_circle((x + dx + 25, y + dy + 25), 18)
        r = fitz.Rect(x - 2, y - 13, x + 320, y + (175 if variant == 2 else 113))
    else:
        page.draw_circle((x + 50, y + 45), 35)
        page.draw_line((x + 15, y + 45), (x + 140, y + 45))
        page.draw_rect((x + 110, y + 20, x + 165, y + 70))
        page.insert_text((x + 60, y + 85), "Fig. 1.1", fontsize=9)
        if kind == 12:
            page.draw_circle((x + 230, y + 45), 30)
            r.x1 = x + 262
        if kind == 15:
            page.insert_text((x + 155, y + 80), "ROTATED", rotate=90, fontsize=8)
    return tuple(r)


def make(kind):
    doc = fitz.open()
    specs = {}
    # Large/continuation/rotation cases use separate pages to keep ownership clear.
    separate = kind in {13, 15, 20}
    for i in range(3 if kind != 17 else 4):
        if i == 0 or separate:
            page = doc.new_page(width=600, height=900)
        x = 35 if kind != 17 or i < 2 else 335
        y = 70 + (i % 2 if kind == 17 else i) * 270 if not separate else 70
        if kind == 17:
            y = 70 + (i % 2) * 360
        if kind == 16 and i == 0:
            page.draw_rect(page.rect, fill=(0.95, 0.95, 0.95), overlay=False)
            page.draw_rect((8, 8, 592, 892), color=(0.6, 0.6, 0.6))
            page.insert_text((200, 450), "WATERMARK", fontsize=35, fill_opacity=0.15)
        if kind == 18 and i == 0:
            page.insert_text((180, 16), "EXAM HEADER", fontsize=10)
            page.insert_text((180, 888), "PAGE FOOTER 1", fontsize=10)
            page.draw_line((30, 23), (570, 23), width=0.25)
        before = {
            j: (len(p.get_text("words")), len(p.get_drawings()), len(p.get_image_info()))
            for j, p in enumerate(doc)
        }
        page.insert_text(
            (x, y), f"{i + 1} Question {i + 1} choose the correct answer.", fontsize=11
        )
        owned = [{"page": len(doc), "bbox": [x, y - 13, min(x + 260, 590), y + 4]}]
        opts_y = y + 210
        if kind == 11:
            opts_y = y + 30
        if kind == 20:
            if i == 0:
                r = fitz.Rect(80, 110, 470, 700)
                page.draw_rect(r)
                opts_y = 760
            else:
                r = fitz.Rect(100, 110, 115, 125)
                page.draw_circle(r.tl + (7, 7), 6)
        elif kind == 17:
            r = fitz.Rect(x + 30, y + 40, x + 170, y + 140)
            page.draw_rect(r)
        else:
            r = fitz.Rect(art(page, kind, x + 45, y + (65 if kind == 11 else 45), i))
        owned.append({"page": len(doc), "bbox": list(r)})
        if kind == 12:
            page.draw_circle((x + 260, y - 3), 2)
        if kind == 13 and i == 0:
            page.draw_rect((80, 780, 350, 890))
            owned.append({"page": len(doc), "bbox": [80, 780, 350, 890]})
            page = doc.new_page(width=600, height=900)
            page.draw_rect((80, 40, 350, 130))
            owned.append({"page": len(doc), "bbox": [80, 40, 350, 130]})
            opts_y = 180
        elif kind == 13 and i == 1:
            page = doc.new_page(width=600, height=900)
            opts_y = 80
        if kind != 10:
            for j, letter in enumerate("ABCD"):
                ox = x + j * (60 if kind == 17 else 100)
                page.insert_text((ox, opts_y), f"{letter} opt{letter}", fontsize=10)
                owned.append({"page": len(doc), "bbox": [ox, opts_y - 11, ox + 40, opts_y + 4]})
        if kind == 14 and i == 0:
            page.insert_text((80, 305), "Use the diagram to answer questions 2 and 3", fontsize=10)
        if kind == 19 and i == 0:
            page.draw_rect((80, 295, 240, 322))  # 6 pt before next header ink.
            owned.append({"page": len(doc), "bbox": [80, 295, 240, 322]})
        if kind == 15 and i == 0:
            page.set_rotation(90)
        owned = []
        for j, p in enumerate(doc):
            nw, nd, ni = before.get(j, (0, 0, 0))
            rects = [fitz.Rect(w[:4]) for w in p.get_text("words")[nw:]]
            rects += [fitz.Rect(d["rect"]) for d in p.get_drawings()[nd:]]
            rects += [fitz.Rect(image["bbox"]) for image in p.get_image_info()[ni:]]
            owned.extend({"page": j + 1, "bbox": list(r)} for r in rects if not r.is_empty)
        specs[str(i + 1)] = {
            "page": owned[0]["page"],
            "first_words": f"Question {i + 1}",
            "options_kind": "text",
            "must_contain_rects": owned,
        }
    return doc, {
        "category": kind,
        "section_counts": {"Unsectioned": len(specs)},
        "questions": specs,
        "expected_key": {n: "A" for n in specs},
        "review_expected": kind in {14, 16},
        "known_limit": (
            "Overlapping watermark requires a clean source; "
            "cannot safely erase underlying content."
        )
        if kind == 16
        else None,
    }


def generate():
    DEST.mkdir(parents=True, exist_ok=True)
    for kind, name in enumerate(NAMES, 1):
        doc, expected = make(kind)
        doc.save(DEST / f"{kind:02}-{name}.pdf", no_new_id=True, garbage=4, deflate=True)
        (DEST / f"{kind:02}-{name}.expected.json").write_text(json.dumps(expected, indent=2))
        if kind == 1:
            for dpi in (150, 300):
                pix = doc[0].get_pixmap(
                    matrix=fitz.Matrix(dpi / 72, dpi / 72).prerotate(1), colorspace=fitz.csGRAY
                )
                samples = bytearray(pix.samples)
                for j in range(len(samples)):
                    if samples[j] > 240:
                        samples[j] = 246 + (j * 17 % 9)
                    if j % pix.width < 9:
                        samples[j] = 60
                noisy = fitz.Pixmap(fitz.csGRAY, pix.width, pix.height, bytes(samples), False)
                image = noisy.tobytes("png" if dpi == 150 else "jpeg")
                stem = f"scan-{dpi}"
                (DEST / (stem + (".png" if dpi == 150 else ".jpg"))).write_bytes(image)
                with fitz.open() as scanned:
                    p = scanned.new_page(width=600, height=900)
                    p.insert_image(p.rect, stream=image)
                    scanned.save(DEST / f"{stem}.pdf", no_new_id=True, deflate=True)
                (DEST / f"{stem}.expected.json").write_text(
                    json.dumps({"scan": True, "dpi": dpi, "review_expected": True})
                )
        doc.close()


if __name__ == "__main__":
    generate()
