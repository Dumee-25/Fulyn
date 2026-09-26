"use client";

import { ArrowUp, MessageCircle, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { ChatActionChips } from "@/components/chat-action-chips";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { announceDataChanged } from "@/hooks/use-api";
import { ApiError, apiSend } from "@/lib/api";
import type { ChatResponse } from "@/types/api";

const STORAGE_KEY = "fulyn.conversationId";

function storedId(): string | undefined {
  try {
    return window.localStorage.getItem(STORAGE_KEY) ?? undefined;
  } catch {
    return undefined;
  }
}

/** Log something from any page. Continues the same conversation as the Chat page. */
export function QuickChat() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const [last, setLast] = useState<ChatResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (pathname === "/chat") return null;

  async function send() {
    const text = draft.trim();
    if (!text || pending) return;
    setPending(true);
    setError(null);
    try {
      const post = (conversationId?: string) =>
        apiSend<ChatResponse>("POST", "/chat", { message: text, conversation_id: conversationId });
      const id = storedId();
      let res: ChatResponse;
      try {
        res = await post(id);
      } catch (e) {
        // The remembered conversation was deleted: start a new one.
        if (!(id && e instanceof ApiError && e.status === 404)) throw e;
        res = await post(undefined);
      }
      try {
        window.localStorage.setItem(STORAGE_KEY, res.conversation_id);
      } catch {
        // storage unavailable
      }
      setLast(res);
      setDraft("");
      if (res.actions.some((a) => a.ok)) announceDataChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setPending(false);
    }
  }

  if (!open) {
    return (
      <Button
        onClick={() => setOpen(true)}
        className="fixed right-4 bottom-4 z-40 rounded-full shadow-lg"
        aria-label="Quick log"
      >
        <MessageCircle /> Tell Fulyn
      </Button>
    );
  }

  return (
    <div className="fixed right-4 bottom-4 z-40 w-[min(24rem,calc(100vw-2rem))] rounded-xl border border-border bg-popover p-3 shadow-xl">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-sm font-medium">Tell Fulyn</span>
        <div className="flex items-center gap-1">
          <Link href="/chat" className="text-xs text-muted-foreground hover:text-foreground">
            Open chat
          </Link>
          <Button variant="ghost" size="icon-xs" aria-label="Close" onClick={() => setOpen(false)}>
            <X />
          </Button>
        </div>
      </div>
      {last && (
        <div className="mb-2 max-h-48 overflow-y-auto rounded-lg bg-muted/40 p-2 text-sm whitespace-pre-wrap">
          {last.reply}
          <ChatActionChips actions={last.actions} />
        </div>
      )}
      {pending && <p className="mb-2 text-xs text-muted-foreground">Thinking…</p>}
      {error && <p className="mb-2 text-xs text-destructive">{error}</p>}
      <form
        className="flex items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
      >
        <Textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              void send();
            }
          }}
          rows={2}
          placeholder="Spent 850 on dinner…"
          aria-label="Quick message"
          className="min-h-10 resize-none"
          autoFocus
        />
        <Button type="submit" size="icon" aria-label="Send" disabled={pending || !draft.trim()}>
          <ArrowUp />
        </Button>
      </form>
    </div>
  );
}
