# Personalizer — Terminal Personal Dashboard

## Context

You want a fullscreen terminal dashboard ("CLI OS") that surfaces only what matters *right now*: the next hour of calendar events, a live clock, micro progress stats, a rotating reminder, an hourly learning topic, and a daily word. The goal is focus and continuous learning without clutter — a single always-on view you can glance at while working.

This is a greenfield Python project.

## Decisions (locked)

| Area | Choice |
|---|---|
| Language / framework | Python 3.11+ with **Textual** (reactive widgets, async, CSS styling) |
| Tasks source | **Google Calendar API** (read-only scope) |
| Progress meaning | **% of calendar events completed** for today / this ISO week |
| Hourly topic | **OpenAI** `gpt-4o-mini` via async SDK |
| Daily word | **random-word-api.vercel.app** + **dictionaryapi.dev** (both free, no auth) |
| Reminder | Rotates through a list in `config.yaml`, advances every 60s |

## Project structure

```
personalizer/
├── pyproject.toml            # hatchling, pinned deps
├── README.md
├── .env.example              # OPENAI_API_KEY placeholder
├── .gitignore                # .env, token.json, cache/, __pycache__
├── src/personalizer/
│   ├── __init__.py
│   ├── __main__.py           # entrypoint: python -m personalizer
│   ├── app.py                # PersonalizerApp(App) — root, bindings, shared timers
│   ├── app.tcss              # Textual CSS — grid layout, colors, .active state
│   ├── config.py             # pydantic-settings loader (config.yaml + .env)
│   ├── paths.py              # ~/.personalizer resolver, auto-creates dirs
│   ├── widgets/
│   │   ├── next_hour.py      # NextHourWidget — ListView of upcoming events
│   │   ├── clock.py          # ClockWidget — 1s tick
│   │   ├── progress.py       # ProgressWidget — T:/W: percentages
│   │   ├── reminder.py       # ReminderWidget — rotating
│   │   ├── topic.py          # TopicWidget — hourly OpenAI result
│   │   └── word.py           # WordWidget — daily dictionary result
│   ├── services/
│   │   ├── gcal.py           # Google Calendar client + event filter
│   │   ├── openai_topic.py   # async OpenAI call + JSON parse
│   │   ├── dictionary.py     # random-word + definition with retry
│   │   └── cache.py          # JSON cache with TTL helpers
│   └── scripts/
│       └── gcal_setup.py     # one-time OAuth flow (entry: personalizer-setup)
└── tests/
    ├── test_cache.py
    ├── test_progress.py      # date-math edge cases (freezegun)
    └── test_gcal_filter.py   # next-60-min filter logic
```

**Dependencies**: `textual>=0.80`, `httpx`, `google-api-python-client`, `google-auth-oauthlib`, `google-auth-httplib2`, `openai>=1.0`, `pydantic-settings`, `pyyaml`, `python-dateutil`. Dev: `pytest`, `pytest-asyncio`, `freezegun`, `pytest-textual-snapshot`, `textual-dev`.

## Layout (Textual Grid)

`app.tcss` defines `grid-size: 2 3; grid-columns: 2fr 1fr; grid-rows: 2fr 1fr 3fr;`

```
┌──────────────────────────────────────────────┐
│ NEXT HOUR (col 1, row 1)  │ CLOCK   (c2,r1) │
│   → Task 1                │ 10:30 PM        │
│   → Task 2                │ Fri, Apr 10     │
│   → Task 3                │                 │
│───────────────────────────┼─────────────────│
│ T: 70%  W: 52% (c1,r2)    │ 💧 Drink water  │
│───────────────────────────┴─────────────────│
│ 📘 Topic: Event Loop        (row 3, span 2) │
│   Handles async using queue & callbacks…    │
│ 🧠 Word: Ephemeral                          │
│   Lasting a short time                      │
└─────────────────────────────────────────────┘
```

Each section is a custom `Widget` subclass with reactive attributes and a bordered `Static` container using `border_title` for the emoji header.

## Update strategy

Each widget owns its own `set_interval` in `on_mount`:

| Widget | Interval | Source |
|---|---|---|
| ClockWidget | 1s | local `datetime.now()` |
| ReminderWidget | 60s | rotates `config.reminders` index |
| Calendar fetch (shared) | 300s | `app.calendar_events` reactive list — `NextHourWidget` and `ProgressWidget` both `watch_calendar_events` |
| TopicWidget | 3600s | OpenAI, guarded by cache timestamp |
| WordWidget | 3600s tick, but only fires API if cache date != today | dictionary APIs |

All network calls use Textual's `@work` decorator. `httpx.AsyncClient` for HTTP, `openai.AsyncOpenAI` for OpenAI. Google API client is sync — wrap in `asyncio.to_thread` so the 1s clock tick never blocks (this is the most likely freeze bug to introduce).

## Google Calendar integration

- **Scope**: `https://www.googleapis.com/auth/calendar.readonly`
- **Files**:
  - `~/.personalizer/google/credentials.json` — user drops in their OAuth client ("Desktop app" type) from Google Cloud Console
  - `~/.personalizer/google/token.json` — auto-written after first consent
- **First-time flow**: separate `personalizer-setup` console script runs `InstalledAppFlow.from_client_secrets_file(...).run_local_server(port=0)`. Must run BEFORE the TUI — `run_local_server` would fight Textual for the screen.
- **Refresh**: on `RefreshError`, surface a banner "Re-run personalizer-setup" instead of crashing.
- **Query**: `events().list(calendarId='primary', timeMin=now, timeMax=now+24h, singleEvents=True, orderBy='startTime')`
- **Next-hour filter**: `start <= now + 60min and end > now`. Active event: `start <= now < end` → CSS class `.active`.
- **Progress math**: today = events with `end < now` / total events today; week = same logic over ISO week (Mon-Sun via `date.isocalendar()`).

## OpenAI integration

- **Model**: `gpt-4o-mini` (~$0.15/1M input). 24 calls/day ≈ <$0.01/day.
- **Key storage**: `OPENAI_API_KEY` in `~/.personalizer/.env` or shell env, loaded via `pydantic-settings`. Never in `config.yaml`.
- **Prompt**:
  - System: "You are a concise tech educator. Return JSON `{topic, explanation}`. Explanation must be exactly 2 sentences, max 120 chars each."
  - User: "Give me a random computer-science or software-engineering concept to learn about."
  - `response_format={"type": "json_object"}`, `temperature=0.9`
- **Cache**: `~/.personalizer/cache/topic.json` with `{topic, explanation, fetched_at}`. Skip call if `fetched_at` is within the last hour.
- **Failure**: fall back to last cached topic, log to status line.

## Dictionary integration

- **Word**: `https://random-word-api.vercel.app/api?words=1`
- **Definition**: `https://api.dictionaryapi.dev/api/v2/entries/en/{word}` → `meanings[0].definitions[0].definition`, truncate to ~80 chars
- **404 handling**: random-word often returns obscure/non-English words dictionaryapi doesn't know. Retry up to 5 times. Final fallback: a bundled list of ~100 curated words shipped in the package.
- **Cache**: `~/.personalizer/cache/word.json` keyed on `date.today().isoformat()`.

## Config layout

```
~/.personalizer/
├── config.yaml
├── .env                       # OPENAI_API_KEY
├── google/
│   ├── credentials.json       # user-supplied
│   └── token.json             # auto-written
└── cache/
    ├── topic.json
    └── word.json
```

`config.yaml`:
```yaml
reminders:
  - "Drink water"
  - "Stretch"
  - "20-20-20: look 20ft away for 20s"
work_hours:
  start: "09:00"
  end: "18:00"
calendar:
  id: "primary"
  lookahead_minutes: 60
openai:
  model: "gpt-4o-mini"
```

## Color / styling

- `.progress-low { color: $error; }` (<40%), `.progress-mid { color: $warning; }` (40-70%), `.progress-high { color: $success; }` (>70%) — toggled in `ProgressWidget`.
- `ListItem.active { background: $accent 30%; text-style: bold; }` with `→` prefix for the currently-running calendar event.
- All panels use `border: round $primary` with `border_title` for the emoji header.

## Critical files

- `src/personalizer/app.py` — composes the grid, owns shared calendar timer, registers key bindings
- `src/personalizer/app.tcss` — entire layout + colors live here
- `src/personalizer/services/gcal.py` — Google client + filter + progress math
- `src/personalizer/services/openai_topic.py` — prompt + cache
- `src/personalizer/scripts/gcal_setup.py` — must run before the TUI
- `pyproject.toml` — pinned deps + console scripts (`personalizer`, `personalizer-setup`)

## Verification

**Key bindings** (defined on `PersonalizerApp`):
- `r` — refresh all (broadcast message)
- `t` — force topic refetch (bypass cache)
- `w` — force word refetch
- `c` — force calendar refetch
- `q` — quit

**Dev workflow**:
1. `pip install -e ".[dev]"` then `personalizer-setup` to complete Google OAuth
2. `OPENAI_API_KEY=sk-... textual run --dev src/personalizer/app.py` for hot-reload + console
3. `pytest` for unit tests (frozen time via `freezegun`, fixture event lists, cache TTL)
4. `pytest-textual-snapshot` for layout regression
5. `--mock` CLI flag routes all services to fixture files for cold-start dev and CI

**End-to-end smoke test**: launch app → press `c` (calendar populates) → press `t` (new topic) → press `w` (new word) → resize terminal narrower than 80 cols (should show "terminal too small" screen) → wait 1 minute (reminder rotates).

## Open risks

- **Sync google-api-python-client blocking the event loop** — must wrap every call in `asyncio.to_thread`. Forgetting this freezes the 1s clock — most visible bug to watch for.
- **OAuth token refresh** — `RefreshError` surfaces a banner, not a crash. Re-run setup script to recover.
- **Terminal resize below 80x24** — `on_resize` handler shows a fallback screen.
- **Laptop sleep** — `set_interval` misses ticks; on every tick recheck cache freshness so hourly topic catches up after a long sleep.
- **OpenAI / network failure** — fall back to last cached topic, never crash the dashboard.
- **Credential leakage** — `.env`, `token.json`, `credentials.json` must be in `.gitignore` from day one and excluded from the wheel.
- **Dictionary 404 loop** — cap retries at 5, then fall back to bundled curated word list.
