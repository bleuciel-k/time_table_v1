"""Flet 진입점: 컨트롤러를 열고 화면을 조립한다."""

import os

import flet as ft

from app.controller import AppController
from app.sample import sample_data
from app.storage import Storage
from app.ui.actions import Actions
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
        editable = not controller.read_only
        body.content = build_grid(
            workspace.active,
            workspace.data.settings,
            on_cell_click=actions.edit_cell if editable else None,
            on_cell_long_press=actions.open_cell_menu if editable else None,
        )
        page.update()

    actions = Actions(page, controller, render)
    page.appbar = ft.AppBar(
        title=title,
        actions=None if controller.read_only else [actions.timetable_menu()],
    )
    page.add(ft.SafeArea(body, expand=True))
    render()
    if warnings:
        page.show_dialog(ft.SnackBar(ft.Text("\n".join(warnings))))


if __name__ == "__main__":
    ft.run(main)
