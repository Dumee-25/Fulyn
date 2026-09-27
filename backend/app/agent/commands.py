"""Slash commands in chat, handled by the backend before (or instead of) the model.

Two kinds:
- Modifiers (/core, /important, /meh, /private, /nolog) can sit anywhere in a normal message
  ("Dinner with Sarah, spent 2400 /core"). The message is logged by the model as usual and
  the modifier is applied to what it logged. On their own they apply to the last message.
- Commands (/undo, /date, /spent, /today, /help, ...) must start the message. They run
  without the model, so they are instant and work even when Ollama is down.
"""

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.orm import Session

from app.agent.llm import LLMClient
from app.agent.loop import ActionRecord
from app.core.config import get_settings
from app.core.dates import parse_date, parse_month, take_date, take_time
from app.core.errors import DomainError
from app.core.time import now_local, today_local
from app.models.caffeine import CaffeineLog
from app.models.expense import Expense
from app.models.mood import MoodLog
from app.models.planning import Reminder
from app.models.sleep import SleepLog
from app.reports.render import format_money
from app.schemas.caffeine import CaffeineLogCreate
from app.schemas.expense import ExpenseCreate, ExpenseUpdate
from app.schemas.mood import MoodLogCreate
from app.schemas.planning import ReminderCreate
from app.schemas.sleep import SleepLogCreate
from app.services import caffeine, expenses, moods, people, planning, reports, sleep, turns
from app.vault import service as vault

IMPORTANCE_MODIFIERS = {"core": 5, "important": 4, "meh": 1}
MODIFIERS = {"core", "important", "meh", "private", "nolog"}
MODIFIER_PATTERN = re.compile(r"(?<!\S)/(core|important|meh|private|nolog)\b", re.IGNORECASE)


@dataclass(frozen=True)
class CommandInfo:
    name: str
    usage: str
    description: str
    kind: str  # "modifier" or "command"
    group: str


COMMANDS: list[CommandInfo] = [
    CommandInfo(
        "core", "/core", "Make this (or the last) message a core memory", "modifier", "Importance"
    ),
    CommandInfo("important", "/important", "Mark it important", "modifier", "Importance"),
    CommandInfo("meh", "/meh", "Mark it not important", "modifier", "Importance"),
    CommandInfo(
        "nolog", "/nolog <message>", "Chat without logging anything", "modifier", "Importance"
    ),
    CommandInfo(
        "private", "/private", "Put this (or the last) message in the vault", "modifier", "Privacy"
    ),
    CommandInfo(
        "vault",
        "/vault last | /vault <words>",
        "Move the last message to the vault, or search the vault",
        "command",
        "Privacy",
    ),
    CommandInfo("undo", "/undo", "Delete everything the last message logged", "command", "Fixing"),
    CommandInfo(
        "date",
        "/date <day>",
        "Move the last message to another day (yesterday, 12 sept, friday)",
        "command",
        "Fixing",
    ),
    CommandInfo(
        "impulse", "/impulse", "Mark the last expense as an impulse purchase", "command", "Fixing"
    ),
    CommandInfo(
        "notimpulse", "/notimpulse", "Unmark the last expense as impulse", "command", "Fixing"
    ),
    CommandInfo(
        "spent", "/spent <amount> <what> [at <place>]", "Log an expense", "command", "Quick log"
    ),
    CommandInfo(
        "coffee", "/coffee [drink] [time]", "Log a caffeinated drink", "command", "Quick log"
    ),
    CommandInfo("mood", "/mood <1-10> [feeling]", "Log your mood", "command", "Quick log"),
    CommandInfo("slept", "/slept <hours>", "Log last night's sleep", "command", "Quick log"),
    CommandInfo(
        "remind", "/remind <day> [time] <what>", "Create a reminder", "command", "Quick log"
    ),
    CommandInfo("today", "/today", "Recap of today", "command", "Views"),
    CommandInfo("week", "/week", "Recap of this week", "command", "Views"),
    CommandInfo(
        "month",
        "/month [month]",
        "Monthly report (this month, or e.g. /month august)",
        "command",
        "Views",
    ),
    CommandInfo("who", "/who <name>", "When you last saw someone", "command", "Views"),
    CommandInfo("waiting", "/waiting", "What you're still waiting for", "command", "Views"),
    CommandInfo("help", "/help", "List all commands", "command", "Views"),
]
STANDALONE = {c.name for c in COMMANDS if c.kind == "command"}


@dataclass
class Parsed:
    command: str | None  # a standalone command, "unknown", or None
    args: str
    modifiers: list[str]
    text: str  # the message without modifiers


@dataclass
class CommandResult:
    reply: str
    actions: list[ActionRecord] = field(default_factory=list)
    # The turn read or moved vault content: keep it out of future model context.
    private: bool = False


@dataclass
class Context:
    db: Session
    conversation_id: uuid.UUID
    message_id: uuid.UUID
    llm: LLMClient | None


def parse(message: str) -> Parsed:
    stripped = message.strip()
    first = re.match(r"/([A-Za-z]+)\b\s*(.*)", stripped, re.DOTALL)
    if first and first.group(1).lower() in STANDALONE:
        return Parsed(first.group(1).lower(), first.group(2).strip(), [], "")
    modifiers = [m.lower() for m in MODIFIER_PATTERN.findall(stripped)]
    text = " ".join(MODIFIER_PATTERN.sub(" ", stripped).split())
    if first and not modifiers and first.group(1).lower() not in MODIFIERS:
        return Parsed("unknown", first.group(1), [], "")
    return Parsed(None, "", list(dict.fromkeys(modifiers)), text)


# --- Formatting --------------------------------------------------------------------


def _day(d: date) -> str:
    return d.strftime("%a %d %b").replace(" 0", " ")


def _action(tool: str, record_id: Any = None) -> ActionRecord:
    return ActionRecord(tool=tool, ok=True, record_id=str(record_id) if record_id else None)


def help_text() -> str:
    lines = ["**Commands** (type `/` to pick one)", ""]
    group = None
    for c in COMMANDS:
        if c.group != group:
            group = c.group
            lines += ["", f"**{group}**"]
        lines.append(f"- `{c.usage}`: {c.description}")
    lines += [
        "",
        "`/core`, `/important`, `/meh`, `/private` and `/nolog` can go anywhere in a normal "
        "message, e.g. *Dinner with Sarah, spent 2400 /core*. On their own they apply to your "
        "last message.",
    ]
    return "\n".join(lines).replace("\n\n\n", "\n\n")


# --- Last-message commands ----------------------------------------------------------


def apply_importance(ctx: Context, score: int, records: list[Any] | None = None) -> CommandResult:
    if records is None:
        _, records = turns.last_turn(ctx.db, ctx.conversation_id)
    changed = turns.set_importance(ctx.db, records, score)
    if not changed:
        return CommandResult("That message didn't log anything that has an importance.")
    label = {5: "a core memory", 4: "important", 1: "not important"}.get(
        score, f"importance {score}"
    )
    return CommandResult(f"Marked as {label}.", [_action("set_memory_importance")])


def apply_private(ctx: Context, records: list[Any] | None = None) -> CommandResult:
    if records is None:
        _, records = turns.last_turn(ctx.db, ctx.conversation_id)
    entry = turns.journal_entry_of(records)
    if entry is None:
        return CommandResult("Only something you logged as a journal entry can go in the vault.")
    vault.set_entry_private(ctx.db, entry.id, True)
    linked = vault.linked_counts(ctx.db, entry.id)
    extra = f" (with {sum(linked.values())} linked records)" if linked else ""
    return CommandResult(
        f"Moved to your private vault{extra}. It won't show up anywhere else.",
        [_action("move_to_vault")],
        private=True,
    )


def cmd_undo(ctx: Context, args: str) -> CommandResult:
    deleted = turns.undo_last(ctx.db, ctx.conversation_id)
    if not deleted:
        return CommandResult("There was nothing left to undo from that message.")
    return CommandResult(
        "Undone. Removed: " + ", ".join(deleted) + ".",
        [_action("delete_" + d.replace(" ", "_")) for d in deleted],
    )


def cmd_date(ctx: Context, args: str) -> CommandResult:
    day = parse_date(args, today_local(), "past")
    if day is None:
        return CommandResult(
            "Which day? For example `/date yesterday`, `/date 12 sept` or `/date friday`."
        )
    old, moved = turns.move_last(ctx.db, ctx.conversation_id, day)
    if not moved:
        return CommandResult("The last message didn't log anything with a date.")
    return CommandResult(
        f"Moved from {_day(old)} to {_day(day)}: " + ", ".join(moved) + ".",
        [_action("update_" + m.replace(" ", "_")) for m in moved],
    )


def _set_impulse(ctx: Context, value: bool) -> CommandResult:
    expense = turns.last_expense(ctx.db, ctx.conversation_id)
    if expense is None:
        return CommandResult("I couldn't find an expense to change.")
    expenses.update_expense(ctx.db, expense.id, ExpenseUpdate(is_impulse=value))
    what = expense.merchant or expense.description or expense.category
    state = "an impulse purchase" if value else "not an impulse purchase"
    return CommandResult(
        f"Marked {format_money(expense.amount, expense.currency)} ({what}, "
        f"{_day(expense.expense_date)}) as {state}.",
        [_action("update_expense", expense.id)],
    )


def cmd_vault(ctx: Context, args: str) -> CommandResult:
    if not args:
        s = vault.summary(ctx.db)
        return CommandResult(
            f"Your vault has {s['entries']} entries. `/vault last` moves your last message "
            "there; `/vault <words>` searches it.",
            private=True,
        )
    if args.lower() == "last":
        return apply_private(ctx)
    results = vault.search(ctx.db, args, limit=5).results
    if not results:
        return CommandResult(f"Nothing in your vault matches “{args}”.", private=True)
    lines = [f"**From your vault** ({len(results)}):"]
    for r in results:
        snippet = " ".join(r.content.split())[:160]
        lines.append(f"- {_day(r.memory_date)}: {snippet}")
    return CommandResult("\n".join(lines), private=True)


# --- Quick logs -----------------------------------------------------------------------

CATEGORY_WORDS = {
    "Cafe": ("coffee", "latte", "cappuccino", "cafe", "café", "tea", "barista", "starbucks"),
    "Food": (
        "lunch",
        "dinner",
        "breakfast",
        "food",
        "meal",
        "snack",
        "groceries",
        "rice",
        "kottu",
        "pizza",
        "burger",
        "keells",
        "cargills",
    ),
    "Transport": ("uber", "pickme", "taxi", "bus", "train", "tuk", "fuel", "petrol", "parking"),
    "Shopping": ("clothes", "shoes", "shirt", "hoodie", "shopping", "daraz"),
    "Entertainment": ("movie", "cinema", "concert", "game", "netflix", "spotify"),
    "Education": ("book", "course", "tuition", "class", "exam", "stationery"),
    "Health": ("doctor", "medicine", "pharmacy", "gym", "hospital"),
    "Bills": ("bill", "electricity", "water", "internet", "phone", "rent", "reload"),
    "Technology": ("laptop", "phone case", "keyboard", "mouse", "headphones", "charger", "cable"),
}


def guess_category(text: str) -> str:
    words = text.lower()
    for category, keys in CATEGORY_WORDS.items():
        if category in get_settings().expense_categories and any(k in words for k in keys):
            return category
    return "Other"


def _amount(token: str) -> Decimal | None:
    cleaned = token.lower().removeprefix("rs.").removeprefix("rs").replace(",", "")
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    return value if value >= 0 and value == value.quantize(Decimal("0.01")) else None


def cmd_spent(ctx: Context, args: str) -> CommandResult:
    words = args.split()
    if not words or _amount(words[0]) is None:
        return CommandResult("Usage: `/spent 850 dinner at Barista`")
    amount, rest = _amount(words[0]), " ".join(words[1:])
    merchant = None
    at = re.search(r"\bat\s+(.+)$", rest, re.IGNORECASE)
    if at:
        merchant = at.group(1).strip()
        rest = rest[: at.start()].strip()
    expense = expenses.create_expense(
        ctx.db,
        ExpenseCreate(
            amount=amount,
            description=rest or None,
            merchant=merchant,
            category=guess_category(f"{rest} {merchant or ''}"),
        ),
    )
    turns.record_turn(ctx.db, ctx.conversation_id, ctx.message_id, [(Expense, expense.id)])
    what = " ".join(x for x in (rest, f"at {merchant}" if merchant else "") if x)
    return CommandResult(
        f"Logged {format_money(expense.amount, expense.currency)}"
        + (f" {what}" if what else "")
        + f" ({expense.category}).",
        [_action("create_expense", expense.id)],
    )


def _today_at(t: time) -> datetime:
    return datetime.combine(today_local(), t, tzinfo=get_settings().tz)


def cmd_coffee(ctx: Context, args: str) -> CommandResult:
    at, words = take_time(args.split())
    drink = " ".join(words) or "coffee"
    data = CaffeineLogCreate(drink_type=drink[:50], consumed_at=_today_at(at) if at else None)
    log = caffeine.create_caffeine_log(ctx.db, data)
    turns.record_turn(ctx.db, ctx.conversation_id, ctx.message_id, [(CaffeineLog, log.id)])
    when = at.strftime("%H:%M") if at else "just now"
    return CommandResult(f"Logged {drink} ({when}).", [_action("create_caffeine_log", log.id)])


def cmd_mood(ctx: Context, args: str) -> CommandResult:
    words = args.split()
    score = None
    if words and words[0].split("/")[0].isdigit():
        score = int(words[0].split("/")[0])
        words = words[1:]
    label = " ".join(words)[:30] or None
    if score is None and label is None:
        return CommandResult("Usage: `/mood 7 tired`")
    if score is not None and not 1 <= score <= 10:
        return CommandResult("Mood is 1 to 10.")
    log = moods.create_mood_log(ctx.db, MoodLogCreate(score=score, label=label))
    turns.record_turn(ctx.db, ctx.conversation_id, ctx.message_id, [(MoodLog, log.id)])
    parts = [p for p in (f"{score}/10" if score else None, log.label) if p]
    return CommandResult(f"Logged mood: {', '.join(parts)}.", [_action("create_mood_log", log.id)])


def cmd_slept(ctx: Context, args: str) -> CommandResult:
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*h?(?:\s*(\d{1,2})\s*m?)?", args.strip().lower())
    if not m:
        return CommandResult("Usage: `/slept 6.5` or `/slept 6h30`")
    minutes = round(float(m.group(1)) * 60) + (int(m.group(2)) if m.group(2) else 0)
    if not 0 < minutes <= 1440:
        return CommandResult("That's not a possible night's sleep.")
    log = sleep.create_sleep_log(ctx.db, SleepLogCreate(duration_minutes=minutes))
    turns.record_turn(ctx.db, ctx.conversation_id, ctx.message_id, [(SleepLog, log.id)])
    hours, mins = divmod(minutes, 60)
    return CommandResult(
        f"Logged {hours}h{f' {mins}m' if mins else ''} of sleep for last night.",
        [_action("create_sleep_log", log.id)],
    )


def cmd_remind(ctx: Context, args: str) -> CommandResult:
    today = today_local()
    day, words = take_date(args.split(), today, "future")
    at, words = take_time(words)
    title = " ".join(words).strip()
    if title.lower().startswith("to "):
        title = title[3:]
    if not title:
        return CommandResult("Usage: `/remind friday 9am call the bank`")
    if day is None and at is None:
        return CommandResult("When? For example `/remind tomorrow 5pm " + title + "`.")
    at = at or time(9, 0)
    due = datetime.combine(day or today, at, tzinfo=get_settings().tz)
    if day is None and due <= now_local():
        # Only a time was given and it has passed today: that means tomorrow.
        due += timedelta(days=1)
    reminder = planning.create_reminder(ctx.db, ReminderCreate(title=title[:200], due_at=due))
    turns.record_turn(ctx.db, ctx.conversation_id, ctx.message_id, [(Reminder, reminder.id)])
    return CommandResult(
        f"I'll remind you to {title} on {_day(due.date())} at {due.strftime('%H:%M')}.",
        [_action("create_reminder", reminder.id)],
    )


# --- Views ----------------------------------------------------------------------------


def cmd_today(ctx: Context, args: str) -> CommandResult:
    report = reports.generate_daily(ctx.db, today_local(), ctx.llm)
    return CommandResult(report.content, [_action("generate_daily_recap")])


def cmd_week(ctx: Context, args: str) -> CommandResult:
    report = reports.generate_weekly(ctx.db, today_local(), ctx.llm)
    return CommandResult(report.content, [_action("generate_weekly_recap")])


def cmd_month(ctx: Context, args: str) -> CommandResult:
    parsed = parse_month(args, today_local())
    if parsed is None:
        return CommandResult(
            "Which month? For example `/month`, `/month august` or `/month 2026-08`."
        )
    report = reports.generate_monthly(ctx.db, parsed[0], parsed[1], ctx.llm)
    return CommandResult(report.content, [_action("generate_monthly_report")])


def cmd_who(ctx: Context, args: str) -> CommandResult:
    if not args:
        return CommandResult("Usage: `/who Maya`")
    try:
        person, _ = people.resolve_person(ctx.db, args, create=False)
    except people.AmbiguousPersonError as exc:
        return CommandResult(str(exc).replace(" Ask which one.", " Try the full name."))
    if person is None:
        return CommandResult(f"I don't have anyone called {args}.")
    interactions = people.list_interactions(ctx.db, person_id=person.id, limit=5)
    if not interactions:
        return CommandResult(f"No interactions with {person.name} logged yet.")
    lines = [f"**{person.name}**, last seen {_day(interactions[0].interaction_date)}", ""]
    for i in interactions:
        where = f" at {i.location}" if i.location else ""
        lines.append(f"- {_day(i.interaction_date)}{where}: {i.summary}")
    return CommandResult("\n".join(lines))


def cmd_waiting(ctx: Context, args: str) -> CommandResult:
    items = planning.list_waiting(ctx.db, limit=20)
    if not items:
        return CommandResult("You're not waiting for anything.")
    lines = ["**Still waiting for:**"]
    for w in items:
        tag = " (overdue)" if w.overdue else ""
        who = f" from {w.related_person_name}" if w.related_person_name else ""
        lines.append(f"- {w.title}{who}, since {_day(w.waiting_since)}{tag}")
    return CommandResult("\n".join(lines))


HANDLERS: dict[str, Callable[[Context, str], CommandResult]] = {
    "undo": cmd_undo,
    "date": cmd_date,
    "impulse": lambda ctx, a: _set_impulse(ctx, True),
    "notimpulse": lambda ctx, a: _set_impulse(ctx, False),
    "vault": cmd_vault,
    "spent": cmd_spent,
    "coffee": cmd_coffee,
    "mood": cmd_mood,
    "slept": cmd_slept,
    "remind": cmd_remind,
    "today": cmd_today,
    "week": cmd_week,
    "month": cmd_month,
    "who": cmd_who,
    "waiting": cmd_waiting,
    "help": lambda ctx, a: CommandResult(help_text()),
}


def run(ctx: Context, parsed: Parsed) -> CommandResult:
    if parsed.command == "unknown":
        return CommandResult(f"I don't know `/{parsed.args}`. Type `/help` for the list.")
    try:
        return HANDLERS[parsed.command](ctx, parsed.args)
    except turns.NothingToActOnError:
        return CommandResult("There's no earlier message in this chat that logged anything.")
    except DomainError as exc:
        return CommandResult(f"Couldn't do that: {exc}.")


def apply_standalone_modifiers(ctx: Context, modifiers: list[str]) -> CommandResult:
    """Modifiers sent on their own act on the last message."""
    try:
        if "private" in modifiers:
            return apply_private(ctx)
        for name, score in IMPORTANCE_MODIFIERS.items():
            if name in modifiers:
                return apply_importance(ctx, score)
    except turns.NothingToActOnError:
        return CommandResult("There's no earlier message in this chat that logged anything.")
    return CommandResult(
        "`/nolog` goes in front of a message you don't want logged, e.g. `/nolog how are you?`"
    )
