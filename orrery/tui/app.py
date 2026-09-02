"""The Orrery deck app: rotating orrery on the left, live panels on the right."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Label

from .orrery_widget import OrreryWidget
from .panels import ContextPanel, DriftBoard
from .theme import CSS


class OrreryApp(App):
    CSS = CSS
    TITLE = "Orrery"
    SUB_TITLE = "operator deck"
    BINDINGS = [
        ("q", "quit", "quit"),
        ("r", "refresh", "refresh"),
    ]

    def __init__(self, profile: str | None, context_config: str | None, cwd: str):
        super().__init__()
        self._profile = profile
        self._context_config = context_config
        self._cwd = cwd

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="body"):
            yield OrreryWidget(id="orrery")
            with Vertical(id="right"):
                yield ContextPanel(self._context_config, self._cwd, id="context")
                yield DriftBoard(self._profile, id="drift")
        yield Footer()

    def action_refresh(self) -> None:
        self.query_one(DriftBoard).refresh_board()
