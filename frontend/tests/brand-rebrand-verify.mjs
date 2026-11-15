import { spawn } from "node:child_process";
import fs from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(__dirname, "..");
const repoRoot = path.resolve(frontendDir, "..");
const outDir = path.join(repoRoot, "docs", "ui-screenshots", "brand-verify");
fs.mkdirSync(outDir, { recursive: true });

function loadFromNpxOrLocal(pkg) {
  const require = createRequire(import.meta.url);
  try {
    return require(pkg);
  } catch {
    const localAppData = process.env.LOCALAPPDATA || "";
    const npxCache = path.join(localAppData, "npm-cache", "_npx");
    if (fs.existsSync(npxCache)) {
      for (const entry of fs.readdirSync(npxCache)) {
        const candidate = path.join(npxCache, entry, "node_modules", pkg);
        if (fs.existsSync(candidate)) {
          return require(candidate);
        }
      }
    }
    throw new Error(`Could not resolve ${pkg}`);
  }
}

const { chromium } = loadFromNpxOrLocal("playwright");
const axeCore = loadFromNpxOrLocal("axe-core");

const PREVIEW_PORT = 4179;
const BASE_URL = `http://127.0.0.1:${PREVIEW_PORT}`;

async function waitForServer(url, timeoutMs = 15000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(url);
      if (res.ok) return;
    } catch {
      // retry
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error(`Preview server did not start within ${timeoutMs}ms`);
}

function getActiveSlideIndex(page) {
  return page.evaluate(() => {
    const dots = Array.from(document.querySelectorAll('[aria-label="Slide indicators"] button'));
    return dots.findIndex((d) => d.getAttribute("aria-current") === "true");
  });
}

async function runAxe(page, routeLabel) {
  await page.addScriptTag({ content: axeCore.source });
  const results = await page.evaluate(async () => {
    return await window.axe.run(document, {
      runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] },
    });
  });
  const seriousOrCritical = results.violations.filter(
    (v) => v.impact === "serious" || v.impact === "critical",
  );
  return {
    route: routeLabel,
    totalViolations: results.violations.length,
    seriousOrCriticalCount: seriousOrCritical.length,
    violations: seriousOrCritical.map((v) => ({
      id: v.id,
      impact: v.impact,
      description: v.description,
      nodes: v.nodes.length,
    })),
  };
}

async function main() {
  const server = spawn(
    process.platform === "win32" ? "npx.cmd" : "npx",
    ["vite", "preview", "--host", "127.0.0.1", "--port", String(PREVIEW_PORT), "--strictPort"],
    { cwd: frontendDir, stdio: "ignore", shell: process.platform === "win32" },
  );

  const report = {
    viewports: [],
    slideshow: {},
    assets404: [],
    axe: [],
    passed: true,
  };

  try {
    await waitForServer(BASE_URL);
    let browser;
    for (const opts of [
      { headless: true },
      { headless: true, channel: "chrome" },
      { headless: true, channel: "msedge" },
    ]) {
      try {
        browser = await chromium.launch(opts);
        break;
      } catch {
        // try next browser channel
      }
    }
    if (!browser) {
      throw new Error("No Playwright Chromium, Chrome, or Edge browser available");
    }

    try {
      const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
      const page = await context.newPage();
      page.on("response", (res) => {
        if (res.status() >= 400 && !res.url().includes("/api/")) {
          report.assets404.push({ url: res.url(), status: res.status() });
        }
      });

      await page.goto(BASE_URL, { waitUntil: "networkidle" });

      // Check BrandLogo + 4 slides loaded
      const logoCheck = await page.evaluate(() => {
        const logos = Array.from(document.querySelectorAll("[data-brand-logo]"));
        return logos.map((img) => ({
          alt: img.getAttribute("alt"),
          complete: img.complete,
          naturalWidth: img.naturalWidth,
          height: img.getBoundingClientRect().height,
        }));
      });
      report.logoCheck = logoCheck;
      if (logoCheck.length === 0 || logoCheck.some((l) => l.naturalWidth === 0 || l.height < 28)) {
        report.passed = false;
      }

      // Capture all 4 slides via dot clicks
      for (let i = 0; i < 4; i++) {
        await page.locator('[aria-label="Slide indicators"] button').nth(i).click();
        await page.waitForTimeout(500);
        await page.screenshot({ path: path.join(outDir, `login-slide-${i + 1}-1440.png`) });
      }

      const slideImgs = await page.evaluate(() => {
        const imgs = Array.from(document.querySelectorAll(".dps-slideshow img[alt]"));
        return imgs
          .filter((i) => i.getAttribute("alt"))
          .map((i) => ({
            alt: i.getAttribute("alt"),
            naturalWidth: i.naturalWidth,
          }));
      });
      report.slideshow.images = slideImgs;
      if (slideImgs.length < 4 || slideImgs.some((s) => s.naturalWidth === 0)) {
        report.passed = false;
      }

      // Return to slide 0 and clear focus/hover for auto-advance test
      await page.locator('[aria-label="Slide indicators"] button').nth(0).click();
      await page.evaluate(() => {
        if (document.activeElement instanceof HTMLElement) {
          document.activeElement.blur();
        }
      });
      await page.mouse.move(1200, 100);
      await page.waitForTimeout(200);
      const idxBefore = await getActiveSlideIndex(page);
      await page.waitForTimeout(6500);
      const idxAfter = await getActiveSlideIndex(page);
      report.slideshow.autoAdvance = { idxBefore, idxAfter, advanced: idxAfter !== idxBefore };
      if (!report.slideshow.autoAdvance.advanced) report.passed = false;

      // Test pause button stops rotation
      const pauseBtn = page.getByRole("button", { name: /pause slideshow/i });
      await pauseBtn.click();
      const idxPausedStart = await getActiveSlideIndex(page);
      await page.waitForTimeout(6500);
      const idxPausedEnd = await getActiveSlideIndex(page);
      report.slideshow.pauseStopsRotation = idxPausedStart === idxPausedEnd;
      if (!report.slideshow.pauseStopsRotation) report.passed = false;

      // Resume and test hover pauses rotation
      await page.getByRole("button", { name: /play slideshow/i }).click();
      const idxHoverStart = await getActiveSlideIndex(page);
      await page.locator(".dps-slideshow").hover();
      await page.waitForTimeout(6500);
      const idxHoverEnd = await getActiveSlideIndex(page);
      report.slideshow.hoverPausesRotation = idxHoverStart === idxHoverEnd;
      if (!report.slideshow.hoverPausesRotation) report.passed = false;

      // Axe on /
      report.axe.push(await runAxe(page, "/"));

      // Responsive viewports check
      for (const vp of [
        { width: 1440, height: 900 },
        { width: 1024, height: 768 },
        { width: 768, height: 1024 },
        { width: 390, height: 844 },
        { width: 360, height: 800 },
      ]) {
        await page.setViewportSize(vp);
        await page.waitForTimeout(200);
        const overflow = await page.evaluate(() => {
          return document.documentElement.scrollWidth > window.innerWidth + 1;
        });
        report.viewports.push({ ...vp, horizontalOverflow: overflow });
        if (overflow) report.passed = false;
        if (vp.width === 390 || vp.width === 360) {
          await page.screenshot({ path: path.join(outDir, `login-${vp.width}.png`) });
        }
      }

      // 404 route check + axe
      await page.setViewportSize({ width: 1280, height: 800 });
      await page.goto(`${BASE_URL}/nonexistent-route-check`, { waitUntil: "networkidle" });
      const has404Logo = await page.locator("[data-brand-logo]").count();
      report.notFoundHasLogo = has404Logo > 0;
      if (!report.notFoundHasLogo) report.passed = false;
      await page.screenshot({ path: path.join(outDir, "404-1280.png") });
      report.axe.push(await runAxe(page, "/nonexistent-route-check"));

      // Reduced motion context
      const rmContext = await browser.newContext({
        viewport: { width: 1280, height: 800 },
        reducedMotion: "reduce",
      });
      const rmPage = await rmContext.newPage();
      await rmPage.goto(BASE_URL, { waitUntil: "networkidle" });
      const rmBefore = await getActiveSlideIndex(rmPage);
      await rmPage.waitForTimeout(6500);
      const rmAfter = await getActiveSlideIndex(rmPage);
      report.slideshow.reducedMotionStopsAutoAdvance = rmBefore === rmAfter;
      if (!report.slideshow.reducedMotionStopsAutoAdvance) report.passed = false;
      await rmContext.close();

      await context.close();
    } finally {
      await browser.close();
    }
  } finally {
    server.kill();
  }

  for (const a of report.axe) {
    if (a.seriousOrCriticalCount > 0) report.passed = false;
  }
  if (report.assets404.length > 0) report.passed = false;

  fs.writeFileSync(
    path.join(outDir, "brand-rebrand-report.json"),
    JSON.stringify(report, null, 2),
  );
  console.log(JSON.stringify(report, null, 2));
  if (!report.passed) process.exit(1);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
