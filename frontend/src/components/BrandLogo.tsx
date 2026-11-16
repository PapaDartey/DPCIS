import logo128 from "@/assets/brand/dps-logo-128.webp";
import logo256 from "@/assets/brand/dps-logo-256.webp";
import logo512 from "@/assets/brand/dps-logo-512.webp";
import logoTile128 from "@/assets/brand/dps-logo-tile-128.webp";
import logoTile256 from "@/assets/brand/dps-logo-tile-256.webp";
import logoTile512 from "@/assets/brand/dps-logo-tile-512.webp";
import { cn } from "@/lib/utils";

export type BrandLogoSize = 24 | 32 | 40 | 64 | 96 | 120;
export type BrandLogoVariant = "mark" | "lockup";

export interface BrandLogoProps {
  size?: BrandLogoSize;
  variant?: BrandLogoVariant;
  onDark?: boolean;
  className?: string;
}

function selectLogoSrc(size: number, onDark: boolean): string {
  if (onDark) {
    if (size <= 64) {
      return logoTile128;
    }
    if (size <= 128) {
      return logoTile256;
    }
    return logoTile512;
  }
  if (size <= 64) {
    return logo128;
  }
  if (size <= 128) {
    return logo256;
  }
  return logo512;
}

export function BrandLogo({
  size = 32,
  variant = "mark",
  onDark = false,
  className,
}: BrandLogoProps) {
  // Minimum rendered crest height is 28px per brand guidelines.
  const imgSize = Math.max(size, 28);
  // Clear space around the mark is at least 25% of its height.
  const clearSpacePx = Math.ceil(imgSize * 0.25);
  const src = selectLogoSrc(imgSize, onDark);

  const imageNode = onDark ? (
    <span
      className="inline-flex shrink-0 items-center justify-center bg-white"
      style={{
        borderRadius: 10,
        padding: 4,
      }}
    >
      <img
        src={src}
        alt="DPS International School logo"
        width={imgSize}
        height={imgSize}
        data-brand-logo={variant}
        className="block shrink-0 object-contain"
        style={{
          width: imgSize,
          height: imgSize,
        }}
      />
    </span>
  ) : (
    <img
      src={src}
      alt="DPS International School logo"
      width={imgSize}
      height={imgSize}
      data-brand-logo={variant}
      className="block shrink-0 object-contain"
      style={{
        width: imgSize,
        height: imgSize,
      }}
    />
  );

  if (variant === "mark") {
    return (
      <span
        className={cn("inline-flex shrink-0 items-center justify-center", className)}
        style={{ padding: clearSpacePx }}
      >
        {imageNode}
      </span>
    );
  }

  return (
    <span
      className={cn("inline-flex min-w-0 items-center gap-2.5", className)}
      style={{ padding: Math.max(4, Math.round(clearSpacePx * 0.5)) }}
    >
      {imageNode}
      <span className="flex min-w-0 flex-col leading-tight">
        <span
          className={cn(
            "truncate text-sm font-bold tracking-tight sm:text-base",
            onDark ? "text-white" : "text-foreground",
          )}
        >
          Examination Hub
        </span>
        <span
          className={cn(
            "truncate text-[11px] font-medium",
            onDark ? "text-[var(--side-text)]" : "text-muted-foreground",
          )}
        >
          DPS International School
        </span>
      </span>
    </span>
  );
}
