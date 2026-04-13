"""Tasks management screen — list, navigate, add/edit/done/delete Google Tasks."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

from ..services.gtasks import Task

DATE_FORMAT = "%Y-%m-%d"


class TaskEditModal(ModalScreen[dict[str, Any] | None]):
    """Modal for creating or editing a Google Task.

    Returns {title, notes, due} on save (due may be None) or None if cancelled.
    Pre-fills from `task` when editing.
    """

    DEFAULT_CSS = """
    TaskEditModal {
        align: center middle;
    }
    TaskEditModal #dialog {
        width: 60;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: round $primary;
    }
    TaskEditModal Static.title {
        text-style: bold;
        color: $accent;
        padding-bottom: 1;
    }
    TaskEditModal Static.label {
        color: $text-muted;
        padding-top: 1;
    }
    TaskEditModal Static.error {
        color: $error;
        padding-top: 1;
    }
    TaskEditModal #buttons {
        height: 3;
        align: right middle;
        padding-top: 1;
    }
    TaskEditModal Button {
        margin-left: 1;
    }
    """

    BINDINGS = [Binding("escape", "cancel", show=False)]

    def __init__(self, task: Task | None = None) -> None:
        super().__init__()
        self.task = task

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static("Edit task" if self.task else "New task", classes="title")
            yield Static("Title", classes="label")
            yield Input(placeholder="What needs doing?", id="title")
            yield Static("Notes (optional)", classes="label")
            yield Input(placeholder="Extra context", id="notes")
            yield Static(f"Due (optional, {DATE_FORMAT})", classes="label")
            yield Input(placeholder="2026-04-15", id="due")
            yield Static("", id="error", classes="error")
            with Horizontal(id="buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Save", id="save", variant="primary")

    def on_mount(self) -> None:
        title_input = self.query_one("#title", Input)
        notes_input = self.query_one("#notes", Input)
        due_input = self.query_one("#due", Input)
        if self.task is not None:
            title_input.value = self.task.title
            notes_input.value = self.task.notes
            if self.task.due is not None:
                due_input.value = self.task.due.astimezone().strftime(DATE_FORMAT)
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
        self._submit()

    def _submit(self) -> None:
        title = self.query_one("#title", Input).value.strip()
        notes = self.query_one("#notes", Input).value.strip()
        due_str = self.query_one("#due", Input).value.strip()
        error = self.query_one("#error", Static)

        if not title:
            error.update("Title is required.")
            return
        due: datetime | None = None
        if due_str:
            try:
                due = datetime.strptime(due_str, DATE_FORMAT).astimezone()
            except ValueError:
                error.update(f"Due must be {DATE_FORMAT}, got: {due_str!r}")
                return

        self.dismiss({"title": title, "notes": notes, "due": due})


class TasksScreen(ModalScreen[None]):
    """Full task management screen — list + selection + CRUD bindings.

    Owns its own copy of `tasks` and an internal `selected_index`. Calls into
    callbacks supplied by the parent app to actually mutate Google Tasks.
    """

    DEFAULT_CSS = """
    TasksScreen {
        align: center middle;
    }
    TasksScreen #panel {
        width: 70%;
        height: 80%;
        background: $surface;
        border: round $primary;
        padding: 1 2;
    }
    TasksScreen #panel-title {
        text-style: bold;
        color: $accent;
        padding-bottom: 1;
    }
    TasksScreen #task-list {
        height: 1fr;
        overflow-y: auto;
    }
    TasksScreen .task {
        padding: 0 1;
    }
    TasksScreen .selected {
        background: $boost;
    }
    TasksScreen .due {
        color: $warning;
    }
    TasksScreen .empty {
        color: $text-muted;
        text-style: italic;
    }
    TasksScreen #help {
        color: $text-muted;
        padding-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("a", "add", "Add"),
        Binding("e", "edit", "Edit"),
        Binding("d", "complete", "Done"),
        Binding("shift+d", "delete", "Delete"),
        Binding("up", "select_prev", show=False, priority=True),
        Binding("down", "select_next", show=False, priority=True),
        Binding("k", "select_prev", show=False),
        Binding("j", "select_next", show=False),
    ]

    tasks: reactive[list[Task]] = reactive(list)
    selected_index: reactive[int] = reactive(0)

    def __init__(
        self,
        tasks: list[Task],
        on_add,
        on_edit,
        on_complete,
        on_delete,
    ) -> None:
        super().__init__()
        self._initial_tasks = tasks
        self._on_add = on_add
        self._on_edit = on_edit
        self._on_complete = on_complete
        self._on_delete = on_delete

    def compose(self) -> ComposeResult:
        with Vertical(id="panel"):
            yield Static("📋 TASKS", id="panel-title")
            yield Vertical(id="task-list")
            yield Static(
                "↑/↓ select  ·  a add  ·  e edit  ·  d done  ·  D delete  ·  Esc close",
                id="help",
            )

    def on_mount(self) -> None:
        self.tasks = self._initial_tasks
        self._render()

    def watch_tasks(self, _old: list[Task], _new: list[Task]) -> None:
        self._render()

    def watch_selected_index(self, _old: int, _new: int) -> None:
        self._render()

    def _render(self) -> None:
        try:
            container = self.query_one("#task-list", Vertical)
        except Exception:
            return
        container.remove_children()
        if not self.tasks:
            container.mount(
                Static("No open tasks. Press 'a' to create one.", classes="empty")
            )
            return
        sel = max(0, min(self.selected_index, len(self.tasks) - 1))
        for i, t in enumerate(self.tasks):
            due_str = (
                f"  ⏰ {t.due.astimezone().strftime('%b %d')}"
                if t.due is not None
                else ""
            )
            line = f"{i + 1:>2}. {t.title}{due_str}"
            classes = "task"
            if i == sel:
                classes += " selected"
            if t.due is not None:
                classes += " due"
            container.mount(Static(line, classes=classes))

    def _selected(self) -> Task | None:
        if not self.tasks:
            return None
        idx = max(0, min(self.selected_index, len(self.tasks) - 1))
        return self.tasks[idx]

    def action_close(self) -> None:
        self.dismiss(None)

    def action_select_prev(self) -> None:
        self.selected_index = max(0, self.selected_index - 1)

    def action_select_next(self) -> None:
        if self.tasks:
            self.selected_index = min(len(self.tasks) - 1, self.selected_index + 1)

    def action_add(self) -> None:
        self._on_add(self)

    def action_edit(self) -> None:
        target = self._selected()
        if target is None:
            return
        self._on_edit(self, target)

    def action_complete(self) -> None:
        target = self._selected()
        if target is None:
            return
        self._on_complete(self, target)

    def action_delete(self) -> None:
        target = self._selected()
        if target is None:
            return
        self._on_delete(self, target)
