import { ArrowLeft } from "lucide-react";
import { Link } from "react-router-dom";

import { BrandLogo } from "@/components/BrandLogo";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";

export function NotFoundPage() {
  return (
    <div className="space-y-6">
      <div className="flex justify-start">
        <BrandLogo size={64} variant="mark" />
      </div>
      <PageHeader
        eyebrow="Not Found"
        title="Page not found"
        description="The page you were looking for could not be found."
      />
      <Button asChild variant="default">
        <Link to="/">
          <ArrowLeft className="size-4" aria-hidden="true" />
          <span>Return to Examination Hub</span>
        </Link>
      </Button>
    </div>
  );
}
