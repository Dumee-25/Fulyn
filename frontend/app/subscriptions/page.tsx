"use client";

import { DeleteButton } from "@/components/delete-button";
import { Field, NativeSelect, formNumber, formValue, useFormSubmit } from "@/components/form";
import { EmptyState, ErrorText, Page, PageHeader } from "@/components/page";
import { Badge } from "@/components/ui/badge";
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
import { formatDate, formatMoney } from "@/lib/format";
import { cn } from "@/lib/utils";
import { BILLING_CYCLES, type Subscription, type SubscriptionSummary } from "@/types/api";

export default function SubscriptionsPage() {
  const subs = useApi<Subscription[]>("/subscriptions");
  const summary = useApi<SubscriptionSummary>("/subscriptions/summary");

  async function reload() {
    await Promise.all([subs.reload(), summary.reload()]);
  }

  const form = useFormSubmit(async (data) => {
    await apiSend("POST", "/subscriptions", {
      name: data.get("name"),
      amount: data.get("amount"),
      billing_cycle: data.get("billing_cycle"),
      custom_interval_days: formNumber(data, "custom_interval_days"),
      next_billing_date: formValue(data, "next_billing_date"),
    });
    await reload();
  });

  async function toggleActive(sub: Subscription) {
    await apiSend("PATCH", `/subscriptions/${sub.id}`, { active: !sub.active });
    await reload();
  }

  return (
    <Page>
      <PageHeader title="Subscriptions" />

      {summary.data && summary.data.totals.length > 0 && (
        <Card>
          <CardContent className="flex flex-wrap gap-10">
            {summary.data.totals.map((t) => (
              <div key={t.currency}>
                <p className="text-xs text-muted-foreground">
                  Per month · {t.count} active{t.currency !== "LKR" && ` (${t.currency})`}
                </p>
                <p className="mt-0.5 font-mono text-lg">{formatMoney(t.monthly_total, t.currency)}</p>
                <p className="text-xs text-muted-foreground">
                  {formatMoney(t.yearly_total, t.currency)} a year
                </p>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent>
          <form onSubmit={form.onSubmit} className="grid gap-3 sm:grid-cols-6">
            <Field label="Name" htmlFor="name" className="sm:col-span-2">
              <Input id="name" name="name" required maxLength={100} placeholder="Netflix" />
            </Field>
            <Field label="Amount" htmlFor="amount">
              <Input
                id="amount"
                name="amount"
                required
                inputMode="decimal"
                pattern="\d+(\.\d{1,2})?"
              />
            </Field>
            <Field label="Every" htmlFor="billing_cycle">
              <NativeSelect id="billing_cycle" name="billing_cycle" defaultValue="monthly">
                {BILLING_CYCLES.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </NativeSelect>
            </Field>
            <Field label="Custom days" htmlFor="custom_interval_days">
              <Input id="custom_interval_days" name="custom_interval_days" type="number" min="1" />
            </Field>
            <Field label="Next billing" htmlFor="next_billing_date">
              <Input id="next_billing_date" name="next_billing_date" type="date" />
            </Field>
            <div className="flex items-end sm:col-span-6 sm:justify-end">
              <Button type="submit" disabled={form.pending}>
                Add subscription
              </Button>
            </div>
            {form.error && <ErrorText>{form.error}</ErrorText>}
          </form>
        </CardContent>
      </Card>

      {subs.error && <ErrorText>{subs.error}</ErrorText>}
      {subs.data?.length === 0 && <EmptyState>No subscriptions yet.</EmptyState>}
      {!!subs.data?.length && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Price</TableHead>
              <TableHead>Next due</TableHead>
              <TableHead className="text-right">Per month</TableHead>
              <TableHead className="w-28" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {subs.data.map((s) => (
              <TableRow key={s.id} className={cn(!s.active && "opacity-50")}>
                <TableCell>
                  {s.name}
                  {!s.active && (
                    <Badge variant="outline" className="ml-2 font-normal">
                      cancelled
                    </Badge>
                  )}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {formatMoney(s.amount, s.currency)} /{" "}
                  {s.billing_cycle === "custom"
                    ? `${s.custom_interval_days} days`
                    : s.billing_cycle.replace("ly", "")}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {s.next_due ? formatDate(s.next_due) : "—"}
                </TableCell>
                <TableCell className="text-right font-mono">
                  {formatMoney(s.monthly_cost, s.currency)}
                </TableCell>
                <TableCell className="flex justify-end gap-1">
                  <Button variant="ghost" size="xs" onClick={() => void toggleActive(s)}>
                    {s.active ? "Cancel" : "Resume"}
                  </Button>
                  <DeleteButton path={`/subscriptions/${s.id}`} onDeleted={() => void reload()} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Page>
  );
}
