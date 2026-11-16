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
assert(playwright, "Existing Playwright installation required");
const { chromium } = playwright;

const FRONTEND = "http://127.0.0.1:5173";
const BACKEND = "http://127.0.0.1:8000";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const outDir = path.join(root, "docs/ui-screenshots/importer-verify/real");

let authToken = "";

async function api(route, options = {}) {
  const res = await fetch(`${BACKEND}${route}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${authToken}`,
      ...(options.headers ?? {}),
    },
  });
  assert.ok(res.ok, `${route} -> ${res.status}`);
  return res.json();
}

async function runWidth(browser, width) {
  const context = await browser.newContext({ viewport: { width, height: 900 } });
  const page = await context.newPage();
  const consoleErrors = [];
  page.on("pageerror", (err) => consoleErrors.push(err.message));
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });

  const exam = await api("/api/admin/exams", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: `Real Scan Verify ${width}`,
      subject: "Physics",
      duration_minutes: 30,
      passing_score: 50,
    }),
  });

  await page.goto(`${FRONTEND}/admin/exams/${exam.id}`, { waitUntil: "networkidle" });
  await page.getByRole("tab", { name: "Questions (0)", exact: true }).click();
  await page.getByRole("tab", { name: "Questions", exact: true }).click();
  await page.locator('input[type="file"]').first().setInputFiles(
    path.join(root, "docs/ui-screenshots/importer-verify/j1.jpg"),
  );
  await page.getByRole("tab", { name: "Answer key", exact: true }).click();
  await page.getByLabel("Answers used for marking").fill("1 A\n2 B\n3 C\n4 A\n5 B");
  const parsePromise = page.waitForResponse((r) => r.url().endsWith("/import-pdf") && r.request().method() === "POST");
  await page.getByRole("button", { name: "Preview Questions", exact: true }).click();
  const parsed = await (await parsePromise).json();
  assert.equal(parsed.valid_count, 5);

  const addReadyBtn = page.getByRole("button", { name: /Add ready questions/i });
  assert.equal(await addReadyBtn.isDisabled(), true, "Scan warnings must block import until acknowledged");

  const tStart = Date.now();

  // Merge Q2+Q3 (P 9) and new Q3+Q4 (P 10) -> 3 questions total
  await page.getByRole("button", { name: "Merge with next question", exact: true }).nth(1).click();
  await page.getByRole("button", { name: "Merge questions", exact: true }).click();
  await page.getByRole("button", { name: "Merge with next question", exact: true }).nth(2).waitFor();
  await page.getByRole("button", { name: "Merge with next question", exact: true }).nth(2).click();
  await page.getByRole("button", { name: "Merge questions", exact: true }).click();
  await page.waitForFunction(() => document.querySelectorAll('button[aria-label^="Drag left crop edge"]').length === 3);
  await page.screenshot({ path: path.join(outDir, `real-${width}-merged.png`), fullPage: false });

  // Left and right edge drag on Q1
  const leftEdge = page.getByRole("button", { name: "Drag left crop edge for page 1", exact: true }).first();
  await leftEdge.scrollIntoViewIfNeeded();
  const lb = await leftEdge.boundingBox();
  const put1 = page.waitForResponse((r) => r.url().includes("/crops") && r.request().method() === "PUT");
  await page.mouse.move(lb.x + lb.width / 2, lb.y + lb.height / 2);
  await page.mouse.down();
  await page.mouse.move(lb.x + lb.width / 2 + 4, lb.y + lb.height / 2, { steps: 3 });
  await page.mouse.up();
  assert.equal((await put1).status(), 200);

  const rightEdge = page.getByRole("button", { name: "Drag right crop edge for page 1", exact: true }).first();
  const rb = await rightEdge.boundingBox();
  const put2 = page.waitForResponse((r) => r.url().includes("/crops") && r.request().method() === "PUT");
  await page.mouse.move(rb.x + rb.width / 2, rb.y + rb.height / 2);
  await page.mouse.down();
  await page.mouse.move(rb.x + rb.width / 2 - 4, rb.y + rb.height / 2, { steps: 3 });
  await page.mouse.up();
  assert.equal((await put2).status(), 200);

  // Coordinate input + Add same page region + 220 DPI re-render
  const leftInput = page.getByLabel("Region 1 left", { exact: true }).first();
  await leftInput.fill("2");
  await page.getByRole("button", { name: "Add same page region", exact: true }).first().click();
  const region2Left = page.getByLabel("Region 2 left", { exact: true }).first();
  await region2Left.waitFor({ state: "visible" });
  await page.getByLabel("DPI", { exact: true }).first().fill("220");
  const put3 = page.waitForResponse((r) => r.url().includes("/crops") && r.request().method() === "PUT");
  await page.getByRole("button", { name: "Regenerate crops", exact: true }).first().click();
  assert.equal((await put3).status(), 200);
  await page.screenshot({ path: path.join(outDir, `real-${width}-crop-edit.png`), fullPage: false });

  const manualFixMs = Date.now() - tStart;
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  assert.equal(overflow, false, `Horizontal overflow at ${width}px`);
  assert.deepEqual(consoleErrors, [], `Unexpected console errors: ${consoleErrors.join("; ")}`);

  await context.close();
  return { width, status: "passed", manualFixMs, mergedCount: 3 };
}

const session = await (await fetch(`${BACKEND}/__test_session`)).json();
assert(session.test_session, "Must use isolated test backend");
authToken = session.token;
let browser;
for (const options of [{ headless: true }, { headless: true, channel: "chrome" }, { headless: true, channel: "msedge" }]) {
  try { browser = await chromium.launch(options); break; } catch { /* next */ }
}
assert(browser, "No Chromium browser available");
try {
  const r1440 = await runWidth(browser, 1440);
  const r390 = await runWidth(browser, 390);
  console.log(JSON.stringify([r1440, r390], null, 2));
} finally {
  await browser.close();
}
