import { Pause, Play } from "lucide-react";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FocusEvent,
  type KeyboardEvent,
  type TouchEvent,
} from "react";

import hrSlide0Building1280 from "@/assets/brand/slides/hr-slide-0-building@1280.webp";
import hrSlide0Building1920 from "@/assets/brand/slides/hr-slide-0-building@1920.webp";
import hrSlide1Lab1280 from "@/assets/brand/slides/hr-slide-1-lab@1280.webp";
import hrSlide1Lab1920 from "@/assets/brand/slides/hr-slide-1-lab@1920.webp";
import hrSlide2Classroom1280 from "@/assets/brand/slides/hr-slide-2-classroom@1280.webp";
import hrSlide2Classroom1920 from "@/assets/brand/slides/hr-slide-2-classroom@1920.webp";
import hrSlide3Sports1280 from "@/assets/brand/slides/hr-slide-3-sports@1280.webp";
import hrSlide3Sports1920 from "@/assets/brand/slides/hr-slide-3-sports@1920.webp";
import hrSlide4Debate1280 from "@/assets/brand/slides/hr-slide-4-debate@1280.webp";
import hrSlide4Debate1920 from "@/assets/brand/slides/hr-slide-4-debate@1920.webp";
import { cn } from "@/lib/utils";

/**
 * Off-by-default fallback flag for the legacy restored low-res slides
 * (archived in `src/assets/brand/slides/slide-{1..4}-*@{1280,1920}.webp`).
 * Keep `false` so only native high-resolution official photos render.
 */
export const USE_LEGACY_RESTORED_SLIDES = false;

/**
 * Official high-resolution photos retrieved from `https://dpsghana.edu.gh/`
 * pending written school approval (`docs/brand/photo-sources.md`).
 */
export const PENDING_APPROVAL_SLIDES = [
  { id: "building-highres", approvalStatus: "pending approval" },
  { id: "lab-highres", approvalStatus: "pending approval" },
  { id: "classroom-highres", approvalStatus: "pending approval" },
  { id: "sports-highres", approvalStatus: "pending approval" },
  { id: "debate-highres", approvalStatus: "pending approval" },
] as const;

export interface SlideDefinition {
  id: string;
  src: string;
  src1280: string;
  w1280: number;
  width: number;
  height: number;
  alt: string;
  objectPosition: string;
  approvalStatus: "pending approval" | "approved";
}

export const SCHOOL_SLIDES: readonly SlideDefinition[] = [
  {
    id: "building-highres",
    src: hrSlide0Building1920,
    src1280: hrSlide0Building1280,
    w1280: 1280,
    width: 1920,
    height: 1280,
    alt: "Main campus building of DPS International Ghana in Tema Community 25",
    objectPosition: "center 65%",
    approvalStatus: "pending approval",
  },
  {
    id: "lab-highres",
    src: hrSlide1Lab1920,
    src1280: hrSlide1Lab1280,
    w1280: 1280,
    width: 1920,
    height: 1280,
    alt: "Pupils and teacher conducting a science experiment in the DPS International Ghana laboratory",
    objectPosition: "center 35%",
    approvalStatus: "pending approval",
  },
  {
    id: "classroom-highres",
    src: hrSlide2Classroom1920,
    src1280: hrSlide2Classroom1280,
    w1280: 1280,
    width: 1920,
    height: 1282,
    alt: "Students and teacher collaborating in a smartboard classroom at DPS International Ghana",
    objectPosition: "center 35%",
    approvalStatus: "pending approval",
  },
  {
    id: "sports-highres",
    src: hrSlide3Sports1920,
    src1280: hrSlide3Sports1280,
    w1280: 1280,
    width: 1920,
    height: 1280,
    alt: "Students playing basketball on the DPS International Ghana campus court",
    objectPosition: "center 45%",
    approvalStatus: "pending approval",
  },
  {
    id: "debate-highres",
    src: hrSlide4Debate1920,
    src1280: hrSlide4Debate1280,
    w1280: 1280,
    width: 1920,
    height: 1282,
    alt: "Students participating in a group classroom discussion at DPS International Ghana",
    objectPosition: "center 35%",
    approvalStatus: "pending approval",
  },
] as const;

export interface LoginSlideshowProps {
  fit?: "frame" | "cover";
  className?: string;
}

const AUTO_ADVANCE_MS = 6000;

function SlideDots({ activeIndex, count }: { activeIndex: number; count: number }) {
  return (
    <div className="flex items-center gap-1.5" aria-hidden="true">
      {Array.from({ length: count }, (_, index) => {
        const isActive = index === activeIndex;
        return (
          <span
            key={index}
            className={cn(
              "block h-2 rounded-full transition-all duration-300",
              isActive ? "w-6 bg-[var(--accent-flame-yellow)]" : "w-2 bg-white/45",
            )}
          />
        );
      })}
    </div>
  );
}

export function LoginSlideshow({ fit = "cover", className }: LoginSlideshowProps) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [isUserPaused, setIsUserPaused] = useState(false);
  const [isHovered, setIsHovered] = useState(false);
  const [isFocusedWithin, setIsFocusedWithin] = useState(false);
  const [isDocumentHidden, setIsDocumentHidden] = useState(() =>
    typeof document !== "undefined" ? document.hidden : false,
  );
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(() =>
    typeof window !== "undefined"
      ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
      : false,
  );
  const [loadedSlides, setLoadedSlides] = useState<boolean[]>([true, false, false, false]);

  const containerRef = useRef<HTMLElement | null>(null);
  const touchStartXRef = useRef<number | null>(null);

  useEffect(() => {
    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const handleChange = () => setPrefersReducedMotion(mediaQuery.matches);
    handleChange();
    mediaQuery.addEventListener("change", handleChange);
    return () => mediaQuery.removeEventListener("change", handleChange);
  }, []);

  useEffect(() => {
    const handleVisibilityChange = () => {
      setIsDocumentHidden(document.hidden);
    };
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => document.removeEventListener("visibilitychange", handleVisibilityChange);
  }, []);

  // Load slides 2..4 after first paint so slide 1 gets immediate network priority.
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setLoadedSlides([true, true, true, true]);
    }, 150);
    return () => window.clearTimeout(timer);
  }, []);

  // Preload the upcoming slide before each transition.
  useEffect(() => {
    const nextIdx = (activeIndex + 1) % SCHOOL_SLIDES.length;
    setLoadedSlides((prev) => {
      if (prev[nextIdx]) {
        return prev;
      }
      const next = [...prev];
      next[nextIdx] = true;
      return next;
    });
  }, [activeIndex]);

  const isAutoRotating =
    !prefersReducedMotion &&
    !isUserPaused &&
    !isHovered &&
    !isFocusedWithin &&
    !isDocumentHidden;

  useEffect(() => {
    if (!isAutoRotating) {
      return;
    }
    const id = window.setInterval(() => {
      setActiveIndex((prev) => (prev + 1) % SCHOOL_SLIDES.length);
    }, AUTO_ADVANCE_MS);
    return () => window.clearInterval(id);
  }, [isAutoRotating]);

  const goToSlide = useCallback((index: number) => {
    const normalized =
      ((index % SCHOOL_SLIDES.length) + SCHOOL_SLIDES.length) % SCHOOL_SLIDES.length;
    setLoadedSlides((prev) => {
      if (prev[normalized]) {
        return prev;
      }
      const next = [...prev];
      next[normalized] = true;
      return next;
    });
    setActiveIndex(normalized);
  }, []);

  const handlePrev = useCallback(() => {
    goToSlide(activeIndex - 1);
  }, [activeIndex, goToSlide]);

  const handleNext = useCallback(() => {
    goToSlide(activeIndex + 1);
  }, [activeIndex, goToSlide]);

  const handleKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      handlePrev();
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      handleNext();
    }
  };

  const handleBlurCapture = (event: FocusEvent<HTMLElement>) => {
    const nextTarget = event.relatedTarget as Node | null;
    if (!containerRef.current?.contains(nextTarget)) {
      setIsFocusedWithin(false);
    }
  };

  const handleTouchStart = (event: TouchEvent<HTMLElement>) => {
    touchStartXRef.current = event.changedTouches[0]?.clientX ?? null;
  };

  const handleTouchEnd = (event: TouchEvent<HTMLElement>) => {
    if (touchStartXRef.current === null) {
      return;
    }
    const endX = event.changedTouches[0]?.clientX ?? touchStartXRef.current;
    const deltaX = endX - touchStartXRef.current;
    touchStartXRef.current = null;
    if (Math.abs(deltaX) >= 40) {
      if (deltaX < 0) {
        handleNext();
      } else {
        handlePrev();
      }
    }
  };

  return (
    <section
      ref={containerRef}
      role="region"
      aria-roledescription="carousel"
      aria-label="School photos"
      aria-live={isAutoRotating ? "off" : "polite"}
      data-fit={fit}
      data-active-slide={activeIndex}
      data-paused={String(!isAutoRotating)}
      tabIndex={0}
      onKeyDown={handleKeyDown}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      onFocusCapture={() => setIsFocusedWithin(true)}
      onBlurCapture={handleBlurCapture}
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
      className={cn(
        "dps-slideshow group relative isolate flex h-[220px] w-full flex-col justify-end overflow-hidden bg-[var(--slideshow-bg)] text-white outline-none focus-visible:ring-3 focus-visible:ring-[var(--brand-focus-outline)] sm:h-[240px] lg:h-full lg:min-h-[100dvh]",
        className,
      )}
    >
      {/* Slides */}
      <div className="absolute inset-0">
        {SCHOOL_SLIDES.map((slide, index) => {
          const isActive = index === activeIndex;
          const shouldLoad = loadedSlides[index] || isActive;
          const maxFrameWidth = Math.round(slide.width * 1.25);
          const maxFrameHeight = Math.round(slide.height * 1.25);

          return (
            <div
              key={slide.id}
              role="group"
              aria-roledescription="slide"
              aria-label={`${index + 1} of ${SCHOOL_SLIDES.length}`}
              aria-hidden={!isActive}
              className={cn(
                "dps-slide absolute inset-0 flex items-center justify-center",
                prefersReducedMotion ? "" : "transition-opacity duration-[1200ms] ease-in-out",
                isActive ? "z-10 opacity-100" : "pointer-events-none z-0 opacity-0",
              )}
            >
              {shouldLoad ? (
                fit === "cover" ? (
                  <img
                    src={slide.src}
                    srcSet={`${slide.src1280} ${slide.w1280}w, ${slide.src} ${slide.width}w`}
                    sizes="(min-width: 1024px) max(58vw, 150vh), 100vw"
                    alt={slide.alt}
                    width={slide.width}
                    height={slide.height}
                    loading={index === 0 ? "eager" : "lazy"}
                    fetchPriority={index === 0 ? "high" : "auto"}
                    decoding={index === 0 ? "sync" : "async"}
                    className="h-full w-full object-cover"
                    style={{ objectPosition: slide.objectPosition }}
                  />
                ) : (
                  <>
                    {/* Blurred green-tinted backdrop of the same photo */}
                    <img
                      src={slide.src}
                      alt=""
                      aria-hidden="true"
                      width={slide.width}
                      height={slide.height}
                      decoding="async"
                      className="absolute inset-0 h-full w-full scale-110 object-cover opacity-55 blur-[32px] saturate-110"
                      style={{ objectPosition: slide.objectPosition }}
                    />
                    <div
                      aria-hidden="true"
                      className="absolute inset-0"
                      style={{
                        background: "var(--slideshow-scrim)",
                      }}
                    />
                    {/* Sharp centered frame capped at <= 1.25x native size */}
                    <div className="relative z-10 flex h-full w-full items-center justify-center px-4 pb-16 pt-4 lg:px-10 lg:pb-28 lg:pt-10">
                      <div
                        className="relative flex max-h-full max-w-full items-center justify-center overflow-hidden rounded-[16px] border border-white/20 bg-[var(--slideshow-frame-bg)] shadow-[var(--slideshow-frame-shadow)]"
                        style={{
                          maxWidth: `min(100%, ${maxFrameWidth}px)`,
                          maxHeight: `min(100%, ${maxFrameHeight}px)`,
                        }}
                      >
                        <img
                          src={slide.src}
                          alt={slide.alt}
                          width={slide.width}
                          height={slide.height}
                          fetchPriority={index === 0 ? "high" : "auto"}
                          decoding={index === 0 ? "sync" : "async"}
                          className="block h-auto max-h-[140px] w-auto max-w-full object-contain sm:max-h-[164px] lg:max-h-[min(68dvh,568px)]"
                          style={{ objectPosition: slide.objectPosition }}
                        />
                      </div>
                    </div>
                  </>
                )
              ) : null}
            </div>
          );
        })}
      </div>

      {/* Faint overall dark-green tint + bottom ~40% gradient for legibility */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 z-20"
        style={{ background: "var(--slideshow-cover-tint)" }}
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 bottom-0 z-20 h-[42%]"
        style={{
          background: "var(--slideshow-bottom-gradient)",
        }}
      />

      {/* Visually hidden until keyboard focus */}
      <button
        type="button"
        aria-label={isUserPaused ? "Play slideshow" : "Pause slideshow"}
        aria-pressed={isUserPaused}
        onClick={() => setIsUserPaused((prev) => !prev)}
        className="sr-only focus:not-sr-only focus:absolute focus:right-4 focus:top-4 focus:z-40 focus:inline-flex focus:min-h-11 focus:items-center focus:gap-2 focus:rounded-full focus:border focus:border-white/40 focus:bg-[var(--slideshow-bg)] focus:px-4 focus:py-2 focus:text-xs focus:font-semibold focus:text-white focus:shadow-lg focus:outline-none focus:ring-3 focus:ring-[var(--brand-focus-outline)]"
      >
        {isUserPaused ? (
          <Play className="size-4" aria-hidden="true" />
        ) : (
          <Pause className="size-4" aria-hidden="true" />
        )}
        <span>{isUserPaused ? "Play slideshow" : "Pause slideshow"}</span>
      </button>

      {/* Fixed school identity overlay + non-interactive slide dots */}
      <div className="relative z-30 flex flex-wrap items-end justify-between gap-4 px-5 pb-4 pt-6 sm:px-8 sm:pb-5 lg:px-10 lg:pb-8">
        <div className="min-w-0 space-y-1">
          <div className="flex items-center gap-2">
            <span
              aria-hidden="true"
              className="inline-block h-1 w-6 rounded-full bg-[var(--accent-flame-yellow)]"
            />
            <span className="text-[11px] font-bold uppercase tracking-[0.14em] text-[var(--accent-flame-yellow)]">
              Service Beyond Self
            </span>
          </div>
          <p className="text-lg font-bold tracking-tight text-white sm:text-xl lg:text-2xl">
            DPS International Ghana
          </p>
        </div>

        <SlideDots activeIndex={activeIndex} count={SCHOOL_SLIDES.length} />
      </div>
    </section>
  );
}
