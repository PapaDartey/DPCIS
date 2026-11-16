import fs from "node:fs";
import http from "node:http";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(__dirname, "..");
const repoRoot = path.resolve(frontendDir, "..");
const distDir = path.join(frontendDir, "dist");
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

function startStaticDistServer() {
  const mimeTypes = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".webp": "image/webp",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".webmanifest": "application/manifest+json",
  };
  const server = http.createServer((req, res) => {
    const urlPath = (req.url || "/").split("?")[0];
    const rel = urlPath === "/" ? "index.html" : urlPath.replace(/^\/+/, "");
    let filePath = path.join(distDir, rel);
    if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
      filePath = path.join(distDir, "index.html");
    }
    const ext = path.extname(filePath).toLowerCase();
    res.writeHead(200, { "Content-Type": mimeTypes[ext] || "application/octet-stream" });
    fs.createReadStream(filePath).pipe(res);
  });
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      const addr = server.address();
      resolve({
        baseUrl: `http://127.0.0.1:${addr.port}`,
        close: () => new Promise((r) => server.close(() => r())),
      });
    });
  });
}

function getActiveSlideIndex(page) {
  return page.evaluate(() => {
    const el = document.querySelector(".dps-slideshow");
    return Number(el?.getAttribute("data-active-slide") ?? -1);
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
  const { baseUrl, close } = await startStaticDistServer();
  const report = {
    viewports: [],
    slideshow: {},
    noCssUpscaling: [],
    assets404: [],
    axe: [],
    passed: true,
  };

  try {
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
        // try next
      }
    }
    if (!browser) throw new Error("No Playwright Chromium/Chrome/Edge available");

    try {
      const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
      const page = await context.newPage();
      page.on("response", (res) => {
        if (res.status() >= 400 && !res.url().includes("/api/")) {
          report.assets404.push({ url: res.url(), status: res.status() });
        }
      });

      await page.goto(baseUrl, { waitUntil: "networkidle" });

      const domCheck = await page.evaluate(() => {
        const slideshow = document.querySelector(".dps-slideshow");
        const arrows = document.querySelectorAll(
          '[aria-label="Previous slide"], [aria-label="Next slide"]',
        ).length;
        const dotButtons = document.querySelectorAll('[aria-label="Slide indicators"] button').length;
        const pauseBtn = document.querySelector('button[aria-label="Pause slideshow"]');
        const pauseRect = pauseBtn?.getBoundingClientRect();
        return {
          fit: slideshow?.getAttribute("data-fit"),
          arrowCount: arrows,
          dotButtonCount: dotButtons,
          pauseButtonExists: Boolean(pauseBtn),
          pauseHiddenInitially: Boolean(pauseRect && pauseRect.width <= 1 && pauseRect.height <= 1),
        };
      });
      report.slideshow.domCheck = domCheck;
      if (
        domCheck.fit !== "cover" ||
        domCheck.arrowCount !== 0 ||
        domCheck.dotButtonCount !== 0 ||
        !domCheck.pauseButtonExists ||
        !domCheck.pauseHiddenInitially
      ) {
        report.passed = false;
      }

      // Check pause button becomes visible on keyboard Tab focus
      await page.locator(".dps-slideshow").focus();
      await page.keyboard.press("Tab");
      const pauseFocusedRect = await page.evaluate(() => {
        const el = document.activeElement;
        const rect = el?.getBoundingClientRect();
        return {
          ariaLabel: el?.getAttribute("aria-label"),
          width: rect?.width ?? 0,
          height: rect?.height ?? 0,
        };
      });
      report.slideshow.pauseFocusedRect = pauseFocusedRect;
      if (
        pauseFocusedRect.ariaLabel !== "Pause slideshow" ||
        pauseFocusedRect.width < 40 ||
        pauseFocusedRect.height < 40
      ) {
        report.passed = false;
      }

      // Capture all 4 slides at 1440x900, 1920x1080, 1024x768, 390x844
      for (const vp of [
        { width: 1440, height: 900, label: "1440" },
        { width: 1920, height: 1080, label: "1920" },
        { width: 1024, height: 768, label: "1024" },
        { width: 390, height: 844, label: "390" },
      ]) {
        await page.setViewportSize({ width: vp.width, height: vp.height });
        for (let step = 0; step < 4; step++) {
          const idx = await getActiveSlideIndex(page);
          await page.evaluate(() => {
            if (document.activeElement instanceof HTMLElement) {
              document.activeElement.blur();
            }
          });
          await page.waitForTimeout(350);
          await page.screenshot({
            path: path.join(outDir, `login-cover-slide-${idx + 1}-${vp.label}.png`),
          });

          // Verify no CSS upscaling at 1440, 1920, 390
          if (vp.label !== "1024") {
            const scaleCheck = await page.evaluate(async (activeIdx) => {
              const img = document.querySelectorAll(".dps-slideshow img[alt]")[activeIdx];
              if (!img) return { ok: false };
              const rect = img.getBoundingClientRect();
              const src = img.currentSrc || img.src;
              const probe = new Image();
              probe.src = src;
              if (!probe.complete) {
                await new Promise((res) => {
                  probe.onload = res;
                  probe.onerror = res;
                });
              }
              const naturalWidth = probe.naturalWidth || img.naturalWidth;
              const naturalHeight = probe.naturalHeight || img.naturalHeight;
              return {
                currentSrc: src.split("/").pop(),
                naturalWidth,
                naturalHeight,
                displayWidth: Math.round(rect.width),
                displayHeight: Math.round(rect.height),
                ok: naturalWidth >= rect.width - 1 && naturalHeight >= rect.height - 1,
              };
            }, idx);
            report.noCssUpscaling.push({ viewport: vp.label, slide: idx + 1, ...scaleCheck });
            if (!scaleCheck.ok) report.passed = false;
          }

          // Capture 100% face-area crop on slide 2 (trophy) and slide 3 (art) at 1920x1080
          if (vp.label === "1920" && (idx === 1 || idx === 2)) {
            await page.screenshot({
              path: path.join(outDir, `face-crop-slide-${idx + 1}-1920.png`),
              clip: { x: 220, y: 120, width: 520, height: 420 },
            });
          }

          await page.locator(".dps-slideshow").focus();
          await page.keyboard.press("ArrowRight");
          await page.waitForTimeout(1300);
        }
      }

      // Test auto-advance at 1440x900
      await page.setViewportSize({ width: 1440, height: 900 });
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

      report.axe.push(await runAxe(page, "/"));

      // Login form error styling check: untouched fields must NOT have aria-invalid="true";
      // invalid only after blur/submit; check show/hide password and sign-up mode.
      await page.setViewportSize({ width: 1440, height: 900 });
      const initialInvalidCount = await page.locator('input[aria-invalid="true"]').count();
      await page.locator('input[name="email"]').focus();
      await page.locator('input[name="email"]').blur();
      const emailInvalidAfterEmptyBlur = await page.locator('input[name="email"]').getAttribute("aria-invalid");
      await page.locator('input[name="password"]').fill("short");
      await page.locator('input[name="password"]').blur();
      const passwordInvalidAfterShortBlur = await page.locator('input[name="password"]').getAttribute("aria-invalid");
      const showBtn = page.getByRole("button", { name: "Show password" });
      await showBtn.click();
      const passwordTypeAfterShow = await page.locator('input[name="password"]').getAttribute("type");
      await page.getByRole("button", { name: /Create one/i }).click();
      const nameInputVisibleInSignUp = await page.locator('input[name="name"]').isVisible();
      const signUpInitialInvalidCount = await page.locator('input[aria-invalid="true"]').count();
      report.formErrorStylingCheck = {
        initialInvalidCount,
        emailInvalidAfterEmptyBlur,
        passwordInvalidAfterShortBlur,
        passwordTypeAfterShow,
        nameInputVisibleInSignUp,
        signUpInitialInvalidCount,
        passed:
          initialInvalidCount === 0 &&
          emailInvalidAfterEmptyBlur === "true" &&
          passwordInvalidAfterShortBlur === "true" &&
          passwordTypeAfterShow === "text" &&
          nameInputVisibleInSignUp &&
          signUpInitialInvalidCount === 0,
      };
      if (!report.formErrorStylingCheck.passed) report.passed = false;
      // Switch back to sign-in mode cleanly
      await page.getByRole("button", { name: /Sign in$/i }).last().click();

      // Route-change focus ring check: skip on first load, no outline on [data-route-heading], outline on focused button
      await page.goto(`${baseUrl}/nonexistent-route`, { waitUntil: "networkidle" });
      const firstLoadFocusedH1 = await page.evaluate(() => document.activeElement?.tagName === "H1");
      await page.locator('a[href="/"]').first().click();
      await page.waitForSelector('h1[data-route-heading]');
      const headingFocusState = await page.evaluate(() => {
        const el = document.activeElement;
        const st = el ? getComputedStyle(el) : null;
        return {
          tagName: el?.tagName,
          hasAttr: el?.hasAttribute("data-route-heading") ?? false,
          outlineStyle: st?.outlineStyle ?? "",
          outlineWidth: st?.outlineWidth ?? "",
        };
      });
      // Tab until we reach a button to confirm keyboard focus ring IS visible on buttons
      let buttonFocusState = { tagName: "", outlineStyle: "none", outlineWidth: "0px" };
      for (let t = 0; t < 12; t++) {
        await page.keyboard.press("Tab");
        buttonFocusState = await page.evaluate(() => {
          const el = document.activeElement;
          const st = el ? getComputedStyle(el) : null;
          return {
            tagName: el?.tagName ?? "",
            outlineStyle: st?.outlineStyle ?? "",
            outlineWidth: st?.outlineWidth ?? "",
          };
        });
        if (buttonFocusState.tagName === "BUTTON") break;
      }
      report.routeFocusCheck = {
        skippedFirstLoad: !firstLoadFocusedH1,
        heading: headingFocusState,
        button: buttonFocusState,
        passed:
          !firstLoadFocusedH1 &&
          headingFocusState.tagName === "H1" &&
          headingFocusState.hasAttr &&
          (headingFocusState.outlineStyle === "none" || headingFocusState.outlineWidth === "0px") &&
          buttonFocusState.tagName === "BUTTON" &&
          buttonFocusState.outlineStyle !== "none" &&
          buttonFocusState.outlineWidth !== "0px",
      };
      if (!report.routeFocusCheck.passed) report.passed = false;

      // Reduced motion context
      const rmContext = await browser.newContext({
        viewport: { width: 1280, height: 800 },
        reducedMotion: "reduce",
      });
      const rmPage = await rmContext.newPage();
      await rmPage.goto(baseUrl, { waitUntil: "networkidle" });
      const rmBefore = await getActiveSlideIndex(rmPage);
      await rmPage.waitForTimeout(6500);
      const rmAfter = await getActiveSlideIndex(rmPage);
      report.slideshow.reducedMotionStopsAutoAdvance = rmBefore === rmAfter;
      if (!report.slideshow.reducedMotionStopsAutoAdvance) report.passed = false;
      await rmContext.close();

      // Google button branding, contrast, focus/hover crops, and 1440/390/360 checks
      const googleIconRequests = [];
      const gContext = await browser.newContext({ viewport: { width: 1440, height: 900 } });
      const gPage = await gContext.newPage();
      gPage.on("request", (req) => {
        const url = req.url().toLowerCase();
        if (url.includes("google") || url.includes("gstatic") || url.includes("fonts.googleapis")) {
          googleIconRequests.push(req.url());
        }
      });
      await gPage.goto(baseUrl, { waitUntil: "networkidle" });
      const gBtn = gPage.locator("button.auth-google");
      await gBtn.waitFor({ state: "visible" });
      await gPage.screenshot({ path: path.join(outDir, "google-btn-signin-1440.png") });

      const signInAudit = await gPage.evaluate(() => {
        const btn = document.querySelector("button.auth-google");
        const svg = btn?.querySelector("svg");
        const fills = svg ? Array.from(svg.querySelectorAll("path")).map((p) => p.getAttribute("fill")) : [];
        const st = btn ? getComputedStyle(btn) : null;
        const parseRgb = (s) => {
          const m = s.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
          return m ? [Number(m[1]), Number(m[2]), Number(m[3])] : [0, 0, 0];
        };
        const lum = ([r, g, b]) => {
          const a = [r, g, b].map((v) => {
            const c = v / 255;
            return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
          });
          return 0.2126 * a[0] + 0.7152 * a[1] + 0.0722 * a[2];
        };
        const fg = st ? parseRgb(st.color) : [0, 0, 0];
        const bg = st ? parseRgb(st.backgroundColor) : [255, 255, 255];
        const l1 = Math.max(lum(fg), lum(bg));
        const l2 = Math.min(lum(fg), lum(bg));
        const contrastRatio = (l1 + 0.05) / (l2 + 0.05);
        const bodyText = document.body.innerText;
        return {
          text: btn?.textContent?.trim() ?? "",
          ariaHidden: svg?.getAttribute("aria-hidden"),
          fills,
          contrastRatio: Number(contrastRatio.toFixed(2)),
          height: btn?.getBoundingClientRect().height ?? 0,
          hasUnableToSignIn: bodyText.includes("Unable to sign in") || bodyText.includes("Google sign-in could not be started"),
        };
      });

      // Hover crop
      await gBtn.hover();
      await gPage.waitForTimeout(150);
      await gBtn.screenshot({ path: path.join(outDir, "google-btn-hover-zoom.png") });

      // Focus-visible crop (Tab onto button)
      await gBtn.focus();
      await gPage.keyboard.press("Shift+Tab");
      await gPage.keyboard.press("Tab");
      await gPage.waitForTimeout(150);
      const focusRing = await gPage.evaluate(() => {
        const btn = document.querySelector("button.auth-google");
        const st = btn ? getComputedStyle(btn) : null;
        return { outlineWidth: st?.outlineWidth ?? "", outlineStyle: st?.outlineStyle ?? "" };
      });
      await gBtn.screenshot({ path: path.join(outDir, "google-btn-focus-zoom.png") });

      // Sign-up mode 1440
      await gPage.getByRole("button", { name: /Don't have an account\? Create one/i }).click();
      await gPage.waitForTimeout(150);
      const signUpText1440 = (await gBtn.textContent())?.trim() ?? "";
      await gPage.screenshot({ path: path.join(outDir, "google-btn-signup-1440.png") });

      // Mobile 390 and 360 single-line checks
      await gPage.setViewportSize({ width: 390, height: 844 });
      await gPage.waitForTimeout(150);
      await gPage.screenshot({ path: path.join(outDir, "google-btn-signup-390.png") });
      await gPage.getByRole("button", { name: /Already have an account\? Sign in/i }).click();
      await gPage.waitForTimeout(150);
      await gPage.screenshot({ path: path.join(outDir, "google-btn-signin-390.png") });

      const mobile390 = await gPage.evaluate(() => {
        const btn = document.querySelector("button.auth-google");
        const span = btn?.querySelector("span");
        const r = document.createRange();
        if (span) r.selectNodeContents(span);
        return {
          height: btn?.getBoundingClientRect().height ?? 0,
          overflowX: btn ? btn.scrollWidth > btn.clientWidth : true,
          lineCount: span ? r.getClientRects().length : 0,
        };
      });

      await gPage.setViewportSize({ width: 360, height: 800 });
      await gPage.waitForTimeout(150);
      const mobile360 = await gPage.evaluate(() => {
        const btn = document.querySelector("button.auth-google");
        const span = btn?.querySelector("span");
        const r = document.createRange();
        if (span) r.selectNodeContents(span);
        return {
          height: btn?.getBoundingClientRect().height ?? 0,
          overflowX: btn ? btn.scrollWidth > btn.clientWidth : true,
          lineCount: span ? r.getClientRects().length : 0,
        };
      });

      const expectedFills = ["#EA4335", "#4285F4", "#FBBC05", "#34A853"];
      report.googleButtonCheck = {
        signInAudit,
        signUpText1440,
        focusRing,
        mobile390,
        mobile360,
        externalIconRequests: googleIconRequests,
        passed:
          signInAudit.text === "Sign in with Google" &&
          signUpText1440 === "Sign up with Google" &&
          signInAudit.ariaHidden === "true" &&
          JSON.stringify(signInAudit.fills) === JSON.stringify(expectedFills) &&
          signInAudit.contrastRatio >= 4.5 &&
          signInAudit.height >= 44 &&
          focusRing.outlineWidth === "3px" &&
          mobile390.height >= 44 && !mobile390.overflowX && mobile390.lineCount === 1 &&
          mobile360.height >= 44 && !mobile360.overflowX && mobile360.lineCount === 1 &&
          googleIconRequests.length === 0,
      };
      if (!report.googleButtonCheck.passed) report.passed = false;
      await gContext.close();

      await context.close();
    } finally {
      await browser.close();
    }
  } finally {
    await close();
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
