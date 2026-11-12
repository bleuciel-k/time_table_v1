"""QR 코드 공유(내보내기) 및 가져오기 UI 다이얼로그 / 바텀시트."""

from __future__ import annotations

import asyncio
from typing import Callable

import flet as ft

from app import design as d
from app.controller import ActionResult, AppController
from app.model import Settings, Timetable
from app.qr import decode_timetable, encode_timetable, make_qr_base64, make_qr_image
from app.ui.theme import sheet, snack_bar, text


def open_qr_export_dialog(
    page: ft.Page,
    timetable: Timetable,
    settings: Settings,
    show_result: Callable[[ActionResult], None],
    picker: ft.FilePicker | None = None,
    share: ft.Share | None = None,
) -> None:
    """현재 활성 시간표의 QR 코드와 딥링크 URL을 팝업으로 띄운다."""
    url = encode_timetable(timetable, settings)
    qr_b64 = make_qr_base64(url, box_size=7, border=2)

    async def copy_link(e: ft.ControlEvent) -> None:
        try:
            await page.set_clipboard(url)
            page.show_dialog(snack_bar("공유 링크가 클립보드에 복사되었습니다."))
        except Exception:
            page.show_dialog(snack_bar("클립보드 접근이 제한되었습니다. 아래 텍스트를 직접 복사해 주세요."))

    async def save_qr_image(e: ft.ControlEvent) -> None:
        filename = f"timetable_qr_{timetable.name}.png"
        png_bytes = make_qr_image(url, box_size=10, border=3)
        if share is not None:
            try:
                res = await share.share_files(
                    [ft.ShareFile.from_bytes(png_bytes, mime_type="image/png", name=filename)],
                    title=filename,
                )
                if res.status == ft.ShareResultStatus.DISMISSED:
                    return
                if res.status != ft.ShareResultStatus.UNAVAILABLE:
                    page.show_dialog(snack_bar("공유 시트를 열었어요. '이미지 저장'으로 앨범에 저장하세요."))
                    return
            except Exception:
                pass
        if picker is None:
            show_result(ActionResult(False, "이 환경에서는 이미지 저장을 지원하지 않습니다."))
            return
        try:
            path = await picker.save_file(
                dialog_title="QR 이미지 저장",
                file_name=filename,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["png"],
                src_bytes=png_bytes,
            )
            if path:
                page.show_dialog(snack_bar(f"QR 이미지를 저장했습니다: {filename}"))
        except Exception as ex:
            page.show_dialog(snack_bar(f"저장 실패: {ex}"))

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Row(
            [
                ft.Icon(ft.Icons.QR_CODE_2, color=d.INK, size=24),
                text("시간표 QR 공유", d.TITLE_SM, color=d.INK),
            ],
            spacing=d.SPACE_XS,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        content=ft.Container(
            content=ft.Column(
                [
                    text(
                        f"'{timetable.name}' · 수업 {len(timetable.cells)}개",
                        d.CAPTION,
                        color=d.MUTED,
                    ),
                    ft.Container(height=d.SPACE_XS),
                    ft.Container(
                        content=ft.Image(
                            src=qr_b64,
                            width=220,
                            height=220,
                            fit=ft.BoxFit.CONTAIN,
                        ),
                        alignment=ft.Alignment.CENTER,
                        padding=ft.Padding.all(d.SPACE_SM),
                        bgcolor="#FFFFFF",
                        border=ft.Border.all(1, d.HAIRLINE),
                        border_radius=ft.BorderRadius.all(d.RADIUS_MD),
                    ),
                    ft.Container(height=d.SPACE_XS),
                    text(
                        "다른 기기의 카메라로 비추거나\n공유 링크/코드를 복사해 전달하세요.",
                        d.CAPTION,
                        color=d.MUTED,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Container(height=4),
                    ft.TextField(
                        value=url,
                        read_only=True,
                        text_size=11,
                        dense=True,
                        border_color=d.HAIRLINE,
                        border_radius=ft.BorderRadius.all(d.RADIUS_SM),
                    ),
                ],
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            width=280,
        ),
        actions=[
            ft.TextButton(
                "링크 복사",
                icon=ft.Icons.COPY,
                on_click=lambda e: asyncio.create_task(copy_link(e)),
            ),
            ft.TextButton(
                "이미지 저장",
                icon=ft.Icons.DOWNLOAD,
                on_click=lambda e: asyncio.create_task(save_qr_image(e)),
            ),
            ft.FilledButton(
                "닫기",
                on_click=lambda e: page.pop_dialog(),
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.show_dialog(dialog)


def open_qr_import_sheet(
    page: ft.Page,
    controller: AppController,
    show_result: Callable[[ActionResult], None],
    on_imported: Callable[[], None] | None = None,
) -> None:
    """QR 공유 링크나 코드를 붙여넣어 시간표를 추가하는 바텀시트."""
    input_field = ft.TextField(
        label="공유 링크 또는 코드",
        hint_text="https://timetable.app/import#... 링크를 붙여넣으세요",
        multiline=True,
        min_lines=2,
        max_lines=3,
        text_size=13,
        border_radius=ft.BorderRadius.all(d.RADIUS_MD),
        border_color=d.HAIRLINE,
        focused_border_color=d.LINK,
        expand=True,
    )

    preview_title = text("", d.LABEL, color=d.INK)
    preview_desc = text("", d.CAPTION, color=d.MUTED)
    preview_box = ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.CHECK_CIRCLE, color=d.SUCCESS, size=18),
                        preview_title,
                    ],
                    spacing=6,
                ),
                preview_desc,
            ],
            spacing=4,
            tight=True,
        ),
        padding=ft.Padding.all(d.SPACE_SM),
        bgcolor=d.SURFACE_STRONG,
        border_radius=ft.BorderRadius.all(d.RADIUS_MD),
        visible=False,
    )

    error_text = text("", d.CAPTION, color=d.DANGER)
    error_box = ft.Container(content=error_text, visible=False)

    import_button = ft.FilledButton(
        "시간표 가져오기",
        icon=ft.Icons.DOWNLOAD_DONE,
        disabled=True,
    )

    parsed_tt: list[Timetable | None] = [None]

    def validate_content(val: str) -> None:
        raw = val.strip()
        if not raw:
            preview_box.visible = False
            error_box.visible = False
            import_button.disabled = True
            parsed_tt[0] = None
            try:
                page.update()
            except Exception:
                pass
            return

        try:
            tt, _ = decode_timetable(raw)
            parsed_tt[0] = tt
            preview_title.value = f"'{tt.name}' 시간표"
            subjects = {c.subject for c in tt.cells.values() if c.subject}
            preview_desc.value = f"수업 {len(tt.cells)}개 ({', '.join(list(subjects)[:4])}{'...' if len(subjects) > 4 else ''})"
            preview_box.visible = True
            error_box.visible = False
            import_button.disabled = False
        except Exception as ex:
            parsed_tt[0] = None
            preview_box.visible = False
            error_text.value = str(ex)
            error_box.visible = True
            import_button.disabled = True

        try:
            page.update()
        except Exception:
            pass

    input_field.on_change = lambda e: validate_content(e.control.value)

    async def paste_from_clipboard(e: ft.ControlEvent) -> None:
        try:
            clip = await page.get_clipboard()
            if clip:
                input_field.value = clip
                validate_content(clip)
        except Exception:
            pass

    def close() -> None:
        sheet_obj.open = False
        page.update()

    def do_import(e: ft.ControlEvent) -> None:
        tt = parsed_tt[0]
        if tt is None:
            return
        result = controller.import_timetable(tt, switch_to=True)
        close()
        show_result(result)
        if on_imported:
            on_imported()

    import_button.on_click = do_import

    sheet_controls = [
        text(
            "다른 기기의 카메라로 스캔한 링크나 공유 코드를 붙여넣으세요.",
            d.CAPTION,
            color=d.MUTED,
        ),
        ft.Row(
            [
                input_field,
                ft.IconButton(
                    icon=ft.Icons.PASTE,
                    tooltip="클립보드에서 붙여넣기",
                    icon_color=d.LINK,
                    on_click=lambda e: asyncio.create_task(paste_from_clipboard(e)),
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        preview_box,
        error_box,
        ft.Row(
            [
                ft.TextButton(
                    "취소",
                    on_click=lambda e: close(),
                ),
                import_button,
            ],
            alignment=ft.MainAxisAlignment.END,
        ),
    ]

    sheet_obj = sheet("시간표 가져오기", sheet_controls, scrollable=False)
    page.show_dialog(sheet_obj)
