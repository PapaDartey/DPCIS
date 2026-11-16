import assert from "node:assert/strict";
import fs from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
let playwright;
try { playwright = require("playwright"); } catch {
  const cache = path.join(process.env.LOCALAPPDATA, "npm-cache/_npx");
  for (const folder of fs.readdirSync(cache)) {
    const candidate = path.join(cache, folder, "node_modules/playwright");
    if (fs.existsSync(candidate)) { playwright = require(candidate); break; }
  }
}
assert(playwright, "Playwright installation required");
const { chromium } = playwright;

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "../..");
const outDir = path.join(root, "docs/ui-screenshots/question-map");
fs.mkdirSync(outDir, { recursive: true });

const mode = process.env.QM_PHASE ?? "after";
const BASE_URL = process.env.QM_URL ?? "http://127.0.0.1:4173";

function buildDelivery(count, answeredIndices = [0, 1]) {
  const now = Date.now();
  const questions = Array.from({ length: count }, (_, idx) => ({
    id: `q-${idx + 1}`,
    display_order: idx + 1,
    question_text: `Sample Question ${idx + 1}: Which option is correct?`,
    image_urls: [],
    points: 1,
    options: [
      { id: `q-${idx + 1}-a`, label: "A", option_text: "Option A" },
      { id: `q-${idx + 1}-b`, label: "B", option_text: "Option B" },
      { id: `q-${idx + 1}-c`, label: "C", option_text: "Option C" },
      { id: `q-${idx + 1}-d`, label: "D", option_text: "Option D" },
    ],
  }));
  const saved_answers = Object.fromEntries(
    answeredIndices.map((idx) => [`q-${idx + 1}`, `q-${idx + 1}-a`]),
  );
  return {
    attempt_id: "attempt-qm",
    exam_id: "exam-qm",
    exam_title: `Question Map Validation (${count}Q)`,
    duration_minutes: 60,
    status: "IN_PROGRESS",
    started_at: new Date(now - 60_000).toISOString(),
    expires_at: new Date(now + 3_540_000).toISOString(),
    server_now: new Date(now).toISOString(),
    total_questions: count,
    questions,
    saved_answers,
  };
}

async function openAttempt(browser, { width, height, count, answeredIndices }) {
  const context = await browser.newContext({ viewport: { width, height } });
  const page = await context.newPage();
  const consoleErrors = [];
  page.on("pageerror", (e) => consoleErrors.push(e.message));
  page.on("console", (m) => {
    if (m.type() === "error") consoleErrors.push(m.text());
  });

  await page.route("**/__test_session", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        test_session: true,
        token: "student-test-token",
        role: "STUDENT",
        user: {
          id: "user-1",
          email: "student@dpsghana.edu.gh",
          name: "Student Tester",
        },
      }),
    }),
  );

  await page.route("**/auth/me", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "user-1",
        email: "student@dpsghana.edu.gh",
        full_name: "Student Tester",
        role: "STUDENT",
      }),
    }),
  );

  await page.route("**/api/attempts/attempt-qm", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(buildDelivery(count, answeredIndices)),
    }),
  );

  await page.route("**/api/attempts/attempt-qm/answers/**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ saved: true }),
    }),
  );

  await page.goto(`${BASE_URL}/student/attempts/attempt-qm`, { waitUntil: "networkidle" });
  await page.locator(".student-attempt-grid").waitFor({ state: "visible" });
  return { context, page, consoleErrors };
}

async function inspectTiles(page, containerSelector) {
  return page.evaluate((sel) => {
    const container = document.querySelector(sel);
    if (!container) return { present: false };
    const buttons = [...container.querySelectorAll("button")];
    const rects = buttons.map((b) => {
      const r = b.getBoundingClientRect();
      const statusSpan = b.querySelector("span:nth-of-type(2)");
      const sr = statusSpan?.getBoundingClientRect();
      return {
        label: b.getAttribute("aria-label") ?? "",
        text: statusSpan?.textContent?.trim() ?? "",
        width: Number(r.width.toFixed(1)),
        height: Number(r.height.toFixed(1)),
        left: Number(r.left.toFixed(1)),
        right: Number(r.right.toFixed(1)),
        top: Number(r.top.toFixed(1)),
        bottom: Number(r.bottom.toFixed(1)),
        clipped: statusSpan ? statusSpan.scrollWidth > statusSpan.clientWidth + 1 : false,
        statusFitsInsideButton: sr ? sr.right <= r.right + 0.5 && sr.left >= r.left - 0.5 : true,
      };
    });
    let overlapCount = 0;
    for (let i = 0; i < rects.length; i++) {
      for (let j = i + 1; j < rects.length; j++) {
        const a = rects[i], b = rects[j];
        if (a.left < b.right - 0.5 && a.right > b.left + 0.5 && a.top < b.bottom - 0.5 && a.bottom > b.top + 0.5) {
          overlapCount++;
        }
      }
    }
    const cols = new Set(rects.map((r) => Math.round(r.left))).size;
    return {
      present: true,
      tileCount: rects.length,
      columns: cols,
      anyClipped: rects.some((r) => r.clipped || !r.statusFitsInsideButton),
      minWidth: Math.min(...rects.map((r) => r.width)),
      minHeight: Math.min(...rects.map((r) => r.height)),
      overlapCount,
      horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      gridHorizontalOverflow: container.scrollWidth > container.clientWidth + 1,
      sampleUnanswered: rects.find((r) => r.text === "Unanswered") ?? null,
      sampleCurrent: rects.find((r) => r.text === "Current") ?? null,
      sampleAnswered: rects.find((r) => r.text === "Answered") ?? null,
    };
  }, containerSelector);
}

let browser;
for (const options of [{ headless: true }, { headless: true, channel: "chrome" }, { headless: true, channel: "msedge" }]) {
  try { browser = await chromium.launch(options); break; } catch { /* next */ }
}
assert(browser, "No Chromium browser available");

try {
  if (mode === "before") {
    const { context, page } = await openAttempt(browser, { width: 1440, height: 900, count: 24, answeredIndices: [0, 2] });
    await page.locator("aside.student-question-map").screenshot({ path: path.join(outDir, "before-1440-map.png") });
    await page.screenshot({ path: path.join(outDir, "before-1440-full.png") });
    const stats = await inspectTiles(page, ".student-question-map-grid");
    console.log("BEFORE_1440:", JSON.stringify(stats));
    await context.close();
  } else {
    const results = [];
    // Desktop 1440 & 1280 across 1, 5, 10, 24, 50, 100 questions + states
    for (const [w, count, answered] of [
      [1440, 24, [0, 2]],
      [1280, 24, []],
      [1440, 1, [0]],
      [1440, 5, [0, 1, 2, 3, 4]],
      [1440, 10, [1, 4, 8]],
      [1440, 50, [0, 5, 10, 25, 49]],
      [1440, 100, [0, 20, 50, 99]],
    ]) {
      const { context, page, consoleErrors } = await openAttempt(browser, { width: w, height: 900, count, answeredIndices: answered });
      if (w === 1440 && count === 24) {
        // Navigate to Q2 so Current, Answered, and Unanswered are all visible
        await page.locator(".student-question-map-grid button").nth(1).click();
        await page.locator(".student-question-map-grid button").nth(1).waitFor();
        await page.waitForTimeout(100);
        await page.locator("aside.student-question-map").screenshot({ path: path.join(outDir, "after-1440-map.png") });
        await page.screenshot({ path: path.join(outDir, "after-1440-full.png") });
        // Keyboard navigation: focus Q3 tile and press Enter
        await page.locator(".student-question-map-grid button").nth(2).focus();
        await page.keyboard.press("Enter");
        await page.waitForFunction(() => document.querySelectorAll(".student-question-map-grid button")[2]?.getAttribute("aria-current") === "step");
        // Navigate to last question (Q24)
        await page.locator(".student-question-map-grid button").nth(count - 1).click();
        await page.waitForFunction((n) => document.querySelectorAll(".student-question-map-grid button")[n - 1]?.getAttribute("aria-current") === "step", count);
      }
      if (w === 1440 && count === 100) {
        await page.locator("aside.student-question-map").screenshot({ path: path.join(outDir, "after-1440-100q-map.png") });
      }
      const stats = await inspectTiles(page, ".student-question-map-grid");
      assert.equal(stats.anyClipped, false, `Clipped tile in ${w}px ${count}Q`);
      assert.equal(stats.overlapCount, 0, `Overlapping tiles in ${w}px ${count}Q`);
      assert.equal(stats.horizontalOverflow, false, `Page overflow in ${w}px ${count}Q`);
      assert.equal(stats.gridHorizontalOverflow, false, `Grid overflow in ${w}px ${count}Q`);
      assert.deepEqual(consoleErrors, [], `Console errors: ${consoleErrors.join("; ")}`);
      results.push({ width: w, count, ...stats });
      await context.close();
    }

    // Tablet 768 and Mobile 390, 320 via Question Navigator dialog
    for (const w of [768, 390, 320]) {
      const { context, page, consoleErrors } = await openAttempt(browser, { width: w, height: 844, count: 24, answeredIndices: [0, 2] });
      await page.getByRole("button", { name: /Open question (navigator|map)/i }).first().click();
      const dialogGrid = page.getByRole("dialog").locator(".grid");
      await dialogGrid.waitFor({ state: "visible" });
      await page.screenshot({ path: path.join(outDir, `after-${w}-navigator.png`) });
      const stats = await inspectTiles(page, 'dialog .grid, [role="dialog"] .grid');
      assert.equal(stats.anyClipped, false, `Clipped tile in mobile dialog ${w}px`);
      assert.equal(stats.overlapCount, 0, `Overlapping tiles in mobile dialog ${w}px`);
      assert.equal(stats.horizontalOverflow, false, `Page overflow at ${w}px`);
      assert.deepEqual(consoleErrors, [], `Console errors at ${w}px`);
      results.push({ width: w, dialog: true, count: 24, ...stats });
      await context.close();
    }

    console.log("AFTER_RESULTS:", JSON.stringify(results, null, 2));
  }
} finally {
  await browser.close();
}
