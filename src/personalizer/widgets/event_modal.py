"""Modal screens: event create/edit, delete confirmation, and start-soon reminder."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

from ..services.gcal import Event

REMINDER_AUTO_DISMISS_SECONDS = 300  # 5 minutes

DATE_FORMAT = "%Y-%m-%d %H:%M"


def _round_to_next_half_hour(dt: datetime) -> datetime:
    minute = (dt.minute // 30 + 1) * 30
    if minute == 60:
        return dt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return dt.replace(minute=minute, second=0, microsecond=0)


class EventEditModal(ModalScreen[dict[str, Any] | None]):
    """Modal for creating or editing a calendar event.

    Returns a dict {summary, start, end} on save, or None if cancelled.
    Pre-fills from `event` when editing; uses sensible defaults when creating.
    """

    DEFAULT_CSS = """
    EventEditModal {
        align: center middle;
    }
    EventEditModal #dialog {
        width: 60;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: round $primary;
    }
    EventEditModal Static.title {
        text-style: bold;
        color: $accent;
        padding-bottom: 1;
    }
    EventEditModal Static.label {
        color: $text-muted;
        padding-top: 1;
    }
    EventEditModal Input {
        margin-bottom: 0;
    }
    EventEditModal Static.error {
        color: $error;
        padding-top: 1;
    }
    EventEditModal #buttons {
        height: 3;
        align: right middle;
        padding-top: 1;
    }
    EventEditModal Button {
        margin-left: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", show=False),
    ]

    def __init__(self, event: Event | None = None) -> None:
        super().__init__()
        self.event = event

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(
                "Edit event" if self.event else "New event", classes="title"
            )
            yield Static("Title", classes="label")
            yield Input(placeholder="Meeting title", id="title")
            yield Static(f"Start ({DATE_FORMAT})", classes="label")
            yield Input(placeholder="2026-04-11 14:30", id="start")
            yield Static("Duration (minutes)", classes="label")
            yield Input(placeholder="30", id="duration")
            yield Static("", id="error", classes="error")
            with Horizontal(id="buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Save", id="save", variant="primary")

    def on_mount(self) -> None:
        title_input = self.query_one("#title", Input)
        start_input = self.query_one("#start", Input)
        dur_input = self.query_one("#duration", Input)
        if self.event is not None:
            title_input.value = self.event.summary
            start_input.value = self.event.start.astimezone().strftime(DATE_FORMAT)
            dur_min = max(
                1, int((self.event.end - self.event.start).total_seconds() // 60)
            )
            dur_input.value = str(dur_min)
        else:
            default_start = _round_to_next_half_hour(datetime.now())
            start_input.value = default_start.strftime(DATE_FORMAT)
            dur_input.value = "30"
        title_input.focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        if event.button.id == "save":
            self._submit()

    def on_input_submitted(self, _event: Input.Submitted) -> None:
        # Allow Enter from any input field to submit.
        self._submit()

    def _submit(self) -> None:
        title = self.query_one("#title", Input).value.strip()
        start_str = self.query_one("#start", Input).value.strip()
        dur_str = self.query_one("#duration", Input).value.strip()
        error = self.query_one("#error", Static)

        if not title:
            error.update("Title is required.")
            return
        try:
            start = datetime.strptime(start_str, DATE_FORMAT).astimezone()
        except ValueError:
            error.update(f"Start must be {DATE_FORMAT}, got: {start_str!r}")
            return
        try:
            duration_min = int(dur_str)
            if duration_min <= 0:
                raise ValueError("must be positive")
        except ValueError:
            error.update(f"Duration must be a positive integer, got: {dur_str!r}")
            return

        end = start + timedelta(minutes=duration_min)
        self.dismiss({"summary": title, "start": start, "end": end})


class ConfirmModal(ModalScreen[bool]):
    """Yes/No confirmation dialog."""

    DEFAULT_CSS = """
    ConfirmModal {
        align: center middle;
    }
    ConfirmModal #dialog {
        width: 50;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: round $error;
    }
    ConfirmModal Static {
        padding-bottom: 1;
    }
    ConfirmModal #buttons {
        height: 3;
        align: right middle;
    }
    ConfirmModal Button {
        margin-left: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", show=False),
        Binding("y", "confirm", show=False),
        Binding("n", "cancel", show=False),
    ]

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(self.message)
            with Horizontal(id="buttons"):
                yield Button("No", id="no")
                yield Button("Yes", id="yes", variant="error")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")


class EventReminderModal(ModalScreen[None]):
    """Compact 'event starts soon' popup. Auto-dismisses after 5 minutes."""

    DEFAULT_CSS = """
    EventReminderModal {
        align: center middle;
    }
    EventReminderModal #reminder-dialog {
        width: 56;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: round $warning;
    }
    EventReminderModal Static.title {
        color: $warning;
        text-style: bold;
        padding-bottom: 1;
    }
    EventReminderModal Static.event-title {
        color: $accent;
        text-style: bold;
    }
    EventReminderModal Static.event-time {
        color: $text;
        padding-top: 1;
    }
    EventReminderModal Static.event-countdown {
        color: $warning;
        text-style: bold;
        padding-top: 1;
    }
    EventReminderModal #buttons {
        height: 3;
        align: right middle;
        padding-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "close", show=False),
        Binding("enter", "close", show=False),
    ]

    def __init__(self, event: Event) -> None:
        super().__init__()
        self.event = event
        self._timer = None  # type: ignore[var-annotated]

    def compose(self) -> ComposeResult:
        local_start = self.event.start.astimezone()
        now = datetime.now(timezone.utc)
        minutes_until = max(
            0, int((self.event.start - now).total_seconds() // 60)
        )
        minutes_label = "minute" if minutes_until == 1 else "minutes"
        with Vertical(id="reminder-dialog"):
            yield Static("⏰  COMING UP", classes="title")
            yield Static(self.event.summary, classes="event-title")
            yield Static(
                f"Starts at {local_start.strftime('%I:%M %p').lstrip('0')}",
                classes="event-time",
            )
            yield Static(
                f"In {minutes_until} {minutes_label}", classes="event-countdown"
            )
            with Horizontal(id="buttons"):
                yield Button("Dismiss", id="dismiss", variant="primary")

    def on_mount(self) -> None:
        # Auto-dismiss after 5 minutes; user can also press Esc/Enter or click.
        self._timer = self.set_timer(
            REMINDER_AUTO_DISMISS_SECONDS, self.action_close
        )

    def action_close(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        try:
            self.dismiss()
        except Exception:  # noqa: BLE001
            # Already dismissed (timer fired after manual close); ignore.
            pass

    def on_button_pressed(self, _event: Button.Pressed) -> None:
        self.action_close()
