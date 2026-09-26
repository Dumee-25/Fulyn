import type { DecimalString, ISODate, ISODateTime } from "@/types/api";

/** Display only. Amounts stay strings everywhere else so no float math touches money. */
export function formatMoney(amount: DecimalString, currency: string): string {
  const value = Number(amount);
  const formatted = new Intl.NumberFormat("en-LK", {
    minimumFractionDigits: value % 1 === 0 ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(value);
  return currency === "LKR" ? `Rs. ${formatted}` : `${currency} ${formatted}`;
}

export function formatDate(date: ISODate): string {
  // Parse as a calendar date, not a UTC instant.
  const [y, m, d] = date.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}

export function formatTime(value: ISODateTime, approximate = false): string {
  const time = new Date(value).toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
  });
  return approximate ? `~${time}` : time;
}

export function formatDuration(minutes: number | null, approximate = false): string {
  if (minutes === null) return "—";
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${approximate ? "~" : ""}${h}h${m ? ` ${m}m` : ""}`;
}

/** Today's date as YYYY-MM-DD in the browser's timezone. */
export function todayISO(): ISODate {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/** Local calendar day of a timestamp, e.g. "Sat, 26 Sept". */
export function formatDayOf(value: ISODateTime): string {
  return new Date(value).toLocaleDateString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}
