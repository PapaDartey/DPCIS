"""Remove only a verified source marker; see the question-number handoff contract."""

from __future__ import annotations

import math
import re
from statistics import median

import fitz


def numberless_text(text: str, number: int) -> str:
    """Remove the same source marker from PDF accessibility/fallback text."""
    return re.sub(
        rf"^\s*(?:(?:Q\.?|Question)\s*)?\(?{number}[.)]?(?:\s+|$)", "", text, count=1, flags=re.I
    ).strip()


def validate_number_bbox(box, crop: fitz.Rect) -> tuple[float, float, float, float]:
    try:
        values = tuple(float(value) for value in box)
        if len(values) != 4 or not all(math.isfinite(value) for value in values):
            raise ValueError
        rect = fitz.Rect(values)
        if (
            not rect.is_valid
            or rect.is_empty
            or not crop.contains(rect)
            or rect.width > min(150, crop.width * 0.4)
            or rect.height > min(48, crop.height * 0.25)
            or rect.y0 > crop.y0 + min(80, crop.height * 0.25)
        ):
            raise ValueError
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(
            "Select a small question-number area inside the top of the question crop."
        ) from exc
    return values


def find_question_number(page: fitz.Page, crop: fitz.Rect, number: int) -> tuple | None:
    """Conservative first-line marker detection; values in figures never qualify."""
    all_words = page.get_text("words")
    words = [w for w in all_words if crop.contains(fitz.Rect(w[:4]))]
    if not words or not 1 <= number <= 999:
        return None
    first_y = min(w[1] for w in words)
    line = sorted([w for w in words if abs(w[1] - first_y) < 5], key=lambda w: w[0])
    first = line[0]
    if first_y - crop.y0 > 60 or first[0] - crop.x0 > min(50, crop.width * 0.25):
        return None
    for length in (1, 2, 3):
        if len(line) <= length:
            continue
        prefix = " ".join(w[4] for w in line[:length])
        matched = re.fullmatch(r"(?:(?:Q\.?|Question)\s*)?\(?(\d{1,3})[.)]?", prefix, re.I)
        if not matched or int(matched[1]) != number:
            continue
        # If a plausible source header above the crop already carries this
        # number, a leading numeric value in the remaining stem is not a label.
        for earlier in all_words:
            if (
                earlier[3] >= first_y - 3
                or not 0 <= first[0] - earlier[0] < page.rect.width * 0.45
                or earlier[4].strip(".()") != str(number)
            ):
                continue
            if any(
                w[0] > earlier[2]
                and w[0] - earlier[2] < 40
                and abs(w[1] - earlier[1]) < 5
                and w[4][0].isalpha()
                and w[4].casefold() not in {"cm", "mm", "kg", "hz"}
                for w in all_words
            ):
                return None
        if any(
            w[0] < crop.x0 and abs(w[1] - first_y) < 5 and 0 <= first[0] - w[2] < 12
            for w in all_words
        ):
            return None  # The crop begins partway through the original header/stem.
        following = line[length]
        if (
            not following[4][0].isalpha()
            or len(following[4]) < 2
            or following[0] - line[length - 1][2] > 40
            or following[4].casefold() in {"cm", "mm", "kg", "hz", "and", "only"}
        ):
            continue
        rect = fitz.Rect(line[0][:4])
        for word in line[1:length]:
            rect |= fitz.Rect(word[:4])
        # A numeral inside a table/diagram is not an ordinary header marker.
        if any(
            rect.intersects(d["rect"])
            and d["rect"].width * d["rect"].height < page.rect.width * page.rect.height * 0.85
            and d["rect"].width > 0
            and d["rect"].height > 0
            for d in page.get_drawings()
        ):
            return None
        try:
            return validate_number_bbox(tuple(rect), crop)
        except ValueError:
            return None
    return None


def mask_png(data: bytes, clip: fitz.Rect, box, *, required: bool = False) -> bytes:
    """Mask a tiny rectangle in a copy; every pixel outside it remains identical."""
    if box is None or not clip.contains(fitz.Rect(box)):
        return data
    pix = fitz.Pixmap(data)
    scale_x, scale_y = pix.width / clip.width, pix.height / clip.height
    rect = fitz.Rect(box)
    x0 = max(0, math.floor((rect.x0 - clip.x0) * scale_x))
    y0 = max(0, math.floor((rect.y0 - clip.y0) * scale_y))
    x1 = min(pix.width, math.ceil((rect.x1 - clip.x0) * scale_x))
    y1 = min(pix.height, math.ceil((rect.y1 - clip.y0) * scale_y))
    if x1 <= x0 or y1 <= y0:
        return data
    left, right = max(0, x0 - 1), min(pix.width - 1, x1)
    top, bottom = max(0, y0 - 1), min(pix.height - 1, y1)
    border = [pix.pixel(x, y) for y in (top, bottom) for x in range(left, right + 1)]
    border += [pix.pixel(x, y) for x in (left, right) for y in range(top, bottom + 1)]
    color = tuple(int(median(pixel[c] for pixel in border)) for c in range(pix.n))
    uniform = sum(all(abs(pixel[c] - color[c]) <= 12 for c in range(pix.n)) for pixel in border)
    if min(color[:3]) < 160 or uniform < len(border) * 0.85:
        if required:
            raise ValueError(
                "The number area touches other content. Select just the printed number."
            )
        return data
    samples = pix.samples_mv
    row = bytes(color) * (x1 - x0)
    if all(
        samples[y * pix.stride + x0 * pix.n : y * pix.stride + x1 * pix.n] == row
        for y in range(y0, y1)
    ):
        return data
    pix.set_rect(fitz.IRect(x0, y0, x1, y1), color)
    return pix.tobytes("png")
