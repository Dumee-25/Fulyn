"use client";

import { useState } from "react";

import { Field, NativeSelect, formValue, useFormSubmit } from "@/components/form";
import { EmptyState, ErrorText, Page, PageHeader } from "@/components/page";
import { ReminderList } from "@/components/reminder-list";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useApi } from "@/hooks/use-api";
import { apiSend } from "@/lib/api";
import { RECURRENCE_RULES, type Reminder } from "@/types/api";

const TABS = [
  { value: "pending", label: "Upcoming" },
  { value: "completed", label: "Done" },
  { value: "cancelled", label: "Cancelled" },
] as const;

export default function RemindersPage() {
  const [status, setStatus] = useState<string>("pending");
  const reminders = useApi<Reminder[]>("/reminders", { status, limit: 200 });

  const form = useFormSubmit(async (data) => {
    const date = data.get("date");
    const time = formValue(data, "time") ?? "09:00";
    await apiSend("POST", "/reminders", {
      title: data.get("title"),
      due_at: `${date}T${time}:00`,
      recurrence_rule: formValue(data, "recurrence_rule"),
    });
    await reminders.reload();
  });

  return (
    <Page>
      <PageHeader title="Reminders" description="Shown here and on the dashboard." />

      <Card>
        <CardContent>
          <form onSubmit={form.onSubmit} className="grid gap-3 sm:grid-cols-6">
            <Field label="Remind me to" htmlFor="title" className="sm:col-span-2">
              <Input id="title" name="title" required maxLength={200} />
            </Field>
            <Field label="Date" htmlFor="date">
              <Input id="date" name="date" type="date" required />
            </Field>
            <Field label="Time" htmlFor="time">
              <Input id="time" name="time" type="time" placeholder="09:00" />
            </Field>
            <Field label="Repeat" htmlFor="recurrence_rule">
              <NativeSelect id="recurrence_rule" name="recurrence_rule" defaultValue="">
                <option value="">never</option>
                {RECURRENCE_RULES.map((r) => (
                  <option key={r}>{r}</option>
                ))}
              </NativeSelect>
            </Field>
            <div className="flex items-end">
              <Button type="submit" disabled={form.pending} className="w-full">
                Add
              </Button>
            </div>
            {form.error && <ErrorText>{form.error}</ErrorText>}
          </form>
        </CardContent>
      </Card>

      <div className="flex gap-1">
        {TABS.map((t) => (
          <Button
            key={t.value}
            variant={status === t.value ? "secondary" : "ghost"}
            size="sm"
            onClick={() => setStatus(t.value)}
          >
            {t.label}
          </Button>
        ))}
      </div>

      {reminders.error && <ErrorText>{reminders.error}</ErrorText>}
      {reminders.data?.length === 0 && <EmptyState>Nothing here.</EmptyState>}
      {reminders.data && <ReminderList reminders={reminders.data} onChange={reminders.reload} />}
    </Page>
  );
}
