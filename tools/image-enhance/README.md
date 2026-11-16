# Login Slideshow Restoration Tool (`tools/image-enhance/`)

Offline restoration and color-treatment script for the Delhi Private School login slideshow photos. Never imported at app runtime and adds zero dependencies to `package.json` or `requirements.txt`.

## Tooling & License

- Python 3 + `Pillow` (`PIL`)
- Optional local super-resolution binary: `realesrgan-ncnn-vulkan` v0.2.5.0 (BSD-3-Clause license), placed in `tools/image-enhance/bin/` and `models/` (both gitignored).

## Usage

```bash
python tools/image-enhance/enhance_slides.py --fallback-for trophy art lab
```

Outputs `@1920.webp` and `@1280.webp` to `frontend/src/assets/brand/slides/` plus 100% comparison sheets and difference heatmaps to `docs/brand/enhance-compare/`.
