"use client";

import { Check, X } from "lucide-react";
import { useState } from "react";

import { DeleteButton } from "@/components/delete-button";
import { Field, formValue, useFormSubmit } from "@/components/form";
import { EmptyState, ErrorText, Page, PageHeader } from "@/components/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useApi } from "@/hooks/use-api";
import { apiSend } from "@/lib/api";
import { daysUntil, formatDate } from "@/lib/format";
import type { WaitingItem } from "@/types/api";

const TABS = [
  { value: "waiting", label: "Waiting" },
  { value: "received", label: "Received" },
  { value: "cancelled", label: "Cancelled" },
  { value: "expired", label: "Expired" },
] as const;

function waitedFor(since: string): string {
  const days = -daysUntil(since);
  if (days <= 0) return "since today";
  return days === 1 ? "1 day" : `${days} days`;
}

export default function WaitingPage() {
  const [status, setStatus] = useState<string>("waiting");
  const items = useApi<WaitingItem[]>("/waiting", { status, limit: 200 });

  const form = useFormSubmit(async (data) => {
    await apiSend("POST", "/waiting", {
      title: data.get("title"),
      description: formValue(data, "description"),
      expected_by: formValue(data, "expected_by"),
    });
    await items.reload();
  });

  async function resolve(item: WaitingItem, next: "received" | "cancelled") {
    await apiSend("PATCH", `/waiting/${item.id}`, { status: next });
    await items.reload();
  }

  return (
    <Page>
      <PageHeader title="Waiting for" description="Refunds, deliveries, replies, results." />

      <Card>
        <CardContent>
          <form onSubmit={form.onSubmit} className="grid gap-3 sm:grid-cols-6">
            <Field label="What" htmlFor="title" className="sm:col-span-2">
              <Input id="title" name="title" required maxLength={200} placeholder="Daraz refund" />
            </Field>
            <Field label="Details" htmlFor="description" className="sm:col-span-2">
              <Input id="description" name="description" />
            </Field>
            <Field label="Expected by" htmlFor="expected_by">
              <Input id="expected_by" name="expected_by" type="date" />
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

      {items.error && <ErrorText>{items.error}</ErrorText>}
      {items.data?.length === 0 && <EmptyState>Nothing here.</EmptyState>}
      <ul className="space-y-2">
        {items.data?.map((item) => (
          <li key={item.id} className="flex items-center gap-3 rounded-lg border border-border p-3">
            <div className="flex-1 text-sm">
              <span className="font-medium">{item.title}</span>
              {item.related_person_name && (
                <span className="text-muted-foreground"> · from {item.related_person_name}</span>
              )}
              {item.overdue && (
                <Badge variant="destructive" className="ml-2 font-normal">
                  overdue
                </Badge>
              )}
              {item.description && (
                <p className="text-xs text-muted-foreground">{item.description}</p>
              )}
              <p className="text-xs text-muted-foreground">
                {item.status === "waiting"
                  ? `Waiting ${waitedFor(item.waiting_since)}`
                  : `Since ${formatDate(item.waiting_since)}`}
                {item.expected_by && ` · expected ${formatDate(item.expected_by)}`}
                {item.resolved_at && ` · ${item.status} ${formatDate(item.resolved_at)}`}
              </p>
            </div>
            {item.status === "waiting" && (
              <>
                <Button variant="outline" size="sm" onClick={() => void resolve(item, "received")}>
                  <Check /> Got it
                </Button>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Cancel"
                  onClick={() => void resolve(item, "cancelled")}
                >
                  <X />
                </Button>
              </>
            )}
            <DeleteButton path={`/waiting/${item.id}`} onDeleted={items.reload} />
          </li>
        ))}
      </ul>
    </Page>
  );
}
