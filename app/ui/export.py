"""이미지 내보내기 시트: 형식·배율 선택, 미리보기, 저장 (F6). 렌더링은 exporter가 한다 (P5)."""

import base64
from dataclasses import replace
from typing import Callable

import flet as ft

from app.controller import ActionResult, AppController
from app.exporter import FORMATS, SCALES, ExportOptions

ShowResult = Callable[[ActionResult], None]
PREVIEW_HEIGHT = 260


def _preview_src(controller: AppController, options: ExportOptions) -> tuple[str, str]:
    """미리보기용 data URI와 저장될 파일명. 미리보기는 항상 1x로 그린다."""
    image, filename = controller.export_image(replace(options, scale=1))
    media = "jpeg" if options.fmt == "jpg" else "png"
    return f"data:image/{media};base64,{base64.b64encode(image).decode()}", filename


def open_export_sheet(
    page: ft.Page, controller: AppController, picker: ft.FilePicker, show_result: ShowResult
) -> None:
    options = ExportOptions()
    sheet = ft.BottomSheet(ft.Container(), show_drag_handle=True, scrollable=True)
    format_row = ft.Row(spacing=8)
    scale_row = ft.Row(spacing=8)
    initial_src, initial_name = _preview_src(controller, options)
    preview = ft.Image(src=initial_src, fit=ft.BoxFit.CONTAIN, height=PREVIEW_HEIGHT)
    hint = ft.Text(initial_name, size=12, color=ft.Colors.ON_SURFACE_VARIANT)

    def close() -> None:
        sheet.open = False
        page.update()

    def choose_format(value: str) -> None:
        nonlocal options
        options = replace(options, fmt=value)
        sync()

    def choose_scale(value: int) -> None:
        nonlocal options
        options = replace(options, scale=value)
        sync()

    async def save(e: ft.Event[ft.FilledButton]) -> None:
        image, filename = controller.export_image(options)
        try:
            path = await picker.save_file(
                dialog_title="이미지 저장",
                file_name=filename,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=[options.fmt],
                src_bytes=image,
            )
        except Exception as ex:  # 저장 실패는 원인을 그대로 보여준다 (spec 2.7)
            show_result(ActionResult(False, f"저장 실패: {ex}"))
            return
        if path is None:
            return  # 취소는 무시 (spec 2.7)
        close()
        show_result(ActionResult(False, f"저장했어요: {path}"))

    def chip(label: str, selected: bool, on_click: Callable[[], None]) -> ft.Container:
        return ft.Container(
            ft.Text(label, color=ft.Colors.ON_PRIMARY if selected else ft.Colors.ON_SURFACE),
            padding=ft.Padding.symmetric(horizontal=14, vertical=8),
            border_radius=ft.BorderRadius.all(20),
            bgcolor=ft.Colors.PRIMARY if selected else None,
            border=None if selected else ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            ink=True,
            on_click=lambda e: on_click(),
        )

    def sync() -> None:
        format_row.controls = [
            chip(value.upper(), options.fmt == value, lambda v=value: choose_format(v))
            for value in FORMATS
        ]
        scale_row.controls = [
            chip(f"{value}x", options.scale == value, lambda v=value: choose_scale(v))
            for value in SCALES
        ]
        preview.src, hint.value = _preview_src(controller, options)
        page.update()

    sheet.content = ft.Container(
        ft.Column(
            [
                ft.Text("이미지로 저장", size=18, weight=ft.FontWeight.BOLD),
                preview,
                hint,
                ft.Text("형식", weight=ft.FontWeight.BOLD),
                format_row,
                ft.Text("배율", weight=ft.FontWeight.BOLD),
                scale_row,
                ft.Row(
                    [
                        ft.TextButton("취소", on_click=lambda e: close()),
                        ft.FilledButton("저장", on_click=save),
                    ],
                    alignment=ft.MainAxisAlignment.END,
                ),
            ],
            tight=True,
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
        ),
        padding=ft.Padding.all(20),
    )
    page.show_dialog(sheet)
    sync()
