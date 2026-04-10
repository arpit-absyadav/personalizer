"""Live clock widget. Updates every second."""

from __future__ import annotations

from datetime import datetime

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Static


class ClockWidget(Widget):
    """Shows current time and date, refreshing every second."""

    DEFAULT_CSS = """
    ClockWidget {
        border: round $primary;
        padding: 1 2;
        content-align: center middle;
    }
    ClockWidget #time {
        text-style: bold;
        color: $accent;
    }
    ClockWidget #date {
        color: $text-muted;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.border_title = "🕒 CLOCK"

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("", id="time")
            yield Static("", id="date")

    def on_mount(self) -> None:
        self._tick()
        self.set_interval(1.0, self._tick)

    def _tick(self) -> None:
        now = datetime.now()
        self.query_one("#time", Static).update(now.strftime("%I:%M %p").lstrip("0"))
        self.query_one("#date", Static).update(now.strftime("%a, %b %d"))
