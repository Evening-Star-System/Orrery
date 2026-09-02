"""Panels that render the engines' output. Read-only calls; no mutation."""

from __future__ import annotations

from rich.table import Table
from rich.text import Text
from textual.widgets import Static

from .theme import EDGE, GOLD, SEV, SLATE


class DriftBoard(Static):
    """Runs a reconciler profile and shows findings colored by severity."""

    def __init__(self, profile_path: str | None, **kwargs):
        super().__init__(**kwargs)
        self._profile = profile_path

    def on_mount(self) -> None:
        self.refresh_board()

    def refresh_board(self) -> None:
        self.update(self._render_board())

    def _render_board(self):
        if not self._profile:
            return Text("no --profile given", style=SLATE)
        try:
            from orrery.reconciler.engine import run_profile

            result = run_profile(self._profile)
        except Exception as exc:  # never let the panel crash the deck
            return Text(f"reconciler error: {exc.__class__.__name__}", style=SEV["FAIL"])

        table = Table(expand=True, border_style=EDGE, title="drift board", title_style=GOLD)
        table.add_column("sev", width=6)
        table.add_column("subject", ratio=2, no_wrap=True)
        table.add_column("detail", ratio=3)
        order = {"FAIL": 0, "DRIFT": 1, "WARN": 2, "INFO": 3, "OK": 4}
        for f in sorted(result.findings, key=lambda f: order.get(f.severity.label, 9)):
            sev = f.severity.label
            table.add_row(
                Text(sev, style=SEV.get(sev, SLATE)),
                Text(f.subject, style=SLATE),
                Text(f.message, style=SEV.get(sev, SLATE)),
            )
        verdict = "CLEAN" if result.clean else "DRIFT DETECTED"
        counts = " ".join(f"{k}={v}" for k, v in result.counts().items() if v)
        foot = Text(f"\n{result.box}: {counts}  ->  ", style=SLATE)
        foot.append(verdict, style=SEV["OK"] if result.clean else SEV["DRIFT"])
        board = Table.grid(expand=True)
        board.add_row(table)
        board.add_row(foot)
        return board


class ContextPanel(Static):
    """Shows the resolved context scope for a working directory."""

    def __init__(self, context_config: str | None, cwd: str, **kwargs):
        super().__init__(**kwargs)
        self._config = context_config
        self._cwd = cwd

    def on_mount(self) -> None:
        self.update(self._render_context())

    def _render_context(self):
        if not self._config:
            return Text("no --context-config given", style=SLATE)
        try:
            from orrery.context import load_config, resolve

            bundle = resolve(self._cwd, load_config(self._config))
        except Exception as exc:
            return Text(f"context error: {exc.__class__.__name__}", style=SEV["FAIL"])

        s = bundle.scope
        where = s.kind if s.kind == "ops" else f"{s.bucket}/{s.project}"
        out = Text()
        out.append("scope: ", style=SLATE)
        out.append(f"{s.kind}  ", style=GOLD)
        out.append(where + "\n", style=SLATE)
        out.append("sources: ", style=SLATE)
        out.append(", ".join(bundle.provenance) + "\n", style=SLATE)
        return out
