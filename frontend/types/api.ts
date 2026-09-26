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

export interface Memory {
  id: string;
  memory_type: string;
  source_id: string | null;
  title: string | null;
  content: string;
  memory_date: ISODate;
  importance_score: number;
  is_private: boolean;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface MemorySearchResult extends Memory {
  similarity: number | null;
  keyword_match: boolean;
}

export interface MemorySearchResponse {
  query: string;
  semantic: boolean;
  results: MemorySearchResult[];
}

export const RELATIONSHIP_TYPES = [
  "friend",
  "crush",
  "mentor",
  "lecturer",
  "family",
  "colleague",
  "acquaintance",
  "other",
] as const;

export interface Person {
  id: string;
  name: string;
  nickname: string | null;
  relationship_type: string | null;
  notes: string | null;
  first_mentioned_at: ISODate;
  last_interaction_at: ISODate | null;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface PersonSummary extends Person {
  interaction_count: number;
}

export interface Interaction {
  id: string;
  person_id: string;
  person_name: string;
  interaction_date: ISODate;
  summary: string;
  raw_context: string | null;
  location: string | null;
  mood_before: string | null;
  mood_after: string | null;
  importance_score: number;
  journal_entry_id: string | null;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface MusicMemory {
  id: string;
  song: string;
  artist: string | null;
  album: string | null;
  memory_text: string | null;
  emotion: string | null;
  memory_date: ISODate;
  person_id: string | null;
  person_name: string | null;
  importance_score: number;
  journal_entry_id: string | null;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface SongCount {
  song: string;
  artist: string | null;
  count: number;
}

export const BILLING_CYCLES = ["weekly", "monthly", "quarterly", "yearly", "custom"] as const;
export const RECURRENCE_RULES = ["daily", "weekly", "monthly", "yearly"] as const;
export const DECISION_STATUSES = ["active", "reconsidered", "reversed", "completed"] as const;

export interface Subscription {
  id: string;
  name: string;
  amount: DecimalString;
  currency: string;
  billing_cycle: (typeof BILLING_CYCLES)[number];
  custom_interval_days: number | null;
  next_billing_date: ISODate | null;
  category: string;
  active: boolean;
  notes: string | null;
  monthly_cost: DecimalString;
  next_due: ISODate | null;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface SubscriptionSummary {
  active_count: number;
  totals: { currency: string; monthly_total: DecimalString; yearly_total: DecimalString; count: number }[];
}

export interface Reminder {
  id: string;
  title: string;
  description: string | null;
  due_at: ISODateTime;
  recurrence_rule: string | null;
  status: "pending" | "completed" | "cancelled";
  last_completed_at: ISODateTime | null;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface Decision {
  id: string;
  title: string;
  decision: string;
  reasoning: string | null;
  decision_date: ISODate;
  status: (typeof DECISION_STATUSES)[number];
  importance_score: number;
  journal_entry_id: string | null;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface WaitingItem {
  id: string;
  title: string;
  description: string | null;
  waiting_since: ISODate;
  expected_by: ISODate | null;
  related_person_id: string | null;
  related_person_name: string | null;
  status: "waiting" | "received" | "cancelled" | "expired";
  resolved_at: ISODate | null;
  overdue: boolean;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export type TimelineKind = "event" | "decision" | "interaction" | "music" | "journal" | "purchase";

export interface TimelineItem {
  kind: TimelineKind;
  id: string;
  date: ISODate;
  title: string;
  detail: string | null;
  importance_score: number;
}

export interface Report {
  kind: "daily" | "weekly" | "monthly";
  period_start: ISODate;
  period_end: ISODate;
  content: string;
  data: Record<string, unknown>;
  generated_at: ISODateTime;
}
