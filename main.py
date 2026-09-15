"""Flet 진입점: 컨트롤러를 열고 화면을 조립한다."""

import os

import flet as ft

from app.controller import AppController
from app.sample import sample_data
from app.storage import Storage
from app.ui.editor import open_cell_editor
from app.ui.grid import build_grid


def main(page: ft.Page) -> None:
    page.title = "시간표"
    seed = sample_data if os.getenv("TIMETABLE_SAMPLE") == "1" else None
    controller, warnings = AppController.open(Storage(), seed=seed)
    workspace = controller.workspace

    title = ft.Text()
    body = ft.Container(expand=True)

    def render() -> None:
        title.value = workspace.active.name
        on_click = None if controller.read_only else open_editor
        body.content = build_grid(workspace.active, workspace.data.settings, on_click)
        page.update()

    def open_editor(key: str) -> None:
        open_cell_editor(page, controller, key, on_saved=render)

    page.appbar = ft.AppBar(title=title)
    page.add(ft.SafeArea(body, expand=True))
    render()
    if warnings:
        page.show_dialog(ft.SnackBar(ft.Text("\n".join(warnings))))


if __name__ == "__main__":
    ft.run(main)
