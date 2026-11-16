"""Coordinate-based PDF MCQ detection and faithful question crops.

Problem: selectable text loses diagrams and scientific notation. The source PDF
is authoritative for display; text is a secondary search and accessibility aid.
Headers must increase by one, occupy the main left text column, and have nearby
stem text. Repeated text in the same page band is excluded from crop bounds.
Scanning is O(words + pages * candidates); rendering cost tracks crop pixels.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from statistics import median
from typing import Any, cast

import fitz

from app.config import get_settings
from app.exams.pdf_coverage import coverage_warnings

MAX_PDF_BYTES = 100 * 1024 * 1024
MAX_PAGES = 200
RENDER_DPI = 220
PADDING = 8.0


def _pdf_limits() -> tuple[int, int, float, int]:
    settings = get_settings()
    return (
        settings.MAX_PDF_BYTES,
        settings.MAX_PDF_PAGES,
        settings.MAX_PDF_PAGE_DIMENSION_PT,
        settings.MAX_PDF_IMAGE_PIXELS,
    )


@dataclass(frozen=True)
class PdfRegion:
    page: int  # one-based
    bbox: tuple[float, float, float, float]


@dataclass
class PdfQuestion:
    number: int
    regions: list[PdfRegion] = field(default_factory=list)
    extracted_text: str = ""
    options_text: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    options_kind: str = "text"
    section: str | None = None
    crop_valid: bool = True


class OCRUnavailable(ValueError):
    """OCR could not run because optional software is unavailable."""


def validate_pdf(data: bytes) -> fitz.Document:
    max_bytes, max_pages, max_dim_pt, _ = _pdf_limits()
    if not data.startswith(b"%PDF-"):
        raise ValueError("The uploaded file is not a PDF.")
    if len(data) > max_bytes:
        raise ValueError("Choose a PDF up to 100 MB.")
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise ValueError("The PDF could not be opened.") from exc
    if doc.is_encrypted:
        doc.close()
        raise ValueError("Encrypted PDFs cannot be imported.")
    if not 1 <= len(doc) <= max_pages:
        doc.close()
        raise ValueError(f"The PDF must contain 1 to {max_pages} pages.")
    for page in doc:
        page.set_rotation(0)  # Canonical unrotated PDF-point coordinates for all crops.
        if page.rect.width > max_dim_pt or page.rect.height > max_dim_pt:
            doc.close()
            raise ValueError("PDF page dimensions exceed the maximum allowed size.")
    return doc


def open_question_upload(data: bytes) -> fitz.Document:
    """Normalize supported raster uploads to PDF using PyMuPDF alone."""
    max_bytes, _, _, max_pixels = _pdf_limits()
    if len(data) > max_bytes:
        raise ValueError("Choose a file up to 100 MB.")
    kind = (
        "png"
        if data.startswith(b"\x89PNG\r\n\x1a\n")
        else ("jpeg" if data.startswith(b"\xff\xd8\xff") else None)
    )
    if kind is None:
        return validate_pdf(data)
    try:
        with fitz.open(stream=data, filetype=kind) as image:
            if len(image) > 0:
                rect = image[0].rect
                if rect.width * rect.height > max_pixels:
                    raise ValueError("The uploaded image exceeds the maximum allowed pixel count.")
            return validate_pdf(image.convert_to_pdf())
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("The uploaded image could not be opened.") from exc


def detect_scan_questions(doc: fitz.Document) -> list[PdfQuestion]:
    """Split raster content at >=24 blank analysis rows, without OCR assumptions.

    Pure Python row traversal with C-level bytes.translate/count is O(pixels).
    Gaps are heuristics: numbers are provisional and require administrator review.
    Noisy/skewed pages fail closed as one editable page region, never disappear.
    """
    questions: list[PdfQuestion] = []
    table = bytes(1 if value < 200 else 0 for value in range(256))
    for page_index, page in enumerate(doc):
        pix = page.get_pixmap(dpi=120, colorspace=fitz.csGRAY, alpha=False)
        samples = pix.samples
        blank = [
            samples[y * pix.stride : y * pix.stride + pix.width].translate(table).count(1)
            <= pix.width * 0.003
            for y in range(pix.height)
        ]
        noisy = sum(blank) / len(blank) < 0.05
        runs: list[tuple[int, int]] = []
        start: int | None = None
        last_content = 0
        for y, is_blank in enumerate(blank):
            if not is_blank:
                if start is None:
                    start = y
                elif y - last_content - 1 >= 24:
                    runs.append((start, last_content + 1))
                    start = y
                last_content = y
        if start is not None:
            runs.append((start, last_content + 1))
        if noisy or not runs:
            runs = [(0, pix.height)]
        page_crops: list[tuple[int, fitz.Rect]] = []
        for first, last in runs:
            rect = fitz.Rect(
                0,
                max(0, first * page.rect.height / pix.height - PADDING),
                page.rect.width,
                min(page.rect.height, last * page.rect.height / pix.height + PADDING),
            )
            warnings = [
                "Scan mode: white-gap split; question numbers are provisional. Review boundaries."
            ]
            valid = not noisy and any(not row for row in blank)
            if not valid:
                warnings.append("Crop failed: needs manual crop (noisy, skewed, or blank page).")
            final = page.get_pixmap(clip=rect, dpi=RENDER_DPI, alpha=False)
            if not white_crop_border(final):
                valid = False
                warnings.append(
                    "Crop failed: non-white pixels touch the left/right "
                    "or top or bottom 2px border."
                )
            page_crops.append((len(questions), rect))
            questions.append(
                PdfQuestion(
                    number=len(questions) + 1,
                    regions=[PdfRegion(page_index + 1, tuple(rect))],
                    warnings=warnings,
                    crop_valid=valid,
                )
            )
        for q_idx, cov_warning in coverage_warnings(page, page_index + 1, page_crops, []):
            questions[q_idx].warnings.append(cov_warning)
    return questions


def repeated_bands(doc: fitz.Document) -> dict[int, list[tuple[float, float]]]:
    """Identify text repeated at approximately the same y on most pages."""
    occurrences: Counter[tuple[str, int]] = Counter()
    lines_by_page: list[list[tuple[str, float, float]]] = []
    for page in cast(Iterable[fitz.Page], doc):
        lines = []
        page_dict = cast(dict[str, Any], page.get_text("dict"))
        for block in page_dict["blocks"]:
            for line in block.get("lines", []):
                value = " ".join(span["text"].strip() for span in line["spans"]).strip()
                if value:
                    y0, y1 = float(line["bbox"][1]), float(line["bbox"][3])
                    lines.append((value, y0, y1))
        lines_by_page.append(lines)
        occurrences.update({(value.casefold(), round(y0 / 8)) for value, y0, _ in lines})
    threshold = max(2, (len(doc) + 1) // 2)
    return {
        index: [
            (y0 - 2, y1 + 2)
            for value, y0, y1 in lines
            if (
                y0 < 25
                or y1 > doc[index].rect.height - 25
                or (
                    occurrences[(value.casefold(), round(y0 / 8))] >= threshold
                    and (y0 < 80 or y1 > doc[index].rect.height - 80)
                )
            )
        ]
        for index, lines in enumerate(lines_by_page)
    }


def _excluded(y0: float, y1: float, bands: list[tuple[float, float]]) -> bool:
    return any(y0 >= top and y1 <= bottom for top, bottom in bands)


def _ordered_words(page: fitz.Page) -> list[tuple[Any, ...]]:
    """PDF stream order is not reading order, even within one page."""
    words = cast(list[tuple[Any, ...]], page.get_text("words"))
    return sorted(words, key=lambda w: (w[1], w[0]))


def _graphic_regions(
    page: fitz.Page,
    bands: list[tuple[float, float]] | None = None,
) -> list[fitz.Rect]:
    """Coalesce adjacent vector strokes into tables and drawings."""
    pieces = [fitz.Rect(item["rect"]) for item in page.get_drawings()]
    # Keep zero-area strokes here only to recognize table interiors for header
    # detection. Crop attribution uses nonempty graphic_boxes instead.
    pieces = [
        piece
        for piece in pieces
        if not (piece.width > page.rect.width * 0.9 and piece.height > page.rect.height * 0.9)
        and not _excluded(piece.y0, piece.y1, bands or [])
    ]
    groups: list[fitz.Rect] = []
    for piece in pieces:
        merged = piece
        remaining: list[fitz.Rect] = []
        for group in groups:
            if (group + (-1, -1, 1, 1)).intersects(merged + (-1, -1, 1, 1)):
                merged |= group
            else:
                remaining.append(group)
        groups = remaining + [merged]
    # A later stroke can join two previously separate groups.
    changed = True
    while changed:
        changed = False
        result: list[fitz.Rect] = []
        for group in groups:
            for index, previous in enumerate(result):
                if (previous + (-1, -1, 1, 1)).intersects(group + (-1, -1, 1, 1)):
                    result[index] |= group
                    changed = True
                    break
            else:
                result.append(group)
        groups = result
    return [group for group in groups if group.width >= 25 and group.height >= 18]


def _inside_graphic(word: tuple, regions: list[fitz.Rect]) -> bool:
    centre = fitz.Point((word[0] + word[2]) / 2, (word[1] + word[3]) / 2)
    return any(region.contains(centre) for region in regions)


def graphic_boxes(page: fitz.Page, bands: list[tuple[float, float]]) -> list[fitz.Rect]:
    """Keep actual vector/image bounds; exclude backgrounds and repeated bands."""
    boxes = []
    for item in page.get_drawings():
        box = fitz.Rect(item["rect"])
        if box.is_empty:
            half = max(0.125, float(item.get("width", 1)) / 2)
            box += (-half, -half, half, half)
        boxes.append(box)
    boxes.extend(fitz.Rect(item["bbox"]) for item in page.get_image_info())
    return [
        box
        for box in boxes
        if not box.is_empty
        and not box.is_infinite
        and not (box.width > page.rect.width * 0.9 and box.height > page.rect.height * 0.9)
        and not _excluded(box.y0, box.y1, bands)
    ]


def _border_background_uniform(pix: fitz.Pixmap, tol: int = 8) -> bool:
    """Verify border pixels match a light uniform background with no ink."""
    if pix.width <= 0 or pix.height <= 0 or pix.n <= 0:
        return False
    data = pix.samples
    n = pix.n
    h_rows = min(2, pix.height)
    edge_px = min(2, pix.width)
    edge = edge_px * n
    row_bytes = pix.width * n
    # Sample top, bottom, left, right border pixels for median background color.
    samples: list[list[int]] = [[] for _ in range(n)]
    step = max(1, pix.width // 16)
    for y in list(range(h_rows)) + list(range(max(0, pix.height - h_rows), pix.height)):
        base = y * pix.stride
        for x in range(0, pix.width, step):
            off = base + x * n
            for c in range(n):
                samples[c].append(data[off + c])
    bg = [sorted(ch)[len(ch) // 2] for ch in samples]
    # Pure-white pages keep strict 255 checking; dark borders indicate ink.
    if min(bg) >= 252 or min(bg) < 180:
        return False
    for y in range(h_rows):
        row = data[y * pix.stride : y * pix.stride + row_bytes]
        for i in range(0, len(row), n):
            if any(abs(row[i + c] - bg[c]) > tol for c in range(n)):
                return False
    for y in range(max(0, pix.height - h_rows), pix.height):
        row = data[y * pix.stride : y * pix.stride + row_bytes]
        for i in range(0, len(row), n):
            if any(abs(row[i + c] - bg[c]) > tol for c in range(n)):
                return False
    for y in range(pix.height):
        base = y * pix.stride
        left = data[base : base + edge]
        right = data[base + row_bytes - edge : base + row_bytes]
        for chunk in (left, right):
            for i in range(0, len(chunk), n):
                if any(abs(chunk[i + c] - bg[c]) > tol for c in range(n)):
                    return False
    return True


def white_horizontal_border(pix: fitz.Pixmap) -> bool:
    """Require every channel of the first/last two pixel rows to be white."""
    data = pix.samples
    size = min(2, pix.height) * pix.stride
    return all(value == 255 for value in data[:size]) and all(
        value == 255 for value in data[-size:]
    )


def white_crop_border(pix: fitz.Pixmap) -> bool:
    """All four two-pixel borders: strict white on white pages, uniform on tinted pages."""
    if white_horizontal_border(pix):
        data = pix.samples
        edge = min(2, pix.width) * pix.n
        white = b"\xff" * edge
        if all(
            data[y * pix.stride : y * pix.stride + edge] == white
            and data[(y + 1) * pix.stride - edge : (y + 1) * pix.stride] == white
            for y in range(pix.height)
        ):
            return True
    return _border_background_uniform(pix)


def graphics_crop(
    page: fitz.Page,
    words: list[tuple],
    boxes: list[fitz.Rect],
    top: float,
    bottom: float,
    x0: float,
    x1: float,
    next_top: float | None,
) -> tuple[fitz.Rect | None, list[tuple], list[str]]:
    """Grow a question interval monotonically to a fixed point, then union content.

    At most G passes; list membership bounds worst-case work at O(G**3 + W).
    A graphic extending into the next text interval is ambiguous and fails closed.
    Padding is applied only after attribution; no graphic may be partly clipped.
    Empty regions are omitted. Columns constrain attribution, not the final guard.
    """
    warnings: list[str] = []
    admitted: list[fitz.Rect] = []
    candidates = [box for box in boxes if box.x0 < x1 and box.x1 > x0]
    while True:
        previous = bottom
        for box in candidates:
            if box in admitted or not top <= box.y0 < bottom:
                continue
            admitted.append(box)
            if next_top is not None and box.y1 >= next_top:
                warnings.append(
                    f"Crop failed: graphic {tuple(box)} overlaps the next question text."
                )
            else:
                bottom = max(bottom, box.y1)
        if bottom == previous:
            break
    selected = [w for w in words if w[1] >= top and w[3] <= bottom]
    content = [fitz.Rect(w[:4]) for w in selected] + admitted
    if not content:
        return None, selected, warnings
    rect = fitz.Rect(content[0])
    for box in content[1:]:
        rect |= box
    rect = (rect + (-PADDING, -PADDING, PADDING, PADDING)) & page.rect
    # Keep a failed preview inside its question interval, without hiding the failure.
    if next_top is not None:
        rect.y1 = min(rect.y1, next_top)
    rect.x0, rect.x1 = max(rect.x0, x0), min(rect.x1, x1)
    # Tight spacing: shrink only whitespace before the first owned word, never ink.
    first_word = min((w[1] for w in selected), default=top)
    for box in boxes:
        if box.y0 < top and box.y1 < first_word and box.x0 < rect.x1 and box.x1 > rect.x0:
            rect.y0 = max(rect.y0, box.y1 + 1)
    for box in boxes:
        if box.intersects(rect) and not rect.contains(box):
            warnings.append(f"Crop failed: partially clipped graphic {tuple(box)}.")
    pix = page.get_pixmap(clip=rect, dpi=RENDER_DPI, alpha=False)
    if not white_crop_border(pix):
        warnings.append(
            "Crop failed: non-white pixels touch the left/right or top or bottom 2px border."
        )
    return rect, selected, warnings


def detect_pdf_questions(doc: fitz.Document) -> list[PdfQuestion]:
    for page in doc:
        page.set_rotation(0)
    pages = list(cast(Iterable[fitz.Page], doc))
    bands = repeated_bands(doc)
    graphics = {index: _graphic_regions(page, bands[index]) for index, page in enumerate(pages)}
    boxes = {index: graphic_boxes(page, bands[index]) for index, page in enumerate(pages)}
    headers: list[tuple[int, int, float, int]] = []
    columns_by_page: dict[int, bool] = {}
    expected = 1
    for page_index, page in enumerate(pages):
        words = _ordered_words(page)
        numeric = [
            w
            for w in words
            if re.fullmatch(r"\d{1,3}", w[4])
            and not _excluded(w[1], w[3], bands[page_index])
            and not _inside_graphic(w, graphics[page_index])
        ]
        right_candidates = [
            w for w in numeric if page.rect.width * 0.45 <= w[0] < page.rect.width * 0.7
        ]
        right = min((w[0] for w in right_candidates), default=0)
        # Require two plausible numbered headers in the right column before
        # treating a page as two-column; isolated numeric table cells do not qualify.
        right_header_numbers = {
            int(w[4])
            for w in right_candidates
            if abs(w[0] - right) <= 22
            and any(
                other[0] > w[2]
                and other[0] - w[2] < 35
                and abs(other[1] - w[1]) < 7
                and other[4][0].isalpha()
                for other in words
            )
        }
        two_columns = sum(n >= expected for n in right_header_numbers) >= 2
        columns_by_page[page_index] = two_columns
        for column in (0, 1) if two_columns else (0,):
            candidates = [
                w
                for w in numeric
                if (
                    page.rect.width * 0.45 <= w[0] < page.rect.width * 0.7
                    if column
                    else w[0] < page.rect.width * 0.3
                )
            ]
            for word in sorted(candidates, key=lambda w: w[1]):
                if word[4] != str(expected):
                    continue
                nearby = [
                    w
                    for w in words
                    if w[0] > word[2] and 0 <= w[0] - word[2] < 35 and abs(w[1] - word[1]) < 7
                ]
                if (
                    not nearby
                    or not nearby[0][4][0].isalpha()
                    or nearby[0][4].casefold() in {"and", "only"}
                ):
                    continue
                headers.append((expected, page_index, float(word[1]), column))
                expected += 1
    questions: list[PdfQuestion] = []
    for index, (number, start_page, start_y, start_column) in enumerate(headers):
        next_page, next_y, next_column = (
            (headers[index + 1][1], headers[index + 1][2], headers[index + 1][3])
            if index + 1 < len(headers)
            else (len(doc), 0.0, 0)
        )
        question = PdfQuestion(number=number)
        option_labels: list[tuple[int, tuple]] = []
        for word in _ordered_words(doc[start_page]):
            if word[1] >= start_y:
                break
            if word[4].casefold() == "paper":
                same_line = [
                    other
                    for other in _ordered_words(doc[start_page])
                    if other[0] > word[2] and abs(other[1] - word[1]) < 5
                ]
                if same_line and same_line[0][4].isdigit():
                    question.section = f"Paper {same_line[0][4]}"
        if question.section is None and questions:
            question.section = questions[-1].section
        text_parts: list[str] = []
        for page_index in range(start_page, min(next_page + 1, len(doc))):
            page = doc[page_index]
            if (
                page_index > start_page
                and len(question.options_text) == 4
                and question.regions
                and question.regions[-1].bbox[3] < doc[page_index - 1].rect.height - 80
            ):
                break
            if page_index == next_page and next_y <= 0:
                break
            column = start_column if page_index == start_page else 0
            x0, x1 = (
                ((page.rect.width / 2, page.rect.width) if column else (0, page.rect.width / 2))
                if columns_by_page.get(page_index)
                else (0, page.rect.width)
            )
            words = [
                w
                for w in _ordered_words(page)
                if x0 <= w[0]
                and w[2] <= x1
                and w[1] >= 20
                and not _excluded(w[1], w[3], bands[page_index])
            ]
            top = max(0.0, start_y - PADDING) if page_index == start_page else 25.0
            bottom_limit = (
                next_y - PADDING
                if page_index == next_page and column == next_column
                else page.rect.height
            )
            rect, selected, crop_warnings = graphics_crop(
                page,
                words,
                boxes[page_index],
                top,
                bottom_limit,
                x0,
                x1,
                next_y if page_index == next_page and column == next_column else None,
            )
            question.warnings.extend(crop_warnings)
            question.crop_valid = question.crop_valid and not crop_warnings
            if rect is None:
                continue
            question.regions.append(PdfRegion(page_index + 1, tuple(rect)))
            text_parts.extend(w[4] for w in sorted(selected, key=lambda w: (round(w[1] / 3), w[0])))
            line_groups: dict[tuple[int, int], list[tuple]] = {}
            for word in selected:
                line_groups.setdefault((word[5], word[6]), []).append(word)
            for line_words in line_groups.values():
                ordered = sorted(line_words, key=lambda w: w[0])
                for word_index, word in enumerate(ordered):
                    label = word[4].strip(".()")
                    if label not in {"A", "B", "C", "D"}:
                        continue
                    option_labels.append((page_index, word))
                    if _inside_graphic(word, graphics[page_index]):
                        continue
                    following = []
                    for next_word in ordered[word_index + 1 :]:
                        if next_word[4].strip(".()") in {"A", "B", "C", "D"}:
                            break
                        following.append(next_word[4])
                    question.options_text.setdefault(label, " ".join(following))
        graphic_labels = [
            (page_index, word, region)
            for page_index, word in option_labels
            for region in graphics[page_index]
            if _inside_graphic(word, [region])
        ]
        if graphic_labels:
            question.options_kind = (
                "image" if any(region.width > 250 for _, _, region in graphic_labels) else "table"
            )
        elif option_labels:
            if any(
                sum(
                    region.width > 40 and region.height > 35 and 0 <= region.y0 - word[1] < 55
                    for region in graphics[page_index]
                )
                >= 4
                for page_index, word in option_labels
            ):
                question.options_kind = "image"
            else:
                line_labels: dict[tuple[int, int], set[str]] = {}
                for page_index, word in option_labels:
                    line_labels.setdefault((page_index, round(word[1] / 4)), set()).add(word[4])
                if any(len(labels) >= 2 for labels in line_labels.values()):
                    question.options_kind = "inline_row"
        question.extracted_text = " ".join(text_parts)
        if not question.options_text:
            question.warnings.append("No option letters detected; review the crop.")
        if any(region.bbox[3] - region.bbox[1] < 45 for region in question.regions):
            question.warnings.append("Short crop; review the boundary.")
        if any(region.bbox[3] - region.bbox[1] > 650 for region in question.regions):
            question.warnings.append("Tall crop; review the boundary.")
        questions.append(question)
    audit_question_crops(doc, questions, bands)
    return questions


def audit_question_crops(doc, questions, bands=None):
    """Independent raster safety net. Review warnings never silently disappear."""
    bands = repeated_bands(doc) if bands is None else bands
    heights = [r.bbox[3] - r.bbox[1] for q in questions for r in q.regions]
    typical = median(heights) if heights else 0
    for page_index, page in enumerate(doc):
        crops = [
            (i, fitz.Rect(r.bbox))
            for i, q in enumerate(questions)
            for r in q.regions
            if r.page == page_index + 1
        ]
        if not crops and questions:
            # Give an otherwise orphan page a visible editable recovery region.
            questions[-1].regions.append(PdfRegion(page_index + 1, tuple(page.rect)))
            questions[-1].warnings.append(
                f"Needs review: no assigned question on page {page_index + 1}; "
                "inspect the full-page region."
            )
            crops = [(len(questions) - 1, page.rect)]
        for i, warning in coverage_warnings(page, page_index + 1, crops, bands[page_index]):
            questions[i].warnings.append(warning)
        shared = re.search(
            r"(?:questions|question)\s+\d+\s+(?:and|to|[--])\s*\d+", page.get_text(), re.I
        )
        if shared:
            for i, _ in crops:
                questions[i].warnings.append(
                    "Needs review: shared stimulus refers to several questions; "
                    "include it in each relevant crop."
                )
        for i, rect in crops:
            q = questions[i]
            if typical and (rect.height < typical * 0.25 or rect.height > typical * 2.5):
                q.warnings.append("Needs review: crop height is outside 25%-250% of the median.")
            if not page.get_text(clip=rect).strip() and not any(
                b.intersects(rect) for b in graphic_boxes(page, bands[page_index])
            ):
                q.warnings.append("Needs review: crop contains no detected text or graphics.")
            has_watermark = any(
                span.get("size", 0) >= 28 or "watermark" in span.get("text", "").lower()
                for block in page.get_text("dict", clip=rect).get("blocks", [])
                if block.get("type") == 0
                for line in block.get("lines", [])
                for span in line.get("spans", [])
            )
            if has_watermark:
                q.warnings.append(
                    "Needs review: background watermark or large overlay text overlaps this crop."
                )
            if not white_crop_border(page.get_pixmap(clip=rect, dpi=RENDER_DPI, alpha=False)):
                message = "Crop failed: ink touches a left/right or top or bottom 2px border."
                if message not in q.warnings:
                    q.warnings.append(message)
                q.crop_valid = False


def render_region(doc: fitz.Document, region: PdfRegion) -> bytes:
    page = doc[region.page - 1]
    return page.get_pixmap(clip=fitz.Rect(region.bbox), dpi=RENDER_DPI, alpha=False).tobytes("png")


def detect_questions_with_ocr(doc: fitz.Document) -> list[PdfQuestion]:
    """Build a temporary coordinate text layer from Tesseract over source pages."""
    try:
        import pytesseract  # type: ignore[import-not-found]
        from PIL import Image  # type: ignore[import-not-found]
    except ImportError as exc:
        raise OCRUnavailable(
            "OCR is needed for this PDF. Install optional pytesseract and Pillow plus Tesseract."
        ) from exc
    searchable = fitz.open()
    try:
        for source_page in doc:
            page = searchable.new_page(width=source_page.rect.width, height=source_page.rect.height)
            pix = source_page.get_pixmap(dpi=200, alpha=False)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            try:
                data = pytesseract.image_to_data(
                    image, output_type=pytesseract.Output.DICT, config="--psm 6"
                )
            except pytesseract.TesseractNotFoundError as exc:
                raise OCRUnavailable(
                    "OCR is needed for this PDF, but the Tesseract executable is not installed."
                ) from exc
            except RuntimeError as exc:
                raise OCRUnavailable(
                    "OCR could not process this PDF; review the scan quality."
                ) from exc
            scale_x = source_page.rect.width / pix.width
            scale_y = source_page.rect.height / pix.height
            for index, raw in enumerate(data["text"]):
                word = raw.strip()
                if not word or float(data["conf"][index]) < 20:
                    continue
                x = float(data["left"][index]) * scale_x
                y = float(data["top"][index]) * scale_y
                height = float(data["height"][index]) * scale_y
                page.insert_text((x, y + height), word, fontsize=max(5, min(height, 16)))
        questions = detect_pdf_questions(searchable)
        for question in questions:
            question.warnings.append("OCR used; review text and crop boundaries carefully.")
        return questions
    finally:
        searchable.close()
