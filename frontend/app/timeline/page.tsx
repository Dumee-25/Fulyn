"use client";

import {
  BookOpen,
  Flag,
  Music,
  Scale,
  ShoppingBag,
  Users,
  type LucideIcon,
} from "lucide-react";
import { useState } from "react";

import { NativeSelect } from "@/components/form";
import { EmptyState, ErrorText, Page, PageHeader } from "@/components/page";
import { Input } from "@/components/ui/input";
import { useApi } from "@/hooks/use-api";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { TimelineItem, TimelineKind } from "@/types/api";

const ICONS: Record<TimelineKind, LucideIcon> = {
  event: Flag,
  decision: Scale,
  interaction: Users,
  music: Music,
  journal: BookOpen,
  purchase: ShoppingBag,
};

const FILTERS = [
  { value: "1", label: "Everything notable" },
  { value: "2", label: "Normal and up" },
  { value: "3", label: "Notable and up" },
  { value: "4", label: "Important and up" },
  { value: "5", label: "Core memories" },
];

function monthLabel(iso: string): string {
  const [y, m] = iso.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString("en-GB", { month: "long", year: "numeric" });
}

export default function TimelinePage() {
  const [minImportance, setMinImportance] = useState("2");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const items = useApi<TimelineItem[]>("/timeline", {
    min_importance: minImportance,
    date_from: from,
    date_to: to,
    limit: 500,
  });

  // Group by month, newest first (the API already sorts).
  const groups: [string, TimelineItem[]][] = [];
  for (const item of items.data ?? []) {
    const key = item.date.slice(0, 7);
    const last = groups.at(-1);
    if (last && last[0] === key) last[1].push(item);
    else groups.push([key, [item]]);
  }

  return (
    <Page>
      <PageHeader
        title="Timeline"
        description="Events, decisions, people, music, important entries and major purchases."
      />

      <div className="flex flex-wrap gap-2">
        <NativeSelect
          aria-label="Minimum importance"
          className="w-48"
          value={minImportance}
          onChange={(e) => setMinImportance(e.target.value)}
        >
          {FILTERS.map((f) => (
            <option key={f.value} value={f.value}>
              {f.label}
            </option>
          ))}
        </NativeSelect>
        <Input type="date" aria-label="From" value={from} onChange={(e) => setFrom(e.target.value)} className="w-40" />
        <Input type="date" aria-label="To" value={to} onChange={(e) => setTo(e.target.value)} className="w-40" />
      </div>

      {items.error && <ErrorText>{items.error}</ErrorText>}
      {items.data?.length === 0 && <EmptyState>Nothing on the timeline for these filters.</EmptyState>}

      {groups.map(([month, monthItems]) => (
        <section key={month}>
          <h2 className="mb-3 text-sm font-medium text-muted-foreground">{monthLabel(month)}</h2>
          <ol className="relative space-y-4 border-l border-border pl-6">
            {monthItems.map((item) => {
              const Icon = ICONS[item.kind];
              return (
                <li key={`${item.kind}-${item.id}`} className="relative">
                  <span
                    className={cn(
                      "absolute top-0.5 -left-[33px] flex size-5 items-center justify-center rounded-full border border-border bg-background",
                      item.importance_score >= 5 && "border-foreground/60",
                    )}
                  >
                    <Icon className="size-3 text-muted-foreground" />
                  </span>
                  <div className="flex flex-wrap items-baseline gap-x-2">
                    <span className="text-xs text-muted-foreground">{formatDate(item.date)}</span>
                    <span className={cn("text-sm", item.importance_score >= 4 && "font-medium")}>
                      {item.title}
                    </span>
                    {item.importance_score >= 5 && (
                      <span className="text-xs text-muted-foreground">· core memory</span>
                    )}
                  </div>
                  {item.detail && item.detail !== item.title && (
                    <p className="mt-0.5 line-clamp-2 text-sm text-muted-foreground">{item.detail}</p>
                  )}
                </li>
              );
            })}
          </ol>
        </section>
      ))}
    </Page>
  );
}
