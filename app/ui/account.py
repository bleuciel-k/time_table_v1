"""계정 시트: 로그인·로그아웃·수동 동기화 (F7). 판단과 네트워크는 SyncManager가 한다 (P5)."""

from datetime import datetime, timezone
from typing import Callable

import flet as ft

from app import design as d
from app.controller import ActionResult, SyncManager, SyncStatus
from app.sync import SyncError
from app.ui import theme as t

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
    email = t.text_field("이메일", autofocus=True, keyboard_type=ft.KeyboardType.EMAIL)
    password = t.text_field("비밀번호", password=True, can_reveal_password=True)
    error = t.text("", d.BODY_MD, color=d.DANGER, visible=False)
    spinner = ft.ProgressRing(width=16, height=16, stroke_width=2, color=d.INK, visible=False)

    def busy(value: bool) -> None:
        spinner.visible = value
        email.disabled = password.disabled = value
        for button in dialog.actions:
            button.disabled = value
        page.update()

    def cancel(e: ft.Event[ft.OutlinedButton]) -> None:
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

    dialog = t.dialog(
        "로그인",
        ft.Column([email, password, error], tight=True, spacing=d.SPACE_SM, width=320),
        [spinner, t.secondary_button("취소", cancel), t.primary_button("로그인", submit)],
    )
    page.show_dialog(dialog)


def _open_account_sheet(page: ft.Page, manager: SyncManager, show_result: ShowResult) -> None:
    status = manager.status

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

    sheet = t.menu_sheet(
        "계정",
        [
            t.menu_item(
                ft.Icons.ACCOUNT_CIRCLE,
                status.email,
                None,
                subtitle=sync_summary(status, manager.controller.dirty),
            ),
            t.divider(),
            t.menu_item(ft.Icons.SYNC, "지금 동기화", lambda e: sync_now()),
            t.menu_item(ft.Icons.LOGOUT, "로그아웃", lambda e: sign_out()),
        ],
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
