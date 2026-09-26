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
    </Page>
  );
}
