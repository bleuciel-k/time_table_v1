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
SAVE_MODES = ("album", "file")
SAVE_MODE_LABELS = {"album": "앨범 · 공유", "file": "파일로 저장"}


def _preview_src(controller: AppController, options: ExportOptions) -> tuple[str, str]:
    """미리보기용 data URI와 저장될 파일명. 미리보기는 항상 1x로 그린다."""
    image, filename = controller.export_image(replace(options, scale=1))
    media = "jpeg" if options.fmt == "jpg" else "png"
    return f"data:image/{media};base64,{base64.b64encode(image).decode()}", filename


def open_export_sheet(
    page: ft.Page,
    controller: AppController,
    picker: ft.FilePicker,
    show_result: ShowResult,
    share: ft.Share | None = None,
) -> None:
    options = ExportOptions()
    save_mode = "album" if share is not None else "file"
    format_row = ft.Row(spacing=d.SPACE_XS)
    scale_row = ft.Row(spacing=d.SPACE_XS)
    mode_row = ft.Row(spacing=d.SPACE_XS)
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
    sheet: ft.BottomSheet | None = None

    def close() -> None:
        if sheet is not None:
            sheet.open = False
        try:
            page.update()
        except Exception:
            pass

    def choose_format(value: str) -> None:
        nonlocal options
        options = replace(options, fmt=value)
        sync()

    def choose_scale(value: int) -> None:
        nonlocal options
        options = replace(options, scale=value)
        sync()

    def choose_mode(value: str) -> None:
        nonlocal save_mode
        save_mode = value
        sync()

    async def save(e: ft.Event[ft.FilledButton]) -> None:
        image, filename = controller.export_image(options)
        if save_mode == "album" and share is not None:
            media = "image/jpeg" if options.fmt == "jpg" else "image/png"
            try:
                res = await share.share_files(
                    [ft.ShareFile.from_bytes(image, mime_type=media, name=filename)],
                    title=filename,
                )
                if res.status == ft.ShareResultStatus.DISMISSED:
                    return
                if res.status == ft.ShareResultStatus.UNAVAILABLE:
                    # 웹 HTTP 등 공유 시트를 띄울 수 없는 환경 -> 파일 저장으로 자동 폴백
                    pass
                else:
                    close()
                    show_result(ActionResult(False, "공유 시트를 열었어요. '이미지 저장'을 누르면 앨범에 저장됩니다."))
                    return
            except Exception:
                # 브라우저 보안상 Share가 막히면 파일 저장으로 자연스럽게 폴백
                pass

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
        mode_row.controls = [
            t.chip(SAVE_MODE_LABELS[m], save_mode == m, lambda v=m: choose_mode(v))
            for m in SAVE_MODES
        ]
        preview.content.src, hint.value = _preview_src(controller, options)
        if sheet is not None:
            try:
                sheet.update()
                return
            except Exception:
                pass
        try:
            page.update()
        except Exception:
            pass

    sheet = t.sheet(
        "이미지로 저장",
        [
            preview,
            hint,
            t.label("형식"),
            format_row,
            t.label("배율"),
            scale_row,
            t.label("저장 방식"),
            mode_row,
            t.actions_row(
                t.secondary_button("취소", lambda e: close()),
                t.primary_button("저장", save),
            ),
        ],
    )
    page.show_dialog(sheet)
    sync()
