# Personal Life Agent

Build a private, single-user AI-powered personal life tracking and memory application.

The core interaction model is conversational: I should be able to type naturally into one chat/input box, and the AI agent should understand what I am saying, extract relevant structured information, store it, and later retrieve/analyze it.

This is primarily a personal application, not a SaaS product. Optimize for simplicity, privacy, maintainability, and data ownership.

---

# 1. Core Philosophy

The application should feel like a personal assistant that remembers my life.

I should be able to type things like:

> Spent 850 on dinner. Had an iced latte around 4. Slept like shit last night, maybe 4 hours. Met Alex after uni and we talked for a while. Pretty good day overall.

The system should be capable of extracting multiple records from the same message:

- Expense: Rs. 850
- Caffeine: iced latte at approximately 4 PM
- Sleep: approximately 4 hours
- Person interaction: Alex
- Mood: positive/good
- Journal entry: preserve the original message
- Life event: met Alex after university

The application should not require me to manually navigate through multiple forms unless I specifically want to edit data.

The AI is responsible for interpretation.

The backend is responsible for validation and persistence.

The LLM must NEVER directly write arbitrary SQL or modify the database.

All database modifications must happen through predefined backend tools/functions.

---

# 2. Tech Stack

Use the following unless there is a strong technical reason not to.

## Backend

- Python
- FastAPI
- SQLAlchemy 2.x
- Pydantic
- PostgreSQL
- pgvector
- Alembic for migrations

## AI

Use Ollama as the LLM interface.

Primary model should be configurable through environment variables.

Example:

```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=nemotron-3-ultra:cloud
```

Do not hard-code the model name.

The system should support switching Ollama models later without major code changes.

Use native tool/function calling where supported.

Avoid LangChain initially.

Implement a lightweight custom agent loop instead.

## Frontend

Preferred:

- Next.js
- TypeScript
- Tailwind CSS
- shadcn/ui

Use a clean dark-mode-first design.

The interface should feel like a personal dashboard rather than enterprise software.

## Development

Use Docker Compose for:

- PostgreSQL
- Backend
- Frontend if useful

Ollama may run separately.

---

# 3. Main Features

The finished application should support:

1. Conversational life logging
2. Expense tracking
3. Journal
4. Mood tracking
5. Sleep tracking
6. Caffeine tracking
7. People / interaction log
8. Music memory log
9. Subscription tracker
10. Reminders
11. Impulse purchase tracking
12. Daily recap
13. Weekly recap
14. Monthly life report
15. Life timeline
16. Decision log
17. Things I'm waiting for
18. Personal analytics dashboard
19. Memory importance score
20. Private vault
21. Semantic memory search
22. Editing/correcting existing records
23. Full data export

---

# 4. Conversational Agent

The main UI should contain a persistent chat/input interface.

The agent should interpret natural language and decide which tools to call.

One message may result in zero, one, or many tool calls.

Example:

User:

> Spent 1200 at Barista with Sarah. Had a cappuccino. Really nice evening actually.

Agent should potentially call:

```text
create_journal_entry()
create_expense()
create_caffeine_log()
create_person_interaction()
create_life_event()
create_mood_log()
```

All records created from one message should reference the original source entry where appropriate.

After execution, respond naturally:

> Logged it — Rs. 1,200 at Barista, cappuccino, and your evening with Sarah. I marked the overall mood as positive.

Do not make responses excessively verbose.

---

# 5. Critical AI Rules

Create a strong system prompt enforcing these rules.

## Rule 1 — Never invent memories

If information does not exist in the database, say so.

Never fabricate:

- events
- dates
- conversations
- people
- expenses
- moods
- locations
- memories

Example:

User:

> Did I meet Sarah in June?

If no evidence exists:

> I couldn't find any record of you meeting Sarah in June.

Never say:

> You probably met her around June 15.

---

## Rule 2 — Preserve original journal text

Never overwrite or replace the user's original journal text with an AI summary.

Store:

```text
raw_text
ai_summary
```

The raw text is authoritative.

The AI summary is optional metadata.

---

## Rule 3 — Be conservative with inference

It is okay to infer obvious categories.

Example:

> Paid 600 for Uber.

May infer:

```text
category = Transport
```

Do not infer sensitive or speculative information.

For people, only record what the user explicitly communicates.

Never infer what another person thinks or feels.

---

## Rule 4 — Uncertainty matters

Structured records should support confidence or uncertainty when appropriate.

Example:

> Slept around 2 and woke around 7.

Store approximate times, not fake precision like 02:03.

---

# 6. Core Database Entities

Use UUID primary keys unless there is a good reason not to.

Every major table should contain:

```text
id
created_at
updated_at
```

Use timezone-aware timestamps.

---

# 7. Journal Entries

Table:

```text
journal_entries

id
raw_text
ai_summary
entry_date
mood_summary
is_private
importance_score
embedding
created_at
updated_at
```

The journal entry should act as one of the central source objects for memories.

---

# 8. Expenses

```text
expenses

id
amount
currency
category
merchant
description
expense_date
is_impulse
journal_entry_id
created_at
updated_at
```

Default currency:

```text
LKR
```

Categories should remain reasonably broad:

- Food
- Cafe
- Transport
- Shopping
- Entertainment
- Subscription
- Education
- Health
- Bills
- Technology
- Other

Allow future customization.

---

# 9. Mood Tracking

```text
mood_logs

id
date
score
label
energy_score
notes
journal_entry_id
created_at
```

Suggested score:

```text
1-10
```

Mood and energy should be separate concepts.

The AI may infer mood from journal text but should allow manual correction.

Example labels:

- great
- good
- calm
- neutral
- tired
- frustrated
- anxious
- angry
- sad
- mixed

Do not perform medical or psychiatric diagnosis.

---

# 10. Sleep Logs

```text
sleep_logs

id
sleep_date
sleep_time
wake_time
duration_minutes
quality_score
notes
journal_entry_id
created_at
```

Allow incomplete data.

Example:

> Slept about 5 hours.

Should be valid even if exact sleep/wake times are unknown.

---

# 11. Caffeine Tracking

```text
caffeine_logs

id
consumed_at
drink_type
description
estimated_caffeine_mg
quantity
journal_entry_id
created_at
```

Do not require caffeine milligrams.

If unknown, store null.

Examples:

- cappuccino
- iced latte
- americano
- cold brew
- tea
- energy drink

---

# 12. People

People records represent individuals appearing in my life.

```text
people

id
name
nickname
relationship_type
notes
first_mentioned_at
last_interaction_at
created_at
updated_at
```

Examples of relationship_type:

- friend
- crush
- mentor
- lecturer
- family
- colleague
- acquaintance
- other

Do not perform relationship scoring.

Do not infer whether another person likes/dislikes me.

---

# 13. Person Interactions

```text
person_interactions

id
person_id
interaction_date
summary
raw_context
location
mood_before
mood_after
importance_score
journal_entry_id
created_at
```

Queries should support:

> When did I last see X?

> Show memories involving X.

> What did I write after talking to X last week?

---

# 14. Music Memory

```text
music_memories

id
song
artist
album
memory_text
emotion
memory_date
person_id
journal_entry_id
importance_score
created_at
```

Support queries such as:

> What songs defined September?

> What memories do I associate with this song?

> Show music connected to Sarah.

Do not require Spotify integration in the initial version.

Music is manually mentioned through conversation.

---

# 15. Subscriptions

```text
subscriptions

id
name
amount
currency
billing_cycle
next_billing_date
category
active
notes
created_at
updated_at
```

Billing cycles:

- weekly
- monthly
- quarterly
- yearly
- custom

Support:

> What subscriptions am I paying for?

> How much do subscriptions cost me every month?

---

# 16. Reminders

```text
reminders

id
title
description
due_at
recurrence_rule
status
created_at
updated_at
```

Statuses:

- pending
- completed
- cancelled

Initial implementation does not need push notifications.

Displaying upcoming reminders inside the app is enough.

Design reminder logic so notifications can be added later.

---

# 17. Impulse Purchases

Use:

```text
expenses.is_impulse
```

Also allow optional metadata:

```text
impulse_reason
```

The user should be able to say:

> This was definitely an impulse purchase.

or:

> Don't count that as impulse.

Analytics should show impulse spending separately.

Do not shame the user.

---

# 18. Decision Log

```text
decisions

id
title
decision
reasoning
decision_date
status
importance_score
journal_entry_id
created_at
updated_at
```

Statuses:

- active
- reconsidered
- reversed
- completed

Example:

> I've decided not to buy the keyboard because I already have one and it's 28k.

Later:

> Why did I decide not to buy that keyboard?

The agent should retrieve the recorded reasoning.

---

# 19. Things I'm Waiting For

```text
waiting_items

id
title
description
waiting_since
expected_by
related_person_id
status
resolved_at
created_at
updated_at
```

Statuses:

- waiting
- received
- cancelled
- expired

Examples:

- refund
- delivery
- someone sending a file
- reply
- results
- approval

Support:

> What am I still waiting for?

---

# 20. Life Events / Timeline

```text
life_events

id
title
description
event_date
event_type
importance_score
journal_entry_id
created_at
```

Timeline should combine relevant entities chronologically.

Examples:

- important journal entries
- major purchases
- interactions
- decisions
- important memories
- events

Do not put every coffee on the main timeline.

Timeline filtering should support importance.

---

# 21. Memory System

Create a generalized memory layer.

```text
memories

id
memory_type
source_id
title
content
memory_date
importance_score
is_private
embedding
created_at
updated_at
```

Possible memory types:

```text
journal
event
person_interaction
decision
music
expense
other
```

This table may reference domain-specific records rather than duplicate all data.

Use pgvector for semantic search.

---

# 22. Memory Importance Score

Use:

```text
0 = disposable
1 = mundane
2 = normal
3 = notable
4 = important
5 = core memory
```

The model may suggest an importance score.

The user must always be able to override it.

Interpret phrases such as:

> Remember this.

as likely:

```text
importance_score = 5
```

And:

> That's not important.

as lowering importance.

Important memories should appear more prominently in timeline/search/report views.

---

# 23. Private Vault

Private content requires special treatment.

Private/vault records must:

- have `is_private = true`
- not appear in automatic recaps
- not appear in standard semantic search
- not appear in dashboard summaries
- not appear in monthly reports
- only be retrieved when the user explicitly requests private/vault content

Example:

> Search my private memories about Sarah.

Private search may then include them.

Architect the system so vault embeddings can be searched separately from normal memories.

For an initial local implementation, database-level encryption is optional.

However:

- isolate vault handling in the application layer
- never log private content to console
- avoid sending private content unnecessarily
- make future encryption easy to add

---

# 24. Daily Recap

Generate a daily recap from stored structured data.

Store:

```text
daily_recaps

id
date
content
generated_at
```

Possible recap sections:

```text
Mood
Sleep
Caffeine
Money spent
People/interactions
Highlights
Music
Important memories
New decisions
Waiting items
```

Keep the recap concise.

Do not include private vault data.

Daily recaps should be generated on demand initially.

Automatic scheduling can be added later.

---

# 25. Weekly Recap

Keep the previously discussed V1 weekly recap.

Include useful patterns such as:

- total spending
- spending vs previous week
- mood trend
- sleep trend
- caffeine
- notable interactions
- important memories
- decisions
- incomplete waiting items

Avoid pretending correlation means causation.

Say:

> Higher caffeine intake coincided with shorter sleep this week.

Not:

> Caffeine caused your sleep problems.

---

# 26. Monthly Life Report

Create a stored monthly report.

```text
monthly_reports

id
year
month
content
generated_at
```

Report should summarize:

- total spending
- category breakdown
- impulse spending
- subscriptions
- mood trend
- average sleep
- caffeine
- significant people/interactions
- important memories
- music memories
- decisions
- waiting items
- timeline highlights
- recurring themes

Include a short natural-language:

```text
Month in one sentence
```

Do not include vault data.

---

# 27. Analytics Dashboard

Create a dashboard page.

Primary dashboard cards:

```text
Today

Mood
Sleep
Caffeine
Money spent
```

Then display:

### Spending

- month total
- spending by category
- impulse spending
- subscription total
- spending over time

### Mood

- mood trend
- energy trend

### Sleep

- duration trend
- average sleep

### Caffeine

- drinks per day
- caffeine timing if available

### People

- recent interactions
- interaction counts

Do not rank people as "best" or "worst."

### Memories

- recent important memories
- core memories

### Waiting

- currently waiting items

### Decisions

- recent decisions

Use charts where appropriate.

---

# 28. Cross-Domain Analytics

One of the important capabilities of this application is comparing different parts of life.

Support queries like:

> How much do I usually spend on days I go out?

> What songs appear most often in positive memories?

> How was my mood during weeks where I slept more?

> How much have I spent at cafes this month?

> Show important memories involving Sarah.

> What happened around the time I made this decision?

The agent should execute structured queries and semantic searches as needed.

Do not claim causal relationships without evidence.

---

# 29. Search

Implement:

## Structured search

For:

- dates
- amounts
- people
- categories
- songs
- sleep
- caffeine
- decisions
- subscriptions

## Semantic search

Using pgvector for:

- journals
- memories
- events
- interactions
- decisions
- music memories

A request may require both.

---

# 30. Agent Tools

Create explicit backend tools.

At minimum:

```text
create_journal_entry
search_journal_entries
update_journal_entry
delete_journal_entry

create_expense
get_expenses
update_expense
delete_expense

create_mood_log
get_mood_logs
update_mood_log

create_sleep_log
get_sleep_logs
update_sleep_log

create_caffeine_log
get_caffeine_logs

create_person
find_person
create_person_interaction
get_person_interactions

create_music_memory
search_music_memories

create_subscription
get_subscriptions
update_subscription

create_reminder
get_reminders
complete_reminder

create_decision
search_decisions
update_decision

create_waiting_item
get_waiting_items
resolve_waiting_item

create_life_event
search_life_events

search_memories
search_private_memories
set_memory_importance

generate_daily_recap
generate_weekly_recap
generate_monthly_report

get_dashboard_stats

export_data
```

Tool input/output should use strict Pydantic schemas.

---

# 31. Corrections and Conversational Editing

The application must handle corrections naturally.

Example:

User:

> Spent 800 on dinner yesterday.

Then:

> Actually it was 850.

The agent should identify the relevant recent record and call:

```text
update_expense
```

If multiple records could match, ask which one rather than guessing.

Support:

> Delete that.

> Change the coffee expense to 650.

> That wasn't an impulse purchase.

> Make that memory important.

> Put that in the private vault.

---

# 32. Export

Data ownership is essential.

Implement an export page.

Support:

## Full export

JSON containing all non-secret application data.

## Expenses

CSV

## Journal

Markdown

Example:

```markdown
# September 26, 2026

Today was...

Mood: Good
Importance: 4
```

## Other structured records

CSV or JSON.

Provide a downloadable ZIP containing:

```text
journal/
expenses.csv
moods.csv
sleep.csv
caffeine.csv
people.csv
interactions.csv
music_memories.csv
subscriptions.csv
decisions.csv
waiting_items.csv
life_events.csv
memories.json
```

Private vault export should be a separate explicit option.

---

# 33. API Structure

Suggested API:

```text
/api/chat

/api/journal
/api/expenses
/api/moods
/api/sleep
/api/caffeine

/api/people
/api/interactions
/api/music

/api/subscriptions
/api/reminders

/api/decisions
/api/waiting
/api/events

/api/memories
/api/vault

/api/analytics
/api/reports

/api/export
```

Use REST initially.

Do not introduce GraphQL.

---

# 34. Frontend Pages

Create:

```text
/
Dashboard

/chat
Agent chat

/timeline
Life timeline

/journal
Journal entries

/expenses
Expenses

/people
People and interactions

/music
Music memories

/decisions
Decision history

/waiting
Things I'm waiting for

/subscriptions
Subscriptions

/reminders
Reminders

/reports
Daily / weekly / monthly reports

/vault
Private vault

/settings
Configuration / exports
```

The chat interface should also be accessible globally if practical.

---

# 35. UI Style

Use a dark, minimal design.

Avoid:

- overly corporate dashboards
- excessive gradients
- giant cards everywhere
- cluttered navigation

Prefer:

- dark charcoal background
- clean typography
- subtle borders
- comfortable spacing
- muted accent colors
- smooth charts
- compact information density

The application should feel calm and personal.

---

# 36. Privacy

This is a personal application containing sensitive data.

Therefore:

- no analytics/tracking scripts
- no third-party telemetry
- no unnecessary external services
- do not log journal content
- do not log vault content
- sanitize server errors
- secrets belong in `.env`
- never commit `.env`

Create:

```text
.env.example
```

---

# 37. Timezone

The default timezone should be configurable.

Initial default:

```text
Asia/Colombo
```

Never assume UTC when interpreting natural phrases like:

- today
- yesterday
- tonight
- this morning

Store timestamps properly and convert for display.

---

# 38. Currency

Default:

```text
LKR
```

Make it configurable.

Amounts should be stored using decimal/numeric database types.

Never use floating point for money.

---

# 39. Project Structure

Use a clean monorepo structure such as:

```text
personal-life-agent/

backend/
    app/
        api/
        agent/
        core/
        db/
        models/
        schemas/
        services/
        tools/
        reports/
        exports/

    alembic/
    tests/
    requirements.txt

frontend/
    app/
    components/
    hooks/
    lib/
    types/

docker-compose.yml
.env.example
README.md
```

---

# 40. Agent Architecture

Use a straightforward agent loop.

Example:

```text
User message
      ↓
Load relevant recent conversation context
      ↓
Send system prompt + user message + tools to Ollama
      ↓
Model selects tool(s)
      ↓
Validate tool arguments
      ↓
Execute backend service
      ↓
Return tool result to model
      ↓
Model decides whether another tool is needed
      ↓
Final response
```

Set a reasonable maximum number of tool-call iterations to avoid loops.

Example:

```text
MAX_TOOL_ITERATIONS = 8
```

---

# 41. Memory Retrieval

Do not dump thousands of database records into the model context.

Use retrieval.

For a question:

> What was July like for me?

Retrieve:

- July summary statistics
- important July memories
- relevant journals
- people interactions
- decisions
- life events
- monthly report if it exists

Then allow the model to synthesize.

---

# 42. Embeddings

Abstract embedding generation behind an interface.

Example:

```python
class EmbeddingService:
    async def embed(self, text: str) -> list[float]:
        ...
```

This allows changing embedding models later.

Generate embeddings for:

- journal entries
- memories
- person interactions
- decisions
- life events
- music memories

Do not generate embeddings for data where semantic search adds little value, such as raw expense amounts.

---

# 43. Testing

Add tests from the beginning.

At minimum:

## Unit tests

- expense creation
- money decimal precision
- date parsing
- tool validation
- memory privacy filters
- importance score validation

## Agent behavior tests

Test inputs like:

```text
Spent 500 on coffee.
```

Expected:

```text
expense created
```

Input:

```text
Spent 500 on coffee and slept 5 hours.
```

Expected:

```text
expense created
sleep log created
```

Input:

```text
Show me memories about Sarah.
```

Expected:

```text
normal memory search
```

Input:

```text
Search my private memories about Sarah.
```

Expected:

```text
private memory search explicitly allowed
```

Input:

```text
What happened with Sarah in 2024?
```

with no data.

Expected:

```text
agent admits no records found
```

---

# 44. Seed / Demo Data

Create optional development seed data.

Do not automatically seed production databases.

Include several example:

- expenses
- journal entries
- moods
- sleep logs
- caffeine logs
- people
- interactions
- decisions
- memories

This will make frontend development easier.

---

# 45. Build Order

Do NOT try to build the entire application at once.

Follow this implementation sequence.

## Phase 1 — Foundation

Build:

- repository structure
- PostgreSQL
- FastAPI
- SQLAlchemy
- Alembic
- Next.js
- Docker setup
- settings/configuration
- health endpoints

Make sure everything runs.

---

## Phase 2 — Core Life Logging

Implement:

- journal
- expenses
- mood
- sleep
- caffeine

Build their CRUD APIs.

Build simple frontend pages.

---

## Phase 3 — Agent

Add Ollama.

Implement:

- agent system prompt
- tool registry
- agent loop
- tool execution
- conversation endpoint

Support:

```text
journal
expense
mood
sleep
caffeine
```

before adding more tools.

---

## Phase 4 — Memory

Implement:

- pgvector
- embeddings
- semantic search
- memory table
- importance score

Add:

```text
search_memories
set_memory_importance
```

---

## Phase 5 — People and Music

Implement:

- people
- interactions
- music memories

Add semantic linking.

---

## Phase 6 — Personal Management

Implement:

- subscriptions
- reminders
- decisions
- waiting items
- impulse purchase handling

---

## Phase 7 — Timeline and Reports

Implement:

- life timeline
- daily recap
- weekly recap
- monthly report

---

## Phase 8 — Analytics

Build dashboard charts and cross-domain analytics.

---

## Phase 9 — Private Vault

Implement:

- private records
- retrieval isolation
- UI
- agent restrictions

Write privacy tests.

---

## Phase 10 — Export and Polish

Implement:

- JSON export
- CSV exports
- Markdown journal export
- ZIP download
- settings
- UI polish

---

# 46. MVP Definition

The first actually usable release only needs:

```text
Chat
Journal
Expenses
Mood
Sleep
Caffeine
People
Semantic memory
Corrections
Daily recap
Weekly recap
Basic dashboard
```

Everything else can follow.

Do not delay having a working app because later features are incomplete.

---

# 47. Acceptance Test

The following conversation should work after the core agent is completed.

User:

> Slept around 2 last night and woke at 7. Had an iced latte at 10. Went to Barista with Maya after uni and spent 1450. Pretty nice day honestly.

Expected records:

```text
Journal:
raw text preserved

Sleep:
02:00 → 07:00
approximately 5 hours

Caffeine:
iced latte
10:00

Person:
Maya created or matched

Interaction:
met Maya after university

Expense:
1450 LKR
Barista
Cafe

Mood:
positive/good

Life event:
Barista with Maya
```

Then:

User:

> Actually the Barista bill was 1550.

Expected:

```text
previous expense updated
```

Then:

User:

> Make that evening a core memory.

Expected:

```text
relevant memory importance = 5
```

Then:

User:

> What did I do that day?

Expected:

The agent retrieves the stored records and summarizes them without inventing additional details.

---

# 48. Development Rules

While implementing:

1. Prefer simple code over abstractions.
2. Do not introduce microservices.
3. Do not introduce Redis until there is an actual need.
4. Do not introduce Kafka.
5. Do not use LangChain initially.
6. Keep domain logic outside API route handlers.
7. Use typed schemas everywhere.
8. Use Alembic migrations.
9. Write tests for important behavior.
10. Keep the application runnable after every phase.
11. Update README as development progresses.
12. Never fabricate missing configuration.
13. If something is ambiguous, choose the simplest sensible implementation and document the choice.

---

# 49. Initial Task

Start by completing Phase 1 only.

Create:

- repository structure
- backend FastAPI application
- PostgreSQL database
- SQLAlchemy setup
- Alembic
- Next.js frontend
- Tailwind
- shadcn/ui setup
- Docker Compose
- environment configuration
- health-check API
- frontend connection to backend
- README with development instructions

Do not implement the AI agent yet.

After Phase 1 is working, proceed to Phase 2.

Before moving between major phases:

- make sure the application runs
- run tests
- fix obvious errors
- document what was completed

The long-term target is the full Personal Life Agent described above.