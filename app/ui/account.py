"""계정 시트: 로그인·로그아웃·수동 동기화 (F7). 판단과 네트워크는 SyncManager가 한다 (P5)."""

from datetime import datetime, timezone
from typing import Callable

import flet as ft

from app.controller import ActionResult, SyncManager, SyncStatus
from app.sync import SyncError

ShowResult = Callable[[ActionResult], None]


def open_account(page: ft.Page, manager: SyncManager | None, show_result: ShowResult) -> None:
    if manager is None:
        show_result(ActionResult(False, "동기화 설정이 없습니다. config.py를 만들어 주세요."))
        return
    if manager.status.signed_in:
        _open_account_sheet(page, manager, show_result)
    else:
        _open_login(page, manager, show_result)


def _open_login(page: ft.Page, manager: SyncManager, show_result: ShowResult) -> None:
    email = ft.TextField(label="이메일", autofocus=True, keyboard_type=ft.KeyboardType.EMAIL)
    password = ft.TextField(label="비밀번호", password=True, can_reveal_password=True)
    error = ft.Text(color=ft.Colors.ERROR, visible=False)
    spinner = ft.ProgressRing(width=16, height=16, visible=False)
    dialog = ft.AlertDialog(
        modal=True,
        title="로그인",
        content=ft.Column([email, password, error], tight=True, spacing=12, width=320),
    )

    def busy(value: bool) -> None:
        spinner.visible = value
        email.disabled = password.disabled = value
        for button in dialog.actions:
            button.disabled = value
        page.update()

    def cancel(e: ft.Event[ft.TextButton]) -> None:
        dialog.open = False
        page.update()

    def submit(e: ft.Event[ft.FilledButton]) -> None:
        error.visible = False
        busy(True)

        def work() -> None:
            try:
                manager.sign_in(email.value or "", password.value or "")
            except SyncError as ex:
                error.value, error.visible = ex.message, True
                busy(False)
                return
            dialog.open = False
            busy(False)
            show_result(ActionResult(False, "로그인했어요. 동기화를 시작합니다."))

        page.run_thread(work)

    dialog.actions = [
        spinner,
        ft.TextButton("취소", on_click=cancel),
        ft.FilledButton("로그인", on_click=submit),
    ]
    page.show_dialog(dialog)


def _open_account_sheet(page: ft.Page, manager: SyncManager, show_result: ShowResult) -> None:
    status = manager.status
    sheet = ft.BottomSheet(ft.Container(), show_drag_handle=True)

    def close() -> None:
        sheet.open = False
        page.update()

    def sync_now() -> None:
        close()
        manager.request()
        show_result(ActionResult(False, "동기화를 요청했어요."))

    def sign_out() -> None:
        close()
        manager.sign_out()
        show_result(ActionResult(False, "로그아웃했어요. 이 기기의 시간표는 그대로 있어요."))

    sheet.content = ft.Container(
        ft.Column(
            [
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.ACCOUNT_CIRCLE),
                    title=status.email,
                    subtitle=sync_summary(status, manager.controller.dirty),
                ),
                ft.Divider(height=1),
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.SYNC), title="지금 동기화", on_click=lambda e: sync_now()
                ),
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.LOGOUT), title="로그아웃", on_click=lambda e: sign_out()
                ),
            ],
            tight=True,
            spacing=0,
        ),
        padding=ft.Padding.only(bottom=16),
    )
    page.show_dialog(sheet)


def sync_summary(status: SyncStatus, dirty: bool) -> str:
    """계정 시트에 보여 줄 한 줄 요약."""
    if status.error is not None:
        return status.error.message
    if status.running:
        return "동기화 중…"
    if status.last_synced_at is None:
        return "아직 동기화하지 않았어요."
    local = status.last_synced_at.astimezone()
    today = datetime.now(timezone.utc).astimezone().date()
    stamp = local.strftime("%H:%M" if local.date() == today else "%m/%d %H:%M")
    return f"{stamp}에 동기화됨" + (" · 올릴 변경 있음" if dirty else "")
