"use client";

import { useState } from "react";

import { useApi } from "@/hooks/use-api";
import { cn } from "@/lib/utils";

export interface ChatCommand {
  name: string;
  usage: string;
  description: string;
  kind: "modifier" | "command";
  group: string;
}

/**
 * Suggests slash commands while the draft is "/" followed by a partial name.
 * Keyboard: arrows to move, Enter or Tab to pick, Escape to dismiss.
 */
export function useCommandPicker(draft: string, setDraft: (value: string) => void) {
  const { data } = useApi<ChatCommand[]>("/chat/commands");
  const [active, setActive] = useState(0);
  const [dismissedFor, setDismissedFor] = useState<string | null>(null);

  const match = /^\/([a-z]*)$/i.exec(draft);
  const items =
    match && data ? data.filter((c) => c.name.startsWith(match[1].toLowerCase())) : [];
  const open = items.length > 0 && dismissedFor !== draft;
  const current = Math.min(active, Math.max(items.length - 1, 0));

  function pick(index: number) {
    const command = items[index];
    if (!command) return;
    setDraft(`/${command.name} `);
    setActive(0);
  }

  /** Returns true when the key was used by the picker. */
  function onKeyDown(e: React.KeyboardEvent): boolean {
    if (!open) return false;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const step = e.key === "ArrowDown" ? 1 : -1;
      setActive((current + step + items.length) % items.length);
      return true;
    }
    if (e.key === "Enter" || e.key === "Tab") {
      e.preventDefault();
      pick(current);
      return true;
    }
    if (e.key === "Escape") {
      setDismissedFor(draft);
      return true;
    }
    return false;
  }

  return { open, items, active: current, pick, onKeyDown };
}

export function CommandList({
  items,
  active,
  onPick,
  className,
}: {
  items: ChatCommand[];
  active: number;
  onPick: (index: number) => void;
  className?: string;
}) {
  return (
    <ul
      role="listbox"
      aria-label="Commands"
      className={cn(
        "max-h-64 overflow-y-auto rounded-lg border border-border bg-popover p-1 shadow-lg",
        className,
      )}
    >
      {items.map((c, i) => (
        <li
          key={c.name}
          role="option"
          aria-selected={i === active}
          // mousedown so the textarea keeps focus
          onMouseDown={(e) => {
            e.preventDefault();
            onPick(i);
          }}
          className={cn(
            "flex cursor-pointer items-baseline gap-3 rounded-md px-2 py-1.5 text-sm",
            i === active ? "bg-muted" : "hover:bg-muted/60",
          )}
        >
          <span className="shrink-0 font-mono text-xs text-foreground">{c.usage}</span>
          <span className="truncate text-xs text-muted-foreground">{c.description}</span>
        </li>
      ))}
    </ul>
  );
}
