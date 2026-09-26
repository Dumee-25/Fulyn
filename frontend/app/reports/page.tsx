"use client";

import { RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";

import { Markdown } from "@/components/markdown";
import { ErrorText, Page, PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, apiGet, apiSend } from "@/lib/api";
import { formatDateTime, todayISO } from "@/lib/format";
import type { Report } from "@/types/api";

type Kind = "daily" | "weekly" | "monthly";

const TABS: { value: Kind; label: string }[] = [
  { value: "daily", label: "Daily" },
  { value: "weekly", label: "Weekly" },
  { value: "monthly", label: "Monthly" },
];

function queryFor(kind: Kind, date: string, month: string) {
  if (kind === "monthly") {
    const [year, m] = month.split("-").map(Number);
    return { query: { year, month: m }, body: { year, month: m } };
  }
  return { query: { date }, body: { date } };
}

export default function ReportsPage() {
  const [kind, setKind] = useState<Kind>("daily");
  const [date, setDate] = useState(todayISO());
  const [month, setMonth] = useState(todayISO().slice(0, 7));
  const [report, setReport] = useState<Report | null>(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  // Load the stored report for the selected period, if there is one.
  useEffect(() => {
    let cancelled = false;
    const { query } = queryFor(kind, date, month);
    apiGet<Report>(`/reports/${kind}`, query)
      .then((r) => {
        if (cancelled) return;
        setReport(r);
        setMissing(false);
        setError(null);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setReport(null);
        if (e instanceof ApiError && e.status === 404) {
          setMissing(true);
          setError(null);
        } else {
          setError(e instanceof Error ? e.message : "Could not load the report");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [kind, date, month]);

  async function generate() {
    setPending(true);
    setError(null);
    try {
      setReport(await apiSend<Report>("POST", `/reports/${kind}`, queryFor(kind, date, month).body));
      setMissing(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not generate the report");
    } finally {
      setPending(false);
    }
  }

  return (
    <Page>
      <PageHeader
        title="Reports"
        description="Built from what you logged. Private entries are never included."
      />

      <div className="flex flex-wrap items-center gap-2">
        {TABS.map((t) => (
          <Button
            key={t.value}
            variant={kind === t.value ? "secondary" : "ghost"}
            size="sm"
            onClick={() => setKind(t.value)}
          >
            {t.label}
          </Button>
        ))}
        <span className="ml-auto" />
        {kind === "monthly" ? (
          <Input
            type="month"
            aria-label="Month"
            value={month}
            max={todayISO().slice(0, 7)}
            onChange={(e) => setMonth(e.target.value)}
            className="w-44"
          />
        ) : (
          <Input
            type="date"
            aria-label={kind === "weekly" ? "Any day in the week" : "Day"}
            value={date}
            max={todayISO()}
            onChange={(e) => setDate(e.target.value)}
            className="w-44"
          />
        )}
        <Button onClick={() => void generate()} disabled={pending}>
          <RefreshCw className={pending ? "animate-spin" : ""} />
          {report ? "Regenerate" : "Generate"}
        </Button>
      </div>

      {error && <ErrorText>{error}</ErrorText>}
      {pending && <p className="text-sm text-muted-foreground">Building the report…</p>}
      {missing && !pending && (
        <p className="py-8 text-center text-sm text-muted-foreground">
          No {kind} report for this period yet.
        </p>
      )}
      {report && !pending && (
        <Card>
          <CardContent>
            <Markdown source={report.content} />
            <p className="mt-4 text-xs text-muted-foreground">
              Generated {formatDateTime(report.generated_at)}
            </p>
          </CardContent>
        </Card>
      )}
    </Page>
  );
}
