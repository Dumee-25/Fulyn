"use client";

import { useState } from "react";

import { DeleteButton } from "@/components/delete-button";
import { Field, NativeSelect, formValue, useFormSubmit } from "@/components/form";
import { EmptyState, ErrorText, Page, PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useApi } from "@/hooks/use-api";
import { apiSend } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { DECISION_STATUSES, type Decision } from "@/types/api";

export default function DecisionsPage() {
  const [query, setQuery] = useState("");
  const decisions = useApi<Decision[]>("/decisions", { q: query, limit: 200 });

  const form = useFormSubmit(async (data) => {
    await apiSend("POST", "/decisions", {
      title: data.get("title"),
      decision: data.get("decision"),
      reasoning: formValue(data, "reasoning"),
      decision_date: formValue(data, "decision_date"),
    });
    await decisions.reload();
  });

  async function setStatus(decision: Decision, status: string) {
    await apiSend("PATCH", `/decisions/${decision.id}`, { status });
    await decisions.reload();
  }

  return (
    <Page>
      <PageHeader title="Decisions" description="What you decided, and why, in your words." />

      <Card>
        <CardContent>
          <form onSubmit={form.onSubmit} className="grid gap-3 sm:grid-cols-6">
            <Field label="Title" htmlFor="title" className="sm:col-span-4">
              <Input id="title" name="title" required maxLength={200} placeholder="Not buying the keyboard" />
            </Field>
            <Field label="Date" htmlFor="decision_date" className="sm:col-span-2">
              <Input id="decision_date" name="decision_date" type="date" />
            </Field>
            <Field label="Decision" htmlFor="decision" className="sm:col-span-6">
              <Input id="decision" name="decision" required />
            </Field>
            <Field label="Why" htmlFor="reasoning" className="sm:col-span-6">
              <Textarea id="reasoning" name="reasoning" rows={2} />
            </Field>
            <div className="flex justify-end sm:col-span-6">
              <Button type="submit" disabled={form.pending}>
                Save decision
              </Button>
            </div>
            {form.error && <ErrorText>{form.error}</ErrorText>}
          </form>
        </CardContent>
      </Card>

      <Input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search decisions…"
        aria-label="Search decisions"
        className="max-w-xs"
      />

      {decisions.error && <ErrorText>{decisions.error}</ErrorText>}
      {decisions.data?.length === 0 && <EmptyState>No decisions recorded.</EmptyState>}
      <ol className="space-y-3">
        {decisions.data?.map((d) => (
          <li
            key={d.id}
            className={cn(
              "rounded-xl border border-border p-4",
              d.status === "reversed" && "opacity-60",
            )}
          >
            <div className="mb-1 flex flex-wrap items-center gap-2">
              <span className="text-xs text-muted-foreground">{formatDate(d.decision_date)}</span>
              <span className="font-medium">{d.title}</span>
              <span className="ml-auto flex items-center gap-1">
                <NativeSelect
                  aria-label="Status"
                  className="h-7 w-32 text-xs"
                  value={d.status}
                  onChange={(e) => void setStatus(d, e.target.value)}
                >
                  {DECISION_STATUSES.map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </NativeSelect>
                <DeleteButton path={`/decisions/${d.id}`} onDeleted={decisions.reload} />
              </span>
            </div>
            <p className="text-sm">{d.decision}</p>
            {d.reasoning && (
              <p className="mt-1 text-sm text-muted-foreground">Why: {d.reasoning}</p>
            )}
          </li>
        ))}
      </ol>
    </Page>
  );
}
