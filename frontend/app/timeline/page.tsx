"use client";

import {
  BookOpen,
  ChevronDown,
  Flag,
  MapPin,
  Music,
  Scale,
  ShoppingBag,
  User,
  Users,
  Wallet,
  type LucideIcon,
} from "lucide-react";
import { useState } from "react";

import { NativeSelect } from "@/components/form";
import { EmptyState, ErrorText, Page, PageHeader } from "@/components/page";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { useApi } from "@/hooks/use-api";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { TimelineDay, TimelineKind, TimelineTag } from "@/types/api";

const ICONS: Record<TimelineKind, LucideIcon> = {
  event: Flag,
  decision: Scale,
  interaction: Users,
  music: Music,
  journal: BookOpen,
  purchase: ShoppingBag,
};

const TAG_ICONS: Record<TimelineTag["kind"], LucideIcon> = {
  person: User,
  place: MapPin,
  amount: Wallet,
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

function DayCard({ day }: { day: TimelineDay }) {
  const [open, setOpen] = useState(false);
  const Icon = ICONS[day.headline_kind];
  const count = day.moments.length;
  return (
    <li className="relative">
      <span
        className={cn(
          "absolute top-4 -left-[33px] flex size-5 items-center justify-center rounded-full border border-border bg-background",
          day.importance_score >= 5 && "border-foreground/60",
        )}
      >
        <Icon className="size-3 text-muted-foreground" />
      </span>
      <article className="rounded-xl border border-border p-4">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <span className="text-xs text-muted-foreground">{formatDate(day.date)}</span>
          <h3 className={cn("text-sm", day.importance_score >= 4 && "font-medium")}>
            {day.headline}
          </h3>
          {day.importance_score >= 5 && (
            <Badge variant="secondary" className="font-normal">
              core memory
            </Badge>
          )}
        </div>
        {day.summary && day.summary !== day.headline && (
          <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">{day.summary}</p>
        )}
        {day.tags.length > 0 && (
          <ul className="mt-2 flex flex-wrap gap-1.5" aria-label="Tags">
            {day.tags.map((tag) => {
              const TagIcon = TAG_ICONS[tag.kind];
              return (
                <li key={`${tag.kind}-${tag.label}`}>
                  <Badge variant="outline" className="gap-1 font-normal">
                    <TagIcon className="size-3" />
                    {tag.label}
                  </Badge>
                </li>
              );
            })}
          </ul>
        )}
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="mt-3 flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        >
          <ChevronDown className={cn("size-3.5 transition-transform", open && "rotate-180")} />
          {open ? "Hide" : "Show"} {count} {count === 1 ? "moment" : "moments"}
        </button>
        {open && (
          <ol className="mt-3 space-y-3 border-t border-border pt-3">
            {day.moments.map((moment, i) => {
              const MomentIcon = ICONS[moment.kinds[0]];
              return (
                <li key={moment.journal_entry_id ?? i} className="flex gap-2.5">
                  <MomentIcon className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
                  <div className="min-w-0">
                    <p className={cn("text-sm", moment.importance_score >= 4 && "font-medium")}>
                      {moment.line}
                    </p>
                    {moment.text && moment.text !== moment.line && (
                      <p className="mt-0.5 text-sm leading-relaxed whitespace-pre-wrap text-muted-foreground">
                        {moment.text}
                      </p>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </article>
    </li>
  );
}

export default function TimelinePage() {
  const [minImportance, setMinImportance] = useState("2");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const days = useApi<TimelineDay[]>("/timeline", {
    min_importance: minImportance,
    date_from: from,
    date_to: to,
    limit: 500,
  });

  // Group days by month, newest first (the API already sorts).
  const groups: [string, TimelineDay[]][] = [];
  for (const day of days.data ?? []) {
    const key = day.date.slice(0, 7);
    const last = groups.at(-1);
    if (last && last[0] === key) last[1].push(day);
    else groups.push([key, [day]]);
  }

  return (
    <Page>
      <PageHeader
        title="Timeline"
        description="One card per day: events, decisions, people, music, important entries and major purchases."
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

      {days.error && <ErrorText>{days.error}</ErrorText>}
      {days.data?.length === 0 && <EmptyState>Nothing on the timeline for these filters.</EmptyState>}

      {groups.map(([month, monthDays]) => (
        <section key={month}>
          <h2 className="mb-3 text-sm font-medium text-muted-foreground">{monthLabel(month)}</h2>
          <ol className="relative space-y-4 border-l border-border pl-6">
            {monthDays.map((day) => (
              <DayCard key={day.date} day={day} />
            ))}
          </ol>
        </section>
      ))}
    </Page>
  );
}
