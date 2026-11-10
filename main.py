"""Flet 진입점: 컨트롤러를 열고 화면을 조립한다."""

import os

import flet as ft

from app import design as d
from app.controller import AppController
from app.sample import sample_data
from app.palette import background_hex
from app.storage import Storage
from app.qr import decode_timetable
from app.ui.actions import Actions
from app.ui.grid import build_grid
from app.ui.theme import build_theme, snack_bar, text


def main(page: ft.Page) -> None:
    page.title = "시간표"
    page.fonts = {  # assets/fonts/… (한·영·일 한 벌, 굵기 2종)
        d.FONT_FAMILY: d.FONT_FILE,
        d.FONT_FAMILY_MEDIUM: d.FONT_FILE_MEDIUM,
    }
    page.theme = build_theme()
    page.theme_mode = ft.ThemeMode.LIGHT  # DESIGN.md는 흰 캔버스 기준의 라이트 전용 시스템
    page.bgcolor = d.CANVAS  # 실제 배경색은 render()에서 설정값에 맞춰 바꾼다 (F9)
    page.padding = ft.Padding.symmetric(horizontal=d.SPACE_XS)  # 스마트폰 양옆 여백을 슬림하게 최적화 (16px -> 8px)
    seed = sample_data if os.getenv("TIMETABLE_SAMPLE") == "1" else None
    controller, warnings = AppController.open(Storage(), seed=seed)
    workspace = controller.workspace

    title = text("", d.TITLE_SM, color=d.INK)
    grid_container = ft.Container(expand=True)

    # 반투명 그라데이션 & 입체감 스타일 (붉어지는 작용 대신 볼륨감과 부드러운 그림자)
    delete_icon = ft.Icon(ft.Icons.DELETE_OUTLINE, color=ft.Colors.RED_400, size=22)
    delete_text = ft.Text("삭제하려면 여기로 드래그하세요", color=ft.Colors.RED_400, size=13, weight=ft.FontWeight.W_500)

    delete_zone_container = ft.Container(
        height=52,
        gradient=ft.LinearGradient(
            begin=ft.Alignment.TOP_CENTER,
            end=ft.Alignment.BOTTOM_CENTER,
            colors=["#FFFFFF", "#F6F7F9"],
        ),
        border=ft.Border.all(0.8, ft.Colors.with_opacity(0.12, "#000000")),
        border_radius=ft.BorderRadius.all(d.RADIUS_MD),
        alignment=ft.Alignment.CENTER,
        shadow=ft.BoxShadow(
            blur_radius=12,
            spread_radius=0,
            color="#18000000",
            offset=ft.Offset(0, 4),
        ),
        scale=1.0,
        animate_scale=ft.Animation(160, ft.AnimationCurve.EASE_OUT_CUBIC),
        content=ft.Row(
            [
                delete_icon,
                delete_text,
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=8,
        ),
    )

    def on_delete_will_accept(e) -> None:
        # 붉어짐 없이 볼륨감과 입체 그림자만 확대 (1.05배 팝업 + 부드러운 딥 섀도우)
        delete_zone_container.scale = 1.05
        delete_zone_container.shadow = ft.BoxShadow(
            blur_radius=22,
            spread_radius=1,
            color="#2E000000",
            offset=ft.Offset(0, 8),
        )
        delete_icon.size = 24
        delete_zone_container.update()

    def on_delete_leave(e) -> None:
        delete_zone_container.scale = 1.0
        delete_zone_container.shadow = ft.BoxShadow(
            blur_radius=12,
            spread_radius=0,
            color="#18000000",
            offset=ft.Offset(0, 4),
        )
        delete_icon.size = 22
        delete_zone_container.update()

    def on_delete_accept(e) -> None:
        src = actions.dragging_cell_key
        if not src:
            if hasattr(e, "src_id") and e.src_id and e.control and e.control.page:
                ctrl = e.control.page.get_control(e.src_id)
                if ctrl and hasattr(ctrl, "data") and ctrl.data:
                    src = ctrl.data
        if not src and hasattr(e, "src") and hasattr(e.src, "data"):
            src = e.src.data
        elif not src and hasattr(e, "data") and e.data:
            src = e.data
        delete_zone_container.scale = 1.0
        delete_zone_container.shadow = ft.BoxShadow(
            blur_radius=12,
            spread_radius=0,
            color="#18000000",
            offset=ft.Offset(0, 4),
        )
        delete_icon.size = 22
        delete_target.visible = False
        try:
            delete_target.update()
        except Exception:
            pass
        actions.delete_dragged_cell(src)

    delete_target = ft.Container(
        content=ft.DragTarget(
            group="cells",
            content=delete_zone_container,
            on_will_accept=on_delete_will_accept,
            on_leave=on_delete_leave,
            on_accept=on_delete_accept,
        ),
        top=6,
        left=12,
        right=12,
        height=48,
        visible=False,
    )
    page.overlay.append(delete_target)

    body = ft.Container(
        expand=True,
        padding=ft.Padding.only(top=d.SPACE_XS, bottom=d.SPACE_XS),
        border=ft.Border.only(top=ft.BorderSide(1, d.HAIRLINE)),  # 앱 바와 본문 사이 실선
        content=grid_container,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,  # GPU 렌더링 레이어 분리 (RepaintBoundary 효과)
    )

    last_width: list[float | None] = [None]
    last_height: list[float | None] = [None]

    def render() -> None:
        settings = workspace.data.settings
        title.value = workspace.active.name
        bg = background_hex(settings.background)
        page.bgcolor = bg
        if page.appbar:
            page.appbar.bgcolor = bg
        editable = not controller.read_only
        avail_w = (page.width - 2 * d.SPACE_XS) if page.width else None
        avail_h = (page.height - 110) if page.height else None
        last_width[0] = page.width
        last_height[0] = page.height
        grid_container.content = build_grid(
            workspace.active,
            settings,
            on_cell_click=actions.edit_cell if editable else None,
            on_cell_long_press=actions.open_cell_menu if editable else None,
            on_add_period=actions.add_period if editable else None,
            drag_mode=actions.drag_mode,
            on_move_cell=actions.move_cell if editable else None,
            available_width=avail_w,
            available_height=avail_h,
            landing_keys=actions.landing_keys,
            landing_controls=actions.landing_controls,
            on_resize_block=actions.resize_block if editable else None,
            on_extend_block=actions.extend_block if editable else None,
            on_drag_change=actions.on_drag_change if editable else None,
        )
        # 수정 모드에서 수업을 실제로 드래그할 때만 상단 바 자리에 삭제 영역 표시
        delete_target.visible = bool(editable and actions.drag_mode and actions.dragging_cell_key)
        page.update()

    def on_drag_listener(dragging: bool, key: str | None) -> None:
        """수업을 드래그할 때만 상단 삭제 영역이 뜨고, 드래그가 끝나면 사라진다."""
        editable = not controller.read_only
        show = bool(editable and actions.drag_mode and dragging)
        delete_target.visible = show
        if show:
            delete_zone_container.border = ft.Border.all(1.2, ft.Colors.RED_300)
            delete_zone_container.shadow = ft.BoxShadow(
                blur_radius=16,
                spread_radius=0,
                color="#22000000",
                offset=ft.Offset(0, 5),
            )
        else:
            delete_zone_container.border = ft.Border.all(0.8, ft.Colors.with_opacity(0.12, "#000000"))
            delete_zone_container.shadow = ft.BoxShadow(
                blur_radius=12,
                spread_radius=0,
                color="#18000000",
                offset=ft.Offset(0, 4),
            )
        try:
            delete_target.update()
        except Exception:
            pass

    actions = Actions(page, controller, render, picker=ft.FilePicker())
    actions.on_drag_listener = on_drag_listener
    page.appbar = ft.AppBar(
        bgcolor=background_hex(controller.workspace.data.settings.background),
        color=d.INK,
        elevation=0,
        elevation_on_scroll=0,
        title_spacing=d.SPACE_XS,
        title=ft.Container(
            ft.Row(
                [title, ft.Icon(ft.Icons.ARROW_DROP_DOWN, color=d.MUTED, size=20)],
                tight=True,
                spacing=0,
            ),
            on_click=None if controller.read_only else (lambda e: actions.open_timetables()),
            ink=not controller.read_only,
            padding=ft.Padding.symmetric(horizontal=d.SPACE_XS, vertical=d.SPACE_XXS),
            border_radius=ft.BorderRadius.all(d.RADIUS_SM),
        ),
        actions=None if controller.read_only else [actions.hand_button(), actions.timetable_menu()],
    )
    page.add(ft.SafeArea(body, expand=True))
    render()
    def handle_resize(e: ft.ControlEvent) -> None:
        # 모바일 가상 키보드 팝업이나 사파리 주소창 스크롤로 인한 미세한 높이 변화 시
        # 전체 그리드를 매 프레임마다 재빌드하는 병목을 방지한다.
        w = page.width or 0
        h = page.height or 0
        prev_w = last_width[0] or 0
        prev_h = last_height[0] or 0
        if prev_w == 0 or abs(w - prev_w) > 6 or abs(h - prev_h) > 120:
            render()

    page.on_resize = handle_resize

    # 딥링크(QR 코드 카메라 스캔 / 외부 링크 클릭)를 통한 시간표 자동 가져오기 처리
    def handle_deep_link(route_str: str) -> None:
        if not route_str or route_str == "/":
            return
        try:
            imported_tt, _ = decode_timetable(route_str)

            def confirm_import(e: ft.ControlEvent) -> None:
                page.pop_dialog()
                actions.show_result(controller.import_timetable(imported_tt, switch_to=True))
                render()

            dlg = ft.AlertDialog(
                title=ft.Row(
                    [
                        ft.Icon(ft.Icons.DOWNLOAD, color=d.INK, size=22),
                        text("시간표 가져오기", d.TITLE, color=d.INK),
                    ],
                    spacing=d.SPACE_XS,
                ),
                content=ft.Container(
                    content=ft.Column(
                        [
                            text(
                                f"공유받은 '{imported_tt.name}' 시간표를 가져올까요?",
                                d.BODY,
                                color=d.INK,
                            ),
                            text(
                                f"등록된 수업: 총 {len(imported_tt.cells)}개",
                                d.CAPTION,
                                color=d.MUTED,
                            ),
                        ],
                        tight=True,
                        spacing=4,
                    ),
                    width=280,
                ),
                actions=[
                    ft.TextButton("취소", on_click=lambda e: page.pop_dialog()),
                    ft.FilledButton("가져오기", on_click=confirm_import),
                ],
            )
            page.show_dialog(dlg)
        except Exception:
            pass

    page.on_route_change = lambda e: handle_deep_link(e.route)
    if page.route and page.route != "/":
        handle_deep_link(page.route)

    if warnings:
        page.show_dialog(snack_bar("\n".join(warnings)))


if __name__ == "__main__":
    ft.run(main, assets_dir="assets")
