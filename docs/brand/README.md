# Delhi Private School Brand Assets & Color System

> **Identity:** Delhi Private School — *"Service Beyond Self"*
> **Updated:** 2026-11-15

## 1. Source Assets & Resolution Notice

All untouched originals are archived in `docs/brand/originals/`:

| Original File | Dimensions | Usage | Bundled Asset |
| --- | --- | --- | --- |
| `DPS_LOGO.jpg` | `554×554` | School crest & `<BrandLogo>` | `frontend/src/assets/brand/dps-logo-{64,128,256,512}.{png,webp}` & `dps-logo-tile-{64,128,256,512}.webp` |
| `IMG_3.jpg` | `678×452` | Slide 1: School building with yellow and green facade | `frontend/src/assets/brand/slides/slide-1-building.webp` (`47.1 KB`) |
| `IMG_2.jpg` | `439×455` | Slide 2: Students celebrating with a trophy | `frontend/src/assets/brand/slides/slide-2-trophy.webp` (`40.0 KB`) |
| `IMG_1.jpg` | `515×388` | Slide 3: Students painting in an art class | `frontend/src/assets/brand/slides/slide-3-art.webp` (`48.3 KB`) |
| `IMG_4.jpg` | `547×365` | Slide 4: Pupils watching a science experiment in a lab | `frontend/src/assets/brand/slides/slide-4-lab.webp` (`24.6 KB`) |

Total bundled WebP size for all 4 slideshow photos: **`160.1 KB`** (native resolution, WebP quality 82, zero upscaling).

### Follow-up Requests for School Media

1. **Official Vector Logo (`SVG`):** `DPS_LOGO.jpg` is a `554×554` raster JPEG with a soft outer bevel shadow. Request the official SVG/vector crest from the school so it scales cleanly without a raster tile on dark surfaces.
2. **High-Resolution Originals (`>= 1920px` width):** The four slideshow photos are `439–678px` wide. Until `>= 1920px` originals are supplied, `LoginSlideshow` defaults to `data-fit="frame"` (sharp centered frame `<= 1.25×` native size over a blurred, green-tinted backdrop). When `>= 1920px` photos arrive, switch `data-fit="cover"`.

---

## 2. Transparent vs. White-Tile Decision (`Step 1.1`)

The white outer background of `DPS_LOGO.jpg` was flood-filled from the four corners only (tolerance `12`), preserving the white interior of the shield and ribbons.

Testing on `#ffffff` vs. `#0c1f14` (dark admin sidebar) in [`logo-dark-surface-test.png`](file:///c:/Users/EricAppiahOwusu/Music/DPCIS/docs/brand/logo-dark-surface-test.png) showed:

- **On light surfaces (`#ffffff`, `#f4f7f5`):** The transparent WebP/PNG renders cleanly without edge artifacts.
- **On dark surfaces (`#0c1f14`):** The JPEG's outer bevel drop-shadow leaves a visible jagged light-gray halo around the shield perimeter when flood-filled.
- **Decision:** Use the transparent asset on light surfaces (`onDark={false}`), and render the original white-background logo inside a **white rounded tile (`border-radius: 10px`, `padding: 4px`)** on dark surfaces (`onDark={true}`).

---

## 3. Pixel-Sampled Logo Colors & Derived Palette

Measured directly from `DPS_LOGO.jpg` using Pillow pixel-sampling:

| Logo Element | Measured Dominant Hex | Role |
| --- | --- | --- |
| **Logo Green** | `#029022` | Large fills, icons, rings, charts, accents (`4.19:1` on white) |
| **Logo Dark Green** | `#086a1c` / `#00751c` | Hover states, link text on white (`6.80:1`) |
| **Flame Red** | `#ef1e24` | Decorative accent only (never status) |
| **Flame Yellow** | `#fec600` | Decorative accent only (active slide dot, dark-surface highlight; `11.29:1` with `#0f1a13`, `6.64:1` on `#064a18`) |
| **Fist Gold** | `#c98f21` | Decorative accent only (never status) |

### Derived OKLCH Brand Scale & WCAG 2.1 Contrast

| Token | Hex | Contrast Verification |
| --- | --- | --- |
| `--brand-50` | `#eef8f0` | `9.66:1` with `#064a18`, `6.26:1` with `#086a1c` |
| `--brand-100` | `#dcf2e2` | `5.78:1` with `#086a1c` |
| `--brand-500` | `#029022` | `4.19:1` on `#ffffff` (icons/rings/large fills) |
| `--brand-600` / `--brand` | `#067a1f` | `5.51:1` with `#ffffff` (primary CTA fill) |
| `--brand-700` | `#086a1c` | `6.80:1` on `#ffffff`, `6.30:1` on `#f4f7f5` (links & hover) |
| `--brand-900` | `#064a18` | `10.50:1` with `#ffffff` (deep forest gradient start) |
| `--canvas` / `--ink` | `#f4f7f5` / `#0f1a13` | `16.53:1` |
| `--side` (dark forest) | `#0c1f14` | `17.19:1` with `#ffffff`, `13.07:1` with `#d6e4da` |
| `--ok` (teal-green) | `#0f766e` on `#e7f6f4` | `4.92:1` (distinct from brand green) |
| `--warn` (amber) | `#a15c07` on `#fff4dc` | `4.75:1` |
| `--danger` (orange-red) | `#b8340a` on `#fdeee7` | `5.25:1` |
| `--info` (blue) | `#1d4ed8` on `#eaf0ff` | `5.87:1` |
