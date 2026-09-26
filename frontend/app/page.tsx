import { BackendStatus } from "@/components/backend-status";
import { DashboardAnalytics } from "@/components/dashboard-analytics";
import { Page, PageHeader } from "@/components/page";
import { PlanningSummary } from "@/components/planning-summary";
import { TodaySummary } from "@/components/today-summary";

export default function DashboardPage() {
  return (
    <Page className="max-w-5xl">
      <PageHeader title="Today" />
      <TodaySummary />
      <PlanningSummary />
      <DashboardAnalytics />
      <details className="text-sm text-muted-foreground">
        <summary className="cursor-pointer select-none">System status</summary>
        <div className="mt-3">
          <BackendStatus />
        </div>
      </details>
    </Page>
  );
}
