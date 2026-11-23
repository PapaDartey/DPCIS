import { useEffect, useId, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Crop, Move, ZoomIn, ZoomOut } from "lucide-react";

import { AuthenticatedPdfImage } from "@/components/exam/AuthenticatedPdfImage";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { sourcePageImageUrl } from "@/features/admin/adminApi";

export interface PageCropRegion {
  page: number;
  bbox: [number, number, number, number];
  number_bbox?: number[] | null;
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  examId: string;
  sourceId: string;
  pageDimensions: Array<[number, number]>;
  initialRegion: PageCropRegion;
  title?: string;
  busy?: boolean;
  minCropHeight?: number;
  allowNumberMask?: boolean;
  onApply: (region: PageCropRegion) => Promise<void> | void;
}

const MIN_CROP_PT = 30;

function clampBox(
  box: [number, number, number, number],
  width: number,
  height: number,
  minHeight = MIN_CROP_PT,
): [number, number, number, number] {
  const x0 = Math.max(0, Math.min(width - 10, box[0]));
  const y0 = Math.max(0, Math.min(height - minHeight, box[1]));
  const x1 = Math.max(x0 + 10, Math.min(width, box[2]));
  const y1 = Math.max(y0 + minHeight, Math.min(height, box[3]));
  return [
    Math.round(x0 * 10) / 10,
    Math.round(y0 * 10) / 10,
    Math.round(x1 * 10) / 10,
    Math.round(y1 * 10) / 10,
  ];
}

export function PdfPageCropModal({
  open,
  onOpenChange,
  examId,
  sourceId,
  pageDimensions,
  initialRegion,
  title = "Crop question from PDF page",
  busy = false,
  minCropHeight = MIN_CROP_PT,
  allowNumberMask = false,
  onApply,
}: Props) {
  const cropId = useId();
  const totalPages = Math.max(1, pageDimensions.length);
  const [page, setPage] = useState(initialRegion.page);
  const [bbox, setBbox] = useState<[number, number, number, number]>(initialRegion.bbox);
  const [zoomPct, setZoomPct] = useState<number>(100);
  const [mode, setMode] = useState<"edit" | "draw" | "number">("edit");
  const [numberBox, setNumberBox] = useState<number[] | null>(initialRegion.number_bbox ?? null);
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const dragCleanupRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (open) {
      setPage(Math.min(Math.max(1, initialRegion.page), totalPages));
      setBbox(initialRegion.bbox);
      setZoomPct(100);
      setMode("edit");
      setNumberBox(initialRegion.number_bbox ?? null);
    }
    return () => {
      dragCleanupRef.current?.();
      dragCleanupRef.current = null;
    };
  }, [open, initialRegion, totalPages]);

  const [pageWidth, pageHeight] = pageDimensions[page - 1] ?? [595, 842];
  const leftPct = (bbox[0] / pageWidth) * 100;
  const topPct = (bbox[1] / pageHeight) * 100;
  const widthPct = Math.max(1, ((bbox[2] - bbox[0]) / pageWidth) * 100);
  const heightPct = Math.max(1, ((bbox[3] - bbox[1]) / pageHeight) * 100);

  const clientToPdfPoint = (clientX: number, clientY: number): [number, number] | null => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect || rect.width < 20 || rect.height < 20) return null;
    const nx = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    const ny = Math.max(0, Math.min(1, (clientY - rect.top) / rect.height));
    return [nx * pageWidth, ny * pageHeight];
  };

  const startDraw = (event: React.PointerEvent<HTMLDivElement>) => {
    if (mode === "edit" || busy) return;
    const startPt = clientToPdfPoint(event.clientX, event.clientY);
    if (!startPt) return;
    event.preventDefault();
    const onMove = (moveEvent: PointerEvent) => {
      const currentPt = clientToPdfPoint(moveEvent.clientX, moveEvent.clientY);
      if (!currentPt) return;
      const raw: [number, number, number, number] = [
        Math.min(startPt[0], currentPt[0]),
        Math.min(startPt[1], currentPt[1]),
        Math.max(startPt[0], currentPt[0]),
        Math.max(startPt[1], currentPt[1]),
      ];
      if (mode === "number") setNumberBox(raw.map((value) => Math.round(value * 10) / 10));
      else setBbox(clampBox(raw, pageWidth, pageHeight, minCropHeight));
    };
    const cleanup = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", cleanup);
      window.removeEventListener("pointercancel", cleanup);
      dragCleanupRef.current = null;
    };
    dragCleanupRef.current?.();
    dragCleanupRef.current = cleanup;
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", cleanup);
    window.addEventListener("pointercancel", cleanup);
  };

  const startBoxAction = (
    kind: "move" | "n" | "s" | "w" | "e" | "nw" | "ne" | "sw" | "se",
    event: React.PointerEvent<HTMLElement>,
  ) => {
    if (mode !== "edit" || busy) return;
    const startPt = clientToPdfPoint(event.clientX, event.clientY);
    if (!startPt) return;
    event.stopPropagation();
    event.preventDefault();
    const startBox: [number, number, number, number] = [...bbox];
    const onMove = (moveEvent: PointerEvent) => {
      const cur = clientToPdfPoint(moveEvent.clientX, moveEvent.clientY);
      if (!cur) return;
      const dx = cur[0] - startPt[0];
      const dy = cur[1] - startPt[1];
      let next: [number, number, number, number] = [...startBox];
      if (kind === "move") {
        const w = startBox[2] - startBox[0];
        const h = startBox[3] - startBox[1];
        const nx0 = Math.max(0, Math.min(pageWidth - w, startBox[0] + dx));
        const ny0 = Math.max(0, Math.min(pageHeight - h, startBox[1] + dy));
        next = [nx0, ny0, nx0 + w, ny0 + h];
      } else {
        if (kind.includes("w")) next[0] = startBox[0] + dx;
        if (kind.includes("e")) next[2] = startBox[2] + dx;
        if (kind.includes("n")) next[1] = startBox[1] + dy;
        if (kind.includes("s")) next[3] = startBox[3] + dy;
      }
      setBbox(clampBox(next, pageWidth, pageHeight, minCropHeight));
    };
    const cleanup = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", cleanup);
      window.removeEventListener("pointercancel", cleanup);
      dragCleanupRef.current = null;
    };
    dragCleanupRef.current?.();
    dragCleanupRef.current = cleanup;
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", cleanup);
    window.addEventListener("pointercancel", cleanup);
  };

  const handleBoxKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const step = event.shiftKey ? 10 : 2;
    let dx = 0;
    let dy = 0;
    if (event.key === "ArrowLeft") dx = -step;
    else if (event.key === "ArrowRight") dx = step;
    else if (event.key === "ArrowUp") dy = -step;
    else if (event.key === "ArrowDown") dy = step;
    else return;
    event.preventDefault();
    const w = bbox[2] - bbox[0];
    const h = bbox[3] - bbox[1];
    const nx0 = Math.max(0, Math.min(pageWidth - w, bbox[0] + dx));
    const ny0 = Math.max(0, Math.min(pageHeight - h, bbox[1] + dy));
    setBbox(clampBox([nx0, ny0, nx0 + w, ny0 + h], pageWidth, pageHeight, minCropHeight));
  };

  const switchPage = (nextPage: number) => {
    const clamped = Math.max(1, Math.min(totalPages, nextPage));
    const [nextW, nextH] = pageDimensions[clamped - 1] ?? [595, 842];
    setPage(clamped);
    setNumberBox(null);
    setBbox((prev) => clampBox(prev, nextW, nextH, minCropHeight));
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      className="max-w-5xl"
      footer={
        <div className="flex w-full flex-wrap items-center justify-between gap-2">
          <p className="text-xs text-muted-foreground">
            Crop (pt): L {Math.round(bbox[0])} · T {Math.round(bbox[1])} · R {Math.round(bbox[2])} · B{" "}
            {Math.round(bbox[3])}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              className="min-h-11"
              disabled={busy}
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              className="min-h-11"
              disabled={busy}
              onClick={() => void onApply({ page, bbox, ...(allowNumberMask && numberBox ? { number_bbox: numberBox } : {}) })}
            >
              {busy ? "Updating crop…" : "Apply crop"}
            </Button>
          </div>
        </div>

      }
    >
      <div className="space-y-3">
        {allowNumberMask ? <div className="space-y-2 rounded-lg border p-3">
          <p className="text-sm font-medium">Printed question number</p>
          <p className="text-xs text-muted-foreground">Recognized numbers are removed automatically. For a scan, mark only the printed question number. Check that no question text or diagram is covered.</p>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant={mode === "number" ? "default" : "outline"}
              className="min-h-11" disabled={busy} onClick={() => {
                setMode("number");
                if (!numberBox) setNumberBox([bbox[0] + 2, bbox[1] + 2, Math.min(bbox[2], bbox[0] + 20), Math.min(bbox[3], bbox[1] + 25)]);
              }}>Mark question number</Button>
            {numberBox ? <Button type="button" variant="ghost" className="min-h-11" disabled={busy}
              onClick={() => { setNumberBox(null); setMode("edit"); }}>Clear number area</Button> : null}
          </div>
          {mode === "number" ? <p role="status" className="text-xs">Draw a small box around the number, or edit its coordinates below.</p> : null}
          {numberBox ? <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {["Left", "Top", "Right", "Bottom"].map((name, coordinate) => <label key={name} className="min-w-0 text-xs">
              Number {name.toLowerCase()} (pt)
              <input aria-label={`Number area ${name.toLowerCase()}`} type="number" step="0.5" disabled={busy}
                className="mt-1 min-h-11 w-full min-w-0 rounded-md border border-input bg-background p-2 text-sm"
                value={Number(numberBox[coordinate].toFixed(2))}
                onChange={(event) => setNumberBox((previous) => previous?.map((value, index) =>
                  index === coordinate ? Number(event.target.value) : value) ?? null)} />
            </label>)}
          </div> : null}
        </div> : null}
        <div className="flex flex-wrap items-center gap-1.5">
          <Button
            type="button"
            size="sm"
            variant={mode === "edit" ? "default" : "outline"}
            className="min-h-11 gap-1.5"
            onClick={() => setMode("edit")}
          >
            <Move className="size-4" aria-hidden="true" />
            Move &amp; resize
          </Button>
          <Button
            type="button"
            size="sm"
            variant={mode === "draw" ? "default" : "outline"}
            className="min-h-11 gap-1.5"
            onClick={() => setMode("draw")}
          >
            <Crop className="size-4" aria-hidden="true" />
            Draw new crop
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="min-h-11 min-w-11"
            aria-label="Previous page"
            disabled={page <= 1 || busy}
            onClick={() => switchPage(page - 1)}
          >
            <ChevronLeft className="size-4" aria-hidden="true" />
          </Button>
          <span className="px-1 text-xs font-medium text-muted-foreground">
            Page {page} of {totalPages}
          </span>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="min-h-11 min-w-11"
            aria-label="Next page"
            disabled={page >= totalPages || busy}
            onClick={() => switchPage(page + 1)}
          >
            <ChevronRight className="size-4" aria-hidden="true" />
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="min-h-11 min-w-11"
            aria-label="Zoom out page"
            disabled={zoomPct <= 75}
            onClick={() => setZoomPct((z) => Math.max(75, z - 25))}
          >
            <ZoomOut className="size-4" aria-hidden="true" />
          </Button>
          <span className="min-w-[3rem] text-center text-xs font-medium text-muted-foreground">
            {zoomPct}%
          </span>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="min-h-11 min-w-11"
            aria-label="Zoom in page"
            disabled={zoomPct >= 200}
            onClick={() => setZoomPct((z) => Math.min(200, z + 25))}
          >
            <ZoomIn className="size-4" aria-hidden="true" />
          </Button>
        </div>

        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {["Left", "Top", "Right", "Bottom"].map((name, coordinate) => (
            <label key={name} htmlFor={`${cropId}-${name}`} className="min-w-0 text-xs font-medium">
              {name} (pt)
              <input id={`${cropId}-${name}`} aria-label={`Crop ${name.toLowerCase()}`}
                type="number" step="0.5" disabled={busy}
                className="mt-1 min-h-11 w-full min-w-0 rounded-md border border-input bg-background p-2 text-sm"
                value={Number(bbox[coordinate].toFixed(2))}
                onChange={(event) => setBbox((previous) => previous.map((value, index) =>
                  index === coordinate ? Number(event.target.value) : value,
                ) as [number, number, number, number])} />
            </label>
          ))}
        </div>
        <div className="max-h-[calc(100dvh-20rem)] overflow-auto rounded-lg border border-border bg-muted/40 p-3">
          <div
            ref={canvasRef}
            onPointerDown={startDraw}
            style={{ width: zoomPct === 100 ? "100%" : `${zoomPct}%` }}
            className={`relative mx-auto select-none bg-white shadow-sm ${
              mode !== "edit" ? "cursor-crosshair touch-none" : ""
            }`}
          >
            <AuthenticatedPdfImage
              path={sourcePageImageUrl(examId, sourceId, page, 150)}
              alt={`PDF page ${page}`}
              className="block h-auto w-full select-none"
            />
            <div
              role="region"
              tabIndex={0}
              aria-label="Selected crop region. Use arrow keys to nudge position."
              onKeyDown={handleBoxKeyDown}
              onPointerDown={(e) => startBoxAction("move", e)}
              style={{
                left: `${leftPct}%`,
                top: `${topPct}%`,
                width: `${widthPct}%`,
                height: `${heightPct}%`,
              }}
              className={`absolute border-2 border-primary bg-primary/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                mode === "edit" ? "cursor-move touch-none" : "pointer-events-none"
              }`}
            >
              {(["nw", "ne", "sw", "se", "n", "s", "w", "e"] as const).map((handle) => {
                const posClass = {
                  nw: "-left-2 -top-2 cursor-nwse-resize",
                  ne: "-right-2 -top-2 cursor-nesw-resize",
                  sw: "-left-2 -bottom-2 cursor-nesw-resize",
                  se: "-right-2 -bottom-2 cursor-nwse-resize",
                  n: "left-1/2 -top-2 -translate-x-1/2 cursor-ns-resize",
                  s: "left-1/2 -bottom-2 -translate-x-1/2 cursor-ns-resize",
                  w: "-left-2 top-1/2 -translate-y-1/2 cursor-ew-resize",
                  e: "-right-2 top-1/2 -translate-y-1/2 cursor-ew-resize",
                }[handle];
                return (
                  <button
                    key={handle}
                    type="button"
                    aria-label={`Resize ${handle} handle`}
                    onPointerDown={(e) => startBoxAction(handle, e)}
                    className={`absolute size-4 rounded-full border-2 border-primary bg-white shadow ${posClass}`}
                  />
                );
              })}
            </div>
            {allowNumberMask && numberBox ? <div aria-label="Question number removal area"
              className="pointer-events-none absolute border border-dashed border-primary bg-white"
              style={{ left: `${numberBox[0] / pageWidth * 100}%`, top: `${numberBox[1] / pageHeight * 100}%`,
                width: `${Math.max(0, numberBox[2] - numberBox[0]) / pageWidth * 100}%`,
                height: `${Math.max(0, numberBox[3] - numberBox[1]) / pageHeight * 100}%` }} /> : null}
          </div>
        </div>
      </div>
    </Dialog>
  );
}
