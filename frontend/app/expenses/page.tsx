"use client";

import { DeleteButton } from "@/components/delete-button";
import { Checkbox, Field, NativeSelect, formValue, useFormSubmit } from "@/components/form";
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
import { formatDate, formatMoney, todayISO } from "@/lib/format";
import type { Expense, ExpenseSummary } from "@/types/api";

function monthStart(): string {
  return `${todayISO().slice(0, 8)}01`;
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-0.5 font-mono text-lg">{value}</p>
    </div>
  );
}

export default function ExpensesPage() {
  const expenses = useApi<Expense[]>("/expenses", { limit: 200 });
  const categories = useApi<string[]>("/expenses/categories");
  const summary = useApi<ExpenseSummary>("/expenses/summary", {
    date_from: monthStart(),
    date_to: todayISO(),
  });

  async function reload() {
    await Promise.all([expenses.reload(), summary.reload()]);
  }

  const form = useFormSubmit(async (data) => {
    await apiSend("POST", "/expenses", {
      amount: data.get("amount"),
      category: data.get("category"),
      merchant: formValue(data, "merchant"),
      description: formValue(data, "description"),
      expense_date: formValue(data, "expense_date"),
      is_impulse: data.get("is_impulse") === "on",
    });
    await reload();
  });

  const s = summary.data;

  return (
    <Page>
      <PageHeader title="Expenses" />

      {s && (
        <Card>
          <CardContent className="grid gap-4 sm:grid-cols-[auto_auto_1fr] sm:gap-10">
            <Stat label="This month" value={formatMoney(s.total, s.currency)} />
            <Stat label="Impulse" value={formatMoney(s.impulse_total, s.currency)} />
            <div className="flex flex-wrap content-start gap-1.5">
              {s.by_category.map((c) => (
                <Badge key={c.category} variant="outline" className="font-normal">
                  {c.category} · {formatMoney(c.total, s.currency)}
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent>
          <form onSubmit={form.onSubmit} className="grid gap-3 sm:grid-cols-6">
            <Field label="Amount" htmlFor="amount" className="sm:col-span-1">
              <Input
                id="amount"
                name="amount"
                required
                inputMode="decimal"
                pattern="\d+(\.\d{1,2})?"
                placeholder="850"
              />
            </Field>
            <Field label="Category" htmlFor="category" className="sm:col-span-2">
              <NativeSelect
                key={categories.data?.length ?? 0}
                id="category"
                name="category"
                defaultValue="Other"
              >
                {categories.data?.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </NativeSelect>
            </Field>
            <Field label="Merchant" htmlFor="merchant" className="sm:col-span-2">
              <Input id="merchant" name="merchant" placeholder="Barista" />
            </Field>
            <Field label="Date" htmlFor="expense_date" className="sm:col-span-1">
              <Input id="expense_date" name="expense_date" type="date" />
            </Field>
            <Field label="Note" htmlFor="description" className="sm:col-span-4">
              <Input id="description" name="description" />
            </Field>
            <div className="flex items-end gap-3 sm:col-span-2">
              <Checkbox name="is_impulse" label="Impulse" />
              <Button type="submit" disabled={form.pending} className="ml-auto">
                Add
              </Button>
            </div>
            {form.error && <ErrorText>{form.error}</ErrorText>}
          </form>
        </CardContent>
      </Card>

      {expenses.error && <ErrorText>{expenses.error}</ErrorText>}
      {expenses.data?.length === 0 && <EmptyState>No expenses yet.</EmptyState>}
      {!!expenses.data?.length && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Date</TableHead>
              <TableHead>Merchant</TableHead>
              <TableHead>Category</TableHead>
              <TableHead className="text-right">Amount</TableHead>
              <TableHead className="w-8" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {expenses.data.map((e) => (
              <TableRow key={e.id}>
                <TableCell className="text-muted-foreground">{formatDate(e.expense_date)}</TableCell>
                <TableCell>
                  {e.merchant ?? e.description ?? "—"}
                  {e.is_impulse && (
                    <Badge variant="outline" className="ml-2 font-normal">
                      impulse
                    </Badge>
                  )}
                </TableCell>
                <TableCell className="text-muted-foreground">{e.category}</TableCell>
                <TableCell className="text-right font-mono">
                  {formatMoney(e.amount, e.currency)}
                </TableCell>
                <TableCell>
                  <DeleteButton path={`/expenses/${e.id}`} onDeleted={() => void reload()} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Page>
  );
}
