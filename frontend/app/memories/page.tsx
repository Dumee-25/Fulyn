"use client";

import { Search } from "lucide-react";
import { useState } from "react";

import { NativeSelect } from "@/components/form";
import { EmptyState, ErrorText, Page, PageHeader } from "@/components/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useApi } from "@/hooks/use-api";
import { apiGet, apiSend } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { IMPORTANCE_LABELS } from "@/lib/importance";
import { cn } from "@/lib/utils";
import type { Memory, MemorySearchResponse, MemorySearchResult } from "@/types/api";

const FILTERS = [
  { value: "", label: "All" },
  { value: "3", label: "Notable and up" },
  { value: "4", label: "Important and up" },
  { value: "5", label: "Core memories" },
];

function ImportanceSelect({
  memory,
  onChange,
}: {
  memory: Memory;
  onChange: (updated: Memory) => void;
}) {
  const [pending, setPending] = useState(false);
  return (
    <NativeSelect
      aria-label="Importance"
      className="h-7 w-36 text-xs"
      value={memory.importance_score}
      disabled={pending}
      onChange={async (e) => {
        setPending(true);
        try {
          onChange(
            await apiSend<Memory>("PATCH", `/memories/${memory.id}`, {
              importance_score: Number(e.target.value),
            }),
          );
        } finally {
          setPending(false);
        }
      }}
    >
      {IMPORTANCE_LABELS.map((label, score) => (
        <option key={score} value={score}>
          {score} · {label}
        </option>
      ))}
    </NativeSelect>
  );
}

function MemoryCard({
  memory,
  dimmed,
  onChange,
}: {
  memory: Memory | MemorySearchResult;
  dimmed: boolean;
  onChange: (updated: Memory) => void;
}) {
  const match = "keyword_match" in memory ? memory : null;
  return (
    <li className={cn("rounded-xl border border-border p-4", dimmed && "opacity-55")}>
      <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span>{formatDate(memory.memory_date)}</span>
        <Badge variant="outline" className="font-normal">
          {memory.memory_type.replace("_", " ")}
        </Badge>
        {match?.keyword_match && (
          <Badge variant="secondary" className="font-normal">
            word match
          </Badge>
        )}
        {match?.similarity != null && (
          <span className="font-mono">sim {match.similarity.toFixed(2)}</span>
        )}
        <span className="ml-auto">
          <ImportanceSelect memory={memory} onChange={onChange} />
        </span>
      </div>
      <p className="line-clamp-4 text-sm leading-relaxed whitespace-pre-wrap">{memory.content}</p>
      {memory.tags.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-1.5" aria-label="Also in this moment">
          {memory.tags.map((tag) => (
            <li key={tag}>
              <Badge variant="outline" className="font-normal text-muted-foreground">
                {tag}
              </Badge>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

export default function MemoriesPage() {
  const [query, setQuery] = useState("");
  const [minImportance, setMinImportance] = useState("");
  const [search, setSearch] = useState<MemorySearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const list = useApi<Memory[]>("/memories", { min_importance: minImportance, limit: 50 });

  async function runSearch(event: React.FormEvent) {
    event.preventDefault();
    const q = query.trim();
    if (!q) {
      setSearch(null);
      return;
    }
    setPending(true);
    setError(null);
    try {
      setSearch(
        await apiGet<MemorySearchResponse>("/memories/search", {
          q,
          min_importance: minImportance,
          limit: 20,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Search failed");
    } finally {
      setPending(false);
    }
  }

  function replace(updated: Memory) {
    setSearch((s) =>
      s && {
        ...s,
        results: s.results.map((r) => (r.id === updated.id ? { ...r, ...updated } : r)),
      },
    );
    void list.reload();
  }

  const items: (Memory | MemorySearchResult)[] = search ? search.results : (list.data ?? []);
  // Semantic neighbours are shown but de-emphasised when real word matches exist.
  const anyWordMatch = search?.results.some((r) => r.keyword_match) ?? false;

  return (
    <Page>
      <PageHeader
        title="Memories"
        description="Search by meaning or by words. Private entries are not included."
      />

      <form onSubmit={runSearch} className="flex flex-wrap gap-2">
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Sarah, rainy days, the keyboard…"
          aria-label="Search memories"
          className="min-w-48 flex-1"
        />
        <NativeSelect
          aria-label="Minimum importance"
          className="w-44"
          value={minImportance}
          onChange={(e) => setMinImportance(e.target.value)}
        >
          {FILTERS.map((f) => (
            <option key={f.value} value={f.value}>
              {f.label}
            </option>
          ))}
        </NativeSelect>
        <Button type="submit" disabled={pending}>
          <Search /> Search
        </Button>
        {search && (
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              setSearch(null);
              setQuery("");
            }}
          >
            Clear
          </Button>
        )}
      </form>

      {search && !search.semantic && (
        <p className="text-xs text-muted-foreground">
          Semantic search is unavailable (embedding model not reachable or not configured), so
          only word matches are shown.
        </p>
      )}
      {(error ?? list.error) && <ErrorText>{error ?? list.error}</ErrorText>}
      {items.length === 0 && !list.loading && (
        <EmptyState>{search ? "No matching memories." : "No memories yet."}</EmptyState>
      )}
      <ol className="space-y-3">
        {items.map((memory) => (
          <MemoryCard
            key={memory.id}
            memory={memory}
            dimmed={anyWordMatch && !(memory as MemorySearchResult).keyword_match}
            onChange={replace}
          />
        ))}
      </ol>
    </Page>
  );
}
