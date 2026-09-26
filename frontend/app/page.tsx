import { BackendStatus } from "@/components/backend-status";
import { Page, PageHeader } from "@/components/page";
import { TodaySummary } from "@/components/today-summary";

export default function DashboardPage() {
  return (
    <Page>
      <PageHeader title="Today" />
      <TodaySummary />
      <BackendStatus />
    </Page>
  );
}
