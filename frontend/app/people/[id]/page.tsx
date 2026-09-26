"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

import { DeleteButton } from "@/components/delete-button";
import { Field, NativeSelect, formValue, useFormSubmit } from "@/components/form";
import { EmptyState, ErrorText, Page } from "@/components/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useApi } from "@/hooks/use-api";
import { apiSend } from "@/lib/api";
import { formatDate } from "@/lib/format";
import {
  RELATIONSHIP_TYPES,
  type Interaction,
  type MusicMemory,
  type Person,
} from "@/types/api";

export default function PersonPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const person = useApi<Person>(`/people/${id}`);
  const interactions = useApi<Interaction[]>("/interactions", { person_id: id, limit: 200 });
  const music = useApi<MusicMemory[]>("/music", { person_id: id, limit: 100 });

  const form = useFormSubmit(async (data) => {
    await apiSend("POST", "/interactions", {
      person_id: id,
      summary: data.get("summary"),
      location: formValue(data, "location"),
      interaction_date: formValue(data, "interaction_date"),
    });
    await Promise.all([interactions.reload(), person.reload()]);
  });

  async function setRelationship(value: string) {
    await apiSend("PATCH", `/people/${id}`, { relationship_type: value || null });
    await person.reload();
  }

  const p = person.data;

  return (
    <Page>
      <Link
        href="/people"
        className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" /> People
      </Link>

      {person.error && <ErrorText>{person.error}</ErrorText>}
      {p && (
        <header className="flex flex-wrap items-end gap-4">
          <div className="flex-1">
            <h1 className="text-xl font-semibold tracking-tight">{p.name}</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {p.nickname && <>“{p.nickname}” · </>}
              First mentioned {formatDate(p.first_mentioned_at)}
              {p.last_interaction_at && <> · last seen {formatDate(p.last_interaction_at)}</>}
            </p>
          </div>
          <NativeSelect
            aria-label="Relationship"
            className="w-40"
            value={p.relationship_type ?? ""}
            onChange={(e) => void setRelationship(e.target.value)}
          >
            <option value="">relationship —</option>
            {RELATIONSHIP_TYPES.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </NativeSelect>
          <DeleteButton path={`/people/${id}`} onDeleted={() => router.push("/people")} />
        </header>
      )}

      <Card>
        <CardContent>
          <form onSubmit={form.onSubmit} className="grid gap-3 sm:grid-cols-6">
            <Field label="What happened" htmlFor="summary" className="sm:col-span-3">
              <Input id="summary" name="summary" required placeholder="Coffee after uni" />
            </Field>
            <Field label="Where" htmlFor="location">
              <Input id="location" name="location" />
            </Field>
            <Field label="Date" htmlFor="interaction_date">
              <Input id="interaction_date" name="interaction_date" type="date" />
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

      <section className="space-y-3">
        <h2 className="text-sm font-medium text-muted-foreground">Interactions</h2>
        {interactions.data?.length === 0 && <EmptyState>No interactions yet.</EmptyState>}
        <ol className="space-y-2">
          {interactions.data?.map((i) => (
            <li key={i.id} className="flex items-start gap-3 rounded-lg border border-border p-3">
              <span className="w-24 shrink-0 text-xs text-muted-foreground">
                {formatDate(i.interaction_date)}
              </span>
              <div className="flex-1 text-sm">
                {i.summary}
                {i.location && (
                  <span className="text-muted-foreground"> · {i.location}</span>
                )}
                {i.importance_score >= 4 && (
                  <Badge variant="secondary" className="ml-2 font-normal">
                    important
                  </Badge>
                )}
              </div>
              <DeleteButton
                path={`/interactions/${i.id}`}
                onDeleted={() => void Promise.all([interactions.reload(), person.reload()])}
              />
            </li>
          ))}
        </ol>
      </section>

      {!!music.data?.length && (
        <section className="space-y-3">
          <h2 className="text-sm font-medium text-muted-foreground">Music</h2>
          <ul className="space-y-2">
            {music.data.map((m) => (
              <li key={m.id} className="rounded-lg border border-border p-3 text-sm">
                <span className="font-medium">{m.song}</span>
                {m.artist && <span className="text-muted-foreground"> · {m.artist}</span>}
                {m.memory_text && <p className="mt-1 text-muted-foreground">{m.memory_text}</p>}
              </li>
            ))}
          </ul>
        </section>
      )}
    </Page>
  );
}
