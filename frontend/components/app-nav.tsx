"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BookOpen,
  Coffee,
  LayoutDashboard,
  Moon,
  Smile,
  Wallet,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/utils";

const LINKS: { href: string; label: string; icon: LucideIcon }[] = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/journal", label: "Journal", icon: BookOpen },
  { href: "/expenses", label: "Expenses", icon: Wallet },
  { href: "/mood", label: "Mood", icon: Smile },
  { href: "/sleep", label: "Sleep", icon: Moon },
  { href: "/caffeine", label: "Caffeine", icon: Coffee },
];

export function AppNav() {
  const pathname = usePathname();

  return (
    <nav className="flex gap-1 overflow-x-auto border-b border-border px-3 py-2 md:w-52 md:shrink-0 md:flex-col md:border-r md:border-b-0 md:px-3 md:py-6">
      <span className="hidden px-2 pb-4 text-sm font-semibold tracking-tight md:block">
        Fulyn
      </span>
      {LINKS.map(({ href, label, icon: Icon }) => {
        const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex shrink-0 items-center gap-2 rounded-md px-2 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground",
              active && "bg-muted text-foreground",
            )}
          >
            <Icon className="size-4" />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
