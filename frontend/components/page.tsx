import { cn } from "@/lib/utils";

export function Page({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <main className={cn("mx-auto w-full max-w-4xl flex-1 space-y-6 px-4 py-8 sm:px-6", className)}>
      {children}
    </main>
  );
}

export function PageHeader({ title, description }: { title: string; description?: string }) {
  return (
    <header>
      <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
      {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
    </header>
  );
}

export function EmptyState({ children }: { children: React.ReactNode }) {
  return <p className="py-8 text-center text-sm text-muted-foreground">{children}</p>;
}

export function ErrorText({ children }: { children: React.ReactNode }) {
  return (
    <p role="alert" className="text-sm text-destructive">
      {children}
    </p>
  );
}
