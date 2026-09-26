"""Render report data as concise markdown. Empty sections are left out."""

from datetime import date
from decimal import Decimal
from typing import Any


def format_money(amount: str | Decimal, currency: str) -> str:
    """Rs. 1,450 / Rs. 1,450.50 / USD 4"""
    value = Decimal(amount)
    text = f"{value:,.0f}" if value == value.to_integral() else f"{value:,.2f}"
    return f"Rs. {text}" if currency == "LKR" else f"{currency} {text}"


def _num(value: float) -> str:
    """7.0 -> "7", 6.25 -> "6.3"."""
    return f"{value:g}" if float(value).is_integer() else f"{value:.1f}"


def _clip(text: str | None, limit: int = 90) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _hours(minutes: int | None) -> str:
    if minutes is None:
        return "—"
    h, m = divmod(int(minutes), 60)
    return f"{h}h {m:02d}m" if m else f"{h}h"


def _change(current: float | None, previous: float | None, unit: str = "") -> str:
    if current is None or previous is None:
        return ""
    diff = current - previous
    if abs(diff) < 1e-9:
        return " (same as the week before)"
    sign = "+" if diff > 0 else "−"
    return f" ({sign}{_num(abs(diff))}{unit} vs the week before)"


def _section(title: str, lines: list[str]) -> list[str]:
    lines = [line for line in lines if line]
    return [f"## {title}", *lines, ""] if lines else []


def _long_date(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%A, %d %B %Y").replace(" 0", " ")


def _common_sections(data: dict[str, Any], *, daily: bool) -> list[str]:
    out: list[str] = []
    sp, md, sl, cf = data["spending"], data["mood"], data["sleep"], data["caffeine"]
    cur = sp["currency"]

    mood_lines = []
    if md["count"]:
        labels = ", ".join(md["labels"]) if md["labels"] else None
        if md["average_score"] is not None:
            mood_lines.append(
                f"- Mood: {_num(md['average_score'])}/10" + (f" ({labels})" if labels else "")
            )
        elif labels:
            mood_lines.append(f"- Mood: {labels}")
        if md["average_energy"] is not None:
            mood_lines.append(f"- Energy: {_num(md['average_energy'])}/10")
    out += _section("Mood", mood_lines)

    sleep_lines = []
    if sl["nights"]:
        approx = "about " if sl["any_approximate"] else ""
        if daily:
            sleep_lines.append(f"- Slept {approx}{_hours(sl['average_minutes'])}")
        else:
            sleep_lines.append(
                f"- Average {approx}{_hours(sl['average_minutes'])} over {sl['nights']} "
                f"night{'s' if sl['nights'] != 1 else ''} "
                f"(shortest {_hours(sl['shortest_minutes'])}, "
                f"longest {_hours(sl['longest_minutes'])})"
            )
    out += _section("Sleep", sleep_lines)

    caffeine_lines = []
    if cf["drinks"]:
        if daily:
            drinks = ", ".join(
                f"{i['drink']} at {'~' if i['approximate'] else ''}{i['time']}" for i in cf["items"]
            )
            caffeine_lines.append(f"- {drinks}")
        else:
            days = len(cf["by_day"])
            caffeine_lines.append(
                f"- {_num(cf['drinks'])} drinks on {days} day{'s' if days != 1 else ''}"
            )
    out += _section("Caffeine", caffeine_lines)

    money_lines = []
    if sp["count"]:
        money_lines.append(f"- Spent {format_money(sp['total'], cur)}")
        if Decimal(sp["impulse_total"]) > 0:
            money_lines.append(f"- Impulse: {format_money(sp['impulse_total'], cur)}")
        if not daily and sp["by_category"]:
            money_lines.append(
                "- By category: "
                + ", ".join(
                    f"{c['category']} {format_money(c['total'], cur)}" for c in sp["by_category"]
                )
            )
    out += _section("Money", money_lines)

    people_lines = []
    for i in data["people"]["interactions"][: 8 if daily else 10]:
        where = f" at {i['location']}" if i.get("location") else ""
        prefix = "" if daily else f"{_long_date(i['date']).split(',')[0][:3]} {i['date'][8:]}: "
        people_lines.append(f"- {prefix}{i['person']}{where}: {i['summary']}")
    out += _section("People", people_lines)

    highlight_lines = [
        f"- {e['title']}" + (f": {e['description']}" if e.get("description") else "")
        for e in data["events"]
    ]
    # Events are listed above; other important memories follow, titles clipped.
    highlight_lines += [
        f"- {_clip(m['title'])} ({m['type'].replace('_', ' ')})"
        for m in data["important_memories"]
        if m["type"] != "event"
    ]
    out += _section("Highlights", highlight_lines)

    music_lines = [
        f"- {m['song']}"
        + (f" by {m['artist']}" if m.get("artist") else "")
        + (f": {m['memory']}" if m.get("memory") else "")
        for m in data["music"]["items"][:5]
    ]
    out += _section("Music", music_lines)

    decision_lines = [
        f"- {d['title']}" + (f", because {d['reasoning']}" if d.get("reasoning") else "")
        for d in data["decisions"]
    ]
    out += _section("Decisions", decision_lines)

    waiting_lines = [
        f"- {w['title']}" + (" (overdue)" if w["overdue"] else "") for w in data["waiting"]["open"]
    ]
    waiting_lines += [f"- Received: {t}" for t in data["waiting"]["received"]]
    out += _section("Waiting for", waiting_lines)
    return out


def render_daily(data: dict[str, Any], narrative: str | None) -> str:
    lines = [f"# {_long_date(data['start'])}", ""]
    if narrative:
        lines += [narrative, ""]
    lines += _common_sections(data, daily=True)
    return "\n".join(lines).strip() + "\n"


def render_weekly(data: dict[str, Any], narrative: str | None) -> str:
    start, end = date.fromisoformat(data["start"]), date.fromisoformat(data["end"])
    lines = [
        f"# Week of {start.strftime('%d %B')} – {end.strftime('%d %B %Y')}".replace(" 0", " "),
        "",
    ]
    if narrative:
        lines += [narrative, ""]

    prev = data["previous_week"]
    sp, md, sl = data["spending"], data["mood"], data["sleep"]
    trend = []
    if sp["count"] or Decimal(prev["spending_total"]):
        diff = Decimal(sp["total"]) - Decimal(prev["spending_total"])
        sign = "+" if diff > 0 else "−" if diff < 0 else "±"
        trend.append(
            f"- Spending {format_money(sp['total'], sp['currency'])} "
            f"({sign}{format_money(str(abs(diff)), sp['currency'])} vs the week before)"
        )
    if md["average_score"] is not None:
        trend.append(
            f"- Mood averaged {_num(md['average_score'])}/10"
            + _change(md["average_score"], prev["mood_average"])
        )
    if sl["average_minutes"] is not None:
        change = ""
        if prev["sleep_average_minutes"] is not None:
            diff = sl["average_minutes"] - prev["sleep_average_minutes"]
            change = f" ({'+' if diff >= 0 else '−'}{abs(diff)} min vs the week before)"
        trend.append(f"- Sleep averaged {_hours(sl['average_minutes'])}{change}")
    coincidence = data.get("caffeine_sleep")
    if coincidence:
        more_or_less = "shorter" if coincidence["sleep_difference_minutes"] > 0 else "longer"
        trend.append(
            f"- Higher caffeine days coincided with {more_or_less} sleep that night "
            f"(about {abs(coincidence['sleep_difference_minutes'])} min, "
            f"{coincidence['pairs']} days compared). This is a pattern, not a cause."
        )
    lines += _section("This week", trend)
    lines += _common_sections(data, daily=False)
    return "\n".join(lines).strip() + "\n"


def render_monthly(
    data: dict[str, Any], one_sentence: str | None, themes: list[str], month_name: str
) -> str:
    lines = [f"# {month_name}", ""]
    if one_sentence:
        lines += [f"**The month in one sentence:** {one_sentence}", ""]
    subs = data["subscriptions"]["totals"]
    lines += _section(
        "Subscriptions",
        [
            f"- {t['count']} active, {format_money(t['monthly_total'], t['currency'])} a month"
            for t in subs
        ],
    )
    by_week = data["mood"].get("by_week") or {}
    if len(by_week) > 1:
        lines += _section(
            "Mood by week",
            [
                f"- Week of {date.fromisoformat(w).strftime('%d %b').lstrip('0')}: {_num(s)}/10"
                for w, s in by_week.items()
                if s is not None
            ],
        )
    counts = data["people"]["by_person"]
    if counts:
        lines += _section(
            "People you saw",
            ["- " + ", ".join(f"{p['name']} ({p['count']})" for p in counts)],
        )
    top = data["music"]["most_mentioned"]
    if top:
        lines += _section(
            "Songs of the month",
            [
                f"- {s['song']}"
                + (f" by {s['artist']}" if s["artist"] else "")
                + (f" ×{s['count']}" if s["count"] > 1 else "")
                for s in top
            ],
        )
    lines += _common_sections(data, daily=False)
    lines += _section("Recurring themes", [f"- {t}" for t in themes])
    return "\n".join(lines).strip() + "\n"
