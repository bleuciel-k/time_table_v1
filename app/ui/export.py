"""이미지 내보내기 시트: 형식·배율 선택, 미리보기, 저장 (F6). 렌더링은 exporter가 한다 (P5)."""

import base64
from dataclasses import replace
from typing import Callable

import flet as ft

from app import design as d
from app.controller import ActionResult, AppController
from app.exporter import FORMATS, SCALES, ExportOptions
from app.ui import theme as t

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
    format_row = ft.Row(spacing=d.SPACE_XS)
    scale_row = ft.Row(spacing=d.SPACE_XS)
    initial_src, initial_name = _preview_src(controller, options)
    preview = ft.Container(
        ft.Image(src=initial_src, fit=ft.BoxFit.CONTAIN, height=PREVIEW_HEIGHT),
        padding=ft.Padding.all(d.SPACE_SM),
        bgcolor=d.SURFACE_SOFT,
        border=ft.Border.all(1, d.HAIRLINE),
        border_radius=ft.BorderRadius.all(d.RADIUS_MD),
        alignment=ft.Alignment.CENTER,
    )
    hint = t.text(initial_name, d.SMALL, color=d.MUTED)

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

    def sync() -> None:
        format_row.controls = [
            t.chip(value.upper(), options.fmt == value, lambda v=value: choose_format(v))
            for value in FORMATS
        ]
        scale_row.controls = [
            t.chip(f"{value}x", options.scale == value, lambda v=value: choose_scale(v))
            for value in SCALES
        ]
        preview.content.src, hint.value = _preview_src(controller, options)
        page.update()

    sheet = t.sheet(
        "이미지로 저장",
        [
            preview,
            hint,
            t.label("형식"),
            format_row,
            t.label("배율"),
            scale_row,
            t.actions_row(
                t.secondary_button("취소", lambda e: close()),
                t.primary_button("저장", save),
            ),
        ],
    )
    page.show_dialog(sheet)
    sync()
