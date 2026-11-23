"""Separate immutable PDF stem/answer assets after explicit draft review.

See docs/handoffs/pdf-option-separation.md for invariants, edge cases, complexity
and tests. Detection is a conservative suggestion, never approval. Ambiguous
labels/scans require manual regions. Raster assets preserve source notation.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Literal
from uuid import UUID

import fitz
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat

from app.config import get_settings
from app.exams.pdf_import import white_crop_border
from app.exams.pdf_question_numbers import find_question_number, mask_png
from app.exams.pdf_storage import source_dir


class LayoutRegion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page: int = Field(ge=1, strict=True)
    bbox: tuple[FiniteFloat, FiniteFloat, FiniteFloat, FiniteFloat]


class LayoutOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: Literal["A", "B", "C", "D"]
    mode: Literal["image", "text"] = "image"
    option_text: str = Field(default="", max_length=5000)
    regions: list[LayoutRegion] = Field(min_length=1, max_length=20)


class LayoutInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stem: list[LayoutRegion] = Field(min_length=1, max_length=20)
    options: list[LayoutOption] = Field(min_length=2, max_length=4)


def signature(question) -> str:
    """Only source, crop and display content determine a reusable layout."""
    content = [
        str(question.source_file_id),
        question.source_number,
        question.question_text,
        json.loads(question.image_regions or "[]"),
        [(o.label, o.option_text) for o in sorted(question.options, key=lambda o: o.position)],
    ]
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


def fingerprint(question) -> str:
    content = [
        signature(question),
        str(question.id),
        str(question.updated_at),
        str(question.points),
        [(str(o.id), o.is_correct) for o in sorted(question.options, key=lambda o: o.position)],
    ]
    return hashlib.sha256(json.dumps(content).encode()).hexdigest()


def confirmed_layout(question) -> dict | None:
    """Fail back to the original full image when authoring/crop metadata changes."""
    if not question.source_file_id or not question.option_layout:
        return None
    try:
        saved = json.loads(question.option_layout)
        UUID(saved["preview_id"])
        LayoutInput.model_validate(saved["layout"])
        if saved["signature"] != signature(question):
            return None
        if saved["source_id"] != str(question.source_file_id):
            return None
        if saved["source_number"] != question.source_number:
            return None
        return saved
    except (KeyError, TypeError, ValueError):
        return None


def layout_directory(source_id: UUID, preview_id: UUID) -> Path:
    return source_dir(source_id) / "option-layouts" / str(preview_id)


def asset_bytes(source_id: UUID, preview_id: UUID, part: str, index: int) -> bytes:
    if part not in {"stem", "A", "B", "C", "D"} or not 0 <= index < 20:
        raise FileNotFoundError("Image not found")
    return (layout_directory(source_id, preview_id) / f"{part}-{index}.png").read_bytes()


def public_layout(question, saved: dict | None = None) -> dict | None:
    saved = saved or confirmed_layout(question)
    if saved is None:
        return None
    prefix = (
        f"/api/admin/exams/{question.exam_id}/questions/{question.id}"
        f"/option-layout/assets/{saved['preview_id']}"
    )
    layout = saved["layout"]
    return {
        **layout,
        "stem_urls": [f"{prefix}/stem/{i}" for i in range(len(layout["stem"]))],
        "options": [
            {**o, "image_urls": [f"{prefix}/{o['label']}/{i}" for i in range(len(o["regions"]))]}
            for o in layout["options"]
        ],
    }


def option_assets(question, option) -> list[str]:
    saved = confirmed_layout(question)
    if not saved:
        return []
    item = next(o for o in saved["layout"]["options"] if o["label"] == option.label)
    return [str(i) for i in range(len(item["regions"]))] if item["mode"] == "image" else []


def _anchors(doc: fitz.Document, regions: list[dict], labels: list[str]) -> list[tuple] | None:
    if len(regions) != 1 or labels != ["A", "B", "C", "D"]:
        return None
    region = regions[0]
    bounds = fitz.Rect(region["bbox"])
    words = doc[region["page"] - 1].get_text("words", sort=True)
    found = [
        word
        for word in words
        if re.fullmatch(r"[ABCD][.)]?", word[4]) and bounds.contains(fitz.Rect(word[:4]))
    ]
    if len(found) != 4 or {w[4].rstrip(".)") for w in found} != set(labels):
        return None
    by_y = sorted(found, key=lambda w: (round(w[1] / 5), w[0]))
    if [w[4].rstrip(".)") for w in by_y] != labels:
        return None
    vertical = max(w[0] for w in found) - min(w[0] for w in found) < 20
    horizontal = max(w[1] for w in found) - min(w[1] for w in found) < 5
    return by_y if vertical or horizontal else None


def suggest_layout(doc: fitz.Document, question) -> tuple[LayoutInput, list[str]]:
    regions = [
        {"page": region["page"], "bbox": region["bbox"]}
        for region in json.loads(question.image_regions or "[]")
    ]
    labels = [o.label for o in sorted(question.options, key=lambda o: o.position)]
    texts = json.loads(question.pdf_options_text or "{}")
    saved = confirmed_layout(question)
    if saved:
        return LayoutInput.model_validate(saved["layout"]), []
    fallback = LayoutInput(
        stem=regions,
        options=[
            LayoutOption(label=label, regions=regions, option_text=texts.get(label, ""))
            for label in labels
        ],
    )
    anchors = _anchors(doc, regions, labels)
    if anchors is None:
        return fallback, ["Answer boundaries need review. Draw the question and each answer crop."]
    region = regions[0]
    bounds = fitz.Rect(region["bbox"])
    page = doc[region["page"] - 1]
    stem = LayoutRegion(
        page=region["page"], bbox=(bounds.x0, bounds.y0, bounds.x1, anchors[0][1] - 5)
    )
    horizontal = max(w[1] for w in anchors) - min(w[1] for w in anchors) < 5
    words = page.get_text("words", sort=True)
    options = []
    for index, anchor in enumerate(anchors):
        label = labels[index]
        if horizontal:
            right = anchors[index + 1][0] - 4 if index < 3 else bounds.x1
            inline = any(
                w[0] > anchor[2] and w[2] < right and abs(w[1] - anchor[1]) < 5 for w in words
            )
            box = (
                (anchor[2] + 3, anchor[1] - 3, right, bounds.y1)
                if inline
                else (max(bounds.x0, anchor[0] - 3), anchor[3] + 3, right, bounds.y1)
            )
        else:
            bottom = anchors[index + 1][1] - 4 if index < 3 else bounds.y1
            box = (anchor[2] + 3, anchor[1] - 3, bounds.x1, bottom)
        options.append(
            LayoutOption(
                label=label,
                option_text=" ".join(page.get_text("text", clip=fitz.Rect(box)).split())
                or texts.get(label, ""),
                regions=[LayoutRegion(page=region["page"], bbox=box)],
            )
        )
    return LayoutInput(stem=[stem], options=options), []


def validate_text(layout: LayoutInput) -> None:
    texts = [" ".join(o.option_text.split()).casefold() for o in layout.options]
    if any(not text for text in texts) or len(set(texts)) != len(texts):
        raise ValueError(
            "Give each answer its own text or distinct image description before confirming."
        )
    if any(re.fullmatch(r"option [a-d] \(see image\)", text) for text in texts):
        raise ValueError("Replace the old answer placeholders with text or image descriptions.")


def render_layout(doc: fitz.Document, question, layout: LayoutInput) -> dict[str, bytes]:
    """Validate all geometry before returning PNGs; callers write only after success."""
    labels = [o.label for o in sorted(question.options, key=lambda o: o.position)]
    if [o.label for o in layout.options] != labels:
        raise ValueError("Include each existing answer once, in its original letter order.")
    original = json.loads(question.image_regions or "[]")
    all_regions = [("stem", r) for r in layout.stem] + [
        (o.label, r) for o in layout.options for r in o.regions
    ]
    rectangles: list[tuple[str, int, fitz.Rect]] = []
    dpi = min(220, get_settings().MAX_PDF_RENDER_DPI)
    pixel_count = 0.0
    anchors = _anchors(doc, original, labels)
    for part, region in all_regions:
        rect = fitz.Rect(region.bbox)
        if region.page > len(doc) or rect.width < 5 or rect.height < 4 or not rect.is_valid:
            raise ValueError("Every crop needs a valid page and a visible area.")
        if not any(
            r["page"] == region.page and fitz.Rect(r["bbox"]).contains(rect) for r in original
        ):
            raise ValueError("Keep every crop inside the original question boundary.")
        if anchors and any(rect.intersects(fitz.Rect(w[:4])) for w in anchors):
            raise ValueError("Exclude the original printed answer letters from every crop.")
        if any(page == region.page and rect.intersects(other) for _, page, other in rectangles):
            raise ValueError("Question and answer crops must not overlap.")
        rectangles.append((part, region.page, rect))
        pixel_count += rect.width * rect.height * (dpi / 72) ** 2
    if pixel_count > get_settings().MAX_PDF_IMAGE_PIXELS:
        raise ValueError("The selected crops exceed the image size limit.")
    result: dict[str, bytes] = {}
    counts: dict[str, int] = {}
    for part, page, rect in rectangles:
        pix = doc[page - 1].get_pixmap(clip=rect, dpi=dpi, alpha=False)
        gray = fitz.Pixmap(fitz.csGRAY, pix)
        if not any(value < 210 for value in gray.samples):
            raise ValueError(f"The {part} crop is blank. Adjust it before previewing.")
        if not white_crop_border(pix):
            raise ValueError(f"Content touches the {part} crop edge. Leave a clear margin.")
        if part != "stem":
            # Remove only empty outer space so a short answer is readable on
            # mobile; the validated PDF region remains the editable source.
            table = bytes(1 if value < 245 else 0 for value in range(256))
            samples = gray.samples
            ink_rows = []
            for row in range(gray.height):
                values = samples[row * gray.stride : row * gray.stride + gray.width].translate(
                    table
                )
                first = values.find(b"\x01")
                if first >= 0:
                    ink_rows.append((row, first, values.rfind(b"\x01")))
            if ink_rows:
                scale = 72 / dpi
                tight = fitz.Rect(
                    max(rect.x0, rect.x0 + min(r[1] for r in ink_rows) * scale - 3),
                    max(rect.y0, rect.y0 + ink_rows[0][0] * scale - 3),
                    min(rect.x1, rect.x0 + (max(r[2] for r in ink_rows) + 1) * scale + 3),
                    min(rect.y1, rect.y0 + (ink_rows[-1][0] + 1) * scale + 3),
                )
                pix = doc[page - 1].get_pixmap(clip=tight, dpi=dpi, alpha=False)
        index = counts.get(part, 0)
        counts[part] = index + 1
        data = pix.tobytes("png")
        if part == "stem" and original and page == original[0]["page"]:
            box = original[0].get("number_bbox") or find_question_number(
                doc[page - 1],
                fitz.Rect(original[0]["bbox"]),
                question.source_number,
            )
            data = mask_png(data, rect, box)
        result[f"{part}-{index}.png"] = data
    return result
