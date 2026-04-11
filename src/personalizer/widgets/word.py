"""Daily word widget (dictionary-backed)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Static

from ..logging_setup import get_logger
from ..services import dictionary

logger = get_logger("word")


class WordWidget(Widget):
    """Shows one word + meaning per day, refreshing on date change."""

    DEFAULT_CSS = """
    WordWidget {
        border: round $primary;
        padding: 1 2;
    }
    WordWidget #word-name {
        text-style: bold;
        color: $accent;
    }
    WordWidget #word-body {
        color: $text;
        padding-top: 1;
    }
    WordWidget #word-example {
        color: $text-muted;
        text-style: italic;
        padding-top: 1;
    }
    WordWidget .error {
        color: $error;
    }
    """

    def __init__(
        self,
        api_key: str = "",
        model: str = "gpt-4o-mini",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.api_key = api_key
        self.model = model
        self.border_title = "🧠 WORD"

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Loading…", id="word-name")
            yield Static("", id="word-body")
            yield Static("", id="word-example")

    def on_mount(self) -> None:
        self.refresh_word()
        # Check every hour; cache.is_today gate keeps API calls to once per day.
        self.set_interval(3600.0, self.refresh_word)

    def refresh_word(self, force: bool = False) -> None:
        self.run_worker(self._fetch(force), exclusive=True, group="word")

    async def _fetch(self, force: bool) -> None:
        try:
            data = await dictionary.get_word(
                force=force,
                openai_api_key=self.api_key,
                openai_model=self.model,
            )
        except dictionary.WordUnavailable as e:
            logger.exception("word fetch failed (force=%s)", force)
            self._show_error(str(e))
            return
        except Exception as e:  # noqa: BLE001
            logger.exception("word fetch crashed (force=%s)", force)
            self._show_error(f"Unexpected error: {e}")
            return
        self.query_one("#word-name", Static).update(f"Word: {data['word'].title()}")
        body = self.query_one("#word-body", Static)
        body.update(data["meaning"])
        body.remove_class("error")
        example = data.get("example", "")
        example_widget = self.query_one("#word-example", Static)
        example_widget.update(f"e.g. {example}" if example else "")

    def _show_error(self, msg: str) -> None:
        self.query_one("#word-name", Static).update("Word: (unavailable)")
        body = self.query_one("#word-body", Static)
        body.update(msg)
        body.add_class("error")
