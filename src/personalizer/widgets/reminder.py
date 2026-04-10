"""Rotating reminder widget."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static


class ReminderWidget(Widget):
    """Cycles through a list of reminders, advancing once per minute."""

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

    def __init__(self, reminders: list[str], **kwargs) -> None:
        super().__init__(**kwargs)
        self.reminders = reminders or ["Take a break"]
        self._index = 0
        self.border_title = "🔔 REMINDER"

    def compose(self) -> ComposeResult:
        yield Static("", id="reminder-text")

    def on_mount(self) -> None:
        self._render()
        self.set_interval(60.0, self._advance)

    def _advance(self) -> None:
        self._index = (self._index + 1) % len(self.reminders)
        self._render()

    def _render(self) -> None:
        text = self.reminders[self._index]
        self.query_one("#reminder-text", Static).update(f"💧 {text}")
