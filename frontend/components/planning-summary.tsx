"use client";

import Link from "next/link";
import { useState } from "react";

import { ReminderList } from "@/components/reminder-list";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useApi } from "@/hooks/use-api";
import type { Reminder, WaitingItem } from "@/types/api";

/** End of the local day, `days` from today. Stable for the whole day. */
function endOfDayIn(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  d.setHours(23, 59, 59, 0);
  return d.toISOString();
}

/** Dashboard: reminders due in the next week (and overdue ones) and open waiting items. */
export function PlanningSummary() {
  // Computed once: a query value that changes on every render would refetch forever.
  const [dueBefore] = useState(() => endOfDayIn(7));
  const reminders = useApi<Reminder[]>("/reminders", { due_before: dueBefore, limit: 8 });
  const waiting = useApi<WaitingItem[]>("/waiting", { limit: 5 });

  return (
    <div className="grid gap-3 md:grid-cols-2">
      <Card size="sm">
        <CardHeader>
          <CardTitle>Coming up</CardTitle>
          <CardAction>
            <Link href="/reminders" className="text-xs text-muted-foreground hover:text-foreground">
              All reminders
            </Link>
          </CardAction>
        </CardHeader>
        <CardContent>
          {reminders.data?.length === 0 && (
            <p className="text-sm text-muted-foreground">Nothing due this week.</p>
          )}
          {reminders.data && (
            <ReminderList reminders={reminders.data} onChange={reminders.reload} />
          )}
        </CardContent>
      </Card>
      <Card size="sm">
        <CardHeader>
          <CardTitle>Waiting for</CardTitle>
          <CardAction>
            <Link href="/waiting" className="text-xs text-muted-foreground hover:text-foreground">
              All
            </Link>
          </CardAction>
        </CardHeader>
        <CardContent>
          {waiting.data?.length === 0 && (
            <p className="text-sm text-muted-foreground">Nothing pending.</p>
          )}
          <ul className="space-y-1.5">
            {waiting.data?.map((w) => (
              <li key={w.id} className="flex items-center gap-2 text-sm">
                {w.title}
                {w.overdue && (
                  <Badge variant="destructive" className="font-normal">
                    overdue
                  </Badge>
                )}
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
