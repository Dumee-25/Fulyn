import { BackendStatus } from "@/components/backend-status";

export default function DashboardPage() {
  return (
    <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-12 sm:px-6">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">Fulyn</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Your private life log. Chat, journal and dashboards arrive in the next phases.
        </p>
      </header>
      <BackendStatus />
    </main>
  );
}
