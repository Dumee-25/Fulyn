"use client";

import Link from "next/link";

import { BarList, DailyBars, MoodEnergyLines } from "@/components/charts";
import { ErrorText } from "@/components/page";
import { Badge } from "@/components/ui/badge";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useApi } from "@/hooks/use-api";
import { formatDate, formatDuration, formatMoney } from "@/lib/format";

type Daily<K extends string> = ({ date: string } & Record<K, number | null>)[];

interface Dashboard {
  today: string;
  spending: {
    month_total: string;
    month_impulse: string;
    currency: string;
    by_category: { category: string; total: string }[];
    subscriptions: { totals: { currency: string; monthly_total: string; count: number }[] };
    daily: { date: string; total: string | null }[];
  };
  mood: { daily: Daily<"mood" | "energy">; average: number | null; energy_average: number | null };
  sleep: { daily: Daily<"minutes">; average_minutes: number | null };
  caffeine: { daily: Daily<"drinks">; by_hour: { hour: number; drinks: number }[] };
  people: {
    recent: { date: string; person: string; summary: string }[];
    counts: { name: string; count: number }[];
  };
  memories: {
    important: { date: string; type: string; title: string | null }[];
    core: { date: string; type: string; title: string | null }[];
  };
  decisions: { date: string; title: string; status: string }[];
}

function Section({
  title,
  href,
  children,
  className,
}: {
  title: string;
  href?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <Card size="sm" className={className}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {href && (
          <CardAction>
            <Link href={href} className="text-xs text-muted-foreground hover:text-foreground">
              Open
            </Link>
          </CardAction>
        )}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="font-mono text-base">{value}</p>
    </div>
  );
}

export function DashboardAnalytics() {
  const { data, error } = useApi<Dashboard>("/analytics/dashboard", { days: 30 });
  if (error) return <ErrorText>{error}</ErrorText>;
  if (!data) return null;

  const cur = data.spending.currency;
  const money = (v: number) => formatMoney(String(v), cur);
  const subs = data.spending.subscriptions.totals.find((t) => t.currency === cur);
  const hours = data.caffeine.by_hour.filter((h) => h.drinks > 0);

  return (
    <div className="grid gap-3 md:grid-cols-2">
      <Section title="Spending" href="/expenses" className="md:col-span-2">
        <div className="mb-4 flex flex-wrap gap-8">
          <Stat label="This month" value={formatMoney(data.spending.month_total, cur)} />
          <Stat label="Impulse" value={formatMoney(data.spending.month_impulse, cur)} />
          <Stat
            label="Subscriptions / month"
            value={subs ? formatMoney(subs.monthly_total, cur) : "—"}
          />
        </div>
        <div className="grid gap-6 md:grid-cols-[2fr_1fr]">
          <div>
            <p className="mb-1 text-xs text-muted-foreground">Spent per day, last 30 days</p>
            <DailyBars
              data={data.spending.daily.map((d) => ({
                date: d.date,
                total: d.total === null ? null : Number(d.total),
              }))}
              valueKey="total"
              name="Spent"
              format={money}
            />
          </div>
          <div>
            <p className="mb-2 text-xs text-muted-foreground">This month by category</p>
            <BarList
              items={data.spending.by_category.map((c) => ({
                label: c.category,
                value: Number(c.total),
              }))}
              format={money}
            />
          </div>
        </div>
      </Section>

      <Section title="Mood and energy" href="/mood">
        <p className="mb-2 text-xs text-muted-foreground">
          30-day average: mood {data.mood.average ?? "—"}, energy {data.mood.energy_average ?? "—"}
        </p>
        <MoodEnergyLines data={data.mood.daily} />
      </Section>

      <Section title="Sleep" href="/sleep">
        <p className="mb-2 text-xs text-muted-foreground">
          30-day average: {formatDuration(data.sleep.average_minutes)}
        </p>
        <DailyBars
          data={data.sleep.daily}
          valueKey="minutes"
          name="Slept"
          format={(v) => formatDuration(v)}
          axisFormat={(v) => `${Math.round(v / 60)}h`}
        />
      </Section>

      <Section title="Caffeine" href="/caffeine">
        <p className="mb-1 text-xs text-muted-foreground">Drinks per day</p>
        <DailyBars
          data={data.caffeine.daily}
          valueKey="drinks"
          name="Drinks"
          format={(v) => String(Math.round(v * 10) / 10)}
          height={120}
        />
        {hours.length > 0 && (
          <>
            <p className="mt-4 mb-2 text-xs text-muted-foreground">When you drink it</p>
            <BarList
              items={hours.map((h) => ({ label: `${String(h.hour).padStart(2, "0")}:00`, value: h.drinks }))}
              format={(v) => String(v)}
            />
          </>
        )}
      </Section>

      <Section title="People" href="/people">
        {data.people.recent.length === 0 ? (
          <p className="text-sm text-muted-foreground">No interactions in the last 30 days.</p>
        ) : (
          <>
            <ul className="mb-3 space-y-1 text-sm">
              {data.people.recent.map((i, n) => (
                <li key={n} className="flex gap-2">
                  <span className="w-16 shrink-0 text-xs text-muted-foreground">
                    {formatDate(i.date).split(",")[1]}
                  </span>
                  <span>
                    {i.person} <span className="text-muted-foreground">· {i.summary}</span>
                  </span>
                </li>
              ))}
            </ul>
            <p className="text-xs text-muted-foreground">
              Last 30 days: {data.people.counts.map((c) => `${c.name} (${c.count})`).join(", ")}
            </p>
          </>
        )}
      </Section>

      <Section title="Memories" href="/memories">
        {data.memories.core.length === 0 && data.memories.important.length === 0 ? (
          <p className="text-sm text-muted-foreground">No important memories yet.</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {data.memories.core.map((m, n) => (
              <li key={`c${n}`} className="flex items-center gap-2">
                <Badge variant="secondary" className="font-normal">core</Badge>
                <span className="truncate">{m.title}</span>
              </li>
            ))}
            {data.memories.important
              .filter((m) => !data.memories.core.some((c) => c.title === m.title))
              .map((m, n) => (
                <li key={`i${n}`} className="truncate text-muted-foreground">
                  {m.title}
                </li>
              ))}
          </ul>
        )}
      </Section>

      <Section title="Recent decisions" href="/decisions">
        {data.decisions.length === 0 ? (
          <p className="text-sm text-muted-foreground">No decisions recorded.</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {data.decisions.map((d, n) => (
              <li key={n} className="flex items-center gap-2">
                <span className="truncate">{d.title}</span>
                {d.status !== "active" && (
                  <Badge variant="outline" className="font-normal">{d.status}</Badge>
                )}
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  );
}
