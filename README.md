# Personalizer

A minimalist, fullscreen terminal dashboard for focus and continuous learning. Shows the next hour of calendar events, a live clock, micro progress stats, a rotating reminder, an hourly learning topic (via OpenAI), and a daily word.

## Install

Requires **Python 3.11+** (tested on 3.13).

```bash
cd /path/to/personalizer

# Create a virtual environment
python3.13 -m venv .venv

# Activate it (re-run this in every new shell)
source .venv/bin/activate

# Install the package + all runtime + dev dependencies
pip install -e ".[dev]"
```

That single `pip install -e ".[dev]"` reads `pyproject.toml` and pulls in everything: `textual`, `httpx`, `google-api-python-client`, `google-auth-oauthlib`, `openai`, `pydantic-settings`, `pyyaml`, `python-dateutil`, plus dev tools (`pytest`, `textual-dev`, `freezegun`).

For **runtime only** (no test tools), drop `[dev]`:

```bash
pip install -e .
```

Verify the install:

```bash
pytest                # should show 29 passed
personalizer --help   # or just: personalizer
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

**Step 1 — activate the venv** (required in every new shell, otherwise you'll see `personalizer: command not found`):

```bash
cd /path/to/personalizer
source .venv/bin/activate
```

You'll see `(.venv)` in your prompt once activated. From then on, `personalizer`, `personalizer-setup`, `pytest`, and `textual` are all on your PATH for that shell session.

**Step 2 — launch the dashboard:**

```bash
personalizer
```

Or for development with hot-reload (uses the `make_app` factory so config is loaded the same way):

```bash
textual run --dev personalizer.app:make_app
```

> **Note:** `textual run --dev src/personalizer/app.py` will NOT work — Textual loads it as a script, which breaks the relative imports. Always use the `personalizer.app:make_app` form.

### Don't want to activate the venv?

You can call the binaries directly without activating:

```bash
.venv/bin/personalizer
.venv/bin/textual run --dev personalizer.app:make_app
```

### Troubleshooting: `personalizer: command not found`

This means the venv isn't activated (or you're in a different shell). Re-run `source .venv/bin/activate` from the project root, or use the `.venv/bin/personalizer` form above.

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

## macOS notes

These tips apply only on macOS — keep them out of cross-platform setup steps.

### Python via Homebrew

System Python on macOS is usually 3.9, which is too old. Install 3.13 from Homebrew:

```bash
brew install python@3.13
```

The binary lives at `/opt/homebrew/bin/python3.13` (Apple Silicon) or `/usr/local/bin/python3.13` (Intel). Use the full path to create the venv if `python3.13` isn't on your PATH:

```bash
/opt/homebrew/bin/python3.13 -m venv .venv
```

### Terminal colors (256-color warning)

The default macOS Terminal.app is limited to 256 colors and Textual will print a warning at startup. For full truecolor + smoother rendering, use one of:

- **iTerm2** (`brew install --cask iterm2`) — recommended
- **WezTerm** (`brew install --cask wezterm`)
- **Ghostty** (`brew install --cask ghostty`)

Or suppress the warning if you don't care about colors:

```bash
export COLORTERM=truecolor
```

Add that to your `~/.zshrc` to make it permanent.

## See also

`PLAN.md` for the full architecture.
