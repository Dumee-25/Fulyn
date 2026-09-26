"use client";

import { Check, Repeat } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { apiSend } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Reminder } from "@/types/api";

function ReminderRow({ reminder, onChange }: { reminder: Reminder; onChange: () => void }) {
  const [pending, setPending] = useState(false);
  const overdue = reminder.status === "pending" && new Date(reminder.due_at) < new Date();

  async function complete() {
    setPending(true);
    try {
      await apiSend("POST", `/reminders/${reminder.id}/complete`);
      onChange();
    } finally {
      setPending(false);
    }
  }

  return (
    <li className="flex items-center gap-3 py-2">
      {reminder.status === "pending" && (
        <Button
          variant="outline"
          size="icon-xs"
          aria-label="Mark done"
          disabled={pending}
          onClick={() => void complete()}
          className="rounded-full"
        >
          <Check />
        </Button>
      )}
      <div className="flex-1 text-sm">
        <span className={cn(reminder.status !== "pending" && "line-through opacity-60")}>
          {reminder.title}
        </span>
        {reminder.description && (
          <p className="text-xs text-muted-foreground">{reminder.description}</p>
        )}
      </div>
      {reminder.recurrence_rule && (
        <span className="flex items-center gap-1 text-xs text-muted-foreground">
          <Repeat className="size-3" />
          {reminder.recurrence_rule}
        </span>
      )}
      <span className={cn("text-xs", overdue ? "text-destructive" : "text-muted-foreground")}>
        {formatDateTime(reminder.due_at)}
      </span>
    </li>
  );
}

export function ReminderList({
  reminders,
  onChange,
}: {
  reminders: Reminder[];
  onChange: () => void;
}) {
  return (
    <ul className="divide-y divide-border">
      {reminders.map((r) => (
        <ReminderRow key={r.id} reminder={r} onChange={onChange} />
      ))}
    </ul>
  );
}
