import { BackendStatus } from "@/components/backend-status";
import { Page, PageHeader } from "@/components/page";
import { PlanningSummary } from "@/components/planning-summary";
import { TodaySummary } from "@/components/today-summary";

export default function DashboardPage() {
  return (
    <Page>
      <PageHeader title="Today" />
      <TodaySummary />
      <PlanningSummary />
      <BackendStatus />
    </Page>
  );
}
