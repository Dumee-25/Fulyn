"use client";

import { Card, CardContent } from "@/components/ui/card";
import { useApi } from "@/hooks/use-api";
import { formatDuration, formatMoney, todayISO } from "@/lib/format";
import type { CaffeineLog, ExpenseSummary, MoodLog, SleepLog } from "@/types/api";

function Tile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card size="sm">
      <CardContent>
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="mt-1 font-mono text-lg">{value}</p>
        {hint && <p className="mt-0.5 truncate text-xs text-muted-foreground">{hint}</p>}
      </CardContent>
    </Card>
  );
}

export function TodaySummary() {
  const today = todayISO();
  const range = { date_from: today, date_to: today };
  const moods = useApi<MoodLog[]>("/moods", { ...range, limit: 1 });
  const sleep = useApi<SleepLog[]>("/sleep", { ...range, limit: 1 });
  const caffeine = useApi<CaffeineLog[]>("/caffeine", range);
  const spend = useApi<ExpenseSummary>("/expenses/summary", range);

  const mood = moods.data?.[0];
  const night = sleep.data?.[0];
  const drinks = caffeine.data ?? [];

  return (
    <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <Tile
        label="Mood"
        value={mood?.label ?? (mood?.score ? `${mood.score}/10` : "—")}
        hint={mood?.energy_score ? `energy ${mood.energy_score}/10` : undefined}
      />
      <Tile
        label="Sleep"
        value={night ? formatDuration(night.duration_minutes, night.is_approximate) : "—"}
      />
      <Tile
        label="Caffeine"
        value={String(drinks.length)}
        hint={drinks.map((d) => d.drink_type).join(", ") || undefined}
      />
      <Tile
        label="Spent"
        value={spend.data ? formatMoney(spend.data.total, spend.data.currency) : "—"}
      />
    </section>
  );
}
