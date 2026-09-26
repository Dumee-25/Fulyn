export type HealthStatus = "ok" | "degraded";

export interface HealthResponse {
  status: HealthStatus;
  app: string;
  version: string;
  environment: string;
  database: "ok" | "unavailable";
  timezone: string;
  currency: string;
}

/** Decimal values (money, quantities) arrive as strings to avoid float rounding. */
export type DecimalString = string;
/** ISO date, e.g. "2026-09-26". */
export type ISODate = string;
/** ISO datetime with offset. */
export type ISODateTime = string;

interface Timestamps {
  id: string;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface JournalEntry extends Timestamps {
  raw_text: string;
  ai_summary: string | null;
  entry_date: ISODate;
  mood_summary: string | null;
  is_private: boolean;
  importance_score: number;
}

export interface Expense extends Timestamps {
  amount: DecimalString;
  currency: string;
  category: string;
  merchant: string | null;
  description: string | null;
  expense_date: ISODate;
  is_impulse: boolean;
  impulse_reason: string | null;
  journal_entry_id: string | null;
}

export interface ExpenseSummary {
  currency: string;
  total: DecimalString;
  impulse_total: DecimalString;
  count: number;
  by_category: { category: string; total: DecimalString; count: number }[];
}

export interface MoodLog extends Timestamps {
  date: ISODate;
  score: number | null;
  label: string | null;
  energy_score: number | null;
  notes: string | null;
  journal_entry_id: string | null;
}

export interface SleepLog extends Timestamps {
  sleep_date: ISODate;
  sleep_time: ISODateTime | null;
  wake_time: ISODateTime | null;
  duration_minutes: number | null;
  is_approximate: boolean;
  quality_score: number | null;
  notes: string | null;
  journal_entry_id: string | null;
}

export interface CaffeineLog extends Timestamps {
  consumed_at: ISODateTime;
  is_approximate: boolean;
  drink_type: string;
  description: string | null;
  estimated_caffeine_mg: number | null;
  quantity: DecimalString;
  journal_entry_id: string | null;
}

export interface ChatAction {
  tool: string;
  ok: boolean;
  record_id: string | null;
  error: string | null;
}

export interface ChatResponse {
  conversation_id: string;
  reply: string;
  actions: ChatAction[];
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  actions: ChatAction[];
  created_at: ISODateTime;
}
