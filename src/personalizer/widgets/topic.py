"""Hourly learning topic widget (OpenAI-backed)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Static

from ..logging_setup import get_logger
from ..services import openai_topic

logger = get_logger("topic")


class TopicWidget(Widget):
    """Displays a short concept + 2-line explanation. Refreshes hourly."""

    DEFAULT_CSS = """
    TopicWidget {
        border: round $primary;
        padding: 1 2;
    }
    TopicWidget #topic-name {
        text-style: bold;
        color: $accent;
    }
    TopicWidget #topic-body {
        color: $text;
        padding-top: 1;
    }
    TopicWidget #topic-vocab {
        color: $secondary;
        padding-top: 1;
    }
    TopicWidget .error {
        color: $error;
    }
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        experience_level: str = "senior software engineer with 8+ years of experience",
        topic_areas: list[str] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.api_key = api_key
        self.model = model
        self.experience_level = experience_level
        self.topic_areas = topic_areas or []
        self.border_title = "📘 TOPIC"

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Loading…", id="topic-name")
            yield Static("", id="topic-body")
            yield Static("", id="topic-vocab")

    def on_mount(self) -> None:
        self.refresh_topic()
        # Recheck every 5 minutes; cache TTL inside get_topic prevents API spam.
        self.set_interval(300.0, self.refresh_topic)

    def refresh_topic(self, force: bool = False) -> None:
        self.run_worker(self._fetch(force), exclusive=True, group="topic")

    async def _fetch(self, force: bool) -> None:
        try:
            data = await openai_topic.get_topic(
                self.api_key,
                self.model,
                force=force,
                experience_level=self.experience_level,
                topic_areas=self.topic_areas,
            )
        except openai_topic.TopicUnavailable as e:
            logger.exception("topic fetch failed (force=%s)", force)
            self._show_error(str(e))
            return
        except Exception as e:  # noqa: BLE001
            logger.exception("topic fetch crashed (force=%s)", force)
            self._show_error(f"Unexpected error: {e}")
            return
        self.query_one("#topic-name", Static).update(f"Topic: {data['topic']}")
        body = self.query_one("#topic-body", Static)
        body.update(data["explanation"])
        body.remove_class("error")
        vocab_lines: list[str] = []
        for v in data.get("vocab", []):
            line = f"• [b]{v['word']}[/b] — {v['meaning']}"
            example = v.get("example", "")
            if example:
                line += f"\n  e.g. [i]{example}[/i]"
            vocab_lines.append(line)
        vocab_text = "📖 Vocab:\n" + "\n".join(vocab_lines) if vocab_lines else ""
        self.query_one("#topic-vocab", Static).update(vocab_text)

    def _show_error(self, msg: str) -> None:
        self.query_one("#topic-name", Static).update("Topic: (unavailable)")
        body = self.query_one("#topic-body", Static)
        body.update(msg)
        body.add_class("error")
