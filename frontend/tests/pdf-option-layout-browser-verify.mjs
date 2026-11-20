import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
let playwright;
try { playwright = require("playwright"); } catch {
  const cache = path.join(os.homedir(), ".npm/_npx");
  for (const folder of fs.readdirSync(cache)) {
    const candidate = path.join(cache, folder, "node_modules/playwright");
    if (fs.existsSync(candidate)) { playwright = require(candidate); break; }
  }
}
assert(playwright, "Use an existing Playwright installation");
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const out = path.join(root, "output/pdf/option-separation");
fs.mkdirSync(out, { recursive: true });
const FRONTEND = "http://127.0.0.1:5181", BACKEND = "http://127.0.0.1:8031";
const sessions = {};
for (const role of ["ADMIN", "STUDENT"]) {
  sessions[role] = await (await fetch(`${BACKEND}/__test_session?role=${role}`)).json();
  assert(sessions[role].test_session, "Only run against the isolated test backend");
}
async function api(route, method = "GET", body, role = "ADMIN") {
  const form = body instanceof FormData;
  const response = await fetch(`${BACKEND}${route}`, {
    method, headers: { Authorization: `Bearer ${sessions[role].token}`,
      ...(form ? {} : { "Content-Type": "application/json" }) },
    body: body ? (form ? body : JSON.stringify(body)) : undefined,
  });
  assert(response.ok, `${method} ${route} returned ${response.status}`);
  return response.json();
}
const brave = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser";
const browser = await playwright.chromium.launch(fs.existsSync(brave)
  ? { executablePath: brave, headless: true } : { headless: true });
const errors = [], checks = [], httpFailures = [];
const check = (message) => { checks.push(message); console.log(message); };
const adminContext = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const adminPage = await adminContext.newPage();
const watchErrors = (page) => {
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("response", async (response) => {
    if (response.status() >= 400) httpFailures.push({
      status: response.status(), path: new URL(response.url()).pathname,
      body: await response.json().catch(() => null),
    });
  });
};
watchErrors(adminPage);
adminPage.setDefaultTimeout(30000);
const widths = [320, 360, 375, 390, 412, 768, 1024, 1280, 1440];
async function noOverflow(page, label) {
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), label);
}
async function waitImages(page, scope = page) {
  const element = await (scope === page ? page.locator("body") : scope).elementHandle();
  await page.waitForFunction((root) => {
    const images = [...root.querySelectorAll("img")];
    images.forEach((image) => { image.loading = "eager"; });
    return images.length > 0 && images.every((image) => image.complete && image.naturalWidth > 0);
  }, element);
  await element.dispose();
}
try {
  await adminPage.goto(`${FRONTEND}/admin/exams/new`, { waitUntil: "networkidle" });
  await adminPage.getByLabel(/Examination title/).fill("PDF answer separation browser check");
  await adminPage.getByLabel(/Retake policy: maximum attempts/).fill("8");
  await adminPage.getByRole("checkbox", { name: /Randomize option order/ }).check();
  const createdResponse = adminPage.waitForResponse((r) => r.request().method() === "POST" &&
    r.url() === `${BACKEND}/api/admin/exams`);
  await adminPage.getByRole("button", { name: "Create Draft Exam", exact: true }).click();
  const exam = await (await createdResponse).json();
  assert.equal(exam.randomize_options, true);
  check("Real admin checkbox persists randomize_options=true");
  const data = await (await fetch(`${BACKEND}/__test_paper`)).arrayBuffer();
  const form = new FormData();
  form.set("file", new Blob([data], { type: "application/pdf" }), "triangles.pdf");
  form.set("answer_key_text", "1 B\n2 A");
  const imported = await api(`/api/admin/exams/${exam.id}/import-pdf`, "POST", form);
  assert.equal(imported.valid_count, 2);
  const questions = imported.valid_questions.map((q, i) => ({
    question_text: q.question_text, source_file_id: q.source_file_id,
    source_number: q.source_number, pdf_options_text: q.pdf_options_text, position: i,
    points: "2.00", options: q.options.map((o) => ({ ...o, is_correct: o.label === q.answer_label })),
  }));
  const saved = await api(`/api/admin/exams/${exam.id}/questions`, "PUT", { questions });
  await adminPage.goto(`${FRONTEND}/admin/exams/${exam.id}`, { waitUntil: "networkidle" });
  await adminPage.getByRole("tab", { name: "Questions (2)", exact: true }).click();
  const panel = adminPage.getByRole("region", { name: "Separate PDF question and answers", exact: true });
  await panel.getByRole("button", { name: "Prepare answer preview", exact: true }).click();
  await panel.getByRole("heading", { name: "Answer A", exact: true }).waitFor();
  assert.equal(await panel.getByRole("button", { name: "Confirm separated answers", exact: true }).isDisabled(), true);
  check("Preview does not allow confirmation before review");
  await panel.getByRole("button", { name: "Adjust answer A crop 1", exact: true }).click();
  const dialog = adminPage.getByRole("dialog", { name: "Adjust answer A", exact: true });
  await dialog.getByLabel("Crop left", { exact: true }).waitFor();
  await waitImages(adminPage, dialog);
  const left = Number(await dialog.getByLabel("Crop left", { exact: true }).inputValue());
  await dialog.getByLabel("Crop left", { exact: true }).fill(String(left + 1));
  await dialog.getByRole("button", { name: "Apply crop", exact: true }).click();
  await panel.getByText("Preview out of date.", { exact: false }).waitFor();
  for (const label of ["A", "B", "C", "D"]) {
    await panel.getByLabel(`Display answer ${label} as`, { exact: true }).selectOption("text");
  }
  await panel.getByRole("button", { name: "Regenerate answer preview", exact: true }).click();
  const review = panel.getByRole("checkbox", { name: /I checked that the question/ });
  await review.waitFor();
  await review.check();
  await panel.getByRole("button", { name: "Confirm separated answers", exact: true }).click();
  await panel.getByText("Separate answers are confirmed for this question.", { exact: true }).waitFor();
  check("Keyboard crop coordinates, text mode, regeneration, explicit confirmation");
  await panel.getByLabel("Saved PDF question", { exact: true }).selectOption(saved.questions[1].id);
  await panel.getByRole("button", { name: "Prepare answer preview", exact: true }).click();
  await panel.getByRole("heading", { name: "Answer A", exact: true }).waitFor();
  await panel.getByRole("checkbox", { name: /I checked that the question/ }).check();
  await panel.getByRole("button", { name: "Confirm separated answers", exact: true }).click();
  await panel.getByText("Separate answers are confirmed for this question.", { exact: true }).waitFor();
  check("Separate image answers confirmed without changing marks/answer key");
  const confirmed = await api(`/api/admin/exams/${exam.id}`);
  const first = confirmed.questions[0];
  const assets = { source: first.image_urls[0], stem: first.option_layout.stem_urls[0],
    ...Object.fromEntries(first.option_layout.options.map((o) => [`answer-${o.label}`, o.image_urls[0]])) };
  for (const [name, route] of Object.entries(assets)) {
    const response = await fetch(`${BACKEND}${route}`, { headers: { Authorization: `Bearer ${sessions.ADMIN.token}` } });
    assert(response.ok);
    fs.writeFileSync(path.join(out, `${name}.png`), Buffer.from(await response.arrayBuffer()));
  }
  await panel.getByLabel("Saved PDF question", { exact: true }).selectOption(saved.questions[0].id);
  await panel.getByRole("button", { name: "Prepare answer preview", exact: true }).click();
  await panel.getByRole("heading", { name: "Answer A", exact: true }).waitFor();
  await waitImages(adminPage, panel);
  for (const width of widths) {
    await adminPage.setViewportSize({ width, height: 1000 });
    await noOverflow(adminPage, `Admin preview overflow at ${width}`);
    if ([320, 768, 1440].includes(width)) {
      await panel.scrollIntoViewIfNeeded();
      await adminPage.screenshot({ path: path.join(out, `admin-${width}.png`), fullPage: true });
    }
  }
  check("Admin preview: nine responsive widths without horizontal overflow");
  await adminPage.setViewportSize({ width: 320, height: 1000 });
  await panel.getByRole("button", { name: "Adjust answer A crop 1", exact: true }).click();
  await dialog.getByLabel("Crop left", { exact: true }).waitFor();
  await waitImages(adminPage, dialog);
  await noOverflow(adminPage, "Crop dialog overflow");
  await adminPage.screenshot({ path: path.join(out, "crop-dialog.png") });
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  const discardedResponse = adminPage.waitForResponse((r) => r.request().method() === "DELETE" && r.url().includes("/option-layout/preview/"));
  await panel.getByRole("button", { name: "Discard answer preview", exact: true }).click();
  assert.equal((await discardedResponse).status(), 204);
  await api(`/api/admin/exams/${exam.id}/publish`, "POST");
  const studentContext = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  await studentContext.addInitScript(() => localStorage.setItem("layout-browser-role", "STUDENT"));
  const student = await studentContext.newPage();
  student.setDefaultTimeout(30000); watchErrors(student);
  const started = await api(`/api/exams/${exam.id}/attempts`, "POST", {}, "STUDENT");
  const delivery = await api(`/api/attempts/${started.attempt_id}`, "GET", undefined, "STUDENT");
  await student.goto(`${FRONTEND}/student/attempts/${started.attempt_id}`, { waitUntil: "networkidle" });
  for (let index = 0; index < 2; index++) {
    const q = delivery.questions[index];
    await student.getByRole("heading", { name: `Question ${index + 1} of 2`, exact: true }).waitFor();
    await waitImages(student);
    assert.equal(q.options_in_image, false);
    assert.deepEqual(await student.locator('input[type="radio"]').evaluateAll((nodes) => nodes.map((n) => n.value)),
      q.options.map((o) => o.id));
    const correctId = saved.questions[index].options.find((o) => o.is_correct).id;
    const answer = student.locator(`label:has(input[value="${correctId}"])`);
    const savedResponse = student.waitForResponse((r) => r.request().method() === "PUT" &&
      r.url().includes(`/answers/${q.id}`));
    await answer.click();
    assert.equal((await savedResponse).status(), 200);
    for (const width of widths) {
      await student.setViewportSize({ width, height: 1000 });
      await noOverflow(student, `Student option overflow at ${width}`);
      for (const option of q.options) {
        const card = student.locator(`label:has(input[value="${option.id}"])`);
        const content = card.locator(":scope > span").nth(1);
        const box = await content.boundingBox();
        assert(box && box.width >= 40 && box.height >= 18, `Answer content must be visible at ${width}`);
        if (option.image_urls.length) {
          assert.equal(await content.locator("img").count(), option.image_urls.length);
        } else assert.equal(await content.innerText(), option.option_text);
      }
      if ([320, 768, 1440].includes(width)) {
        await student.screenshot({ path: path.join(out, `student-${index + 1}-${width}.png`), fullPage: true });
      }
    }
    await student.setViewportSize({ width: 1440, height: 1000 });
    const before = await api(`/api/attempts/${started.attempt_id}`, "GET", undefined, "STUDENT");
    await student.reload({ waitUntil: "networkidle" });
    const after = await api(`/api/attempts/${started.attempt_id}`, "GET", undefined, "STUDENT");
    assert.deepEqual(after.questions, before.questions);
    assert.equal(after.expires_at, before.expires_at);
    assert.equal(after.saved_answers[q.id], correctId);
    await student.locator(`input[value="${correctId}"]`).waitFor({ state: "attached" });
    assert.equal(await student.locator(`input[value="${correctId}"]`).isChecked(), true);
    if (!index) await student.getByRole("button", { name: "Next", exact: true }).first().click();
  }
  check("Student text/image options follow API UUID order; UI autosave and refresh preserve selection/deadline");
  check("Both student presentation modes: nine responsive widths without horizontal overflow");
  await student.getByRole("button", { name: "Review & Submit", exact: true }).first().click();
  const submission = student.waitForResponse((r) => r.request().method() === "POST" && r.url().endsWith("/submit"));
  await student.getByRole("dialog", { name: "Review & Submit Examination?", exact: true })
    .getByRole("button", { name: "Submit Examination", exact: true }).click();
  const result = await (await submission).json();
  assert.equal(result.percentage, "100.00");
  check("Browser-selected answers graded 100% after mixed PDF option shuffling");
  assert.deepEqual(httpFailures, []);
  assert.deepEqual(errors, []);
  const summary = { checks, widths, consoleErrors: errors, httpFailures, status: "passed" };
  fs.writeFileSync(path.join(out, "browser-results.json"), JSON.stringify(summary, null, 2));
  console.log(JSON.stringify(summary, null, 2));
  await studentContext.close();
} catch (error) {
  await adminPage.screenshot({ path: path.join(out, "browser-failure.png"), fullPage: true }).catch(() => {});
  fs.writeFileSync(path.join(out, "browser-errors.json"), JSON.stringify({ errors, httpFailures }, null, 2));
  throw error;
} finally {
  await browser.close();
}
