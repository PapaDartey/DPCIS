import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

function violations(manifest) {
  const found = [];
  function inspect(entries, location) {
    for (const [name, value] of Object.entries(entries ?? {})) {
      const field = `${location}.${name}`;
      if (/^dpcis(?:@|$)/.test(name)) found.push(field);
      if (typeof value === "string" && /^(file:|link:)/.test(value)) {
        found.push(field);
      } else if (value && typeof value === "object") {
        inspect(value, field);
      }
    }
  }
  for (const section of ["dependencies", "devDependencies", "overrides"]) {
    inspect(manifest[section], section);
  }
  return found;
}

test("dependency guard: no local file/link dependencies or dpcis self-reference", () => {
  const manifest = JSON.parse(fs.readFileSync(new URL("../package.json", import.meta.url), "utf8"));
  assert.deepEqual(violations(manifest), []);
});

test("dependency guard: rejects local paths and nested self-reference overrides", () => {
  for (const section of ["dependencies", "devDependencies", "overrides"]) {
    for (const entry of [{ example: "file:.." }, { example: "link:../" }, { dpcis: "*" }]) {
      assert.ok(violations({ [section]: entry }).length > 0);
    }
  }
  assert.ok(violations({ overrides: { parent: { ".": "file:.." } } }).length > 0);
  assert.ok(violations({ overrides: { parent: { "dpcis@*": "1.0.0" } } }).length > 0);
  assert.deepEqual(violations({ dependencies: { react: "^19.0.0" }, overrides: { parent: { child: "1.0.0" } } }), []);
});
