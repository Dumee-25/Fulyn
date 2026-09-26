"use client";

import { DeleteButton } from "@/components/delete-button";
import { Field, NativeSelect, formNumber, formValue, useFormSubmit } from "@/components/form";
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
import { formatDate } from "@/lib/format";
import type { MoodLog } from "@/types/api";

const LABELS = [
  "great",
  "good",
  "calm",
  "neutral",
  "tired",
  "frustrated",
  "anxious",
  "angry",
  "sad",
  "mixed",
];
const SCALE = Array.from({ length: 10 }, (_, i) => i + 1);

function ScaleSelect({ id }: { id: string }) {
  return (
    <NativeSelect id={id} name={id} defaultValue="">
      <option value="">—</option>
      {SCALE.map((n) => (
        <option key={n}>{n}</option>
      ))}
    </NativeSelect>
  );
}

export default function MoodPage() {
  const moods = useApi<MoodLog[]>("/moods", { limit: 100 });

  const form = useFormSubmit(async (data) => {
    await apiSend("POST", "/moods", {
      label: formValue(data, "label"),
      score: formNumber(data, "score"),
      energy_score: formNumber(data, "energy_score"),
      notes: formValue(data, "notes"),
      date: formValue(data, "date"),
    });
    await moods.reload();
  });

  return (
    <Page>
      <PageHeader title="Mood" description="Mood and energy, tracked separately (1–10)." />

      <Card>
        <CardContent>
          <form onSubmit={form.onSubmit} className="grid gap-3 sm:grid-cols-6">
            <Field label="Mood" htmlFor="label" className="sm:col-span-2">
              <NativeSelect id="label" name="label" defaultValue="">
                <option value="">—</option>
                {LABELS.map((l) => (
                  <option key={l}>{l}</option>
                ))}
              </NativeSelect>
            </Field>
            <Field label="Score" htmlFor="score">
              <ScaleSelect id="score" />
            </Field>
            <Field label="Energy" htmlFor="energy_score">
              <ScaleSelect id="energy_score" />
            </Field>
            <Field label="Date" htmlFor="date" className="sm:col-span-2">
              <Input id="date" name="date" type="date" />
            </Field>
            <Field label="Notes" htmlFor="notes" className="sm:col-span-5">
              <Input id="notes" name="notes" />
            </Field>
            <div className="flex items-end">
              <Button type="submit" disabled={form.pending} className="w-full">
                Log mood
              </Button>
            </div>
            {form.error && <ErrorText>{form.error}</ErrorText>}
          </form>
        </CardContent>
      </Card>

      {moods.error && <ErrorText>{moods.error}</ErrorText>}
      {moods.data?.length === 0 && <EmptyState>No mood logs yet.</EmptyState>}
      {!!moods.data?.length && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Date</TableHead>
              <TableHead>Mood</TableHead>
              <TableHead>Score</TableHead>
              <TableHead>Energy</TableHead>
              <TableHead>Notes</TableHead>
              <TableHead className="w-8" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {moods.data.map((m) => (
              <TableRow key={m.id}>
                <TableCell className="text-muted-foreground">{formatDate(m.date)}</TableCell>
                <TableCell>{m.label ?? "—"}</TableCell>
                <TableCell className="font-mono">{m.score ?? "—"}</TableCell>
                <TableCell className="font-mono">{m.energy_score ?? "—"}</TableCell>
                <TableCell className="max-w-64 truncate text-muted-foreground">
                  {m.notes}
                </TableCell>
                <TableCell>
                  <DeleteButton path={`/moods/${m.id}`} onDeleted={moods.reload} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Page>
  );
}
