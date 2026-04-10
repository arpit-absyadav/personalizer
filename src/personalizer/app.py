"""Root Textual application — composes the dashboard grid and owns shared timers."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widgets import Footer, Static

from .config import AppConfig, Secrets, load_config, load_secrets
from .logging_setup import get_logger, setup_logging
from .services import gcal
from .services.gcal import Event

logger = get_logger("app")
from .widgets.clock import ClockWidget
from .widgets.next_hour import NextHourWidget
from .widgets.progress import ProgressWidget
from .widgets.reminder import ReminderWidget
from .widgets.topic import TopicWidget
from .widgets.word import WordWidget

MIN_WIDTH = 80
MIN_HEIGHT = 24
CALENDAR_REFRESH_SECONDS = 300


class PersonalizerApp(App):
    """Fullscreen terminal personal dashboard."""

    CSS_PATH = "app.tcss"
    TITLE = "Personalizer"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh_all", "Refresh all"),
        Binding("c", "refresh_calendar", "Calendar"),
        Binding("t", "refresh_topic", "Topic"),
        Binding("w", "refresh_word", "Word"),
    ]

    calendar_events: reactive[list[Event]] = reactive(list)

    def __init__(self, config: AppConfig, secrets: Secrets, **kwargs) -> None:
        super().__init__(**kwargs)
        self.config = config
        self.secrets = secrets

    def compose(self) -> ComposeResult:
        yield NextHourWidget(lookahead_minutes=self.config.calendar.lookahead_minutes)
        yield ClockWidget()
        yield ProgressWidget()
        yield ReminderWidget(reminders=self.config.reminders)
        with Vertical(id="bottom"):
            yield TopicWidget(
                api_key=self.secrets.openai_api_key,
                model=self.config.openai.model,
                experience_level=self.config.openai.experience_level,
                topic_areas=self.config.openai.topic_areas,
            )
            yield WordWidget()
        yield Footer()

    def on_mount(self) -> None:
        self._maybe_show_too_small()
        self.action_refresh_calendar()
        self.set_interval(CALENDAR_REFRESH_SECONDS, self.action_refresh_calendar)

    def on_resize(self) -> None:
        self._maybe_show_too_small()

    def _maybe_show_too_small(self) -> None:
        size = self.size
        too_small = size.width < MIN_WIDTH or size.height < MIN_HEIGHT
        try:
            existing = self.query_one("#too-small", Static)
        except Exception:
            existing = None
        if too_small and existing is None:
            self.mount(
                Static(
                    f"Terminal too small ({size.width}x{size.height}). "
                    f"Need at least {MIN_WIDTH}x{MIN_HEIGHT}.",
                    id="too-small",
                )
            )
        elif not too_small and existing is not None:
            existing.remove()

    # ---- watchers ----

    def watch_calendar_events(self, events: list[Event]) -> None:
        for w in self.query(NextHourWidget):
            w.events = events
        for w in self.query(ProgressWidget):
            w.events = events

    # ---- actions ----

    def action_refresh_all(self) -> None:
        self.action_refresh_calendar()
        self.action_refresh_topic()
        self.action_refresh_word()

    def action_refresh_calendar(self) -> None:
        self.run_worker(self._fetch_calendar(), exclusive=True, group="calendar")

    def action_refresh_topic(self) -> None:
        for w in self.query(TopicWidget):
            w.refresh_topic(force=True)

    def action_refresh_word(self) -> None:
        for w in self.query(WordWidget):
            w.refresh_word(force=True)

    async def _fetch_calendar(self) -> None:
        try:
            events = await asyncio.to_thread(
                gcal.fetch_events,
                self.config.calendar.id,
                24,
            )
        except gcal.CalendarUnavailable as e:
            logger.exception("calendar unavailable")
            self.notify(str(e), severity="error", timeout=10)
            return
        except Exception as e:  # noqa: BLE001
            logger.exception("calendar fetch failed")
            self.notify(f"Calendar fetch failed: {e}", severity="error", timeout=10)
            return
        self.calendar_events = events


def make_app() -> PersonalizerApp:
    """Factory used by `textual run --dev personalizer.app:make_app`."""
    setup_logging()
    config = load_config()
    secrets = load_secrets()
    logger.info(
        "starting; openai_key_set=%s calendar_id=%s",
        bool(secrets.openai_api_key),
        config.calendar.id,
    )
    return PersonalizerApp(config=config, secrets=secrets)


def run() -> None:
    make_app().run()
