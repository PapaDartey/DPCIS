"""Offline restoration and color-treatment pipeline for DPS login slideshow photos.

Starts from untouched originals in docs/brand/originals/:
1. Super-resolution via realesrgan-ncnn-vulkan (4x, realesrgan-x4plus, NO face-enhance)
   OR conservative 2-step Lanczos fallback for photos with small faces that fail
   visual/SSIM fidelity gates.
2. Light sharpening (UnsharpMask r=0.8, 40%) + ~1.5% luminance grain.
3. Consistent natural tone & color treatment (0.4% autocontrast blend, gentle
   luminance shadow lift / highlight recovery, subtle 7% vibrance, ~5% vignette)
   preserving natural skin tones without any green shift.
4. Fidelity gate: downscales @1920 back to original size (Lanczos) and computes
   luminance SSIM + MAD both ungraded (vs untouched original) and grade-matched
   (vs graded original). Requires SSIM >= 0.93; otherwise falls back to Lanczos.
5. Saves @1920 and @1280 WebP (quality ~85, <= 250 KB), 100% zoom side-by-side
   comparison crops, and per-photo difference heatmaps in docs/brand/enhance-compare/.
"""

from __future__ import annotations

import argparse
import math
import random
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

REPO_ROOT = Path(__file__).resolve().parents[2]
ORIGINALS_DIR = REPO_ROOT / "docs" / "brand" / "originals"
COMPARE_DIR = REPO_ROOT / "docs" / "brand" / "enhance-compare"
OUT_DIR = REPO_ROOT / "frontend" / "src" / "assets" / "brand" / "slides"
TMP_DIR = Path(__file__).resolve().parent / "tmp"
BIN_EXE = Path(__file__).resolve().parent / "bin" / "realesrgan-ncnn-vulkan.exe"

SSIM_MIN_THRESHOLD = 0.93

SLIDES = [
    {
        "id": "building",
        "src": "IMG_3.jpg",
        "out_base": "slide-1-building",
        "w1920": 1920,
        "w1280": 1280,
        # Facade/signage and left building wing
        "crop_centers": [(0.45, 0.42), (0.20, 0.45)],
    },
    {
        "id": "trophy",
        "src": "IMG_2.jpg",
        "out_base": "slide-2-trophy",
        "w1920": 1500,  # 439x455 -> 1500x1555 (short side 1500 >= 1250)
        "w1280": 1280,  # 1280x1327
        # Student faces & trophy/uniform badges
        "crop_centers": [(0.52, 0.34), (0.36, 0.28)],
    },
    {
        "id": "art",
        "src": "IMG_1.jpg",
        "out_base": "slide-3-art",
        "w1920": 1920,
        "w1280": 1280,
        # Student faces, painting table, and bottom watermark/signage area
        "crop_centers": [(0.35, 0.36), (0.68, 0.42), (0.50, 0.90)],
    },
    {
        "id": "lab",
        "src": "IMG_4.jpg",
        "out_base": "slide-4-lab",
        "w1920": 1920,
        "w1280": 1280,
        # Pupils' faces & teacher/table
        "crop_centers": [(0.46, 0.35), (0.72, 0.44)],
    },
]


def build_tone_lut() -> list[int]:
    """Gentle luminance LUT: subtle shadow lift (+6 max) and soft highlight roll-off."""
    lut = []
    for i in range(256):
        t = i / 255.0
        # Shadow lift peaks around t=0.22, gentle highlight compression above t=0.82
        lift = 6.5 * ((1.0 - t) ** 2.2) * (t * 3.0 if t < 0.33 else 1.0)
        compress = -4.0 * max(0.0, (t - 0.82) / 0.18) ** 1.5
        lut.append(max(0, min(255, round(i + lift + compress))))
    return lut


TONE_LUT = build_tone_lut()


def apply_color_grade(img: Image.Image) -> Image.Image:
    """Consistent, natural tone & color treatment with zero green shift on skin."""
    rgb = img.convert("RGB")
    # 1. Mild auto-levels (0.4% clip) blended 40% to gently balance exposure & WB
    leveled = ImageOps.autocontrast(rgb, cutoff=0.4)
    balanced = Image.blend(rgb, leveled, 0.40)

    # 2. Gentle shadow lift & highlight recovery on luminance Y only (preserves natural Cb/Cr)
    ycbcr = balanced.convert("YCbCr")
    y_band, cb_band, cr_band = ycbcr.split()
    y_band = y_band.point(TONE_LUT)
    toned = Image.merge("YCbCr", (y_band, cb_band, cr_band)).convert("RGB")

    # 3. Subtle vibrance/color boost (1.07x) without oversaturating skin
    graded = ImageEnhance.Color(toned).enhance(1.07)

    # 4. Subtle vignette (~5.5% edge darkening)
    w, h = graded.size
    cx, cy = w / 2.0, h / 2.0
    max_r2 = cx * cx + cy * cy
    # Build low-res vignette mask and resize smoothly for speed
    mw, mh = max(32, w // 16), max(32, h // 16)
    mask_vals = []
    for my in range(mh):
        dy = ((my + 0.5) / mh - 0.5) * h
        for mx in range(mw):
            dx = ((mx + 0.5) / mw - 0.5) * w
            r2 = (dx * dx + dy * dy) / max_r2
            factor = 1.0 - 0.055 * (r2 ** 1.35)
            mask_vals.append(max(0, min(255, round(255 * factor))))
    vignette_mask = Image.new("L", (mw, mh))
    vignette_mask.putdata(mask_vals)
    vignette_mask = vignette_mask.resize((w, h), Image.Resampling.BILINEAR)
    dark = Image.new("RGB", (w, h), (0, 0, 0))
    return Image.composite(graded, dark, vignette_mask)


def add_subtle_grain(img: Image.Image, sigma: float = 1.8) -> Image.Image:
    """Add ~1.5% fine luminance grain to prevent waxy smooth areas."""
    rng = random.Random(42)
    ycbcr = img.convert("YCbCr")
    y_band, cb_band, cr_band = ycbcr.split()
    y_px = list(y_band.getdata())
    noisy = [max(0, min(255, int(v + rng.gauss(0, sigma)))) for v in y_px]
    y_out = Image.new("L", y_band.size)
    y_out.putdata(noisy)
    return Image.merge("YCbCr", (y_out, cb_band, cr_band)).convert("RGB")


def lanczos_two_step(orig: Image.Image, target_w: int, target_h: int, polish: bool) -> Image.Image:
    """Two-step Lanczos upscale (2x then remainder), with optional unsharp + grain."""
    ow, oh = orig.size
    step1 = orig.resize((ow * 2, oh * 2), Image.Resampling.LANCZOS)
    out = step1.resize((target_w, target_h), Image.Resampling.LANCZOS)
    if polish:
        out = out.filter(ImageFilter.UnsharpMask(radius=0.8, percent=40, threshold=2))
        out = add_subtle_grain(out, sigma=1.8)
    return out


def run_realesrgan_4x(src_path: Path, dst_path: Path) -> None:
    """Run realesrgan-ncnn-vulkan 4x with tile mode (no face-enhance)."""
    cmd = [
        str(BIN_EXE),
        "-i",
        str(src_path),
        "-o",
        str(dst_path),
        "-s",
        "4",
        "-n",
        "realesrgan-x4plus",
        "-t",
        "256",
        "-f",
        "png",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0 or not dst_path.exists():
        raise RuntimeError(f"realesrgan failed ({res.returncode}): {res.stderr or res.stdout}")


def compute_luminance_ssim_and_mad(
    ref: Image.Image, cand: Image.Image, block: int = 8
) -> tuple[float, float, float]:
    """Compute windowed luminance SSIM (8x8 blocks), RGB MAD, and max 16x16 block MAD."""
    ref_rgb = ref.convert("RGB")
    cand_rgb = cand.convert("RGB")
    w, h = ref_rgb.size
    r_px = list(ref_rgb.getdata())
    c_px = list(cand_rgb.getdata())

    mad_sum = 0.0
    for (r1, g1, b1), (r2, g2, b2) in zip(r_px, c_px):
        mad_sum += (abs(r1 - r2) + abs(g1 - g2) + abs(b1 - b2)) / 3.0
    mad = mad_sum / len(r_px)

    ref_l = list(ref_rgb.convert("L").getdata())
    cand_l = list(cand_rgb.convert("L").getdata())
    c1 = (0.01 * 255.0) ** 2
    c2 = (0.03 * 255.0) ** 2

    ssim_vals: list[float] = []
    for y0 in range(0, h - block + 1, block):
        for x0 in range(0, w - block + 1, block):
            xs: list[int] = []
            ys: list[int] = []
            for dy in range(block):
                off = (y0 + dy) * w + x0
                xs.extend(ref_l[off : off + block])
                ys.extend(cand_l[off : off + block])
            n = len(xs)
            mx = sum(xs) / n
            my = sum(ys) / n
            vx = sum((x - mx) ** 2 for x in xs) / n
            vy = sum((y - my) ** 2 for y in ys) / n
            cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / n
            num = (2 * mx * my + c1) * (2 * cov + c2)
            den = (mx * mx + my * my + c1) * (vx + vy + c2)
            ssim_vals.append(num / den if den > 0 else 1.0)

    mean_ssim = sum(ssim_vals) / len(ssim_vals) if ssim_vals else 1.0

    # Max 16x16 block luminance MAD to catch localized hallucinations
    b16 = 16
    max_block_mad = 0.0
    for y0 in range(0, h - b16 + 1, b16):
        for x0 in range(0, w - b16 + 1, b16):
            bsum = 0.0
            for dy in range(b16):
                off = (y0 + dy) * w + x0
                for dx in range(b16):
                    bsum += abs(ref_l[off + dx] - cand_l[off + dx])
            bmad = bsum / (b16 * b16)
            if bmad > max_block_mad:
                max_block_mad = bmad

    return mean_ssim, mad, max_block_mad


def save_diff_heatmap(ref: Image.Image, cand: Image.Image, out_path: Path) -> None:
    """Save 6x amplified RGB difference heatmap (dark blue -> yellow -> red)."""
    r_px = list(ref.convert("RGB").getdata())
    c_px = list(cand.convert("RGB").getdata())
    heat_px: list[tuple[int, int, int]] = []
    for (r1, g1, b1), (r2, g2, b2) in zip(r_px, c_px):
        diff = min(255.0, ((abs(r1 - r2) + abs(g1 - g2) + abs(b1 - b2)) / 3.0) * 6.0)
        t = diff / 255.0
        if t < 0.5:
            u = t * 2.0
            rgb = (round(15 + u * 235), round(25 + u * 195), round(70 - u * 40))
        else:
            u = (t - 0.5) * 2.0
            rgb = (250, round(220 - u * 190), round(30 - u * 20))
        heat_px.append(rgb)
    heat = Image.new("RGB", ref.size)
    heat.putdata(heat_px)
    heat.save(out_path, format="PNG")


def save_webp_under_budget(img: Image.Image, out_path: Path, max_bytes: int = 250 * 1024) -> int:
    """Save WebP starting at quality=85, stepping down slightly only if > max_bytes."""
    for q in (85, 82, 78, 74):
        img.save(out_path, format="WEBP", quality=q, method=6)
        size = out_path.stat().st_size
        if size <= max_bytes:
            return size
    return out_path.stat().st_size


def make_compare_sheet(
    lanczos_img: Image.Image,
    enhanced_img: Image.Image,
    centers: list[tuple[float, float]],
    out_path: Path,
    crop_size: int = 360,
) -> None:
    """Save 100% zoom side-by-side crops (left: plain Lanczos, right: restored+graded)."""
    w, h = enhanced_img.size
    pad = 12
    sheet_w = crop_size * 2 + pad * 3
    sheet_h = (crop_size + 28) * len(centers) + pad
    sheet = Image.new("RGB", (sheet_w, sheet_h), (244, 247, 245))
    draw = ImageDraw.Draw(sheet)

    for idx, (cx, cy) in enumerate(centers):
        x0 = max(0, min(w - crop_size, int(w * cx - crop_size / 2)))
        y0 = max(0, min(h - crop_size, int(h * cy - crop_size / 2)))
        box = (x0, y0, x0 + crop_size, y0 + crop_size)
        top = pad + idx * (crop_size + 28)
        draw.text((pad, top), f"Crop {idx + 1}: Plain Lanczos (100%)", fill=(15, 26, 19))
        draw.text((pad * 2 + crop_size, top), f"Crop {idx + 1}: Restored+Graded (100%)", fill=(6, 122, 31))
        sheet.paste(lanczos_img.crop(box), (pad, top + 18))
        sheet.paste(enhanced_img.crop(box), (pad * 2 + crop_size, top + 18))

    sheet.save(out_path, format="PNG")


def build_candidate(
    orig: Image.Image,
    src_path: Path,
    sid: str,
    w1920: int,
    h1920: int,
    w1280: int,
    h1280: int,
    use_ai: bool,
) -> tuple[Image.Image, Image.Image, Image.Image]:
    """Return (ungraded_1920, graded_1920, graded_1280)."""
    if use_ai:
        tmp_4x = TMP_DIR / f"{sid}_4x.png"
        if not tmp_4x.exists():
            run_realesrgan_4x(src_path, tmp_4x)
        ai_4x = Image.open(tmp_4x).convert("RGB")
        ungraded_1920 = ai_4x.resize((w1920, h1920), Image.Resampling.LANCZOS)
        ungraded_1920 = ungraded_1920.filter(ImageFilter.UnsharpMask(radius=0.8, percent=40, threshold=2))
        ungraded_1920 = add_subtle_grain(ungraded_1920, sigma=1.6)
        ungraded_1280 = ai_4x.resize((w1280, h1280), Image.Resampling.LANCZOS)
        ungraded_1280 = add_subtle_grain(ungraded_1280, sigma=1.4)
    else:
        ungraded_1920 = lanczos_two_step(orig, w1920, h1920, polish=True)
        ungraded_1280 = lanczos_two_step(orig, w1280, h1280, polish=True)

    return ungraded_1920, apply_color_grade(ungraded_1920), apply_color_grade(ungraded_1280)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fallback-for", nargs="*", default=[], help="Slide IDs to force Lanczos fallback")
    args = parser.parse_args()
    fallback_ids = set(args.fallback_for)

    COMPARE_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)

    has_ai = BIN_EXE.exists()
    total_bytes = 0

    for slide in SLIDES:
        sid = slide["id"]
        src_path = ORIGINALS_DIR / slide["src"]
        orig = Image.open(src_path).convert("RGB")
        orig_graded = apply_color_grade(orig)
        ow, oh = orig.size

        w1920 = slide["w1920"]
        h1920 = round(oh * (w1920 / ow))
        w1280 = slide["w1280"]
        h1280 = round(oh * (w1280 / ow))

        plain_lanczos = lanczos_two_step(orig, w1920, h1920, polish=False)

        use_ai = has_ai and sid not in fallback_ids
        mode = "realesrgan-x4plus" if use_ai else "lanczos-fallback"

        ungraded_1920, graded_1920, graded_1280 = build_candidate(
            orig, src_path, sid, w1920, h1920, w1280, h1280, use_ai=use_ai
        )

        rt_ungraded = ungraded_1920.resize((ow, oh), Image.Resampling.LANCZOS)
        rt_graded = graded_1920.resize((ow, oh), Image.Resampling.LANCZOS)
        ssim_ungraded, mad_ungraded, max_blk_ungraded = compute_luminance_ssim_and_mad(orig, rt_ungraded)
        ssim_graded, mad_graded, max_blk_graded = compute_luminance_ssim_and_mad(orig_graded, rt_graded)

        # Fidelity gate: require SSIM >= 0.93 on both ungraded and grade-matched round-trips
        if use_ai and (ssim_ungraded < SSIM_MIN_THRESHOLD or ssim_graded < SSIM_MIN_THRESHOLD):
            print(
                f"  [GATE] {sid} realesrgan failed SSIM >= {SSIM_MIN_THRESHOLD} "
                f"(ungraded={ssim_ungraded:.4f}, graded={ssim_graded:.4f}) -> falling back to Lanczos"
            )
            mode = "lanczos-fallback (ssim-gate)"
            ungraded_1920, graded_1920, graded_1280 = build_candidate(
                orig, src_path, sid, w1920, h1920, w1280, h1280, use_ai=False
            )
            rt_ungraded = ungraded_1920.resize((ow, oh), Image.Resampling.LANCZOS)
            rt_graded = graded_1920.resize((ow, oh), Image.Resampling.LANCZOS)
            ssim_ungraded, mad_ungraded, max_blk_ungraded = compute_luminance_ssim_and_mad(orig, rt_ungraded)
            ssim_graded, mad_graded, max_blk_graded = compute_luminance_ssim_and_mad(orig_graded, rt_graded)

        out_1920 = OUT_DIR / f"{slide['out_base']}@1920.webp"
        out_1280 = OUT_DIR / f"{slide['out_base']}@1280.webp"
        sz_1920 = save_webp_under_budget(graded_1920, out_1920)
        sz_1280 = save_webp_under_budget(graded_1280, out_1280)
        total_bytes += sz_1920 + sz_1280

        cmp_path = COMPARE_DIR / f"{slide['out_base']}-compare.png"
        heat_path = COMPARE_DIR / f"{slide['out_base']}-heatmap.png"
        make_compare_sheet(plain_lanczos, graded_1920, slide["crop_centers"], cmp_path)
        save_diff_heatmap(orig_graded, rt_graded, heat_path)

        print(
            f"{sid} [{mode}]: {ow}x{oh} -> @1920={w1920}x{h1920} ({sz_1920/1024:.1f} KB), "
            f"@1280={w1280}x{h1280} ({sz_1280/1024:.1f} KB) | "
            f"SSIM(ungraded={ssim_ungraded:.4f}, graded={ssim_graded:.4f}) | "
            f"MAD(ungraded={mad_ungraded:.2f}, graded={mad_graded:.2f}, max16={max_blk_graded:.2f})"
        )

    print(f"Total 8 WebP files: {total_bytes / 1024:.1f} KB ({total_bytes} B)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
