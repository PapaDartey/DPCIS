import type { OptionLabel, ParseQuestionsError } from "@/types/adminExam";

export interface ValidationGroup {
  id: string;
  label: string;
  summary: string;
  items: ParseQuestionsError[];
}

export function groupParserErrors(errors: ParseQuestionsError[]): ValidationGroup[] {
  const answerKey: ParseQuestionsError[] = [];
  const crop: ParseQuestionsError[] = [];
  const formatting: ParseQuestionsError[] = [];

  for (const err of errors) {
    const msg = err.message.toLowerCase();
    if (msg.startsWith("crop failed:") || msg.includes("crop")) {
      crop.push(err);
    } else if (err.block_index === 0 || msg.includes("answer key") || msg.includes("answer")) {
      answerKey.push(err);
    } else {
      formatting.push(err);
    }
  }

  const groups: ValidationGroup[] = [];
  if (answerKey.length > 0) {
    groups.push({
      id: "answer-key",
      label: "Answer key",
      summary:
        answerKey.length === 1
          ? answerKey[0].message
          : `${answerKey.length} answer-key entries need review`,
      items: answerKey,
    });
  }
  if (crop.length > 0) {
    const nums = [...new Set(crop.map((e) => e.block_index).filter((n) => n > 0))];
    groups.push({
      id: "crop",
      label: "Crop review",
      summary:
        nums.length > 0
          ? `${crop.length} crop issue${crop.length === 1 ? "" : "s"} (Q${nums.join(", Q")})`
          : `${crop.length} crop issue${crop.length === 1 ? "" : "s"}`,
      items: crop,
    });
  }
  if (formatting.length > 0) {
    const nums = [...new Set(formatting.map((e) => e.block_index).filter((n) => n > 0))];
    groups.push({
      id: "formatting",
      label: "Formatting",
      summary:
        nums.length > 0
          ? `${formatting.length} formatting issue${formatting.length === 1 ? "" : "s"} (Q${nums.join(", Q")})`
          : formatting[0].message,
      items: formatting,
    });
  }
  return groups;
}

/**
 * Parse flexible answer-key formats client-side for instant non-destructive
 * assignment to already-cropped PDF questions without re-uploading the PDF.
 */
export function parseFlexibleAnswerKey(raw: string): Record<number, OptionLabel> {
  const result: Record<number, OptionLabel> = {};
  const trimmed = raw.trim();
  if (!trimmed) return result;

  const compact = trimmed.replace(/\s+/g, "");
  if (/^[A-Da-d]+$/.test(compact)) {
    [...compact].forEach((ch, idx) => {
      result[idx + 1] = ch.toUpperCase() as OptionLabel;
    });
    return result;
  }

  const commaTokens = trimmed.split(",").map((s) => s.trim()).filter(Boolean);
  if (commaTokens.length > 1 && commaTokens.every((t) => /^[A-Da-d]$/.test(t))) {
    commaTokens.forEach((t, idx) => {
      result[idx + 1] = t.toUpperCase() as OptionLabel;
    });
    return result;
  }

  const lines = trimmed.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  if (lines.length > 0 && lines.every((l) => /^[A-Da-d]$/.test(l))) {
    lines.forEach((l, idx) => {
      result[idx + 1] = l.toUpperCase() as OptionLabel;
    });
    return result;
  }

  const entryPattern = /(?:^|[\s,;])(?:Q(?:uestion)?\s*)?(\d{1,4})\s*(?:[.):-]|\s)\s*([A-Da-d])\b/gi;
  for (const line of lines) {
    let match: RegExpExecArray | null;
    entryPattern.lastIndex = 0;
    while ((match = entryPattern.exec(line)) !== null) {
      const num = Number.parseInt(match[1], 10);
      if (num >= 1) result[num] = match[2].toUpperCase() as OptionLabel;
    }
  }
  return result;
}
