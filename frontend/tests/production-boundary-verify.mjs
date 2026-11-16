// Inspect the real production module graph without changing the production config.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { build } from "vite";

const output = path.resolve("../output/pdf/recrop-verification");
const modules = [];
await build({
  build: { write: false },
  plugins: [{
    name: "record-production-boundary",
    generateBundle(_options, bundle) {
      for (const chunk of Object.values(bundle)) {
        if (chunk.type !== "chunk") continue;
        for (const [id, info] of Object.entries(chunk.modules)) {
          modules.push({ id: id.replaceAll("\\", "/"), renderedLength: info.renderedLength });
        }
        assert(!/__test_session|browser-test-admin|importer-test-auth|DPCIS_BROWSER_TEST/.test(chunk.code));
      }
    },
  }],
});
assert(!modules.some(({ id }) => /\/tests\/(importer|vite\.importer)/.test(id)));
fs.writeFileSync(path.join(output, "production-modules.json"), JSON.stringify(modules, null, 2));
const audit = JSON.parse(fs.readFileSync(path.join(output, "audit-full.json"), "utf8"));
const lock = JSON.parse(fs.readFileSync("package-lock.json", "utf8"));
const summary = Object.entries(audit.vulnerabilities)
  .filter(([, v]) => ["high", "critical"].includes(v.severity))
  .map(([name, v]) => ({
    package: name, severity: v.severity,
    versions: v.nodes.map((node) => ({ path: node, version: lock.packages[node]?.version })),
    emitted: modules.filter((m) => v.nodes.some((node) => m.id.includes(`/${node}/`)) && m.renderedLength > 0),
    advisories: v.via,
  }));
fs.writeFileSync(path.join(output, "audit-bundle-reachability.json"), JSON.stringify(summary, null, 2));
console.log("Production boundary: no test modules or test-session markers emitted.");
console.log(summary.map((v) => `${v.package}: ${v.emitted.length} emitted modules`).join("\n"));
