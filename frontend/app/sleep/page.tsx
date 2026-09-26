"use client";

import { DeleteButton } from "@/components/delete-button";
import { Checkbox, Field, formNumber, formValue, useFormSubmit } from "@/components/form";
import { EmptyState, ErrorText, Page, PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useApi } from "@/hooks/use-api";
import { apiSend } from "@/lib/api";
import { formatDate, formatDuration, formatTime } from "@/lib/format";
import type { SleepLog } from "@/types/api";

export default function SleepPage() {
  const logs = useApi<SleepLog[]>("/sleep", { limit: 100 });

  const form = useFormSubmit(async (data) => {
    const hours = formNumber(data, "hours");
    await apiSend("POST", "/sleep", {
      sleep_time: formValue(data, "sleep_time"),
      wake_time: formValue(data, "wake_time"),
      duration_minutes: hours === undefined ? undefined : Math.round(hours * 60),
      quality_score: formNumber(data, "quality_score"),
      is_approximate: data.get("is_approximate") === "on",
      notes: formValue(data, "notes"),
    });
    await logs.reload();
  });

  return (
    <Page>
      <PageHeader
        title="Sleep"
        description="Give times, or just a rough duration. Unknowns can stay empty."
      />

      <Card>
        <CardContent>
          <form onSubmit={form.onSubmit} className="grid gap-3 sm:grid-cols-6">
            <Field label="Fell asleep" htmlFor="sleep_time" className="sm:col-span-2">
              <Input id="sleep_time" name="sleep_time" type="datetime-local" />
            </Field>
            <Field label="Woke up" htmlFor="wake_time" className="sm:col-span-2">
              <Input id="wake_time" name="wake_time" type="datetime-local" />
            </Field>
            <Field label="Or hours" htmlFor="hours">
              <Input id="hours" name="hours" type="number" min="0" max="24" step="0.25" />
            </Field>
            <Field label="Quality 1–10" htmlFor="quality_score">
              <Input id="quality_score" name="quality_score" type="number" min="1" max="10" />
            </Field>
            <Field label="Notes" htmlFor="notes" className="sm:col-span-4">
              <Input id="notes" name="notes" />
            </Field>
            <div className="flex items-end gap-3 sm:col-span-2">
              <Checkbox name="is_approximate" label="Approximate" defaultChecked />
              <Button type="submit" disabled={form.pending} className="ml-auto">
                Log sleep
              </Button>
            </div>
            {form.error && <ErrorText>{form.error}</ErrorText>}
          </form>
        </CardContent>
      </Card>

      {logs.error && <ErrorText>{logs.error}</ErrorText>}
      {logs.data?.length === 0 && <EmptyState>No sleep logs yet.</EmptyState>}
      {!!logs.data?.length && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Woke on</TableHead>
              <TableHead>Asleep</TableHead>
              <TableHead>Awake</TableHead>
              <TableHead>Duration</TableHead>
              <TableHead>Quality</TableHead>
              <TableHead className="w-8" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {logs.data.map((l) => (
              <TableRow key={l.id}>
                <TableCell className="text-muted-foreground">{formatDate(l.sleep_date)}</TableCell>
                <TableCell className="font-mono">
                  {l.sleep_time ? formatTime(l.sleep_time, l.is_approximate) : "—"}
                </TableCell>
                <TableCell className="font-mono">
                  {l.wake_time ? formatTime(l.wake_time, l.is_approximate) : "—"}
                </TableCell>
                <TableCell className="font-mono">
                  {formatDuration(l.duration_minutes, l.is_approximate)}
                </TableCell>
                <TableCell className="font-mono">{l.quality_score ?? "—"}</TableCell>
                <TableCell>
                  <DeleteButton path={`/sleep/${l.id}`} onDeleted={logs.reload} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Page>
  );
}
