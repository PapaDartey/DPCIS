import { useState } from "react";

import { AuthenticatedPdfImage } from "@/components/exam/AuthenticatedPdfImage";
import { Button } from "@/components/ui/button";
import { apiDelete, apiPost } from "@/lib/api";

interface Candidate {
  question_id: string;
  position: number;
  valid: boolean;
  warnings: string[];
  before_urls: string[];
  after_urls: string[];
}
interface Preview { preview_id: string; questions: Candidate[] }

export function RecropPanel({ examId, disabled, onApplied }: {
  examId: string; disabled: boolean; onApplied: () => void;
}) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const [approved, setApproved] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const generate = async () => {
    setBusy(true); setMessage(null); setApproved([]);
    try {
      if (preview) await apiDelete(`/api/admin/exams/${examId}/recrop-preview/${preview.preview_id}`);
      setPreview(null);
      setPreview(await apiPost<Preview>(`/api/admin/exams/${examId}/recrop-preview`, {
        timeoutMs: 120000,
      }));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not prepare re-crops.");
    } finally { setBusy(false); }
  };
  const discard = async () => {
    if (!preview) return;
    setBusy(true); setMessage(null);
    try {
      await apiDelete(`/api/admin/exams/${examId}/recrop-preview/${preview.preview_id}`);
      setPreview(null); setApproved([]);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not discard preview.");
    } finally { setBusy(false); }
  };
  const apply = async () => {
    if (!preview || !approved.length) return;
    setBusy(true); setMessage(null);
    try {
      await apiPost(`/api/admin/exams/${examId}/recrop-preview/${preview.preview_id}/apply`, {
        body: { question_ids: approved }, timeoutMs: 120000,
      });
      setPreview(null); setApproved([]);
      onApplied();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Old crops kept; approval failed.");
    } finally { setBusy(false); }
  };
  return <section aria-label="Re-crop stored questions" className="space-y-4 rounded-xl border p-4">
    <h2 className="text-lg font-semibold">Re-crop from stored PDF</h2>
    <p className="text-sm text-muted-foreground">
      Compare new crops with the saved images, then approve individual questions.
      Answer keys and marks stay unchanged. Old images are retained.
    </p>
    {disabled ? <p className="text-sm">Save or discard pending edits first. Re-cropping is available for draft exams.</p> : null}
    <Button type="button" disabled={disabled || busy} onClick={() => void generate()}>
      {busy ? "Processing crops…" : "Re-crop from stored PDF"}
    </Button>
    {message ? <p role="alert" className="text-sm text-destructive">{message}</p> : null}
    {preview ? <>
      {!preview.questions.length ? <p>No saved PDF questions are available.</p> : null}
      {preview.questions.map((candidate) => <article key={candidate.question_id}
        className="min-w-0 space-y-3 rounded-lg border p-3">
        <label className="flex min-h-11 items-center gap-3 font-medium">
          <input type="checkbox" className="h-5 w-5" aria-label={`Approve re-crop for question ${candidate.position + 1}`}
            disabled={disabled || busy || !candidate.valid}
            checked={approved.includes(candidate.question_id)}
            onChange={(event) => setApproved((current) => event.target.checked
              ? [...current, candidate.question_id] : current.filter((id) => id !== candidate.question_id))} />
          Question {candidate.position + 1}: {candidate.valid ? "Approve this re-crop" : "Failed checks — old crop kept"}
        </label>
        {candidate.warnings.map((warning, index) => {
          const [message, thumbnail] = warning.split("\nthumbnail:");
          return (
            <div key={index} className="min-w-0 space-y-1 text-sm">
              <p className="break-words">{message}</p>
              {thumbnail?.startsWith("data:image/png;base64,") ? (
                <img
                  src={thumbnail}
                  alt={message}
                  className="max-h-40 max-w-full border border-border"
                />
              ) : null}
            </div>
          );
        })}
        <div className="grid min-w-0 gap-4 md:grid-cols-2">
          <div className="min-w-0 space-y-2"><h3 className="font-medium">Before</h3>
            {candidate.before_urls.map((url, index) => <AuthenticatedPdfImage key={url} path={url}
              alt={`Question ${candidate.position + 1} before crop ${index + 1}`} />)}</div>
          <div className="min-w-0 space-y-2"><h3 className="font-medium">After</h3>
            {candidate.after_urls.map((url, index) => <AuthenticatedPdfImage key={url} path={url}
              alt={`Question ${candidate.position + 1} after crop ${index + 1}`} />)}</div>
        </div>
      </article>)}
      <Button type="button" disabled={disabled || busy || !approved.length} onClick={() => void apply()}>
        Apply {approved.length} approved re-crop{approved.length === 1 ? "" : "s"}
      </Button>
      <Button type="button" disabled={busy} onClick={() => void discard()}>Discard re-crop preview</Button>
    </> : null}
  </section>;
}
