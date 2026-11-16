import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "../..");
const out = path.join(root, "output/pdf/recrop-verification");
const screenshots = path.join(root, "docs/ui-screenshots/importer-verify");
fs.mkdirSync(screenshots, { recursive: true });
fs.mkdirSync(out, { recursive: true });
const require = createRequire(import.meta.url);
let playwright;
try { playwright = require("playwright"); } catch {
  const cache = path.join(process.env.LOCALAPPDATA, "npm-cache/_npx");
  for (const folder of fs.readdirSync(cache)) {
    const candidate = path.join(cache, folder, "node_modules/playwright");
    if (fs.existsSync(candidate)) { playwright = require(candidate); break; }
  }
}
assert(playwright, "Existing Playwright installation required; no packages are installed by this script");
let browser;
for (const options of [{ headless: true }, { headless: true, channel: "chrome" }, { headless: true, channel: "msedge" }]) {
  try { browser = await playwright.chromium.launch(options); break; } catch { /* next installed browser */ }
}
assert(browser, "No installed Chromium browser available");
const session = await fetch("http://127.0.0.1:8000/__test_session").then((r) => r.json());
assert(session.test_session, "Must use isolated test backend");
async function api(url, method = "GET", body) {
  const response = await fetch(`http://127.0.0.1:8000${url}`, {
    method, headers: { Authorization: `Bearer ${session.token}`, "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  assert(response.ok, `API ${method} ${url}: ${response.status}`);
  return response.json();
}
const results = [];
for (const width of (process.env.VERIFY_WIDTHS || "1440,1024,768,390").split(",").map(Number)) {
  const context = await browser.newContext({ viewport: { width, height: 1000 } });
  const page = await context.newPage();
  page.setDefaultTimeout(30000);
  const result = { width, checks: [], errors: [], screenshots: [] };
  const expectedHttpErrors = [];
  let stage = "start";
  page.on("pageerror", (error) => result.errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() !== "error") return;
    // Chromium logs the deliberate clipping rejection as a resource error.
    if (/Failed to load resource.*422/.test(message.text())) expectedHttpErrors.push(message.text());
    else result.errors.push(message.text());
  });
  async function screenshot(name, locator) {
    if (locator) await locator.scrollIntoViewIfNeeded();
    const filename = `${width}-${name}.png`;
    await page.screenshot({ path: path.join(screenshots, filename) });
    result.screenshots.push(`docs/ui-screenshots/importer-verify/${filename}`);
    result.viewport = await page.evaluate(() => {
      const nav = document.querySelector('.admin-nav');
      return { document: document.documentElement.scrollWidth, inner: innerWidth,
        nav: nav?.getBoundingClientRect().toJSON(), overflow: nav && getComputedStyle(nav).overflowX };
    });
    result.overflow = await page.evaluate(() => [...document.querySelectorAll("body *")]
      .filter((el) => el.getBoundingClientRect().right > innerWidth)
      .map((el) => ({ tag: el.tagName, class: el.className, width: el.getBoundingClientRect().width,
        text: ["A", "BUTTON", "SPAN"].includes(el.tagName) ? el.textContent : undefined,
        right: el.getBoundingClientRect().right, parent: el.parentElement?.className })));
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `Horizontal overflow: ${name}`);
  }
  async function upload(filename, key) {
    await page.getByRole("tab", { name: "Questions", exact: true }).click();
    await page.locator('input[type="file"]').first().setInputFiles(path.join(root, "backend/tests/fixtures", filename));
    await page.getByRole("tab", { name: "Answer key", exact: true }).click();
    await page.getByLabel("Answers used for marking").fill(key);
    const response = page.waitForResponse((r) => r.url().endsWith("/import-pdf") && r.request().method() === "POST", { timeout: 120000 });
    await page.getByRole("button", { name: "Preview Questions", exact: true }).click();
    const imported = await response;
    assert.equal(imported.status(), 200);
    return imported.json();
  }
  async function drag(name, delta, expected) {
    const handle = page.getByRole("button", { name, exact: true }).first();
    await handle.scrollIntoViewIfNeeded();
    await page.waitForTimeout(150);
    const box = await handle.boundingBox();
    assert(box);
    const response = page.waitForResponse((r) => r.url().endsWith("/crops") && r.request().method() === "PUT");
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2 + delta, { steps: 5 });
    await page.mouse.up();
    const received = await response;
    assert.equal(received.status(), expected);
    const body = await received.json();
    await page.waitForFunction(() => [...document.querySelectorAll('button[aria-label^="Drag"]')].every((el) => !el.disabled));
    await page.waitForFunction(() => [...document.querySelectorAll('img[src^="blob:"]')].every((img) => img.complete && img.naturalWidth > 0));
    return body;
  }
  try {
    const exam = await api("/api/admin/exams", "POST", {
      title: `Importer browser confirmation ${width}`, duration_minutes: 45, pass_mark: 50,
    });
    result.exam_id = exam.id;
    await page.goto(`http://127.0.0.1:5173/admin/exams/${exam.id}`, { waitUntil: "domcontentloaded", timeout: 120000 });
    await page.getByRole("tab", { name: "Questions (0)", exact: true }).click();
    stage = "invalid upload";
    const invalid = await upload("graphics_boundaries.pdf", "AAA");
    assert.equal(invalid.invalid_questions.length, 2);
    await screenshot("invalid-preview", page.getByText("Needs attention:", { exact: false }).first());
    await page.getByRole("button", { name: "Add questions needing fixes (2)", exact: true }).click();
    await page.getByText("Repair failed crops in the preview before importing these questions.").waitFor();
    result.checks.push("Invalid vector crops rejected in preview and blocked from import");
    stage = "valid upload";
    const manifest = JSON.parse(fs.readFileSync(path.join(root,
      "backend/tests/fixtures/pdfs/cie_igcse_chem_2_2_atomic_structure_qp.expected.json"), "utf8"));
    const key = Object.entries(manifest.expected_key).map(([n, answer]) => `${n} ${answer}`).join("\n");
    const valid = await upload("pdfs/cie_igcse_chem_2_2_atomic_structure_qp.pdf", key);
    assert.equal(valid.valid_count, 24);
    await page.getByRole("button", { name: "Drag top crop edge for page 1", exact: true }).first().waitFor();
    await page.waitForFunction(() => [...document.querySelectorAll('img[src^="blob:"]')].length > 0 &&
      [...document.querySelectorAll('img[src^="blob:"]')].every((img) => img.complete && img.naturalWidth > 0));
    result.checks.push("PDF upload and 24-question graphics-aware preview");
    stage = "top drag";
    const topCrop = await drag("Drag top crop edge for page 1", -4, 200);
    stage = "invalid bottom drag";
    // Aim through a text line using PDF geometry, not a viewport-specific pixel guess.
    const handle = page.getByRole("button", { name: "Drag bottom crop edge for page 1", exact: true }).first();
    await handle.scrollIntoViewIfNeeded();
    const imageHeight = await handle.evaluate((el) => el.parentElement.querySelector("img").getBoundingClientRect().height);
    const region = topCrop.regions[0].bbox;
    const delta = -(region[3] - 215) * imageHeight / (region[3] - region[1]);
    await drag("Drag bottom crop edge for page 1", delta, 422);
    await screenshot("invalid-drag", page.getByRole("alert").last());
    result.checks.push("Top drag accepted; deliberate bottom clipping rejected (422), old image kept");
    stage = "bottom drag";
    await drag("Drag bottom crop edge for page 1", 3, 200);
    await screenshot("crop-editor", handle);
    result.checks.push("Bottom drag accepted");
    stage = "import";
    const addReadyBtn = page.getByRole("button", { name: "Add ready questions (24)", exact: true });
    const ackBoxes = page.getByLabel(/Acknowledge crop warnings for question/i);
    const ackCount = await ackBoxes.count();
    if (ackCount > 0) {
      assert.equal(await addReadyBtn.isDisabled(), true, "Warnings must block import until acknowledged");
      for (let k = 0; k < ackCount; k++) {
        await ackBoxes.nth(k).check();
      }
      result.checks.push(`Confirmed warning acknowledgment gate (${ackCount} flagged questions)`);
    }
    await addReadyBtn.click();
    const saved = page.waitForResponse((r) => r.url().endsWith(`/exams/${exam.id}/questions`) && r.request().method() === "PUT");
    await page.getByRole("button", { name: "Save Questions", exact: true }).first().click();
    assert.equal((await saved).status(), 200);
    const before = await api(`/api/admin/exams/${exam.id}`);
    assert.equal(before.questions.length, 24);
    result.checks.push("Imported and saved 24 questions through browser UI");
    stage = "recrop preview";
    await page.getByRole("button", { name: "Re-crop from stored PDF", exact: true }).click();
    const approve = page.getByLabel("Approve re-crop for question 1", { exact: true });
    await approve.waitFor({ timeout: 120000 });
    await page.getByAltText("Question 1 after crop 1").waitFor();
    await page.waitForFunction(() => {
      const image = document.querySelector('img[alt="Question 1 after crop 1"]');
      return image?.complete && image.naturalWidth > 0;
    });
    await screenshot("recrop-before-after", approve);
    assert.deepEqual((await api(`/api/admin/exams/${exam.id}`)).questions, before.questions);
    await approve.check();
    const applied = page.waitForResponse((r) => /recrop-preview\/[^/]+\/apply$/.test(r.url()));
    await page.getByRole("button", { name: "Apply 1 approved re-crop", exact: true }).click();
    assert.equal((await applied).status(), 200);
    const after = await api(`/api/admin/exams/${exam.id}`);
    const selectedId = before.questions.find((question) => question.position === 0).id;
    before.questions.forEach((question) => {
      const updated = after.questions.find((item) => item.id === question.id);
      for (const key of ["id", "question_text", "points", "options", "position"])
        assert.deepEqual(updated[key], question[key]);
      assert.equal(updated.source_file_id !== question.source_file_id, question.id === selectedId);
      if (question.id !== selectedId) assert.deepEqual(updated, question);
    });
    result.checks.push("Before/after preview read-only; only approved Q1 changed; keys and marks identical");
    await page.getByRole("tab", { name: "Questions (24)", exact: true }).waitFor();
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "Horizontal overflow");
    assert.equal(result.errors.length, 0, "Browser runtime errors");
    result.status = "passed";
    result.expected_http_errors = expectedHttpErrors.length;
  } catch (error) {
    result.status = "failed"; result.stage = stage; result.failure = error.message;
    await screenshot("failure").catch(() => {});
  } finally {
    results.push(result);
    fs.writeFileSync(path.join(out, "browser-results.json"), JSON.stringify(results, null, 2));
    console.log(JSON.stringify({ width, status: result.status, stage: result.stage, checks: result.checks, failure: result.failure }));
    await context.close();
  }
}
await browser.close();
if (results.some((r) => r.status !== "passed")) process.exitCode = 1;
