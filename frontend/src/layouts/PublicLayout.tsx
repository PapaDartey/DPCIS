import type { ReactNode, RefObject } from "react";
import { NavLink, useLocation } from "react-router-dom";

import { BrandLogo } from "@/components/BrandLogo";
import { cn } from "@/lib/utils";

export interface PublicLayoutProps {
  mainRef: RefObject<HTMLElement | null>;
  children: ReactNode;
}

export function PublicLayout({ mainRef, children }: PublicLayoutProps) {
  const { pathname } = useLocation();
  const isLoginRoute = pathname === "/";

  return (
    <div className="flex min-h-dvh flex-col bg-background text-foreground">
      {!isLoginRoute ? (
        <header className="sticky top-0 z-30 border-b border-border bg-card/95 backdrop-blur-xs">
          <div className="mx-auto flex min-h-[60px] max-w-7xl items-center justify-between gap-4 px-4 sm:px-6">
            <NavLink
              to="/"
              className="inline-flex min-h-11 items-center rounded-md no-underline"
            >
              <BrandLogo size={32} variant="lockup" />
            </NavLink>

            <span className="hidden text-xs font-medium text-muted-foreground sm:inline">
              Service Beyond Self
            </span>
          </div>
        </header>
      ) : null}

      <main
        id="main-content"
        ref={mainRef}
        className={cn(
          "mx-auto w-full flex-1 outline-none",
          isLoginRoute ? "max-w-none p-0" : "max-w-[1160px] px-4 py-8 sm:px-6 sm:py-10",
        )}
      >
        {children}
      </main>

      {!isLoginRoute ? (
        <footer className="border-t border-border bg-card">
          <div className="mx-auto flex max-w-[1160px] flex-col gap-2 px-4 py-4 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-6">
            <div className="flex items-center gap-2">
              <BrandLogo size={24} variant="mark" />
              <span>DPS International Ghana — Examination Hub</span>
            </div>
            <p>Service Beyond Self</p>
          </div>
        </footer>
      ) : null}
    </div>
  );
}
