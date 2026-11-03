"""Flet 진입점: 컨트롤러를 열고 화면을 조립한다."""

import os

import flet as ft

from app import design as d
from app.controller import AppController, SyncManager
from app.sample import sample_data
from app.palette import background_hex
from app.storage import Storage
from app.sync import Auth, CloudStore
from app.ui.actions import Actions
from app.ui.grid import build_grid
from app.ui.theme import build_theme, snack_bar, text


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
    page.fonts = {  # assets/fonts/… (한·영·일 한 벌, 굵기 2종)
        d.FONT_FAMILY: d.FONT_FILE,
        d.FONT_FAMILY_MEDIUM: d.FONT_FILE_MEDIUM,
    }
    page.theme = build_theme()
    page.theme_mode = ft.ThemeMode.LIGHT  # DESIGN.md는 흰 캔버스 기준의 라이트 전용 시스템
    page.bgcolor = d.CANVAS  # 실제 배경색은 render()에서 설정값에 맞춰 바꾼다 (F9)
    page.padding = ft.Padding.symmetric(horizontal=d.SPACE_XS)  # 스마트폰 양옆 여백을 슬림하게 최적화 (16px -> 8px)
    # v1.1: 크기 조절 모퉁이 추적 및 연속 교시 스마트 안착 하이라이트 반영
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
        actions.delete_dragged_cell(src)

    delete_target = ft.Container(
        content=ft.DragTarget(
            group="cells",
            content=delete_zone_container,
            on_will_accept=on_delete_will_accept,
            on_leave=on_delete_leave,
            on_accept=on_delete_accept,
        ),
        top=4,
        left=12,
        right=12,
        height=52,
    )

    body = ft.Container(
        expand=True,
        padding=ft.Padding.only(top=d.SPACE_XS, bottom=d.SPACE_XS),
        border=ft.Border.only(top=ft.BorderSide(1, d.HAIRLINE)),  # 앱 바와 본문 사이 실선
        content=ft.Stack(
            [grid_container],
            expand=True,
        ),
    )

    def render() -> None:
        settings = workspace.data.settings
        title.value = workspace.active.name
        page.bgcolor = background_hex(settings.background)
        editable = not controller.read_only
        avail_w = (page.width - 2 * d.SPACE_XS) if page.width else None
        avail_h = (page.height - 110) if page.height else None
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
        # 수정 모드일 때 상단에 삭제 영역을 플로팅 오버레이로 배치
        show_delete = editable and actions.drag_mode
        stack_controls: list[ft.Control] = [grid_container]
        if show_delete:
            stack_controls.append(delete_target)
        body.content.controls = stack_controls
        page.update()

    def on_drag_listener(dragging: bool, key: str | None) -> None:
        """드래그 시작/종료 시 전체 render 대신 삭제 바의 입체 스타일만 갱신 (그리드 보존)."""
        if dragging:
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
            delete_zone_container.update()
        except Exception:
            pass

    sync = build_sync(page, controller, render)
    actions = Actions(page, controller, render, picker=ft.FilePicker(), sync=sync)
    actions.on_drag_listener = on_drag_listener
    page.appbar = ft.AppBar(
        bgcolor=d.CANVAS,
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
    page.on_resize = lambda e: render()  # 창 크기가 바뀌면 드래그 카드 너비도 다시 맞춘다
    if sync is not None:
        sync.start()
        page.on_close = lambda e: sync.stop()
    if warnings:
        page.show_dialog(snack_bar("\n".join(warnings)))


if __name__ == "__main__":
    ft.run(main, assets_dir="assets")
