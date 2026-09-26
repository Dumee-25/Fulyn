"use client";

import { Download, Lock, Trash2 } from "lucide-react";
import { useState } from "react";

import { BackendStatus } from "@/components/backend-status";
import { ErrorText, Page, PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useApi } from "@/hooks/use-api";
import { apiSend } from "@/lib/api";

interface Settings {
  version: string;
  environment: string;
  timezone: string;
  currency: string;
  expense_categories: string[];
  major_purchase_amount: string;
  chat_model: string | null;
  embedding_model: string | null;
  agent_max_tool_iterations: number;
  agent_history_messages: number;
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-border py-2 text-sm last:border-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-mono text-xs">{value}</span>
    </div>
  );
}

function DownloadLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a
      href={href}
      download
      className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border px-2.5 text-sm hover:bg-muted"
    >
      <Download className="size-4" />
      {children}
    </a>
  );
}

export default function SettingsPage() {
  const settings = useApi<Settings>("/settings");
  const [vaultExport, setVaultExport] = useState(false);
  const [cleared, setCleared] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const s = settings.data;

  async function clearChats() {
    if (!window.confirm("Delete all chat history? Your journal and records are kept.")) return;
    try {
      await apiSend("DELETE", "/chat/conversations");
      try {
        window.localStorage.removeItem("fulyn.conversationId");
      } catch {
        // storage unavailable
      }
      setCleared(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not delete chat history");
    }
  }

  return (
    <Page>
      <PageHeader title="Settings" />

      <Card>
        <CardHeader>
          <CardTitle>Export your data</CardTitle>
          <CardDescription>
            Your data, in open formats. The private vault is never included in these.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <DownloadLink href="/api/export/zip">Everything (ZIP)</DownloadLink>
            <DownloadLink href="/api/export/json">Everything (JSON)</DownloadLink>
            <DownloadLink href="/api/export/expenses.csv">Expenses (CSV)</DownloadLink>
          </div>
          <p className="text-xs text-muted-foreground">
            The ZIP holds your journal as Markdown (one file per day), a CSV for each kind of
            record, your memories and your chat history.
          </p>
          <div className="rounded-lg border border-border p-3">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="size-4 accent-primary"
                checked={vaultExport}
                onChange={(e) => setVaultExport(e.target.checked)}
              />
              <Lock className="size-4 text-muted-foreground" />I want a separate export of my
              private vault
            </label>
            {vaultExport && (
              <div className="mt-3">
                <DownloadLink href="/api/export/vault.zip">Private vault (ZIP)</DownloadLink>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Configuration</CardTitle>
          <CardDescription>
            Read from <span className="font-mono">.env</span>. Change it there and restart the
            backend.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {settings.error && <ErrorText>{settings.error}</ErrorText>}
          {s && (
            <div>
              <Row label="Timezone" value={s.timezone} />
              <Row label="Currency" value={s.currency} />
              <Row label="Chat model" value={s.chat_model ?? "not set"} />
              <Row label="Embedding model" value={s.embedding_model ?? "not set (word search only)"} />
              <Row label="Major purchase (timeline)" value={`${s.currency} ${s.major_purchase_amount}`} />
              <Row label="Expense categories" value={s.expense_categories.join(", ")} />
              <Row label="Agent steps per message" value={s.agent_max_tool_iterations} />
              <Row label="Chat history sent to the model" value={`${s.agent_history_messages} messages`} />
              <Row label="Version" value={`${s.version} (${s.environment})`} />
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Chat history</CardTitle>
          <CardDescription>
            Deleting conversations keeps everything that was logged from them.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex items-center gap-3">
          <Button variant="destructive" onClick={() => void clearChats()}>
            <Trash2 /> Delete all chat history
          </Button>
          {cleared && <span className="text-sm text-muted-foreground">Deleted.</span>}
          {error && <ErrorText>{error}</ErrorText>}
        </CardContent>
      </Card>

      <BackendStatus />
    </Page>
  );
}
