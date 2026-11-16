# Delhi Private School Brand Assets

Official brand assets derived from user-provided originals in `docs/brand/originals/`.

## Logo Assets (`frontend/src/assets/brand/`)

Derived from `docs/brand/originals/DPS_LOGO.jpg` (`554×554`):
- `dps-logo-{64,128,256,512}.{png,webp}`: corner-flood-filled transparent background (tolerance 12, preserving white inside the shield). Used on light surfaces.
- `dps-logo-tile-{64,128,256,512}.{png,webp}`: original logo centered on a rounded white tile (`#ffffff`, 18% corner radius) for dark surfaces (`#0c1f14` sidebar) so no dark-edge halo appears.

## Login Slideshow Photos (`frontend/src/assets/brand/slides/`)

Generated offline by [`tools/image-enhance/enhance_slides.py`](../../tools/image-enhance/enhance_slides.py) from the untouched originals in `docs/brand/originals/`. Each slide has a `@1920.webp` (short side `>= 1250 px`, `<= 250 KB`) and `@1280.webp` (`<= 250 KB`) variant wired via `srcSet` and `sizes="(min-width: 1024px) max(58vw, 150vh), 100vw"`.

### Restoration & Color Treatment (No Generative Editing)

- **No generative / face-restoration models:** No diffusion, img2img, inpainting, outpainting, GFPGAN, CodeFormer, RestoreFormer, or `face_enhance` was used. Faces, expressions, uniforms, badges, signage, and watermarks remain faithful to the originals.
- **Super-resolution / Upscaling:**
  - `slide-1-building` (`IMG_3.jpg`, `678×452`, `2.83×` to `1920×1280`): `realesrgan-ncnn-vulkan` v0.2.5.0 (`realesrgan-x4plus`, 4×, tile=256, no `face_enhance`), Lanczos-downscaled to target sizes.
  - `slide-2-trophy` (`IMG_2.jpg`, `439×455`, `3.42×` to `1500×1555`), `slide-3-art` (`IMG_1.jpg`, `515×388`, `3.73×` to `1920×1447`), `slide-4-lab` (`IMG_4.jpg`, `547×365`, `3.51×` to `1920×1281`): 2-step Lanczos fallback (`2×` then target) because AI super-resolution altered small facial features on `trophy`/`lab` and sleeve badge detail on `art`.
- **Consistent Restoration Polish & Color Grade:**
  - Light sharpening (`UnsharpMask(radius=0.8, percent=40, threshold=2)`) + fine luminance grain (`sigma=1.6–1.8`, ~1.5%) in YCbCr `Y` only.
  - Mild auto-levels (`cutoff=0.4%`, 40% blend), gentle luminance shadow lift / highlight roll-off (`Y` channel only so skin tones stay natural with zero green shift), subtle vibrance (`1.07×`), and a soft ~5.5% edge vignette.

### Fidelity Gate Metrics (Round-Trip Lanczos vs Original, Threshold: SSIM >= 0.93)

| Slide | Original | `@1920` Size | `@1280` Size | Route | SSIM (Ungraded / Graded) | MAD (Ungraded / Graded / Max 16×16) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `slide-1-building` | `678×452` | `1920×1280` (`242.7 KB`) | `1280×853` (`171.8 KB`) | `realesrgan-x4plus` | `0.9354` / `0.9354` | `7.18` / `7.19` / `25.43` |
| `slide-2-trophy` | `439×455` | `1500×1555` (`192.9 KB`) | `1280×1327` (`162.8 KB`) | `lanczos-fallback` | `0.9950` / `0.9941` | `2.06` / `1.74` / `4.38` |
| `slide-3-art` | `515×388` | `1920×1447` (`228.9 KB`) | `1280×964` (`172.0 KB`) | `lanczos-fallback` | `0.9945` / `0.9937` | `2.32` / `2.27` / `5.20` |
| `slide-4-lab` | `547×365` | `1920×1281` (`131.3 KB`) | `1280×854` (`83.4 KB`) | `lanczos-fallback` | `0.9950` / `0.9939` | `1.89` / `1.49` / `3.66` |

Side-by-side 100% comparison crops and difference heatmaps are archived in `docs/brand/enhance-compare/`.

> **Replacement Note:** The three people-focused slides (`trophy`, `art`, `lab`) remain softer at full 1080p height because their source JPEGs are 365–455 px tall and conservative Lanczos restoration cannot invent missing facial detail without altering identity. Replace `docs/brand/originals/IMG_*.jpg` and re-run `enhance_slides.py` when higher-resolution official school photography becomes available.
