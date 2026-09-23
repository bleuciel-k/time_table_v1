"""Flet 진입점: 컨트롤러를 열고 화면을 조립한다."""

import os

import flet as ft

from app.controller import AppController, SyncManager
from app.sample import sample_data
from app.storage import Storage
from app.sync import Auth, CloudStore
from app.ui.actions import Actions
from app.ui.grid import build_grid


def build_sync(page: ft.Page, controller: AppController, render) -> SyncManager | None:
    """config.py가 있으면 동기화를 준비한다 (F7). 없으면 로컬 전용으로 동작한다 (P3)."""
    try:
        import config
    except ImportError:
        return None
    api_key = getattr(config, "FIREBASE_API_KEY", "")
    database_url = getattr(config, "DATABASE_URL", "")
    if not api_key or not database_url:
        return None

    def on_update(changed: bool) -> None:
        if changed:
            render()  # 원격 변경을 받아 로컬이 바뀜

    auth = Auth(api_key)
    return SyncManager(controller, auth, CloudStore(auth, database_url), on_update=on_update)


def main(page: ft.Page) -> None:
    page.title = "시간표"
    seed = sample_data if os.getenv("TIMETABLE_SAMPLE") == "1" else None
    controller, warnings = AppController.open(Storage(), seed=seed)
    workspace = controller.workspace

    title = ft.Text(weight=ft.FontWeight.BOLD)
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

    sync = build_sync(page, controller, render)
    actions = Actions(page, controller, render, picker=ft.FilePicker(), sync=sync)
    page.appbar = ft.AppBar(
        title=ft.Container(
            ft.Row([title, ft.Icon(ft.Icons.ARROW_DROP_DOWN)], tight=True, spacing=0),
            on_click=None if controller.read_only else (lambda e: actions.open_timetables()),
            ink=not controller.read_only,
            padding=ft.Padding.symmetric(horizontal=8, vertical=4),
            border_radius=ft.BorderRadius.all(8),
        ),
        actions=None if controller.read_only else [actions.timetable_menu()],
    )
    page.add(ft.SafeArea(body, expand=True))
    render()
    if sync is not None:
        sync.start()
        page.on_close = lambda e: sync.stop()
    if warnings:
        page.show_dialog(ft.SnackBar(ft.Text("\n".join(warnings))))


if __name__ == "__main__":
    ft.run(main)
