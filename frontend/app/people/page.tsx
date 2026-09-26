"use client";

import Link from "next/link";
import { useState } from "react";

import { Field, NativeSelect, formValue, useFormSubmit } from "@/components/form";
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
import { RELATIONSHIP_TYPES, type PersonSummary } from "@/types/api";

export default function PeoplePage() {
  const [query, setQuery] = useState("");
  const list = useApi<PersonSummary[]>("/people", { q: query });

  const form = useFormSubmit(async (data) => {
    await apiSend("POST", "/people", {
      name: data.get("name"),
      nickname: formValue(data, "nickname"),
      relationship_type: formValue(data, "relationship_type"),
    });
    await list.reload();
  });

  return (
    <Page>
      <PageHeader
        title="People"
        description="People in your life and when you last saw them. Alphabetical, never ranked."
      />

      <Card>
        <CardContent>
          <form onSubmit={form.onSubmit} className="grid gap-3 sm:grid-cols-6">
            <Field label="Name" htmlFor="name" className="sm:col-span-2">
              <Input id="name" name="name" required maxLength={100} />
            </Field>
            <Field label="Nickname" htmlFor="nickname" className="sm:col-span-2">
              <Input id="nickname" name="nickname" maxLength={100} />
            </Field>
            <Field label="Relationship" htmlFor="relationship_type">
              <NativeSelect id="relationship_type" name="relationship_type" defaultValue="">
                <option value="">—</option>
                {RELATIONSHIP_TYPES.map((t) => (
                  <option key={t}>{t}</option>
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

      <Input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Filter by name…"
        aria-label="Filter people"
        className="max-w-xs"
      />

      {list.error && <ErrorText>{list.error}</ErrorText>}
      {list.data?.length === 0 && (
        <EmptyState>
          {query ? "Nobody matches." : "No people yet. Mention someone in chat and they appear here."}
        </EmptyState>
      )}
      {!!list.data?.length && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Relationship</TableHead>
              <TableHead>Last seen</TableHead>
              <TableHead className="text-right">Interactions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {list.data.map((p) => (
              <TableRow key={p.id}>
                <TableCell>
                  <Link href={`/people/${p.id}`} className="hover:underline">
                    {p.name}
                  </Link>
                  {p.nickname && (
                    <span className="ml-2 text-xs text-muted-foreground">“{p.nickname}”</span>
                  )}
                </TableCell>
                <TableCell className="text-muted-foreground">{p.relationship_type ?? "—"}</TableCell>
                <TableCell className="text-muted-foreground">
                  {p.last_interaction_at ? formatDate(p.last_interaction_at) : "—"}
                </TableCell>
                <TableCell className="text-right font-mono">{p.interaction_count}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Page>
  );
}
