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
    NextHourWidget .upcoming {
        color: $text;
    }
    NextHourWidget .active {
        color: $warning;
        text-style: bold;
    }
    NextHourWidget .done {
        color: $success;
    }
    NextHourWidget .cancelled {
        color: $error;
        text-style: strike;
    }
    NextHourWidget .selected {
        background: $boost;
    }
    """

    events: reactive[list[Event]] = reactive(list, layout=True)
    selected_index: reactive[int] = reactive(0)

    def __init__(self, lookahead_minutes: int = 60, **kwargs) -> None:
        super().__init__(**kwargs)
        self.lookahead_minutes = lookahead_minutes
        self.border_title = "🧠 NEXT HOUR"

    def compose(self) -> ComposeResult:
        with Vertical(id="event-list"):
            yield Static("Loading…", classes="empty")

    def on_mount(self) -> None:
        # Re-render every 30s so events that have ended drop off the list
        # without waiting for the next 5-min calendar refetch.
        self.set_interval(30.0, self._refresh_view)

    def watch_events(self, events: list[Event]) -> None:
        self._render_events(events)

    def watch_selected_index(self, _old: int, _new: int) -> None:
        self._render_events(self.events)

    def _refresh_view(self) -> None:
        self._render_events(self.events)

    def _visible_events(self) -> list[Event]:
        now = datetime.now(timezone.utc)
        return filter_next_hour(self.events, now, self.lookahead_minutes, limit=5)

    def selected_event(self) -> Event | None:
        """Return the currently selected event, or None if the list is empty."""
        upcoming = self._visible_events()
        if not upcoming:
            return None
        idx = max(0, min(self.selected_index, len(upcoming) - 1))
        return upcoming[idx]

    def _render_events(self, events: list[Event]) -> None:
        container = self.query_one("#event-list", Vertical)
        container.remove_children()
        now = datetime.now(timezone.utc)
        upcoming = filter_next_hour(events, now, self.lookahead_minutes, limit=5)
        if not upcoming:
            container.mount(Static("Nothing in the next hour.", classes="empty"))
            return
        sel = max(0, min(self.selected_index, len(upcoming) - 1))
        for i, evt in enumerate(upcoming):
            local_start = evt.start.astimezone()
            time_str = local_start.strftime("%I:%M %p").lstrip("0")
            state = evt.state(now)
            marker = {"active": "→", "done": "✓", "cancelled": "✗"}.get(state, " ")
            # Number prefix so the user can see which key picks which row.
            line = f"{i + 1}.{marker} {time_str}  {evt.summary}"
            classes = f"event {state}"
            if i == sel:
                classes += " selected"
            container.mount(Static(line, classes=classes))
