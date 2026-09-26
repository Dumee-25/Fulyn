"use client";

import { Trash2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { apiSend } from "@/lib/api";

export function DeleteButton({ path, onDeleted }: { path: string; onDeleted: () => void }) {
  const [pending, setPending] = useState(false);

  async function handleClick() {
    if (!window.confirm("Delete this record?")) return;
    setPending(true);
    try {
      await apiSend("DELETE", path);
      onDeleted();
    } finally {
      setPending(false);
    }
  }

  return (
    <Button
      variant="ghost"
      size="icon-sm"
      aria-label="Delete"
      disabled={pending}
      onClick={() => void handleClick()}
      className="text-muted-foreground hover:text-destructive"
    >
      <Trash2 />
    </Button>
  );
}
