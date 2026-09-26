"use client";

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
import { formatDate, todayISO } from "@/lib/format";
import type { MusicMemory, SongCount } from "@/types/api";

function monthStart(): string {
  return `${todayISO().slice(0, 8)}01`;
}

export default function MusicPage() {
  const [query, setQuery] = useState("");
  const music = useApi<MusicMemory[]>("/music", { q: query, limit: 200 });
  const top = useApi<SongCount[]>("/music/top", {
    date_from: monthStart(),
    date_to: todayISO(),
    limit: 5,
  });

  async function reload() {
    await Promise.all([music.reload(), top.reload()]);
  }

  const form = useFormSubmit(async (data) => {
    await apiSend("POST", "/music", {
      song: data.get("song"),
      artist: formValue(data, "artist"),
      memory_text: formValue(data, "memory_text"),
      emotion: formValue(data, "emotion"),
      memory_date: formValue(data, "memory_date"),
    });
    await reload();
  });

  return (
    <Page>
      <PageHeader title="Music" description="Songs tied to moments, feelings and people." />

      {!!top.data?.length && (
        <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
          <span className="mr-1">This month:</span>
          {top.data.map((s) => (
            <Badge key={`${s.song}-${s.artist}`} variant="outline" className="font-normal">
              {s.song}
              {s.artist && ` · ${s.artist}`}
              {s.count > 1 && ` ×${s.count}`}
            </Badge>
          ))}
        </div>
      )}

      <Card>
        <CardContent>
          <form onSubmit={form.onSubmit} className="grid gap-3 sm:grid-cols-6">
            <Field label="Song" htmlFor="song" className="sm:col-span-2">
              <Input id="song" name="song" required maxLength={200} />
            </Field>
            <Field label="Artist" htmlFor="artist" className="sm:col-span-2">
              <Input id="artist" name="artist" maxLength={200} />
            </Field>
            <Field label="Feeling" htmlFor="emotion">
              <Input id="emotion" name="emotion" maxLength={50} placeholder="nostalgic" />
            </Field>
            <Field label="Date" htmlFor="memory_date">
              <Input id="memory_date" name="memory_date" type="date" />
            </Field>
            <Field label="What it reminds you of" htmlFor="memory_text" className="sm:col-span-5">
              <Input id="memory_text" name="memory_text" />
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
        placeholder="Search songs, artists, memories…"
        aria-label="Search music"
        className="max-w-xs"
      />

      {music.error && <ErrorText>{music.error}</ErrorText>}
      {music.data?.length === 0 && <EmptyState>No music memories yet.</EmptyState>}
      <ol className="space-y-2">
        {music.data?.map((m) => (
          <li key={m.id} className="flex items-start gap-3 rounded-lg border border-border p-3">
            <span className="w-24 shrink-0 text-xs text-muted-foreground">
              {formatDate(m.memory_date)}
            </span>
            <div className="flex-1 text-sm">
              <span className="font-medium">{m.song}</span>
              {m.artist && <span className="text-muted-foreground"> · {m.artist}</span>}
              {m.emotion && (
                <Badge variant="outline" className="ml-2 font-normal">
                  {m.emotion}
                </Badge>
              )}
              {m.person_name && (
                <span className="text-muted-foreground"> · with {m.person_name}</span>
              )}
              {m.memory_text && <p className="mt-1 text-muted-foreground">{m.memory_text}</p>}
            </div>
            <DeleteButton path={`/music/${m.id}`} onDeleted={() => void reload()} />
          </li>
        ))}
      </ol>
    </Page>
  );
}
