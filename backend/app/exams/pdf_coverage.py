"""Independent, bounded raster coverage audit (PyMuPDF + standard library).

At 100 DPI, threshold grayscale <235. Horizontal runs are connected across
adjacent rows (8-connectivity) with union/find: O(pixels + runs alpha(runs)).
Only explicitly detected margin bands are masked. Broad background/watermark
pixels are NOT erased by their bounding box: that could hide real content.
Meaningful components have >80 dark pixels or both dimensions >=12 px.
Coverage means one crop contains the entire component, not merely its centre.
Small isolated marks below these thresholds and white/very pale art remain a
known limit; no raster threshold is a proof of semantic question ownership.
"""

from __future__ import annotations

import base64
import re
import time
from dataclasses import dataclass

import fitz

MAX_RUNS_PER_PAGE = 6000
MAX_THUMBNAILS_PER_PAGE = 5
MAX_WARNINGS_PER_PAGE = 8
MAX_SECONDS_PER_PAGE = 0.75


@dataclass
class InkRegion:
    rect: fitz.Rect
    pixels: int


def ink_regions(page: fitz.Page, bands: list[tuple[float, float]]) -> list[InkRegion]:
    pix = page.get_pixmap(dpi=100, colorspace=fitz.csGRAY, alpha=False)
    data = pix.samples
    scale = 100 / 72
    table = bytes(1 if v < 235 else 0 for v in range(256))
    parents: list[int] = []
    bounds: list[list[int]] = []
    counts: list[int] = []

    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    previous = []
    deadline = time.monotonic() + MAX_SECONDS_PER_PAGE
    for y in range(pix.height):
        if (y & 31) == 0 and (time.monotonic() > deadline or len(parents) > MAX_RUNS_PER_PAGE):
            break
        if any(lo <= y / scale <= hi for lo, hi in bands):
            previous = []
            continue
        row = data[y * pix.stride : y * pix.stride + pix.width].translate(table)
        current = []
        cursor = 0
        for match in re.finditer(b"\x01+", row):
            x0, x1 = match.span()
            label = len(parents)
            parents.append(label)
            bounds.append([x0, y, x1, y + 1])
            counts.append(x1 - x0)
            while cursor < len(previous) and previous[cursor][1] < x0:
                cursor += 1
            j = cursor
            while j < len(previous) and previous[j][0] <= x1:
                prior = root(previous[j][2])
                label = root(label)
                if prior != label:
                    parents[prior] = label
                    a, b = bounds[label], bounds[prior]
                    a[:] = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]
                    counts[label] += counts[prior]
                j += 1
            current.append((x0, x1, label))
        previous = current
    page_w, page_h = page.rect.width, page.rect.height
    regions = []
    for i in range(len(parents)):
        if root(i) != i:
            continue
        if not (
            counts[i] > 80
            or (bounds[i][2] - bounds[i][0] >= 12 and bounds[i][3] - bounds[i][1] >= 12)
        ):
            continue
        rect = fitz.Rect(*(v / scale for v in bounds[i]))
        # Skip known page-frame decorations and header/footer rules near outer margins.
        if rect.width > page_w * 0.88 and rect.height > page_h * 0.88:
            continue
        if (
            (rect.y1 < 45 or rect.y0 > page_h - 45)
            and rect.height <= 3
            and rect.width > page_w * 0.5
        ):
            continue
        regions.append(InkRegion(rect, counts[i]))
    return regions


def coverage_warnings(page, page_number, crops, bands):
    """Return (nearest question index, warning) pairs, including bounded thumbnails."""
    warnings = []
    if not crops:
        return warnings
    thumb_count = 0
    for ink in ink_regions(page, bands):
        # One analysis pixel tolerance for raster rounding, not missing artwork.
        if any((rect + (-0.72, -0.72, 0.72, 0.72)).contains(ink.rect) for _, rect in crops):
            continue
        if len(warnings) >= MAX_WARNINGS_PER_PAGE:
            break
        centre = (ink.rect.tl + ink.rect.br) / 2
        index, _ = min(
            crops,
            key=lambda item: (
                max(item[1].x0 - centre.x, 0, centre.x - item[1].x1) ** 2
                + max(item[1].y0 - centre.y, 0, centre.y - item[1].y1) ** 2
            ),
        )
        rect = ink.rect
        message = (
            f"Needs review: Unassigned content on page {page_number} at "
            f"({rect.x0:.1f}, {rect.y0:.1f}, {rect.width:.1f}, {rect.height:.1f})"
        )
        if thumb_count < MAX_THUMBNAILS_PER_PAGE:
            # Existing preview warning strings carry the thumbnail without new routes.
            clip = (rect + (-3, -3, 3, 3)) & page.rect
            zoom = min(1, 160 / max(clip.width, clip.height))
            thumbnail = page.get_pixmap(clip=clip, matrix=fitz.Matrix(zoom, zoom), alpha=False)
            message += (
                "\nthumbnail:data:image/png;base64,"
                + base64.b64encode(thumbnail.tobytes("png")).decode()
            )
            thumb_count += 1
        warnings.append((index, message))
    return warnings
