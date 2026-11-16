import test from "node:test";
import assert from "node:assert/strict";

import {
  groupParserErrors,
  parseFlexibleAnswerKey,
} from "../src/features/admin/validationGroups.ts";

test("groupParserErrors groups 28 repetitive errors into concise categories", () => {
  const errors = [
    { block_index: 0, message: "Answer key has 27 answers but 24 questions were detected" },
    ...Array.from({ length: 27 }, (_, idx) => ({
      block_index: idx + 1,
      message: "Select a correct answer (A-D).",
    })),
  ];
  const groups = groupParserErrors(errors);
  assert.equal(groups.length, 1);
  assert.equal(groups[0].id, "answer-key");
  assert.equal(groups[0].items.length, 28);
});

test("groupParserErrors separates crop, answer-key, and formatting groups", () => {
  const groups = groupParserErrors([
    { block_index: 4, message: "Crop failed: partially clipped graphic" },
    { block_index: 16, message: "Crop failed: non-white pixels touch border" },
    { block_index: 0, message: "Answer key has 10 answers" },
    { block_index: 2, message: "Missing option D" },
  ]);
  assert.deepEqual(
    groups.map((g) => g.id),
    ["answer-key", "crop", "formatting"],
  );
  assert.match(groups[1].summary, /Q4, Q16/);
});

test("parseFlexibleAnswerKey normalizes all supported formats", () => {
  assert.deepEqual(parseFlexibleAnswerKey("1. B\n2. C"), { 1: "B", 2: "C" });
  assert.deepEqual(parseFlexibleAnswerKey("1) B\n2) C"), { 1: "B", 2: "C" });
  assert.deepEqual(parseFlexibleAnswerKey("1-B\n2-C"), { 1: "B", 2: "C" });
  assert.deepEqual(parseFlexibleAnswerKey("1: B\n2: C"), { 1: "B", 2: "C" });
  assert.deepEqual(parseFlexibleAnswerKey("Q1 B\nQ2 C"), { 1: "B", 2: "C" });
  assert.deepEqual(parseFlexibleAnswerKey("B, C, D"), { 1: "B", 2: "C", 3: "D" });
  assert.deepEqual(parseFlexibleAnswerKey("BCDA"), { 1: "B", 2: "C", 3: "D", 4: "A" });
});
