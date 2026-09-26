"use client";

import { useCallback, useEffect, useState } from "react";

import { apiGet } from "@/lib/api";
import type { HealthResponse } from "@/types/api";

type HealthState =
  | { state: "loading" }
  | { state: "ok"; data: HealthResponse }
  | { state: "error"; message: string };

async function fetchHealth(): Promise<HealthState> {
  try {
    return { state: "ok", data: await apiGet<HealthResponse>("/health") };
  } catch {
    return { state: "error", message: "Backend is unreachable" };
  }
}

export function useHealth() {
  const [health, setHealth] = useState<HealthState>({ state: "loading" });

  useEffect(() => {
    let cancelled = false;
    void fetchHealth().then((next) => {
      if (!cancelled) setHealth(next);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const refresh = useCallback(async () => {
    setHealth({ state: "loading" });
    setHealth(await fetchHealth());
  }, []);

  return { health, refresh };
}
