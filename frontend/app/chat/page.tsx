"use client";

import { ArrowUp, Plus } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { ChatActionChips } from "@/components/chat-action-chips";
import { ErrorText } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { apiGet, apiSend } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { ChatMessage, ChatResponse } from "@/types/api";

const STORAGE_KEY = "fulyn.conversationId";

function readStoredId(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function storeId(id: string | null) {
  try {
    if (id) window.localStorage.setItem(STORAGE_KEY, id);
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // storage unavailable: the conversation just won't survive a reload
  }
}

function Bubble({ message }: { message: ChatMessage }) {
  const mine = message.role === "user";
  return (
    <div className={cn("flex", mine && "justify-end")}>
      <div
        className={cn(
          "max-w-[85%] rounded-2xl px-3.5 py-2 text-sm leading-relaxed whitespace-pre-wrap",
          mine ? "bg-secondary text-secondary-foreground" : "text-foreground",
        )}
      >
        {message.content}
        {!mine && <ChatActionChips actions={message.actions} />}
      </div>
    </div>
  );
}

export default function ChatPage() {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Restore the last conversation.
  useEffect(() => {
    const id = readStoredId();
    if (!id) return;
    let cancelled = false;
    apiGet<ChatMessage[]>(`/chat/conversations/${id}/messages`)
      .then((history) => {
        if (cancelled) return;
        setConversationId(id);
        setMessages(history);
      })
      .catch(() => storeId(null));
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages, pending]);

  async function send() {
    const text = draft.trim();
    if (!text || pending) return;
    setDraft("");
    setError(null);
    setPending(true);
    const now = new Date().toISOString();
    setMessages((m) => [...m, { role: "user", content: text, actions: [], created_at: now }]);
    try {
      const res = await apiSend<ChatResponse>("POST", "/chat", {
        message: text,
        conversation_id: conversationId ?? undefined,
      });
      setConversationId(res.conversation_id);
      storeId(res.conversation_id);
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: res.reply,
          actions: res.actions,
          created_at: new Date().toISOString(),
        },
      ]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
      setDraft(text);
      setMessages((m) => m.slice(0, -1));
    } finally {
      setPending(false);
    }
  }

  function newChat() {
    setConversationId(null);
    setMessages([]);
    setError(null);
    storeId(null);
  }

  return (
    <main className="mx-auto flex h-dvh w-full max-w-3xl flex-1 flex-col px-4 sm:px-6">
      <header className="flex items-center justify-between py-4">
        <h1 className="text-xl font-semibold tracking-tight">Chat</h1>
        <Button variant="ghost" size="sm" onClick={newChat} disabled={pending}>
          <Plus /> New chat
        </Button>
      </header>

      <div className="flex-1 space-y-4 overflow-y-auto pb-4">
        {messages.length === 0 && !pending && (
          <div className="pt-16 text-center text-sm text-muted-foreground">
            <p>Tell me about your day, or ask about it.</p>
            <p className="mt-2 italic">
              “Slept around 2, had an iced latte at 10, spent 1450 at Barista with Maya.”
            </p>
          </div>
        )}
        {messages.map((message, i) => (
          <Bubble key={i} message={message} />
        ))}
        {pending && <p className="px-3.5 text-sm text-muted-foreground">Thinking…</p>}
        <div ref={bottomRef} />
      </div>

      <form
        className="sticky bottom-0 border-t border-border bg-background py-3"
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
      >
        {error && (
          <div className="mb-2">
            <ErrorText>{error}</ErrorText>
          </div>
        )}
        <div className="flex items-end gap-2">
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
            placeholder="Message Fulyn…"
            aria-label="Message"
            className="max-h-48 min-h-10 resize-none"
            autoFocus
          />
          <Button type="submit" size="icon" aria-label="Send" disabled={pending || !draft.trim()}>
            <ArrowUp />
          </Button>
        </div>
      </form>
    </main>
  );
}
