"use client";

import { RefreshCw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useHealth } from "@/hooks/use-health";

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between py-1.5 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-mono text-xs">{value}</span>
    </div>
  );
}

export function BackendStatus() {
  const { health, refresh } = useHealth();

  return (
    <Card>
      <CardHeader>
        <CardTitle>System</CardTitle>
        <CardDescription>Connection to the Fulyn backend</CardDescription>
        <CardAction>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Refresh status"
            onClick={() => void refresh()}
          >
            <RefreshCw className={health.state === "loading" ? "animate-spin" : ""} />
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="divide-y divide-border">
        {health.state === "loading" && <Row label="API" value="checking…" />}
        {health.state === "error" && (
          <Row label="API" value={<Badge variant="destructive">{health.message}</Badge>} />
        )}
        {health.state === "ok" && (
          <>
            <Row
              label="API"
              value={
                <Badge variant={health.data.status === "ok" ? "secondary" : "destructive"}>
                  {health.data.status}
                </Badge>
              }
            />
            <Row
              label="Database"
              value={
                <Badge variant={health.data.database === "ok" ? "secondary" : "destructive"}>
                  {health.data.database}
                </Badge>
              }
            />
            <Row label="Version" value={health.data.version} />
            <Row label="Environment" value={health.data.environment} />
            <Row label="Timezone" value={health.data.timezone} />
            <Row label="Currency" value={health.data.currency} />
          </>
        )}
      </CardContent>
    </Card>
  );
}
