"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Bell,
  BookOpen,
  CalendarRange,
  Coffee,
  FileText,
  Hourglass,
  LayoutDashboard,
  Lock,
  MessageCircle,
  Moon,
  Music,
  Repeat,
  Scale,
  Settings,
  Smile,
  Sparkles,
  Users,
  Wallet,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/utils";

type NavLink = { href: string; label: string; icon: LucideIcon };

const GROUPS: { label: string | null; links: NavLink[] }[] = [
  {
    label: null,
    links: [
      { href: "/", label: "Dashboard", icon: LayoutDashboard },
      { href: "/chat", label: "Chat", icon: MessageCircle },
      { href: "/timeline", label: "Timeline", icon: CalendarRange },
      { href: "/reports", label: "Reports", icon: FileText },
    ],
  },
  {
    label: "Life",
    links: [
      { href: "/journal", label: "Journal", icon: BookOpen },
      { href: "/memories", label: "Memories", icon: Sparkles },
      { href: "/people", label: "People", icon: Users },
      { href: "/music", label: "Music", icon: Music },
      { href: "/decisions", label: "Decisions", icon: Scale },
      { href: "/vault", label: "Vault", icon: Lock },
    ],
  },
  {
    label: "Tracking",
    links: [
      { href: "/expenses", label: "Expenses", icon: Wallet },
      { href: "/mood", label: "Mood", icon: Smile },
      { href: "/sleep", label: "Sleep", icon: Moon },
      { href: "/caffeine", label: "Caffeine", icon: Coffee },
    ],
  },
  {
    label: "Planning",
    links: [
      { href: "/reminders", label: "Reminders", icon: Bell },
      { href: "/waiting", label: "Waiting for", icon: Hourglass },
      { href: "/subscriptions", label: "Subscriptions", icon: Repeat },
    ],
  },
  {
    label: null,
    links: [{ href: "/settings", label: "Settings", icon: Settings }],
  },
];

export function AppNav() {
  const pathname = usePathname();

  return (
    <nav className="flex gap-1 overflow-x-auto border-b border-border px-3 py-2 md:sticky md:top-0 md:h-dvh md:w-52 md:shrink-0 md:flex-col md:overflow-y-auto md:border-r md:border-b-0 md:py-6">
      <span className="hidden px-2 pb-4 text-sm font-semibold tracking-tight md:block">
        Fulyn
      </span>
      {GROUPS.map((group, i) => (
        <div key={group.label ?? i} className="flex gap-1 md:mb-3 md:flex-col">
          {group.label && (
            <span className="hidden px-2 pb-1 text-[0.7rem] font-medium tracking-wide text-muted-foreground/70 uppercase md:block">
              {group.label}
            </span>
          )}
          {group.links.map(({ href, label, icon: Icon }) => {
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
        </div>
      ))}
    </nav>
  );
}
