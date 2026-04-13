"""Root Textual application — composes the dashboard grid and owns shared timers."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Footer, Static

from .config import AppConfig, Secrets, load_config, load_secrets
from .logging_setup import get_logger, setup_logging
from .services import gcal, gtasks
from .services.gcal import Event
from .services.gtasks import Task
from .widgets.clock import ClockWidget
from .widgets.event_modal import ConfirmModal, EventEditModal, EventReminderModal
from .widgets.tasks_screen import TaskEditModal, TasksScreen
from .widgets.next_hour import (
    VIEW_DAY,
    VIEW_HOUR,
    VIEW_LABELS,
    VIEW_WEEK,
    NextHourWidget,
)
from .widgets.progress import ProgressWidget
from .widgets.reminder import ReminderWidget
from .widgets.topic import TopicWidget
from .widgets.word import WordWidget

logger = get_logger("app")

MIN_WIDTH = 80
MIN_HEIGHT = 24
CALENDAR_REFRESH_SECONDS = 300
TASKS_REFRESH_SECONDS = 600
REMINDER_CHECK_SECONDS = 30
REMINDER_LEAD_MINUTES = 10


class PersonalizerApp(App):
    """Fullscreen terminal personal dashboard."""

    CSS_PATH = "app.tcss"
    TITLE = "Personalizer"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh_all", "Refresh"),
        Binding("H", "view_hour", "Hour"),
        Binding("T", "view_today", "Day"),
        Binding("W", "view_week", "Week"),
        Binding("a", "add_event", "Add"),
        Binding("e", "edit_event", "Edit"),
        Binding("shift+d", "delete_event", "Delete"),
        Binding("g", "open_tasks", "Tasks"),
        Binding("d", "mark_done", "Done"),
        Binding("x", "mark_cancelled", "Cancel"),
        Binding("v", "cycle_view", show=False),
        Binding("c", "refresh_calendar", "Cal", show=False),
        Binding("t", "refresh_topic", "Topic", show=False),
        Binding("w", "refresh_word", "Word", show=False),
        Binding("1", "select_event(0)", show=False),
        Binding("2", "select_event(1)", show=False),
        Binding("3", "select_event(2)", show=False),
        Binding("4", "select_event(3)", show=False),
        Binding("5", "select_event(4)", show=False),
        # priority=True so the app receives arrow keys even when a focusable
        # child (Footer) would otherwise consume them for tab traversal.
        Binding("up", "select_prev", show=False, priority=True),
        Binding("down", "select_next", show=False, priority=True),
        Binding("k", "select_prev", show=False, priority=True),
        Binding("j", "select_next", show=False, priority=True),
    ]

    calendar_events: reactive[list[Event]] = reactive(list)
    google_tasks: reactive[list[Task]] = reactive(list)

    def __init__(self, config: AppConfig, secrets: Secrets, **kwargs) -> None:
        super().__init__(**kwargs)
        self.config = config
        self.secrets = secrets
        # Event IDs we've already shown a "starts soon" reminder for, so the
        # popup doesn't re-fire on the next 30s tick.
        self._reminded_event_ids: set[str] = set()

    def compose(self) -> ComposeResult:
        left = Vertical(
            NextHourWidget(lookahead_minutes=self.config.calendar.lookahead_minutes),
            ReminderWidget(reminders=self.config.reminders),
            id="left",
        )
        left.border_title = "🧠 NEXT HOUR"
        with Horizontal(id="top"):
            yield left
            with Vertical(id="top-right"):
                with Horizontal(id="clock-row"):
                    yield ClockWidget()
                    yield ProgressWidget()
                yield WordWidget(
                    api_key=self.secrets.openai_api_key,
                    model=self.config.openai.model,
                )
        yield TopicWidget(
            api_key=self.secrets.openai_api_key,
            model=self.config.openai.model,
            experience_level=self.config.openai.experience_level,
            topic_areas=self.config.openai.topic_areas,
        )
        yield Footer()

    def on_mount(self) -> None:
        self._maybe_show_too_small()
        self.action_refresh_calendar()
        self.action_refresh_tasks()
        self.set_interval(CALENDAR_REFRESH_SECONDS, self.action_refresh_calendar)
        self.set_interval(TASKS_REFRESH_SECONDS, self.action_refresh_tasks)
        self.set_interval(REMINDER_CHECK_SECONDS, self._check_upcoming_reminders)

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
        # Re-check immediately after a refetch so a freshly-added event that's
        # already inside the 10-minute window pops a reminder right away.
        self._check_upcoming_reminders()

    def watch_google_tasks(self, tasks: list[Task]) -> None:
        for w in self.query(ReminderWidget):
            w.tasks = tasks

    # ---- actions ----

    def action_refresh_all(self) -> None:
        self.action_refresh_calendar()
        self.action_refresh_tasks()
        self.action_refresh_topic()
        self.action_refresh_word()

    def action_refresh_calendar(self) -> None:
        self.run_worker(self._fetch_calendar(), exclusive=True, group="calendar")

    def action_refresh_tasks(self) -> None:
        self.run_worker(self._fetch_tasks(), exclusive=True, group="tasks")

    async def _fetch_tasks(self) -> None:
        """Best-effort task fetch — failures are logged but not surfaced."""
        try:
            tasks = await asyncio.to_thread(gtasks.fetch_tasks)
        except gcal.CalendarUnavailable as e:
            # Calendar fetch already shows the auth error; don't double-notify.
            logger.warning("tasks fetch skipped: %s", e)
            return
        except gtasks.TasksUnavailable:
            logger.exception("tasks unavailable")
            return
        except Exception:  # noqa: BLE001
            logger.exception("tasks fetch crashed")
            return
        self.google_tasks = tasks

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

    # ---- selection ----

    def action_select_event(self, idx: int) -> None:
        for w in self.query(NextHourWidget):
            w.selected_index = idx

    def action_select_prev(self) -> None:
        for w in self.query(NextHourWidget):
            w.selected_index = max(0, w.selected_index - 1)

    def action_select_next(self) -> None:
        for w in self.query(NextHourWidget):
            w.selected_index = w.selected_index + 1  # widget clamps on render

    # ---- start-soon reminder ----

    def _check_upcoming_reminders(self) -> None:
        """Pop a reminder modal for any event starting within the next 10 min.

        Each event triggers at most once (tracked in self._reminded_event_ids).
        Only one reminder modal is on screen at a time — if one is already
        open, this tick is a no-op.
        """
        if not self.calendar_events:
            return
        # Don't stack reminders on top of each other.
        for screen in self.screen_stack:
            if isinstance(screen, EventReminderModal):
                return

        now = datetime.now(timezone.utc)
        horizon = now + timedelta(minutes=REMINDER_LEAD_MINUTES)

        # Garbage-collect ids whose events have already ended so the set
        # doesn't grow without bound across days.
        live_ids = {e.id for e in self.calendar_events if e.id and e.end > now}
        self._reminded_event_ids &= live_ids

        # Earliest qualifying event wins.
        candidates = sorted(
            (
                e
                for e in self.calendar_events
                if e.id
                and e.id not in self._reminded_event_ids
                and not e.cancelled
                and not e.done
                and not e.is_all_day
                and now < e.start <= horizon
            ),
            key=lambda e: e.start,
        )
        if not candidates:
            return
        target = candidates[0]
        self._reminded_event_ids.add(target.id)
        self.push_screen(EventReminderModal(target))

    # ---- view mode ----

    def _set_view(self, mode: str) -> None:
        for w in self.query(NextHourWidget):
            w.view_mode = mode
        try:
            self.query_one("#left").border_title = VIEW_LABELS[mode]
        except Exception:
            pass

    def action_view_hour(self) -> None:
        self._set_view(VIEW_HOUR)

    def action_view_today(self) -> None:
        self._set_view(VIEW_DAY)

    def action_view_week(self) -> None:
        self._set_view(VIEW_WEEK)

    def action_cycle_view(self) -> None:
        for w in self.query(NextHourWidget):
            w.cycle_view_mode()
        try:
            mode = self.query_one(NextHourWidget).view_mode
            self.query_one("#left").border_title = VIEW_LABELS[mode]
        except Exception:
            pass

    # ---- selection helpers ----

    def _selected_event(self) -> Event | None:
        try:
            return self.query_one(NextHourWidget).selected_event()
        except Exception:
            return None

    def _format_error(self, base: str, exc: Exception) -> str:
        msg = f"{base}: {exc}"
        err = str(exc).lower()
        if "403" in err or "insufficient" in err or "scope" in err:
            msg += "  — re-run `personalizer-setup` to grant write access."
        return msg

    # ---- mark done / cancelled ----

    def action_mark_done(self) -> None:
        self.run_worker(self._mark_selected("done"), exclusive=True, group="mark")

    def action_mark_cancelled(self) -> None:
        self.run_worker(self._mark_selected("cancelled"), exclusive=True, group="mark")

    async def _mark_selected(self, kind: str) -> None:
        target = self._selected_event()
        if target is None:
            self.notify("No event selected.", severity="warning")
            return
        if not target.id:
            self.notify("Event missing ID — cannot update calendar.", severity="error")
            return
        action = gcal.mark_done if kind == "done" else gcal.mark_cancelled
        try:
            await asyncio.to_thread(action, self.config.calendar.id, target.id)
        except gcal.CalendarUnavailable as e:
            logger.exception("mark %s: calendar unavailable", kind)
            self.notify(str(e), severity="error", timeout=10)
            return
        except Exception as e:  # noqa: BLE001
            logger.exception("mark %s failed for event %s", kind, target.id)
            self.notify(self._format_error(f"Mark {kind} failed", e), severity="error", timeout=12)
            return
        self.notify(f"Marked '{target.summary[:40]}' as {kind}.", timeout=4)
        await self._fetch_calendar()

    # ---- CRUD ----

    def action_add_event(self) -> None:
        self.run_worker(self._add_event_flow(), group="crud")

    def action_edit_event(self) -> None:
        self.run_worker(self._edit_event_flow(), group="crud")

    def action_delete_event(self) -> None:
        self.run_worker(self._delete_event_flow(), group="crud")

    async def _add_event_flow(self) -> None:
        result = await self.push_screen_wait(EventEditModal())
        if result is None:
            return
        try:
            await asyncio.to_thread(
                gcal.create_event,
                self.config.calendar.id,
                result["summary"],
                result["start"],
                result["end"],
            )
        except gcal.CalendarUnavailable as e:
            logger.exception("create event: calendar unavailable")
            self.notify(str(e), severity="error", timeout=10)
            return
        except Exception as e:  # noqa: BLE001
            logger.exception("create event failed")
            self.notify(self._format_error("Create failed", e), severity="error", timeout=12)
            return
        self.notify(f"Created '{result['summary'][:40]}'.")
        await self._fetch_calendar()

    async def _edit_event_flow(self) -> None:
        target = self._selected_event()
        if target is None:
            self.notify("No event selected.", severity="warning")
            return
        if not target.id:
            self.notify("Event missing ID — cannot edit.", severity="error")
            return
        result = await self.push_screen_wait(EventEditModal(event=target))
        if result is None:
            return
        try:
            await asyncio.to_thread(
                gcal.update_event,
                self.config.calendar.id,
                target.id,
                result["summary"],
                result["start"],
                result["end"],
            )
        except gcal.CalendarUnavailable as e:
            logger.exception("update event: calendar unavailable")
            self.notify(str(e), severity="error", timeout=10)
            return
        except Exception as e:  # noqa: BLE001
            logger.exception("update event %s failed", target.id)
            self.notify(self._format_error("Update failed", e), severity="error", timeout=12)
            return
        self.notify(f"Updated '{result['summary'][:40]}'.")
        await self._fetch_calendar()

    # ---- Google Tasks CRUD ----

    def action_open_tasks(self) -> None:
        screen = TasksScreen(
            tasks=list(self.google_tasks),
            on_add=self._task_add,
            on_edit=self._task_edit,
            on_complete=self._task_complete,
            on_delete=self._task_delete,
        )
        self.push_screen(screen)

    def _task_add(self, screen: TasksScreen) -> None:
        self.run_worker(self._task_add_flow(screen), group="tasks_crud")

    def _task_edit(self, screen: TasksScreen, task: Task) -> None:
        self.run_worker(self._task_edit_flow(screen, task), group="tasks_crud")

    def _task_complete(self, screen: TasksScreen, task: Task) -> None:
        self.run_worker(self._task_complete_flow(screen, task), group="tasks_crud")

    def _task_delete(self, screen: TasksScreen, task: Task) -> None:
        self.run_worker(self._task_delete_flow(screen, task), group="tasks_crud")

    async def _refresh_screen_tasks(self, screen: TasksScreen) -> None:
        """Refetch tasks and push them into the open TasksScreen."""
        try:
            fresh = await asyncio.to_thread(gtasks.fetch_tasks)
        except Exception:  # noqa: BLE001
            logger.exception("tasks refresh inside screen failed")
            return
        self.google_tasks = fresh
        screen.tasks = fresh

    async def _task_add_flow(self, screen: TasksScreen) -> None:
        result = await self.push_screen_wait(TaskEditModal())
        if result is None:
            return
        try:
            list_id = await asyncio.to_thread(gtasks.default_tasklist_id)
            await asyncio.to_thread(
                gtasks.create_task,
                list_id,
                result["title"],
                result["notes"],
                result["due"],
            )
        except gcal.CalendarUnavailable as e:
            logger.exception("task create: auth")
            self.notify(str(e), severity="error", timeout=10)
            return
        except Exception as e:  # noqa: BLE001
            logger.exception("task create failed")
            self.notify(self._format_error("Add task failed", e), severity="error", timeout=12)
            return
        self.notify(f"Added task '{result['title'][:40]}'.")
        await self._refresh_screen_tasks(screen)

    async def _task_edit_flow(self, screen: TasksScreen, target: Task) -> None:
        result = await self.push_screen_wait(TaskEditModal(task=target))
        if result is None:
            return
        try:
            await asyncio.to_thread(
                gtasks.update_task,
                target.list_id,
                target.id,
                result["title"],
                result["notes"],
                result["due"],
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("task update %s failed", target.id)
            self.notify(self._format_error("Edit task failed", e), severity="error", timeout=12)
            return
        self.notify(f"Updated task '{result['title'][:40]}'.")
        await self._refresh_screen_tasks(screen)

    async def _task_complete_flow(self, screen: TasksScreen, target: Task) -> None:
        try:
            await asyncio.to_thread(
                gtasks.complete_task, target.list_id, target.id
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("task complete %s failed", target.id)
            self.notify(self._format_error("Complete failed", e), severity="error", timeout=12)
            return
        self.notify(f"Completed '{target.title[:40]}'.")
        await self._refresh_screen_tasks(screen)

    async def _task_delete_flow(self, screen: TasksScreen, target: Task) -> None:
        confirmed = await self.push_screen_wait(
            ConfirmModal(f"Delete task '{target.title[:50]}'?")
        )
        if not confirmed:
            return
        try:
            await asyncio.to_thread(
                gtasks.delete_task, target.list_id, target.id
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("task delete %s failed", target.id)
            self.notify(self._format_error("Delete task failed", e), severity="error", timeout=12)
            return
        self.notify(f"Deleted task '{target.title[:40]}'.")
        await self._refresh_screen_tasks(screen)

    async def _delete_event_flow(self) -> None:
        target = self._selected_event()
        if target is None:
            self.notify("No event selected.", severity="warning")
            return
        if not target.id:
            self.notify("Event missing ID — cannot delete.", severity="error")
            return
        confirmed = await self.push_screen_wait(
            ConfirmModal(f"Delete '{target.summary[:50]}'?")
        )
        if not confirmed:
            return
        try:
            await asyncio.to_thread(
                gcal.delete_event, self.config.calendar.id, target.id
            )
        except gcal.CalendarUnavailable as e:
            logger.exception("delete event: calendar unavailable")
            self.notify(str(e), severity="error", timeout=10)
            return
        except Exception as e:  # noqa: BLE001
            logger.exception("delete event %s failed", target.id)
            self.notify(self._format_error("Delete failed", e), severity="error", timeout=12)
            return
        self.notify(f"Deleted '{target.summary[:40]}'.")
        await self._fetch_calendar()


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
