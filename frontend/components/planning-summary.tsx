"use client";

import Link from "next/link";

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

function inDays(days: number): string {
  const d = new Date(Date.now() + days * 86_400_000);
  return d.toISOString();
}

/** Dashboard: reminders due in the next week (and overdue ones) and open waiting items. */
export function PlanningSummary() {
  const reminders = useApi<Reminder[]>("/reminders", { due_before: inDays(7), limit: 8 });
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
