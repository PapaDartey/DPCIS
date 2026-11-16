import { useEffect } from "react";
import { Navigate } from "react-router-dom";

import { BrandLogo } from "@/components/BrandLogo";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ErrorStatePanel, LoadingStatePanel } from "@/components/ui/state-panel";
import { AuthBoundary } from "@/features/auth/AuthBoundary";
import { LoginSlideshow } from "@/features/auth/LoginSlideshow";
import { useAuth } from "@/features/auth/useAuth";
import { useHealthCheck } from "@/hooks/useHealthCheck";

export function OverviewPage() {
  const {
    isConfigured,
    isLoading,
    sessionUser,
    identity,
    errorMessage,
    refreshAuth,
    signOut,
  } = useAuth();
  const { state: healthState, refresh: refreshHealth } = useHealthCheck();

  useEffect(() => {
    if (import.meta.env.DEV && healthState.kind === "unreachable") {
      console.warn(
        "[Examination Hub] Background connectivity check unavailable:",
        healthState.errorMessage,
      );
    }
  }, [healthState]);

  if (isConfigured && isLoading) {
    return (
      <div className="mx-auto flex min-h-dvh max-w-md flex-col justify-center space-y-6 px-4 py-8">
        <header className="flex flex-col items-center space-y-3 text-center">
          <BrandLogo size={64} variant="mark" />
          <h1
            tabIndex={-1}
            className="text-2xl font-semibold tracking-tight text-foreground outline-none sm:text-3xl"
          >
            Examination Hub
          </h1>
          <p className="text-sm text-muted-foreground sm:text-base">
            DPS International School · Checking your session...
          </p>
        </header>
        <LoadingStatePanel label="Checking your session..." cards={1} />
      </div>
    );
  }

  if (isConfigured && sessionUser && identity) {
    return <Navigate to={identity.role === "ADMIN" ? "/admin" : "/student"} replace />;
  }

  if (isConfigured && sessionUser && !identity) {
    return (
      <div className="mx-auto flex min-h-dvh max-w-xl flex-col justify-center space-y-6 px-4 py-8">
        <header className="flex flex-col items-center space-y-3 text-center">
          <BrandLogo size={64} variant="mark" />
          <h1
            tabIndex={-1}
            className="text-2xl font-semibold tracking-tight text-foreground outline-none sm:text-3xl"
          >
            Examination Hub
          </h1>
          <p className="text-sm text-muted-foreground sm:text-base">
            DPS International School · Service Beyond Self
          </p>
        </header>

        <ErrorStatePanel
          title="We could not open your workspace right now."
          message={errorMessage ?? "Please check your connection and try again."}
          retryLabel="Try Again"
          onRetry={() => void refreshAuth()}
          action={
            <Button type="button" variant="outline" onClick={() => void signOut()}>
              Sign out
            </Button>
          }
        />
      </div>
    );
  }

  return (
    <div className="auth-stage grid min-h-dvh w-full bg-card lg:grid-cols-[minmax(0,58fr)_minmax(0,42fr)]">
      <LoginSlideshow />

      <section
        aria-label="Account access"
        className="auth-form-column flex min-w-0 flex-col justify-between px-6 py-8 sm:px-10 sm:py-10 lg:min-h-dvh lg:px-12 lg:py-10"
      >
        <div className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center space-y-6">
          <div className="flex flex-col items-start space-y-3">
            <BrandLogo size={96} variant="mark" className="-ml-6" />
            <div className="space-y-1">
              <h1
                tabIndex={-1}
                className="text-2xl font-bold tracking-tight text-foreground outline-none sm:text-[1.75rem]"
              >
                Welcome to Examination Hub
              </h1>
              <p className="text-sm font-medium text-muted-foreground">
                DPS International School
              </p>
            </div>
          </div>

          {healthState.kind === "unreachable" ? (
            <Alert variant="warning" role="status">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0 space-y-1">
                  <AlertTitle>We&apos;re having trouble connecting to Examination Hub.</AlertTitle>
                  <AlertDescription>Please check your connection and try again.</AlertDescription>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  className="min-h-[44px] shrink-0"
                  onClick={() => void refreshHealth()}
                >
                  Try Again
                </Button>
              </div>
            </Alert>
          ) : null}

          <AuthBoundary embedded onAuthSuccess={refreshAuth} />
        </div>

        <footer className="mx-auto mt-8 flex w-full max-w-md items-center justify-between border-t border-border pt-4 text-xs text-muted-foreground">
          <span>Service Beyond Self</span>
          <span>DPS International School</span>
        </footer>
      </section>
    </div>
  );
}
