"""Rotating reminder widget — cycles through static reminders + open Google Tasks."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from ..services.gtasks import Task

REMINDER_ICON = "💧"
TASK_ICON = "📋"


class ReminderWidget(Widget):
    """Cycles through static reminders + open Google Tasks once per minute."""

    DEFAULT_CSS = """
    ReminderWidget {
        border: round $primary;
        padding: 1 2;
        content-align: center middle;
    }
    ReminderWidget #reminder-text {
        text-style: bold;
        color: $secondary;
    }
    """

    tasks: reactive[list[Task]] = reactive(list)

    def __init__(self, reminders: list[str], **kwargs) -> None:
        super().__init__(**kwargs)
        self.reminders = reminders or ["Take a break"]
        self._index = 0
        self.border_title = "🔔 REMINDER"

    def compose(self) -> ComposeResult:
        yield Static("", id="reminder-text")

    def on_mount(self) -> None:
        self._refresh_text()
        self.set_interval(60.0, self._advance)

    def watch_tasks(self, _old: list[Task], _new: list[Task]) -> None:
        # Re-render immediately when tasks list changes (e.g. periodic refresh).
        items = self._items()
        if items and self._index >= len(items):
            self._index = 0
        self._refresh_text()

    def _items(self) -> list[tuple[str, str]]:
        """Combined rotation list of (icon, label) entries."""
        out: list[tuple[str, str]] = [(REMINDER_ICON, r) for r in self.reminders]
        for t in self.tasks:
            out.append((TASK_ICON, t.title))
        return out

    def _advance(self) -> None:
        items = self._items()
        if not items:
            return
        self._index = (self._index + 1) % len(items)
        self._refresh_text()

    def _refresh_text(self) -> None:
        items = self._items()
        widget = self.query_one("#reminder-text", Static)
        if not items:
            widget.update("")
            return
        idx = self._index % len(items)
        icon, text = items[idx]
        widget.update(f"{icon} {text}")
