"use client";

import { Lock } from "lucide-react";

import { DeleteButton } from "@/components/delete-button";
import { Checkbox, Field, NativeSelect, formValue, useFormSubmit } from "@/components/form";
import { EmptyState, ErrorText, Page, PageHeader } from "@/components/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useApi } from "@/hooks/use-api";
import { apiSend } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { IMPORTANCE_LABELS } from "@/lib/importance";
import type { JournalEntry } from "@/types/api";

export default function JournalPage() {
  const entries = useApi<JournalEntry[]>("/journal", { limit: 100 });

  const form = useFormSubmit(async (data) => {
    await apiSend("POST", "/journal", {
      raw_text: data.get("raw_text"),
      entry_date: formValue(data, "entry_date"),
      importance_score: Number(data.get("importance_score")),
      is_private: data.get("is_private") === "on",
    });
    await entries.reload();
  });

  return (
    <Page>
      <PageHeader title="Journal" description="Your own words, stored exactly as written." />

      <Card>
        <CardContent>
          <form onSubmit={form.onSubmit} className="grid gap-3">
            <Textarea
              name="raw_text"
              required
              rows={4}
              placeholder="How was today?"
              aria-label="Journal entry"
            />
            <div className="flex flex-wrap items-end gap-3">
              <Field label="Date" htmlFor="entry_date" className="w-40">
                <Input id="entry_date" name="entry_date" type="date" />
              </Field>
              <Field label="Importance" htmlFor="importance_score" className="w-40">
                <NativeSelect id="importance_score" name="importance_score" defaultValue="2">
                  {IMPORTANCE_LABELS.map((label, score) => (
                    <option key={score} value={score}>
                      {score} · {label}
                    </option>
                  ))}
                </NativeSelect>
              </Field>
              <Checkbox name="is_private" label="Private" />
              <Button type="submit" disabled={form.pending} className="ml-auto">
                Save entry
              </Button>
            </div>
            {form.error && <ErrorText>{form.error}</ErrorText>}
          </form>
        </CardContent>
      </Card>

      {entries.error && <ErrorText>{entries.error}</ErrorText>}
      {entries.data?.length === 0 && <EmptyState>No journal entries yet.</EmptyState>}
      <ol className="space-y-3">
        {entries.data?.map((entry) => (
          <li key={entry.id} className="rounded-xl border border-border p-4">
            <div className="mb-2 flex items-center gap-2 text-xs text-muted-foreground">
              <span>{formatDate(entry.entry_date)}</span>
              {entry.importance_score >= 3 && (
                <Badge variant="secondary">{IMPORTANCE_LABELS[entry.importance_score]}</Badge>
              )}
              {entry.is_private && <Lock className="size-3" aria-label="Private" />}
              <span className="ml-auto">
                <DeleteButton path={`/journal/${entry.id}`} onDeleted={entries.reload} />
              </span>
            </div>
            <p className="text-sm leading-relaxed whitespace-pre-wrap">{entry.raw_text}</p>
          </li>
        ))}
      </ol>
    </Page>
  );
}
