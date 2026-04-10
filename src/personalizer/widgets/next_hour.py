"""Next-hour calendar events widget."""

from __future__ import annotations

from datetime import datetime, timezone

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from ..services.gcal import Event, filter_next_hour


class NextHourWidget(Widget):
    """Lists up to 5 events that fall within the next 60 minutes."""

    DEFAULT_CSS = """
    NextHourWidget {
        border: round $primary;
        padding: 1 2;
    }
    NextHourWidget .empty {
        color: $text-muted;
        text-style: italic;
    }
    NextHourWidget .event {
        padding: 0 1;
    }
    NextHourWidget .active {
        background: $accent 30%;
        text-style: bold;
        color: $accent;
    }
    """

    events: reactive[list[Event]] = reactive(list, layout=True)

    def __init__(self, lookahead_minutes: int = 60, **kwargs) -> None:
        super().__init__(**kwargs)
        self.lookahead_minutes = lookahead_minutes
        self.border_title = "🧠 NEXT HOUR"

    def compose(self) -> ComposeResult:
        with Vertical(id="event-list"):
            yield Static("Loading…", classes="empty")

    def watch_events(self, events: list[Event]) -> None:
        self._render(events)

    def _render(self, events: list[Event]) -> None:
        container = self.query_one("#event-list", Vertical)
        container.remove_children()
        now = datetime.now(timezone.utc)
        upcoming = filter_next_hour(events, now, self.lookahead_minutes, limit=5)
        if not upcoming:
            container.mount(Static("Nothing in the next hour.", classes="empty"))
            return
        for evt in upcoming:
            local_start = evt.start.astimezone()
            time_str = local_start.strftime("%I:%M %p").lstrip("0")
            arrow = "→" if evt.is_active(now) else " "
            line = f"{arrow} {time_str}  {evt.summary}"
            classes = "event active" if evt.is_active(now) else "event"
            container.mount(Static(line, classes=classes))
