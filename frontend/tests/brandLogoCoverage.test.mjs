import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(__dirname, "..");
const repoRoot = path.resolve(frontendDir, "..");

function parseManifestRoutes() {
  const manifestPath = path.join(repoRoot, "docs", "ui-manifest.md");
  const content = fs.readFileSync(manifestPath, "utf8");
  const match = content.match(
    /<!-- ROUTE_MANIFEST_START -->\r?\n([\s\S]*?)<!-- ROUTE_MANIFEST_END -->/,
  );
  assert.ok(match, "ROUTE_MANIFEST_START/END block must exist");
  const block = match[1];
  const rows = [];
  for (const line of block.split(/\r?\n/)) {
    if (!line.startsWith("|")) continue;
    const cols = line
      .split("|")
      .slice(1, -1)
      .map((c) => c.trim());
    if (cols.length < 4 || cols[0] === "path" || cols[0].startsWith("---")) continue;
    rows.push({
      path: cols[0].replace(/^`|`$/g, ""),
      file: cols[1].replace(/^`|`$/g, ""),
      role: cols[2].replace(/^`|`$/g, ""),
      layout: cols[3].replace(/^`|`$/g, ""),
    });
  }
  return rows;
}

test("brand assets and slideshow webp files exist under size budget", () => {
  const requiredFiles = [
    "src/assets/brand/dps-logo-64.webp",
    "src/assets/brand/dps-logo-128.webp",
    "src/assets/brand/dps-logo-256.webp",
    "src/assets/brand/dps-logo-512.webp",
    "src/assets/brand/dps-logo-tile-128.webp",
    "src/assets/brand/dps-logo-tile-256.webp",
    "src/assets/brand/dps-logo-tile-512.webp",
    "public/favicon.ico",
    "public/favicon-32x32.png",
    "public/apple-touch-icon.png",
    "public/icon-192.png",
    "public/icon-512.png",
    "public/og-image.png",
    "public/site.webmanifest",
  ];
  for (const rel of requiredFiles) {
    const abs = path.join(frontendDir, rel);
    assert.ok(fs.existsSync(abs), `Missing brand asset: ${rel}`);
    assert.ok(fs.statSync(abs).size > 0, `Empty brand asset: ${rel}`);
  }

  const desktopSlides = [
    "src/assets/brand/slides/slide-1-building@1920.webp",
    "src/assets/brand/slides/slide-2-trophy@1920.webp",
    "src/assets/brand/slides/slide-3-art@1920.webp",
    "src/assets/brand/slides/slide-4-lab@1920.webp",
  ];
  const mobileSlides = [
    "src/assets/brand/slides/slide-1-building@1280.webp",
    "src/assets/brand/slides/slide-2-trophy@1280.webp",
    "src/assets/brand/slides/slide-3-art@1280.webp",
    "src/assets/brand/slides/slide-4-lab@1280.webp",
  ];
  let totalDesktopBytes = 0;
  for (const rel of [...desktopSlides, ...mobileSlides]) {
    const abs = path.join(frontendDir, rel);
    assert.ok(fs.existsSync(abs), `Missing slideshow asset: ${rel}`);
    const sz = fs.statSync(abs).size;
    assert.ok(sz <= 250 * 1024, `${rel} (${sz} B) exceeds 250 KB per-file budget`);
    if (desktopSlides.includes(rel)) {
      totalDesktopBytes += sz;
    }
  }
  assert.ok(
    totalDesktopBytes <= 1024 * 1024,
    `Total @1920 slideshow WebP size (${totalDesktopBytes} B) must stay under 1 MB`,
  );
});

test("every route in docs/ui-manifest.md uses a layout/page with BrandLogo", () => {
  const routes = parseManifestRoutes();
  assert.ok(routes.length >= 12, `Expected >= 12 routes, found ${routes.length}`);

  const layoutFiles = {
    PublicLayout: "src/layouts/PublicLayout.tsx",
    StudentLayout: "src/layouts/StudentLayout.tsx",
    FocusLayout: "src/layouts/FocusLayout.tsx",
    AdminLayout: "src/layouts/AdminLayout.tsx",
  };

  for (const [name, rel] of Object.entries(layoutFiles)) {
    const src = fs.readFileSync(path.join(frontendDir, rel), "utf8");
    assert.ok(
      src.includes("BrandLogo") || (name === "PublicLayout" && src.includes("AppHeader")),
      `${name} (${rel}) must render BrandLogo`,
    );
    assert.ok(
      !src.includes("ShieldCheck"),
      `${name} (${rel}) must not use ShieldCheck placeholder`,
    );
  }

  const overviewSrc = fs.readFileSync(
    path.join(frontendDir, "src/pages/OverviewPage.tsx"),
    "utf8",
  );
  assert.ok(overviewSrc.includes("BrandLogo"), "OverviewPage must render BrandLogo");
  assert.ok(overviewSrc.includes("LoginSlideshow"), "OverviewPage must render LoginSlideshow");

  for (const route of routes) {
    const matchedLayout = Object.keys(layoutFiles).find((l) => route.layout.includes(l));
    assert.ok(
      matchedLayout,
      `Route ${route.path} (${route.file}) layout "${route.layout}" must map to a branded layout`,
    );
  }
});

test("no legacy wine/crimson hexes remain in index.css or student-console.css", () => {
  const legacyPattern = /#a3123f|#8a0f35|#9f1239|#fdf0f4|#6d0d2d|#cf3f68|#f08aa6/i;
  for (const rel of ["src/index.css", "src/features/student/student-console.css"]) {
    const css = fs.readFileSync(path.join(frontendDir, rel), "utf8");
    assert.ok(!legacyPattern.test(css), `Legacy wine hex found in ${rel}`);
  }
});
