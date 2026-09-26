"use client";

import { useState } from "react";

import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

export function Field({
  label,
  htmlFor,
  className,
  children,
}: {
  label: string;
  htmlFor: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("grid gap-1.5", className)}>
      <Label htmlFor={htmlFor} className="text-xs text-muted-foreground">
        {label}
      </Label>
      {children}
    </div>
  );
}

export function NativeSelect({ className, ...props }: React.ComponentProps<"select">) {
  return (
    <select
      className={cn(
        "h-8 w-full rounded-lg border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30",
        className,
      )}
      {...props}
    />
  );
}

export function Checkbox({ label, ...props }: { label: string } & React.ComponentProps<"input">) {
  return (
    <label className="flex items-center gap-2 text-sm text-muted-foreground">
      <input type="checkbox" className="size-4 accent-primary" {...props} />
      {label}
    </label>
  );
}

/** Read a FormData value, turning empty strings into undefined. */
export function formValue(form: FormData, name: string): string | undefined {
  const value = form.get(name);
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

export function formNumber(form: FormData, name: string): number | undefined {
  const value = formValue(form, name);
  return value === undefined ? undefined : Number(value);
}

/**
 * Wraps a create form: runs `submit`, shows its error, resets the form on success.
 */
export function useFormSubmit(submit: (form: FormData) => Promise<void>) {
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const element = event.currentTarget;
    setPending(true);
    setError(null);
    try {
      await submit(new FormData(element));
      element.reset();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setPending(false);
    }
  }

  return { onSubmit, error, pending };
}
