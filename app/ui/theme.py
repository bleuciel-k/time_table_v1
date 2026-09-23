"""DESIGN.md 토큰을 Flet 컨트롤로 옮긴 공용 위젯 (T11). 값은 `app.design`에만 둔다."""

from typing import Callable, Iterable

import flet as ft

from app import design as d

WEIGHTS = {400: ft.FontWeight.W_400, 500: ft.FontWeight.W_500, 600: ft.FontWeight.W_600}


def build_theme(font_family: str | None = d.FONT_FAMILY) -> ft.Theme:
    """라이트 고정 테마. 폰트는 앱에 넣은 본고딕(한·영·일)을 쓴다."""
    return ft.Theme(
        font_family=font_family,
        color_scheme=ft.ColorScheme(
            primary=d.INK,
            on_primary=d.ON_PRIMARY,
            surface=d.CANVAS,
            on_surface=d.INK,
            on_surface_variant=d.MUTED,
            outline=d.BORDER_STRONG,
            outline_variant=d.HAIRLINE,
            error=d.DANGER,
            on_error=d.ON_PRIMARY,
        ),
        divider_color=d.HAIRLINE,
        scaffold_bgcolor=d.CANVAS,
        canvas_color=d.CANVAS,
    )


# ---------------------------------------------------------------- 글자


def text(
    value: str, role: tuple[int, int] = d.BODY_MD, color: str = d.BODY, **kwargs
) -> ft.Text:
    size, weight = role
    return ft.Text(value, size=size, weight=WEIGHTS[weight], color=color, **kwargs)


def title(value: str, role: tuple[int, int] = d.TITLE_MD) -> ft.Text:
    return text(value, role, color=d.INK)


def label(value: str) -> ft.Text:
    """구역 이름 (요일 수, 색상 …). 굵게 하지 않고 색으로 구분한다."""
    return text(value, d.CAPTION, color=d.MUTED)


def style(role: tuple[int, int], color: str) -> ft.TextStyle:
    size, weight = role
    return ft.TextStyle(size=size, weight=WEIGHTS[weight], color=color)


# ---------------------------------------------------------------- 버튼

_SHAPE = ft.RoundedRectangleBorder(radius=d.RADIUS_LG)
_BUTTON_PADDING = ft.Padding.symmetric(horizontal=d.SPACE_LG, vertical=d.SPACE_MD)


def primary_button(value: str, on_click: Callable, **kwargs) -> ft.FilledButton:
    """먹색 기본 버튼. 한 화면에 하나만 둔다 (DESIGN.md)."""
    return ft.FilledButton(
        value,
        on_click=on_click,
        style=ft.ButtonStyle(
            bgcolor={ft.ControlState.DEFAULT: d.INK, ft.ControlState.PRESSED: d.INK_ACTIVE,
                     ft.ControlState.DISABLED: d.SURFACE_STRONG},
            color={ft.ControlState.DEFAULT: d.ON_PRIMARY, ft.ControlState.DISABLED: d.MUTED},
            shape=_SHAPE,
            padding=_BUTTON_PADDING,
            text_style=style(d.BUTTON, d.ON_PRIMARY),
            elevation=0,
        ),
        **kwargs,
    )


def secondary_button(value: str, on_click: Callable, **kwargs) -> ft.OutlinedButton:
    """흰 배경 + 얇은 테두리. 기본 버튼과 짝으로 쓴다 (DESIGN.md)."""
    return ft.OutlinedButton(
        value,
        on_click=on_click,
        style=ft.ButtonStyle(
            bgcolor=d.CANVAS,
            color=d.INK,
            shape=_SHAPE,
            padding=_BUTTON_PADDING,
            side=ft.BorderSide(1, d.HAIRLINE),
            text_style=style(d.BUTTON, d.INK),
        ),
        **kwargs,
    )


def danger_button(value: str, on_click: Callable, **kwargs) -> ft.TextButton:
    """삭제·덮어쓰기처럼 되돌리기 어려운 확인 버튼."""
    return ft.TextButton(
        value,
        on_click=on_click,
        style=ft.ButtonStyle(
            color=d.DANGER, shape=_SHAPE, padding=_BUTTON_PADDING,
            text_style=style(d.BUTTON, d.DANGER),
        ),
        **kwargs,
    )


def actions_row(*controls: ft.Control) -> ft.Row:
    return ft.Row(list(controls), alignment=ft.MainAxisAlignment.END, spacing=d.SPACE_SM)


def chip(value: str, selected: bool, on_click: Callable[[], None]) -> ft.Container:
    """고르는 칩(형식·배율·요일 수). 선택된 것만 먹색으로 채운다."""
    return ft.Container(
        text(value, d.BODY_MD, color=d.ON_PRIMARY if selected else d.BODY),
        padding=ft.Padding.symmetric(horizontal=d.SPACE_MD, vertical=d.SPACE_SM),
        border_radius=ft.BorderRadius.all(d.RADIUS_SM),
        bgcolor=d.INK if selected else d.CANVAS,
        border=None if selected else ft.Border.all(1, d.HAIRLINE),
        ink=True,
        on_click=lambda e: on_click(),
    )


# ---------------------------------------------------------------- 입력


def text_field(label_text: str, **kwargs) -> ft.TextField:
    def outline(color: str, width: int) -> ft.OutlineInputBorder:
        return ft.OutlineInputBorder(
            side=ft.BorderSide(width, color), border_radius=ft.BorderRadius.all(d.RADIUS_SM)
        )

    return ft.TextField(
        label=label_text,
        border={
            ft.ControlState.DEFAULT: outline(d.HAIRLINE, 1),
            ft.ControlState.FOCUSED: outline(d.FOCUS, 2),
            ft.ControlState.ERROR: outline(d.DANGER, 1),
        },
        bgcolor=d.CANVAS,
        filled=True,
        text_style=style(d.BODY_MD, d.INK),
        label_style=style(d.BODY_MD, d.MUTED),
        helper_style=style(d.SMALL, d.MUTED),
        error_style=style(d.SMALL, d.DANGER),
        content_padding=ft.Padding.symmetric(horizontal=d.SPACE_MD, vertical=d.SPACE_SM),
        **kwargs,
    )


# ---------------------------------------------------------------- 면


def divider() -> ft.Divider:
    return ft.Divider(height=1, thickness=1, color=d.HAIRLINE)


def sheet(heading: str, controls: Iterable[ft.Control], scrollable: bool = True) -> ft.BottomSheet:
    """제목 + 내용 + (보통) 버튼 줄로 이루어진 바텀 시트."""
    return ft.BottomSheet(
        ft.Container(
            ft.Column(
                [title(heading), *controls],
                tight=True,
                spacing=d.SPACE_MD,
                scroll=ft.ScrollMode.AUTO if scrollable else None,
            ),
            padding=ft.Padding.only(
                left=d.SPACE_LG, right=d.SPACE_LG, top=d.SPACE_MD, bottom=d.SPACE_LG
            ),
            bgcolor=d.CANVAS,
        ),
        bgcolor=d.CANVAS,
        shape=ft.RoundedRectangleBorder(radius=d.RADIUS_LG),
        show_drag_handle=True,
        scrollable=scrollable,
    )


def menu_sheet(heading: str, items: Iterable[ft.Control]) -> ft.BottomSheet:
    """목록만 있는 시트(셀 메뉴, 시간표 목록, 계정). 항목은 가장자리까지 닿게 둔다."""
    return ft.BottomSheet(
        ft.Container(
            ft.Column(
                [
                    ft.Container(
                        title(heading),
                        padding=ft.Padding.only(
                            left=d.SPACE_MD, right=d.SPACE_MD, top=d.SPACE_XS, bottom=d.SPACE_XS
                        ),
                    ),
                    *items,
                ],
                tight=True,
                spacing=0,
            ),
            padding=ft.Padding.only(bottom=d.SPACE_LG),
            bgcolor=d.CANVAS,
        ),
        bgcolor=d.CANVAS,
        shape=ft.RoundedRectangleBorder(radius=d.RADIUS_LG),
        show_drag_handle=True,
    )


def menu_item(
    icon: ft.IconData,
    value: str,
    on_click: Callable,
    subtitle: str | None = None,
    color: str = d.INK,
    trailing: ft.Control | None = None,
) -> ft.ListTile:
    return ft.ListTile(
        leading=ft.Icon(icon, color=color, size=20),
        title=value,
        subtitle=subtitle,
        trailing=trailing,
        on_click=on_click,
        title_text_style=style(d.LABEL, color),
        subtitle_text_style=style(d.BODY_MD, d.MUTED),
        content_padding=ft.Padding.symmetric(horizontal=d.SPACE_MD),
    )


def dialog(heading: str, content: ft.Control, actions: list[ft.Control]) -> ft.AlertDialog:
    return ft.AlertDialog(
        modal=True,
        title=heading,
        content=content,
        actions=actions,
        bgcolor=d.CANVAS,
        shape=ft.RoundedRectangleBorder(radius=d.RADIUS_LG),
        title_text_style=style(d.TITLE_SM, d.INK),
        content_text_style=style(d.BODY_MD, d.BODY),
        title_padding=ft.Padding.only(left=d.SPACE_LG, right=d.SPACE_LG, top=d.SPACE_LG),
        content_padding=ft.Padding.only(left=d.SPACE_LG, right=d.SPACE_LG, top=d.SPACE_SM),
        actions_padding=ft.Padding.all(d.SPACE_MD),
    )


def snack_bar(message: str, action: str | None = None, on_action=None, duration: int = 3000):
    """먹색 바. DESIGN.md의 어두운 면 규칙을 따른다."""
    return ft.SnackBar(
        text(message, d.BODY_MD, color=d.ON_PRIMARY),
        action=action,
        on_action=on_action,
        duration=duration,
        bgcolor=d.INK,
        behavior=ft.SnackBarBehavior.FLOATING,
        margin=ft.Margin.all(d.SPACE_MD),
        shape=ft.RoundedRectangleBorder(radius=d.RADIUS_MD),
    )
