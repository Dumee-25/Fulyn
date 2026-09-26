"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { compactNumber } from "@/lib/format";

/*
 * Chart conventions (see the dataviz method): thin marks, 4px rounded bar ends on the
 * value side, 2px lines, recessive grid and axes, a hover tooltip on every chart, text in
 * text colors (never the series color), a legend whenever there are two series, and
 * single-series charts named by their title instead of a legend. Colors come from the
 * --series-* tokens, validated for colour-blind separation and contrast in both themes.
 */

const AXIS = { stroke: "var(--muted-foreground)", fontSize: 11 };
const GRID = "color-mix(in oklch, var(--border) 70%, transparent)";

type Row = Record<string, string | number | null>;

function shortDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

function TooltipBox({
  label,
  rows,
}: {
  label: string;
  rows: { name: string; value: string; color: string }[];
}) {
  return (
    <div className="rounded-md border border-border bg-popover px-2.5 py-1.5 text-xs shadow-sm">
      <p className="mb-1 text-muted-foreground">{label}</p>
      {rows.map((r) => (
        <p key={r.name} className="flex items-center gap-1.5 text-foreground">
          <span className="size-2 rounded-full" style={{ background: r.color }} />
          {r.name}: <span className="font-mono">{r.value}</span>
        </p>
      ))}
    </div>
  );
}

export function EmptyChart({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-40 items-center justify-center text-xs text-muted-foreground">
      {children}
    </div>
  );
}

/** One series over days, as thin bars. Missing days render as gaps, never as zero. */
export function DailyBars({
  data,
  valueKey,
  name,
  format,
  axisFormat = compactNumber,
  height = 160,
}: {
  data: Row[];
  valueKey: string;
  name: string;
  /** Tooltip value format (full precision). */
  format: (value: number) => string;
  /** Short y-axis labels. */
  axisFormat?: (value: number) => string;
  height?: number;
}) {
  if (!data.some((d) => d[valueKey] !== null && d[valueKey] !== undefined)) {
    return <EmptyChart>Nothing logged in this period.</EmptyChart>;
  }
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -12 }} barCategoryGap={2}>
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis
          dataKey="date"
          tickFormatter={shortDate}
          tick={AXIS}
          tickLine={false}
          axisLine={false}
          interval="preserveStartEnd"
          minTickGap={24}
        />
        <YAxis
          tick={AXIS}
          tickLine={false}
          axisLine={false}
          width={40}
          tickFormatter={axisFormat}
          allowDecimals={false}
        />
        <Tooltip
          cursor={{ fill: "color-mix(in oklch, var(--muted) 60%, transparent)" }}
          content={({ active, payload, label }) =>
            active && payload?.length && payload[0].value != null ? (
              <TooltipBox
                label={shortDate(String(label))}
                rows={[{ name, value: format(Number(payload[0].value)), color: "var(--series-1)" }]}
              />
            ) : null
          }
        />
        <Bar dataKey={valueKey} name={name} fill="var(--series-1)" radius={[4, 4, 0, 0]} maxBarSize={14} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Mood and energy (1–10) as two lines with a legend. */
export function MoodEnergyLines({ data }: { data: Row[] }) {
  if (!data.some((d) => d.mood != null || d.energy != null)) {
    return <EmptyChart>No mood logged in this period.</EmptyChart>;
  }
  const series = [
    { key: "mood", name: "Mood", color: "var(--series-1)" },
    { key: "energy", name: "Energy", color: "var(--series-2)" },
  ];
  return (
    <div>
      <div className="mb-2 flex gap-4 text-xs text-muted-foreground" aria-label="Legend">
        {series.map((s) => (
          <span key={s.key} className="flex items-center gap-1.5">
            <span className="h-0.5 w-3 rounded-full" style={{ background: s.color }} />
            {s.name}
          </span>
        ))}
      </div>
      <ResponsiveContainer width="100%" height={160}>
        <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -24 }}>
          <CartesianGrid vertical={false} stroke={GRID} />
          <XAxis
            dataKey="date"
            tickFormatter={shortDate}
            tick={AXIS}
            tickLine={false}
            axisLine={false}
            interval="preserveStartEnd"
            minTickGap={24}
          />
          <YAxis domain={[1, 10]} ticks={[1, 5, 10]} tick={AXIS} tickLine={false} axisLine={false} />
          <Tooltip
            cursor={{ stroke: "var(--muted-foreground)", strokeDasharray: "3 3" }}
            content={({ active, payload, label }) =>
              active && payload?.length ? (
                <TooltipBox
                  label={shortDate(String(label))}
                  rows={payload
                    .filter((p) => p.value != null)
                    .map((p) => ({
                      name: String(p.name),
                      value: `${p.value}/10`,
                      color: String(p.color),
                    }))}
                />
              ) : null
            }
          />
          {series.map((s) => (
            <Line
              key={s.key}
              dataKey={s.key}
              name={s.name}
              stroke={s.color}
              strokeWidth={2}
              dot={{ r: 3, strokeWidth: 0, fill: s.color }}
              activeDot={{ r: 4, stroke: "var(--card)", strokeWidth: 2 }}
              connectNulls
              type="monotone"
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/** A labelled horizontal bar list (categories, hours). Values are shown as text too. */
export function BarList({
  items,
  format,
}: {
  items: { label: string; value: number }[];
  format: (value: number) => string;
}) {
  const max = Math.max(...items.map((i) => i.value), 0);
  if (!items.length || max === 0) return <EmptyChart>Nothing yet.</EmptyChart>;
  return (
    <ul className="space-y-1.5">
      {items.map((item) => (
        <li key={item.label} className="grid grid-cols-[6rem_1fr_auto] items-center gap-2 text-xs">
          <span className="truncate text-muted-foreground">{item.label}</span>
          <span className="h-2 rounded-r-[4px] bg-muted">
            <span
              className="block h-2 rounded-r-[4px] bg-series-1"
              style={{ width: `${(item.value / max) * 100}%` }}
              title={`${item.label}: ${format(item.value)}`}
            />
          </span>
          <span className="font-mono text-foreground">{format(item.value)}</span>
        </li>
      ))}
    </ul>
  );
}
