import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(__dirname, "..");
const srcDir = path.join(frontendDir, "src");

function walkFiles(dir, exts) {
  const results = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...walkFiles(full, exts));
    } else if (exts.some((ext) => entry.name.endsWith(ext))) {
      results.push(full);
    }
  }
  return results;
}

const LEGACY_COLOR_TOKENS = [
  /#a3123f/gi,
  /#8a0f35/gi,
  /#9f1239/gi,
  /#881337/gi,
  /#fdf0f4/gi,
  /#fff1f2/gi,
  /#fecdd3/gi,
  /#f08aa6/gi,
  /#6d0d2d/gi,
  /#cf3f68/gi,
  /#17121d/gi,
  /#f6f5f8/gi,
  /#16121c/gi,
  /#f0eef3/gi,
  /#f5c2d1/gi,
  /163\s+18\s+63/g,
  /22\s+18\s+28/g,
];

const RETIRED_CLASS_PATTERNS = [
  /\bportal-hero\b/g,
  /\bportal-stat\b/g,
  /\bportal-panel\b/g,
  /\bauth-story\b/g,
];

test("legacy-style guard: zero old wine/crimson tokens or retired portal/auth-story classes in frontend/src", () => {
  const allFiles = walkFiles(srcDir, [".ts", ".tsx", ".css"]);
  const violations = [];
  for (const file of allFiles) {
    const content = fs.readFileSync(file, "utf8");
    const rel = path.relative(frontendDir, file).replace(/\\/g, "/");
    for (const pattern of LEGACY_COLOR_TOKENS) {
      const matches = content.match(pattern);
      if (matches) {
        violations.push(`${rel}: ${matches.join(", ")}`);
      }
    }
    for (const pattern of RETIRED_CLASS_PATTERNS) {
      const matches = content.match(pattern);
      if (matches) {
        violations.push(`${rel}: ${matches.join(", ")}`);
      }
    }
  }
  assert.deepEqual(violations, [], `Legacy wine/portal tokens found:\n${violations.join("\n")}`);
});

test("legacy-style guard: fails on simulated old wine token and allows DPS green tokens", () => {
  const sampleOld = "color: #a3123f; background: rgb(163 18 63 / 0.1);";
  const sampleNew = "color: var(--brand); background: rgb(6 122 31 / 0.1);";
  assert.ok(LEGACY_COLOR_TOKENS.some((re) => re.test(sampleOld)));
  assert.ok(!LEGACY_COLOR_TOKENS.some((re) => re.test(sampleNew)));
});

test("style baseline metrics scan across frontend/src outside token files", () => {
  const allFiles = walkFiles(srcDir, [".ts", ".tsx", ".css"]);
  const nonTokenFiles = allFiles.filter((f) => {
    const norm = f.replace(/\\/g, "/");
    return !norm.endsWith("/src/index.css") && !norm.endsWith("/src/features/student/student-console.css");
  });

  let hardHex = 0;
  let hardRgb = 0;
  let rawTailwindPalette = 0;
  let hardFontSizes = 0;
  let hardSpacing = 0;

  const twPaletteRe =
    /\b(?:bg|text|border|ring|fill|stroke)-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3}\b/g;

  for (const file of nonTokenFiles) {
    const content = fs.readFileSync(file, "utf8");
    hardHex += (content.match(/#[0-9a-fA-F]{3,8}\b/g) ?? []).length;
    hardRgb += (content.match(/\brgba?\(/g) ?? []).length;
    rawTailwindPalette += (content.match(twPaletteRe) ?? []).length;
    hardFontSizes += (content.match(/\btext-\[\d+(?:\.\d+)?(?:px|rem)\]|font-size\s*:/g) ?? []).length;
    hardSpacing += (content.match(/\b(?:p|px|py|pt|pb|pl|pr|m|mx|my|mt|mb|ml|mr|gap)-\[\d+(?:\.\d+)?(?:px|rem)\]/g) ?? []).length;
  }

  console.log(
    JSON.stringify({
      legacyStyleBaselineCheck: {
        scannedNonTokenFiles: nonTokenFiles.length,
        hardcodedHexOutsideTokenFiles: hardHex,
        hardcodedRgbOutsideTokenFiles: hardRgb,
        rawTailwindPaletteClasses: rawTailwindPalette,
        totalColorViolationsOutsideTokenFiles: hardHex + hardRgb + rawTailwindPalette,
        arbitraryFontSizesOutsideTokenFiles: hardFontSizes,
        arbitrarySpacingOutsideTokenFiles: hardSpacing,
      },
    }),
  );

  // Ensure 0 non-token color violations remain outside token files
  assert.equal(hardHex, 0, "Expected 0 hardcoded hex colors outside token files");
  assert.equal(hardRgb, 0, "Expected 0 hardcoded rgb() colors outside token files");
  assert.equal(rawTailwindPalette, 0, "Expected 0 raw Tailwind palette classes");
});
