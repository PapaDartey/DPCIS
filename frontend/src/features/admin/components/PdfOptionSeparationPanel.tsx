import { useState } from "react";

import { AuthenticatedPdfImage } from "@/components/exam/AuthenticatedPdfImage";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { PdfPageCropModal, type PageCropRegion } from "@/features/admin/components/PdfPageCropModal";
import { apiDelete, apiPost } from "@/lib/api";
import type { ImageRegion, PdfOptionLayout, QuestionAdminOut } from "@/types/adminExam";

interface Preview {
  question_id: string;
  preview_id: string | null;
  valid: boolean;
  warnings: string[];
  page_dimensions: Array<[number, number]>;
  layout: PdfOptionLayout;
}

interface Props {
  examId: string;
  questions: QuestionAdminOut[];
  disabled: boolean;
  onApplied: () => void;
}

/** Only saved draft questions can acquire a reviewed, shuffleable layout. */
export function PdfOptionSeparationPanel({ examId, questions, disabled, onApplied }: Props) {
  const pdfQuestions = questions.filter((q) => q.source_file_id && q.source_number);
  const [questionId, setQuestionId] = useState("");
  const question = pdfQuestions.find((q) => q.id === questionId) ?? pdfQuestions[0];
  const [preview, setPreview] = useState<Preview | null>(null);
  const [layout, setLayout] = useState<PdfOptionLayout | null>(null);
  const [dirty, setDirty] = useState(false);
  const [reviewed, setReviewed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [crop, setCrop] = useState<{ part: number; index: number } | null>(null);
  const base = `/api/admin/exams/${examId}/questions/${question?.id}/option-layout`;
  const readyTexts = layout?.options.every((o) => o.option_text.trim()) &&
    new Set(layout?.options.map((o) => o.option_text.trim().replace(/\s+/g, " ").toLowerCase())).size === layout?.options.length;

  const change = (next: PdfOptionLayout) => {
    setLayout(next); setDirty(true); setReviewed(false); setMessage(null);
  };
  const generate = async (automatic: boolean) => {
    if (!question) return;
    setBusy(true); setReviewed(false); setMessage(null);
    try {
      const body = automatic ? {} : { layout: {
        stem: layout?.stem.map(({ page, bbox }) => ({ page, bbox })),
        options: layout?.options.map(({ label, mode, option_text, regions }) => ({
          label, mode, option_text,
          regions: regions.map(({ page, bbox }) => ({ page, bbox })),
        })),
      } };
      const result = await apiPost<Preview>(`${base}/preview`, { body, timeoutMs: 120000 });
      setPreview(result); setLayout(result.layout); setDirty(false);
      if (!result.valid) setMessage("Adjust the crop boundaries, then regenerate the preview.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not prepare separate answers.");
    } finally { setBusy(false); }
  };
  const confirm = async () => {
    if (!preview?.preview_id || dirty || !reviewed) return;
    setBusy(true); setMessage(null);
    try {
      await apiPost(`${base}/confirm`, { body: { preview_id: preview.preview_id, confirm: true } });
      setPreview(null); setLayout(null); setReviewed(false);
      onApplied();
      setMessage("Separate answers confirmed. This question can now use the exam's option-shuffling setting.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not confirm the split. Original images kept.");
    } finally { setBusy(false); }
  };
  const discard = async () => {
    setBusy(true); setMessage(null);
    try {
      if (preview?.preview_id) await apiDelete(`${base}/preview/${preview.preview_id}`);
      setPreview(null); setLayout(null); setReviewed(false); setDirty(false);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not discard the preview.");
    } finally { setBusy(false); }
  };
  const updateRegions = (part: number, regions: ImageRegion[]) => {
    if (!layout) return;
    change(part < 0 ? { ...layout, stem: regions } : {
      ...layout, options: layout.options.map((o, i) => i === part ? { ...o, regions } : o),
    });
  };
  const regionsEditor = (part: number, regions: ImageRegion[], title: string) => {
    const cropName = title[0].toLowerCase() + title.slice(1);
    return (
    <div className="flex flex-wrap gap-2">
      {regions.map((_, index) => <div key={index} className="flex flex-wrap gap-1">
        <Button type="button" variant="outline" disabled={disabled || busy}
          onClick={() => setCrop({ part, index })}>
          Adjust {cropName} crop {index + 1}
        </Button>
        {regions.length > 1 ? <Button type="button" variant="ghost" disabled={disabled || busy}
          aria-label={`Remove ${cropName} crop ${index + 1}`}
          onClick={() => updateRegions(part, regions.filter((_, i) => i !== index))}>
          Remove
        </Button> : null}
      </div>)}
      <Button type="button" variant="ghost" disabled={disabled || busy || regions.length >= 20}
        onClick={() => updateRegions(part, [...regions, structuredClone(regions[regions.length - 1])])}>
        Add {cropName} crop
      </Button>
    </div>
    );
  };
  const selectedRegions = crop && layout ? (crop.part < 0 ? layout.stem : layout.options[crop.part].regions) : [];
  const selectedRegion = crop ? selectedRegions[crop.index] : null;

  if (!question) return null;
  return <section aria-label="Separate PDF question and answers" className="min-w-0 space-y-4 rounded-xl border border-border bg-card p-4 sm:p-5">
    <h2 className="text-lg font-semibold">Separate answers for shuffling</h2>
    <p className="text-sm text-muted-foreground">
      Keep the question and figure together. Review each answer as a separate image or text.
      Original images stay available until you confirm a split on a draft examination.
    </p>
    {disabled ? <p className="text-sm">Save or discard pending edits first. Splitting is available for draft exams.</p> : null}
    <Label className="flex min-w-0 flex-col gap-2">Saved PDF question
      <select className="min-h-11 w-full max-w-full rounded-md border border-input bg-background p-2 text-sm"
        aria-label="Saved PDF question" value={question.id} disabled={busy || disabled}
        onChange={(event) => {
          setQuestionId(event.target.value); setPreview(null); setLayout(null); setReviewed(false);
          setDirty(false); setCrop(null); setMessage(null);
        }}>
        {pdfQuestions.map((q) => <option key={q.id} value={q.id}>
          Question {q.position + 1}{q.option_layout ? " - answers separated" : " - full image"}
        </option>)}
      </select>
    </Label>
    <Button type="button" disabled={busy || disabled} onClick={() => void generate(true)}>
      {busy ? "Processing answers…" : "Prepare answer preview"}
    </Button>
    {question.option_layout && !preview ? <p role="status" className="text-sm font-medium text-primary">
      Separate answers are confirmed for this question.
    </p> : null}
    {message ? <p role="status" className="break-words text-sm">{message}</p> : null}
    {preview && layout ? <div className="min-w-0 space-y-5">
      {preview.warnings.map((warning, index) => <p key={index} className="text-sm text-destructive">{warning}</p>)}
      <details className="rounded-lg border p-3">
        <summary className="min-h-11 cursor-pointer font-medium">View original complete question</summary>
        {question.image_urls?.map((path) => <AuthenticatedPdfImage key={path} path={path}
          alt="Original complete question including printed answer choices" />)}
      </details>
      <div className="min-w-0 space-y-3 rounded-lg border p-3">
        <h3 className="font-semibold">Question and figure</h3>
        {layout.stem_urls?.map((path) => <AuthenticatedPdfImage key={path} path={path}
          alt="Separated question and figure" className="h-auto max-w-full rounded bg-white" />)}
        {regionsEditor(-1, layout.stem, "Question")}
      </div>
      <div className="grid min-w-0 gap-4 md:grid-cols-2">
        {layout.options.map((option, index) => <article key={option.label} className="min-w-0 space-y-3 rounded-lg border p-3">
          <h3 className="font-semibold">Answer {option.label}</h3>
          <Label className="flex flex-col gap-2">Display answer {option.label} as
            <select className="min-h-11 w-full rounded-md border border-input bg-background p-2"
              aria-label={`Display answer ${option.label} as`} value={option.mode} disabled={disabled || busy}
              onChange={(event) => change({ ...layout, options: layout.options.map((o, i) => i === index
                ? { ...o, mode: event.target.value as "image" | "text" } : o) })}>
              <option value="image">Image (preserves diagrams and notation)</option>
              <option value="text">Editable text</option>
            </select>
          </Label>
          {option.image_urls?.map((path) => <AuthenticatedPdfImage key={path} path={path}
            alt={`Source crop for answer ${option.label}`} className="h-auto max-w-full rounded bg-white" />)}
          <Label className="flex flex-col gap-2">
            {option.mode === "text" ? `Answer ${option.label} text` : `Answer ${option.label} image description`}
            <Textarea aria-label={option.mode === "text" ? `Answer ${option.label} text` : `Answer ${option.label} image description`}
              disabled={disabled || busy} maxLength={5000} value={option.option_text}
              onChange={(event) => change({ ...layout, options: layout.options.map((o, i) => i === index
                ? { ...o, option_text: event.target.value } : o) })} />
          </Label>
          {option.mode === "text" ? <p className="break-words rounded bg-muted p-2 text-sm">{option.option_text || "Enter the complete answer text."}</p> :
            <p className="text-xs text-muted-foreground">Use a distinct description that explains the image to a screen reader.</p>}
          {regionsEditor(index, option.regions, `Answer ${option.label}`)}
        </article>)}
      </div>
      {dirty ? <p role="status" className="text-sm font-medium">Preview out of date. Regenerate after adjusting text or crops.</p> : null}
      {!readyTexts ? <p className="text-sm">Every answer needs its own text or distinct image description before confirmation.</p> : null}
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" disabled={disabled || busy} onClick={() => void generate(false)}>
          Regenerate answer preview
        </Button>
        <Button type="button" variant="ghost" disabled={busy} onClick={() => void discard()}>Discard answer preview</Button>
      </div>
      <label className="flex min-h-11 items-start gap-3 rounded-lg border p-3 text-sm">
        <input type="checkbox" className="mt-0.5 size-5 shrink-0" checked={reviewed}
          disabled={disabled || busy || dirty || !preview.valid || !readyTexts}
          onChange={(event) => setReviewed(event.target.checked)} />
        I checked that the question and answer crops are complete, printed answer letters are excluded, and the text matches the source.
      </label>
      <Button type="button" disabled={disabled || busy || dirty || !preview.valid || !reviewed || !readyTexts}
        onClick={() => void confirm()}>Confirm separated answers</Button>
    </div> : null}
    {crop && selectedRegion && question.source_file_id && preview ? <PdfPageCropModal
      open onOpenChange={(open) => { if (!open) setCrop(null); }} examId={examId}
      sourceId={question.source_file_id} pageDimensions={preview.page_dimensions} minCropHeight={4}
      title={crop.part < 0 ? "Adjust question and figure" : `Adjust answer ${layout?.options[crop.part].label}`}
      initialRegion={{ page: selectedRegion.page, bbox: selectedRegion.bbox as [number, number, number, number] }}
      busy={busy} onApply={(region: PageCropRegion) => {
        updateRegions(crop.part, selectedRegions.map((r, i) => i === crop.index ? region : r));
        setCrop(null);
      }} /> : null}
  </section>;
}
