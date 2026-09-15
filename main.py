"""Flet 진입점: 저장소에서 데이터를 불러와 화면을 조립한다."""

import logging

import flet as ft

from app.model import Workspace
from app.sample import sample_data
from app.storage import Storage
from app.ui.grid import build_grid


def main(page: ft.Page) -> None:
    page.title = "시간표"
    result = Storage().load()
    for warning in result.warnings:
        logging.warning(warning)
    # T3: 저장된 시간표가 없으면 샘플을 표시만 한다(저장하지 않음). 편집·자동 저장은 T4에서 연결.
    data = result.data if result.data.visible() else sample_data()
    ws = Workspace(data)

    page.appbar = ft.AppBar(title=ft.Text(ws.active.name))
    page.add(ft.SafeArea(build_grid(ws.active, ws.data.settings), expand=True))


if __name__ == "__main__":
    ft.run(main)
