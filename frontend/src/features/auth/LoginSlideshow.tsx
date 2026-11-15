import { ChevronLeft, ChevronRight, Pause, Play } from "lucide-react";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FocusEvent,
  type KeyboardEvent,
  type TouchEvent,
} from "react";

import slide3Art from "@/assets/brand/slides/slide-3-art.webp";
import slide1Building from "@/assets/brand/slides/slide-1-building.webp";
import slide4Lab from "@/assets/brand/slides/slide-4-lab.webp";
import slide2Trophy from "@/assets/brand/slides/slide-2-trophy.webp";
import { cn } from "@/lib/utils";

export interface SlideDefinition {
  id: string;
  src: string;
  width: number;
  height: number;
  alt: string;
  objectPosition: string;
}

export const SCHOOL_SLIDES: readonly SlideDefinition[] = [
  {
    id: "building",
    src: slide1Building,
    width: 678,
    height: 452,
    alt: "School building with a yellow and green facade",
    objectPosition: "50% 45%",
  },
  {
    id: "trophy",
    src: slide2Trophy,
    width: 439,
    height: 455,
    alt: "Students celebrating with a trophy",
    objectPosition: "50% 25%",
  },
  {
    id: "art",
    src: slide3Art,
    width: 515,
    height: 388,
    alt: "Students painting in an art class",
    objectPosition: "50% 35%",
  },
  {
    id: "lab",
    src: slide4Lab,
    width: 547,
    height: 365,
    alt: "Pupils watching a science experiment in a laboratory",
    objectPosition: "50% 35%",
  },
] as const;

export interface LoginSlideshowProps {
  fit?: "frame" | "cover";
  className?: string;
}

const AUTO_ADVANCE_MS = 6000;

export function LoginSlideshow({ fit = "frame", className }: LoginSlideshowProps) {
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
                    alt={slide.alt}
                    width={slide.width}
                    height={slide.height}
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

      {/* Bottom dark-green gradient (~60% height) for legibility */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 bottom-0 z-20 h-[62%]"
        style={{
          background: "var(--slideshow-bottom-gradient)",
        }}
      />

      {/* Previous / Next arrows on hover or focus */}
      <button
        type="button"
        aria-label="Previous slide"
        onClick={handlePrev}
        className="hidden sm:inline-flex absolute left-3 top-1/2 z-30 size-11 -translate-y-1/2 items-center justify-center rounded-full border border-white/25 bg-[var(--slideshow-control-bg)] text-white opacity-0 transition-opacity hover:bg-[var(--slideshow-bg)] focus-visible:opacity-100 group-hover:opacity-100 group-focus-within:opacity-100"
      >
        <ChevronLeft className="size-5" aria-hidden="true" />
      </button>

      <button
        type="button"
        aria-label="Next slide"
        onClick={handleNext}
        className="hidden sm:inline-flex absolute right-3 top-1/2 z-30 size-11 -translate-y-1/2 items-center justify-center rounded-full border border-white/25 bg-[var(--slideshow-control-bg)] text-white opacity-0 transition-opacity hover:bg-[var(--slideshow-bg)] focus-visible:opacity-100 group-hover:opacity-100 group-focus-within:opacity-100"
      >
        <ChevronRight className="size-5" aria-hidden="true" />
      </button>

      {/* Fixed school identity overlay + slide controls */}
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
            Delhi Private School
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            aria-label={isUserPaused ? "Play slideshow" : "Pause slideshow"}
            aria-pressed={isUserPaused}
            onClick={() => setIsUserPaused((prev) => !prev)}
            className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-full border border-white/30 bg-[var(--slideshow-control-bg)] px-3 text-xs font-semibold text-white transition-colors hover:bg-[var(--slideshow-control-hover)]"
          >
            {isUserPaused ? (
              <Play className="size-4" aria-hidden="true" />
            ) : (
              <Pause className="size-4" aria-hidden="true" />
            )}
            <span className="sr-only">{isUserPaused ? "Play" : "Pause"}</span>
          </button>

          <div className="flex items-center gap-1.5" role="group" aria-label="Slide indicators">
            {SCHOOL_SLIDES.map((slide, index) => {
              const isActive = index === activeIndex;
              return (
                <button
                  key={slide.id}
                  type="button"
                  aria-label={`Show slide ${index + 1} of ${SCHOOL_SLIDES.length}`}
                  aria-current={isActive ? "true" : undefined}
                  onClick={() => goToSlide(index)}
                  className="inline-flex min-h-11 min-w-6 items-center justify-center px-0.5"
                >
                  <span
                    className={cn(
                      "block h-2 rounded-full transition-all duration-300",
                      isActive ? "w-6 bg-[var(--accent-flame-yellow)]" : "w-2 bg-white/45 hover:bg-white/75",
                    )}
                  />
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
