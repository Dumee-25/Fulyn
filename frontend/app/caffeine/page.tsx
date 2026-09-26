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
import { formatDayOf, formatTime } from "@/lib/format";
import type { CaffeineLog } from "@/types/api";

const DRINKS = ["cappuccino", "iced latte", "americano", "cold brew", "tea", "energy drink"];

export default function CaffeinePage() {
  const logs = useApi<CaffeineLog[]>("/caffeine", { limit: 100 });

  const form = useFormSubmit(async (data) => {
    await apiSend("POST", "/caffeine", {
      drink_type: data.get("drink_type"),
      consumed_at: formValue(data, "consumed_at"),
      is_approximate: data.get("is_approximate") === "on",
      estimated_caffeine_mg: formNumber(data, "estimated_caffeine_mg"),
      description: formValue(data, "description"),
    });
    await logs.reload();
  });

  return (
    <Page>
      <PageHeader title="Caffeine" description="Leave the time empty to use now (approximate)." />

      <Card>
        <CardContent>
          <form onSubmit={form.onSubmit} className="grid gap-3 sm:grid-cols-6">
            <Field label="Drink" htmlFor="drink_type" className="sm:col-span-2">
              <Input
                id="drink_type"
                name="drink_type"
                required
                list="drink-suggestions"
                placeholder="iced latte"
              />
              <datalist id="drink-suggestions">
                {DRINKS.map((d) => (
                  <option key={d} value={d} />
                ))}
              </datalist>
            </Field>
            <Field label="When" htmlFor="consumed_at" className="sm:col-span-2">
              <Input id="consumed_at" name="consumed_at" type="datetime-local" />
            </Field>
            <Field label="mg (if known)" htmlFor="estimated_caffeine_mg" className="sm:col-span-2">
              <Input
                id="estimated_caffeine_mg"
                name="estimated_caffeine_mg"
                type="number"
                min="0"
                max="2000"
              />
            </Field>
            <Field label="Note" htmlFor="description" className="sm:col-span-4">
              <Input id="description" name="description" />
            </Field>
            <div className="flex items-end gap-3 sm:col-span-2">
              <Checkbox name="is_approximate" label="Approximate" />
              <Button type="submit" disabled={form.pending} className="ml-auto">
                Log drink
              </Button>
            </div>
            {form.error && <ErrorText>{form.error}</ErrorText>}
          </form>
        </CardContent>
      </Card>

      {logs.error && <ErrorText>{logs.error}</ErrorText>}
      {logs.data?.length === 0 && <EmptyState>No caffeine logged yet.</EmptyState>}
      {!!logs.data?.length && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Day</TableHead>
              <TableHead>Time</TableHead>
              <TableHead>Drink</TableHead>
              <TableHead>mg</TableHead>
              <TableHead className="w-8" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {logs.data.map((l) => (
              <TableRow key={l.id}>
                <TableCell className="text-muted-foreground">
                  {formatDayOf(l.consumed_at)}
                </TableCell>
                <TableCell className="font-mono">
                  {formatTime(l.consumed_at, l.is_approximate)}
                </TableCell>
                <TableCell>{l.drink_type}</TableCell>
                <TableCell className="font-mono">{l.estimated_caffeine_mg ?? "—"}</TableCell>
                <TableCell>
                  <DeleteButton path={`/caffeine/${l.id}`} onDeleted={logs.reload} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Page>
  );
}
