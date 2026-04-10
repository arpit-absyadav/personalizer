# Personalizer

A minimalist, fullscreen terminal dashboard for focus and continuous learning. Shows the next hour of calendar events, a live clock, micro progress stats, a rotating reminder, an hourly learning topic (via OpenAI), and a daily word.

## Install

```bash
pip install -e ".[dev]"
```

## First-time setup

1. Create an OAuth client ("Desktop app") in Google Cloud Console with the `https://www.googleapis.com/auth/calendar.readonly` scope.
2. Save the downloaded JSON as `~/.personalizer/google/credentials.json`.
3. Put your OpenAI key in `~/.personalizer/.env`:
   ```
   OPENAI_API_KEY=sk-...
   ```
4. Run the one-time OAuth flow:
   ```bash
   personalizer-setup
   ```
   This opens your browser, completes consent, and writes `~/.personalizer/google/token.json`.

## Run

```bash
personalizer
```

Or for development with hot-reload:

```bash
textual run --dev src/personalizer/app.py
```

## Key bindings

| Key | Action |
|---|---|
| `r` | Refresh everything |
| `c` | Force calendar refetch |
| `t` | Force topic refetch (bypass cache) |
| `w` | Force word refetch |
| `q` | Quit |

## Config

Edit `~/.personalizer/config.yaml`. A default is created on first run.

## See also

`PLAN.md` for the full architecture.
