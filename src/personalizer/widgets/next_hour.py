"""Calendar events widget — next-hour, today, or this-week view."""

from __future__ import annotations

from datetime import datetime, timezone

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from ..services.gcal import Event, filter_next_hour, filter_today, filter_week

VIEW_HOUR = "hour"
VIEW_DAY = "day"
VIEW_WEEK = "week"
VIEW_MODES = (VIEW_HOUR, VIEW_DAY, VIEW_WEEK)
VIEW_LABELS = {
    VIEW_HOUR: "🧠 NEXT HOUR",
    VIEW_DAY: "📅 TODAY",
    VIEW_WEEK: "📆 THIS WEEK",
}
VIEW_LIMITS = {VIEW_HOUR: 5, VIEW_DAY: 20, VIEW_WEEK: 50}


class NextHourWidget(Widget):
    """Lists calendar events in one of three view modes (hour/day/week)."""

    DEFAULT_CSS = """
    NextHourWidget {
        border: round $primary;
        padding: 1 2;
    }
    NextHourWidget #event-list {
        overflow-y: auto;
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
    view_mode: reactive[str] = reactive(VIEW_HOUR)

    def __init__(self, lookahead_minutes: int = 60, **kwargs) -> None:
        super().__init__(**kwargs)
        self.lookahead_minutes = lookahead_minutes
        self.border_title = VIEW_LABELS[VIEW_HOUR]

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

    def watch_view_mode(self, _old: str, new: str) -> None:
        self.border_title = VIEW_LABELS.get(new, VIEW_LABELS[VIEW_HOUR])
        # Reset selection to top when changing modes — cleaner UX than
        # leaving it pointing at row N of a different list.
        self.selected_index = 0
        self._render_events(self.events)

    def cycle_view_mode(self) -> None:
        idx = (VIEW_MODES.index(self.view_mode) + 1) % len(VIEW_MODES)
        self.view_mode = VIEW_MODES[idx]

    def _refresh_view(self) -> None:
        self._render_events(self.events)

    def _visible_events(self) -> list[Event]:
        now = datetime.now(timezone.utc)
        if self.view_mode == VIEW_DAY:
            return filter_today(self.events, now, limit=VIEW_LIMITS[VIEW_DAY])
        if self.view_mode == VIEW_WEEK:
            return filter_week(self.events, now, limit=VIEW_LIMITS[VIEW_WEEK])
        return filter_next_hour(
            self.events, now, self.lookahead_minutes, limit=VIEW_LIMITS[VIEW_HOUR]
        )

    def selected_event(self) -> Event | None:
        """Return the currently selected event, or None if the list is empty."""
        visible = self._visible_events()
        if not visible:
            return None
        idx = max(0, min(self.selected_index, len(visible) - 1))
        return visible[idx]

    def _render_events(self, _events: list[Event]) -> None:
        container = self.query_one("#event-list", Vertical)
        container.remove_children()
        now = datetime.now(timezone.utc)
        visible = self._visible_events()
        if not visible:
            container.mount(
                Static(
                    {
                        VIEW_HOUR: "Nothing in the next hour.",
                        VIEW_DAY: "Nothing scheduled today.",
                        VIEW_WEEK: "Nothing scheduled this week.",
                    }.get(self.view_mode, "Nothing to show."),
                    classes="empty",
                )
            )
            return
        sel = max(0, min(self.selected_index, len(visible) - 1))
        for i, evt in enumerate(visible):
            local_start = evt.start.astimezone()
            if self.view_mode == VIEW_WEEK:
                time_str = local_start.strftime("%a %I:%M%p").lstrip("0")
            else:
                time_str = local_start.strftime("%I:%M %p").lstrip("0")
            state = evt.state(now)
            marker = {"active": "→", "done": "✓", "cancelled": "✗"}.get(state, " ")
            line = f"{i + 1:>2}.{marker} {time_str}  {evt.summary}"
            classes = f"event {state}"
            if i == sel:
                classes += " selected"
            container.mount(Static(line, classes=classes))
