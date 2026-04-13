"""Google Tasks service.

Pulls open (non-completed) tasks across all the user's task lists. Shares
OAuth credentials with the calendar service via gcal.load_credentials, so
one token + one consent flow covers both APIs.

Like gcal, the Google API client is synchronous; callers must wrap
`fetch_tasks` in `asyncio.to_thread` so the Textual event loop never blocks.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from dateutil import parser as dtparser

from .gcal import CalendarUnavailable, load_credentials


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    list_id: str
    notes: str = ""
    due: datetime | None = None
    completed: bool = False


class TasksUnavailable(Exception):
    """Raised when the tasks API call fails for a non-auth reason."""


def _build_tasks_service():
    """Build a Google Tasks API v1 client. Lazy import for the same reason gcal does."""
    from googleapiclient.discovery import build

    return build("tasks", "v1", credentials=load_credentials(), cache_discovery=False)


def _parse_task(raw: dict[str, Any], list_id: str) -> Task | None:
    title = (raw.get("title") or "").strip()
    if not title:
        return None
    due: datetime | None = None
    due_str = raw.get("due")
    if isinstance(due_str, str) and due_str:
        try:
            due = dtparser.isoparse(due_str)
        except (ValueError, TypeError):
            due = None
    return Task(
        id=str(raw.get("id", "")),
        title=title,
        list_id=list_id,
        notes=str(raw.get("notes", "") or ""),
        due=due,
        completed=raw.get("status") == "completed",
    )


def fetch_tasks(max_results_per_list: int = 100) -> list[Task]:
    """Fetch all open tasks from every task list. Synchronous — wrap in to_thread.

    Auth failures bubble up as `CalendarUnavailable` (shared with the calendar
    service); other failures bubble up as `TasksUnavailable`.
    """
    service = _build_tasks_service()
    try:
        lists = (
            service.tasklists()
            .list(maxResults=20)
            .execute()
            .get("items", [])
        )
    except Exception as e:
        raise TasksUnavailable(f"Could not list task lists: {e}") from e

    out: list[Task] = []
    for tl in lists:
        list_id = tl.get("id", "")
        if not list_id:
            continue
        try:
            items = (
                service.tasks()
                .list(
                    tasklist=list_id,
                    showCompleted=False,
                    showHidden=False,
                    maxResults=max_results_per_list,
                )
                .execute()
                .get("items", [])
            )
        except Exception as e:
            raise TasksUnavailable(
                f"Could not list tasks in {list_id}: {e}"
            ) from e
        for item in items:
            parsed = _parse_task(item, list_id)
            if parsed and not parsed.completed:
                out.append(parsed)

    # Sort: due tasks first (earliest due), then undue.
    def _sort_key(t: Task) -> tuple[int, datetime | str]:
        if t.due is not None:
            return (0, t.due)
        return (1, t.title.lower())

    out.sort(key=_sort_key)
    return out


def complete_task(list_id: str, task_id: str) -> None:
    """Mark a task as completed. Synchronous — wrap in to_thread."""
    service = _build_tasks_service()
    service.tasks().patch(
        tasklist=list_id,
        task=task_id,
        body={"status": "completed"},
    ).execute()


def default_tasklist_id() -> str:
    """Return the id of the user's default ('@default') task list."""
    service = _build_tasks_service()
    return str(service.tasklists().get(tasklist="@default").execute().get("id", ""))


def _task_body(title: str, notes: str, due: datetime | None) -> dict[str, Any]:
    body: dict[str, Any] = {"title": title}
    if notes:
        body["notes"] = notes
    if due is not None:
        # Google Tasks API stores due as RFC3339 with date-only precision.
        body["due"] = due.astimezone().replace(microsecond=0).isoformat()
    return body


def create_task(
    list_id: str, title: str, notes: str = "", due: datetime | None = None
) -> str:
    """Create a new task. Returns the new task id. Synchronous — wrap in to_thread."""
    service = _build_tasks_service()
    created = (
        service.tasks()
        .insert(tasklist=list_id, body=_task_body(title, notes, due))
        .execute()
    )
    return str(created.get("id", ""))


def update_task(
    list_id: str,
    task_id: str,
    title: str,
    notes: str = "",
    due: datetime | None = None,
) -> None:
    """Update a task's title/notes/due. Synchronous — wrap in to_thread."""
    service = _build_tasks_service()
    service.tasks().patch(
        tasklist=list_id,
        task=task_id,
        body=_task_body(title, notes, due),
    ).execute()


def delete_task(list_id: str, task_id: str) -> None:
    """Permanently delete a task. Synchronous — wrap in to_thread."""
    service = _build_tasks_service()
    service.tasks().delete(tasklist=list_id, task=task_id).execute()
