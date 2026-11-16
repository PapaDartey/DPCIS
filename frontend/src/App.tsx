import { Suspense, lazy } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import { ErrorBoundary } from "@/components/ErrorBoundary";
import { LoadingStatePanel } from "@/components/ui/state-panel";
import { AuthProvider } from "@/features/auth/AuthContext";
import { ProtectedRoute } from "@/features/auth/ProtectedRoute";
import { AppShell } from "@/layouts/AppShell";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { OverviewPage } from "@/pages/OverviewPage";

const StudentDashboardPage = lazy(() =>
  import("@/pages/StudentDashboardPage").then((m) => ({ default: m.StudentDashboardPage })),
);
const StudentExamInstructionsPage = lazy(() =>
  import("@/pages/StudentExamInstructionsPage").then((m) => ({
    default: m.StudentExamInstructionsPage,
  })),
);
const StudentAttemptPage = lazy(() =>
  import("@/pages/StudentAttemptPage").then((m) => ({ default: m.StudentAttemptPage })),
);
const StudentResultPage = lazy(() =>
  import("@/pages/StudentResultPage").then((m) => ({ default: m.StudentResultPage })),
);
const AdminOverviewPage = lazy(() =>
  import("@/pages/AdminOverviewPage").then((m) => ({ default: m.AdminOverviewPage })),
);
const AdminDashboardPage = lazy(() =>
  import("@/pages/AdminDashboardPage").then((m) => ({ default: m.AdminDashboardPage })),
);
const AdminResultsPage = lazy(() =>
  import("@/pages/AdminResultsPage").then((m) => ({ default: m.AdminResultsPage })),
);
const AdminExamNewPage = lazy(() =>
  import("@/pages/AdminExamNewPage").then((m) => ({ default: m.AdminExamNewPage })),
);
const AdminExamEditorPage = lazy(() =>
  import("@/pages/AdminExamEditorPage").then((m) => ({ default: m.AdminExamEditorPage })),
);
const AdminExamResultsPage = lazy(() =>
  import("@/pages/AdminExamResultsPage").then((m) => ({ default: m.AdminExamResultsPage })),
);

function RouteChunkFallback() {
  return (
    <div className="py-4">
      <LoadingStatePanel label="Loading page..." cards={3} />
    </div>
  );
}

export function App() {
  return (
    <ErrorBoundary fallbackTitle="Examination Hub could not initialize">
      <AuthProvider>
        <BrowserRouter>
          <Suspense fallback={<RouteChunkFallback />}>
            <Routes>
              <Route element={<AppShell />}>
                <Route path="/" element={<OverviewPage />} />
                <Route element={<ProtectedRoute requiredRole="STUDENT" />}>
                  <Route path="/student" element={<StudentDashboardPage />} />
                  <Route path="/student/exams/:examId" element={<StudentExamInstructionsPage />} />
                  <Route path="/student/attempts/:attemptId" element={<StudentAttemptPage />} />
                  <Route path="/student/results/:attemptId" element={<StudentResultPage />} />
                </Route>
                <Route element={<ProtectedRoute requiredRole="ADMIN" />}>
                  <Route path="/admin" element={<AdminOverviewPage />} />
                  <Route path="/admin/exams" element={<AdminDashboardPage />} />
                  <Route path="/admin/results" element={<AdminResultsPage />} />
                  <Route path="/admin/exams/new" element={<AdminExamNewPage />} />
                  <Route path="/admin/exams/:examId" element={<AdminExamEditorPage />} />
                  <Route path="/admin/exams/:examId/results" element={<AdminExamResultsPage />} />
                </Route>
                <Route path="*" element={<NotFoundPage />} />
              </Route>
            </Routes>
          </Suspense>
        </BrowserRouter>
      </AuthProvider>
    </ErrorBoundary>
  );
}

export default App;
