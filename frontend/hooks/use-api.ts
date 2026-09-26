"use client";

import { useCallback, useEffect, useState } from "react";

import { apiGet } from "@/lib/api";

type Query = Parameters<typeof apiGet>[1];

export interface ApiResource<T> {
  data: T | undefined;
  error: string | null;
  loading: boolean;
  reload: () => Promise<void>;
}

/** Fetch a GET endpoint on mount and whenever `path` or `query` changes. */
export function useApi<T>(path: string, query?: Query): ApiResource<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const queryKey = JSON.stringify(query ?? {});

  const load = useCallback(async () => {
    try {
      const result = await apiGet<T>(path, JSON.parse(queryKey));
      setData(result);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }, [path, queryKey]);

  useEffect(() => {
    let cancelled = false;
    apiGet<T>(path, JSON.parse(queryKey))
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setError(null);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Request failed");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [path, queryKey]);

  // Refetch when something (e.g. the quick-chat box) reports changed data.
  useEffect(() => {
    const onChange = () => void load();
    window.addEventListener(DATA_CHANGED, onChange);
    return () => window.removeEventListener(DATA_CHANGED, onChange);
  }, [load]);

  return { data, error, loading, reload: load };
}

export const DATA_CHANGED = "fulyn:data-changed";

export function announceDataChanged() {
  window.dispatchEvent(new Event(DATA_CHANGED));
}
