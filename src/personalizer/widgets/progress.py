"""Today / Week progress percentages widget."""

from __future__ import annotations

from datetime import datetime, timezone

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from ..services.gcal import Event, progress_today, progress_week


def _bucket_class(pct: int) -> str:
    if pct < 40:
        return "progress-low"
    if pct < 70:
        return "progress-mid"
    return "progress-high"


class ProgressWidget(Widget):
    """Shows T: XX% W: XX% based on completed calendar events."""

    DEFAULT_CSS = """
    ProgressWidget {
        border: round $primary;
        padding: 1 2;
        content-align: center middle;
    }
    ProgressWidget Horizontal {
        align: center middle;
    }
    ProgressWidget .label {
        padding: 0 2;
        text-style: bold;
    }
    ProgressWidget .progress-low {
        color: $error;
    }
    ProgressWidget .progress-mid {
        color: $warning;
    }
    ProgressWidget .progress-high {
        color: $success;
    }
    """

    events: reactive[list[Event]] = reactive(list)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.border_title = "📊 PROGRESS"

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Static("T: --%", id="today", classes="label")
            yield Static("W: --%", id="week", classes="label")

    def watch_events(self, events: list[Event]) -> None:
        now = datetime.now(timezone.utc)
        t = progress_today(events, now)
        w = progress_week(events, now)

        today_widget = self.query_one("#today", Static)
        week_widget = self.query_one("#week", Static)

        today_widget.update(f"T: {t}%")
        week_widget.update(f"W: {w}%")

        for cls in ("progress-low", "progress-mid", "progress-high"):
            today_widget.remove_class(cls)
            week_widget.remove_class(cls)
        today_widget.add_class(_bucket_class(t))
        week_widget.add_class(_bucket_class(w))
