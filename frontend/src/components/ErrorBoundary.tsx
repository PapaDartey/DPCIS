import { AlertTriangle, RotateCcw } from "lucide-react";
import { Component, type ErrorInfo, type ReactNode } from "react";

import { BrandLogo } from "@/components/BrandLogo";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

export interface ErrorBoundaryProps {
  children: ReactNode;
  resetKeys?: readonly unknown[];
  fallbackTitle?: string;
}

interface ErrorBoundaryState {
  hasError: boolean;
  isChunkError: boolean;
}

function isChunkLoadError(error: unknown): boolean {
  if (!(error instanceof Error)) {
    return false;
  }
  const msg = error.message.toLowerCase();
  return (
    error.name === "ChunkLoadError" ||
    msg.includes("loading chunk") ||
    msg.includes("failed to fetch dynamically imported module") ||
    msg.includes("importing a module script failed")
  );
}

function keysChanged(
  prevKeys: readonly unknown[] | undefined,
  nextKeys: readonly unknown[] | undefined,
): boolean {
  if (!prevKeys || !nextKeys) {
    return prevKeys !== nextKeys;
  }
  if (prevKeys.length !== nextKeys.length) {
    return true;
  }
  return prevKeys.some((item, index) => !Object.is(item, nextKeys[index]));
}

export class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { hasError: false, isChunkError: false };

  static getDerivedStateFromError(error: unknown): ErrorBoundaryState {
    return { hasError: true, isChunkError: isChunkLoadError(error) };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("ErrorBoundary caught rendering error:", error, info.componentStack);
  }

  componentDidUpdate(prevProps: ErrorBoundaryProps): void {
    if (this.state.hasError && keysChanged(prevProps.resetKeys, this.props.resetKeys)) {
      this.setState({ hasError: false, isChunkError: false });
    }
  }

  private handleReset = () => {
    this.setState({ hasError: false, isChunkError: false });
  };

  private handleReload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="my-6 space-y-4">
          <div className="flex justify-center">
            <BrandLogo size={64} variant="mark" />
          </div>
          <Alert variant="destructive" role="alert">
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-0.5 size-5 shrink-0" aria-hidden="true" />
              <div className="space-y-3">
                <div>
                  <AlertTitle>
                    {this.state.isChunkError
                      ? "A new version or network interruption prevented this page from loading"
                      : (this.props.fallbackTitle ?? "Something unexpected interrupted this view")}
                  </AlertTitle>
                  <AlertDescription>
                    {this.state.isChunkError
                      ? "Reload the application to fetch the latest page bundle."
                      : "No local data was lost. You can reload this section or return to another route."}
                  </AlertDescription>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button variant="outline" size="sm" onClick={this.handleReload}>
                    <RotateCcw className="size-4" aria-hidden="true" />
                    Reload
                  </Button>
                  {!this.state.isChunkError ? (
                    <Button variant="ghost" size="sm" onClick={this.handleReset}>
                      Retry view
                    </Button>
                  ) : null}
                </div>
              </div>
            </div>
          </Alert>
        </div>
      );
    }

    return this.props.children;
  }
}
