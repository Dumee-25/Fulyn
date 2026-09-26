"use client";

import { Lock, LockOpen, Search } from "lucide-react";
import { useState } from "react";

import { EmptyState, ErrorText, Page, PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiGet, apiSend } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { JournalEntry, MemorySearchResponse } from "@/types/api";

/**
 * The only page that shows private content. Nothing is fetched until the vault is opened,
 * so private text is never on screen by accident.
 */
export default function VaultPage() {
  const [open, setOpen] = useState(false);
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<MemorySearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      setEntries(await apiGet<JournalEntry[]>("/vault/entries", { limit: 500 }));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not open the vault");
    }
  }

  async function openVault() {
    await load();
    setOpen(true);
  }

  function lock() {
    setOpen(false);
    setEntries([]);
    setResults(null);
    setQuery("");
  }

  async function search(event: React.FormEvent) {
    event.preventDefault();
    if (!query.trim()) return setResults(null);
    setResults(await apiGet<MemorySearchResponse>("/vault/search", { q: query.trim() }));
  }

  async function restore(entry: JournalEntry) {
    if (!window.confirm("Move this entry out of the vault? It will appear everywhere again.")) {
      return;
    }
    await apiSend("DELETE", `/vault/entries/${entry.id}`);
    await load();
  }

  return (
    <Page>
      <PageHeader
        title="Private vault"
        description="Kept out of search, recaps, reports, the timeline, the dashboard and the assistant unless you ask for it by name."
      />

      {!open ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-8 text-center">
            <Lock className="size-6 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">The vault is closed.</p>
            <Button onClick={() => void openVault()}>Open vault</Button>
            {error && <ErrorText>{error}</ErrorText>}
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="flex flex-wrap gap-2">
            <form onSubmit={search} className="flex flex-1 gap-2">
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search private memories…"
                aria-label="Search the vault"
              />
              <Button type="submit" variant="secondary">
                <Search /> Search
              </Button>
            </form>
            <Button variant="ghost" onClick={lock}>
              <Lock /> Close vault
            </Button>
          </div>

          {results && (
            <section className="space-y-2">
              <h2 className="text-sm font-medium text-muted-foreground">
                Results for “{results.query}”
              </h2>
              {results.results.length === 0 && <EmptyState>No private memories match.</EmptyState>}
              {results.results.map((r) => (
                <div key={r.id} className="rounded-lg border border-border p-3 text-sm">
                  <p className="mb-1 text-xs text-muted-foreground">
                    {formatDate(r.memory_date)} · {r.memory_type.replace("_", " ")}
                  </p>
                  <p className="whitespace-pre-wrap">{r.content}</p>
                </div>
              ))}
            </section>
          )}

          <section className="space-y-3">
            <h2 className="text-sm font-medium text-muted-foreground">Private entries</h2>
            {entries.length === 0 && (
              <EmptyState>
                Nothing in the vault. Mark a journal entry private, or tell the assistant to
                put something in the vault.
              </EmptyState>
            )}
            {entries.map((entry) => (
              <div key={entry.id} className="rounded-xl border border-border p-4">
                <div className="mb-2 flex items-center gap-2 text-xs text-muted-foreground">
                  <span>{formatDate(entry.entry_date)}</span>
                  <span className="ml-auto">
                    <Button variant="ghost" size="xs" onClick={() => void restore(entry)}>
                      <LockOpen /> Move out of vault
                    </Button>
                  </span>
                </div>
                <p className="text-sm leading-relaxed whitespace-pre-wrap">{entry.raw_text}</p>
              </div>
            ))}
          </section>
        </>
      )}
    </Page>
  );
}
