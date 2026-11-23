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
const out = path.join(root, "output/pdf/question-number-removal");
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

async function saveImage(route, name, role = "ADMIN") {
  const response = await fetch(`${BACKEND}${route}`, { headers: { Authorization: `Bearer ${sessions[role].token}` } });
  assert(response.ok);
  fs.writeFileSync(path.join(out, name), Buffer.from(await response.arrayBuffer()));
}
try {
  const exam = await api("/api/admin/exams", "POST", {
    title: "Number-free shuffled image questions", duration_minutes: 45,
    randomize_questions: true, randomize_options: true, show_result: true,
  });
  const pdf = Buffer.from(await (await fetch(`${BACKEND}/__test_number_paper`)).arrayBuffer());
  fs.writeFileSync(path.join(out, "source-paper.pdf"), pdf);
  const form = new FormData();
  form.set("file", new Blob([pdf], { type: "application/pdf" }), "numbered-figures.pdf");
  form.set("answer_key_text", "1 B\n2 B\n3 B");
  const imported = await api(`/api/admin/exams/${exam.id}/import-pdf`, "POST", form);
  assert.equal(imported.valid_count, 3);
  const saved = await api(`/api/admin/exams/${exam.id}/questions`, "PUT", {
    questions: imported.valid_questions.map((q, i) => ({
      question_text: q.question_text, source_file_id: q.source_file_id, source_number: q.source_number,
      position: i, points: "1.00", options: q.options.map((o) => ({ ...o, is_correct: o.label === q.answer_label })),
    })),
  });
  const sourceById = new Map(saved.questions.map((q) => [q.id, q.source_number]));
  const first = saved.questions[0];
  const base = `/api/admin/exams/${exam.id}/questions/${first.id}/option-layout`;
  const preview = await api(`${base}/preview`, "POST", {});
  assert(preview.valid, JSON.stringify(preview.warnings));
  await api(`${base}/confirm`, "POST", { preview_id: preview.preview_id, confirm: true });
  check("New full-question crops and reviewed split stems prepared from real PDF data");
  await api(`/api/admin/exams/${exam.id}/publish`, "POST");
  const studentContext = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  await studentContext.addInitScript(() => localStorage.setItem("layout-browser-role", "STUDENT"));
  const student = await studentContext.newPage(); watchErrors(student);
  const started = await api(`/api/exams/${exam.id}/attempts`, "POST", {}, "STUDENT");
  const route = `/api/attempts/${started.attempt_id}`;
  const delivery = await api(route, "GET", undefined, "STUDENT");
  const orders = delivery.questions.map((q, i) => ({ display: i + 1, source: sourceById.get(q.id) }));
  await student.goto(`${FRONTEND}/student/attempts/${started.attempt_id}`, { waitUntil: "networkidle" });
  for (const [index, question] of delivery.questions.entries()) {
    const number = sourceById.get(question.id);
    await student.getByRole("heading", { name: `Question ${index + 1} of 3`, exact: true }).waitFor();
    await waitImages(student);
    assert(!new RegExp(`^${number}\\s`).test(question.question_text));
    const stem = student.locator("fieldset img").first();
    await stem.scrollIntoViewIfNeeded();
    assert.equal(await stem.isVisible(), true);
    assert(!new RegExp(`^${number}\\s`).test(await stem.getAttribute("alt")));
    await saveImage(question.image_urls[0], `student-source-${number}.png`, "STUDENT");
    const correct = saved.questions.find((q) => q.id === question.id).options.find((o) => o.is_correct).id;
    const autosaved = student.waitForResponse((r) => r.request().method() === "PUT" && r.url().includes(`/answers/${question.id}`));
    await student.locator(`label:has(input[value="${correct}"])`).click();
    assert.equal((await autosaved).status(), 200);
    for (const width of widths) {
      await student.setViewportSize({ width, height: 1000 });
      await noOverflow(student, `Student question overflow at ${width}`);
      if ([320, 768, 1440].includes(width)) {
        await student.screenshot({ path: path.join(out, `student-source-${number}-${width}.png`), fullPage: true });
      }
    }
    await student.setViewportSize({ width: 1440, height: 1000 });
    if (index === 1) {
      await student.reload({ waitUntil: "networkidle" });
      const resumed = await api(route, "GET", undefined, "STUDENT");
      assert.deepEqual(resumed.questions, delivery.questions);
      assert.equal(resumed.expires_at, delivery.expires_at);
      assert.equal(resumed.saved_answers[question.id], correct);
    }
    if (index < 2) await student.getByRole("button", { name: "Next", exact: true }).first().click();
  }
  check("Shuffled student images: only the application question number; saved answers/order/deadline survive refresh");
  await student.getByRole("button", { name: "Review & Submit", exact: true }).first().click();
  const submitted = student.waitForResponse((r) => r.request().method() === "POST" && r.url().endsWith("/submit"));
  await student.getByRole("dialog", { name: "Review & Submit Examination?", exact: true })
    .getByRole("button", { name: "Submit Examination", exact: true }).click();
  assert.equal((await (await submitted).json()).percentage, "100.00");
  check("Correct selections grade 100% with question and option randomization enabled");

  const manualExam = await api("/api/admin/exams", "POST", { title: "Scanned question number review", duration_minutes: 45 });
  await adminPage.goto(`${FRONTEND}/admin/exams/${manualExam.id}`, { waitUntil: "networkidle" });
  await adminPage.getByRole("tab", { name: "Questions (0)", exact: true }).click();
  const scan = Buffer.from(await (await fetch(`${BACKEND}/__test_number_paper?scan=true`)).arrayBuffer());
  await adminPage.locator('input[type="file"]').first().setInputFiles({ name: "scanned-questions.pdf", mimeType: "application/pdf", buffer: scan });
  const scanImported = adminPage.waitForResponse((r) => r.request().method() === "POST" && r.url().endsWith("/import-pdf"));
  await adminPage.getByRole("button", { name: "Preview Questions", exact: true }).click();
  assert.equal((await scanImported).status(), 200);
  await adminPage.getByRole("button", { name: "Draw question from PDF page", exact: true }).click();
  const dialog = adminPage.getByRole("dialog", { name: "Draw new question crop from PDF page", exact: true });
  await waitImages(adminPage, dialog);
  for (const [label, value] of Object.entries({ left: 20, top: 34, right: 570, bottom: 450 })) {
    await dialog.getByLabel(`Crop ${label}`, { exact: true }).fill(String(value));
  }
  await dialog.getByRole("button", { name: "Mark question number", exact: true }).click();
  for (const [label, value] of Object.entries({ left: 49, top: 41, right: 58, bottom: 60 })) {
    await dialog.getByLabel(`Number area ${label}`, { exact: true }).fill(String(value));
  }
  for (const width of widths) {
    await adminPage.setViewportSize({ width, height: 1000 });
    await noOverflow(adminPage, `Number crop editor overflow at ${width}`);
    if ([320, 768, 1440].includes(width)) {
      await adminPage.screenshot({ path: path.join(out, `manual-number-${width}.png`) });
    }
  }
  const cropped = adminPage.waitForResponse((r) => r.request().method() === "PUT" && r.url().endsWith("/crops"));
  await dialog.getByRole("button", { name: "Apply crop", exact: true }).click();
  const cropResponse = await cropped;
  assert.equal(cropResponse.status(), 200);
  const rendered = await cropResponse.json();
  assert.deepEqual(rendered.regions[0].number_bbox, [49, 41, 58, 60]);
  await dialog.waitFor({ state: "hidden" });
  await saveImage(rendered.image_urls[0], "scan-number-removed.png");
  check("Scanned paper: real UI manual number box, keyboard coordinates, crop regeneration and private image delivery");
  check("Student images and manual crop editor: nine responsive widths without horizontal overflow");
  assert.deepEqual(httpFailures, []);
  assert.deepEqual(errors, []);
  const summary = { checks, widths, orders, consoleErrors: errors, httpFailures, status: "passed" };
  fs.writeFileSync(path.join(out, "browser-results.json"), JSON.stringify(summary, null, 2));
  console.log(JSON.stringify(summary, null, 2));
  await studentContext.close();
} catch (error) {
  await adminPage.screenshot({ path: path.join(out, "browser-failure.png"), fullPage: true }).catch(() => {});
  fs.writeFileSync(path.join(out, "browser-errors.json"), JSON.stringify({ errors, httpFailures }, null, 2));
  throw error;
} finally { await browser.close(); }
