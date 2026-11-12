"""주간 그리드. 표시만 담당하고 배치 계산은 `model.day_blocks`에 둔다 (P5). 스타일은 DESIGN.md (T11).

요일마다 세로 칸(Stack)을 두고 수업 묶음을 교시 위치에 놓는다. 같은 요일의 연속 수업은
한 덩어리로 이어 그리고, 요일이 다르면 지금처럼 칸 사이 틈을 둔다.
"""

from datetime import datetime
from typing import Callable

import flet as ft

from app import design as d
from app.model import (
    DAY_LABELS,
    PERIOD_MAX,
    PERIOD_MIN,
    Block,
    Cell,
    Settings,
    Timetable,
    cell_key,
    day_blocks,
    has_lunch,
    lunch_time,
    parse_cell_key,
    period_times,
)
from app.palette import darken_hex, lighten_hex, resolve_hex, text_color
from app.ui.theme import text

PERIOD_COL_WIDTH = 22  # 교시 번호만 표시할 때
TIME_COL_WIDTH = 38  # 교시 시간을 함께 표시할 때 (컴팩트하게 정돈)
HEADER_HEIGHT = 32
CELL_HEIGHT = 84
LUNCH_HEIGHT = 30
MEMO_MAX_LINES = 2

# 그리드 글자 크기 (크기, 굵기). 칸이 좁아 앱의 기본 크기보다 한 단계씩 작게 쓴다
HEADER_TEXT = (13, 500)  # 요일
PERIOD_TEXT = (13, 400)  # 교시 번호
TIME_TEXT = (8, 400)  # 교시 시각
SUBJECT_TEXT = (12, 500)
ROOM_TEXT = (10, 400)
MEMO_TEXT = (8, 400)
LUNCH_TEXT = (11, 400)
GAP = d.SPACE_XXS
RADIUS = d.RADIUS_MD
FEEDBACK_FALLBACK_WIDTH = 76  # 화면 너비를 모를 때 드래그 카드 너비
LANDING_SCALE = 1.02  # 놓은 직후 크기 → 1.0으로 내려앉는다 (과한 튕김 없이 부드럽게 안착)
LANDING_MS = 180
HANDLE = 40  # 수정 모드에서 수업 모퉁이를 잡는 터치 영역 크기 (잡기 쉽도록 20->40으로 대폭 확대)
HANDLE_PILL = 5  # 모퉁이 보조 표시(작은 점) 크기

KeyHandler = Callable[[str], None]
ResizeHandler = Callable[[int, int, int, int, int], None]  # (요일, 시작, 끝, 새 시작, 새 끝)
ExtendHandler = Callable[[int, int, int, int], None]  # (요일, 시작, 끝, 늘릴 요일)


def calc_cell_height(
    available_height: float | None, settings: Settings, cell_width: float | None = None
) -> float:
    """화면 높이와 셀 너비 비율(약 1.25~1.3배)에 맞춰 수업 셀 크기를 균형있게 유지."""
    # 셀 너비가 있으면 카드로서 가장 보기 좋은 종횡비(가로 대비 약 1.25배)를 기준값으로 삼는다
    ideal_by_ratio = (cell_width * 1.25) if cell_width and cell_width > 0 else CELL_HEIGHT

    if not available_height or available_height <= 0:
        return ideal_by_ratio

    periods = settings.periods
    header_h = HEADER_HEIGHT
    lunch_h = LUNCH_HEIGHT if has_lunch(settings) else 0.0
    gaps = (periods + (1 if lunch_h > 0 else 0)) * GAP
    fixed = header_h + lunch_h + gaps
    remaining = available_height - fixed
    h_fit = remaining / periods

    # 화면에 꽉 채웠을 때 너무 길쭉해지지 않도록 ideal_by_ratio의 1.15배까지만 허용하고,
    # 교시 수가 많아서 공간이 부족할 때도 텍스트가 잘리지 않는 최소 66px 보장
    target = min(h_fit, ideal_by_ratio * 1.15)
    return max(66.0, min(108.0, target))


def build_grid(
    timetable: Timetable,
    settings: Settings,
    on_cell_click: KeyHandler | None = None,
    on_cell_long_press: KeyHandler | None = None,
    on_add_period: Callable[[], None] | None = None,
    today_weekday: int | None = None,
    drag_mode: bool = False,
    on_move_cell: Callable[[str, str], None] | None = None,
    available_width: float | None = None,
    available_height: float | None = None,
    landing_keys: set[str] | None = None,
    landing_controls: list[ft.Control] | None = None,
    on_resize_block: ResizeHandler | None = None,
    on_extend_block: ExtendHandler | None = None,
    on_drag_change: Callable[[bool, str | None], None] | None = None,
) -> ft.Control:
    """핸들러가 None이면 해당 조작 없음 (읽기 전용).

    available_width: 그리드가 차지하는 가로 폭. 드래그 카드·옆으로 늘리기 계산에 칸 너비가 필요하다.
    available_height: 그리드가 차지하는 세로 높이. 기기별 최적 셀 높이 계산에 쓰인다.
    landing_keys: 방금 이동한 칸. 그 칸의 컨트롤을 landing_controls에 모아 내려앉는 애니메이션에 쓴다.
    on_resize_block / on_extend_block: 수정 모드에서 가장자리를 끌어 위·아래 / 양옆으로 늘릴 때.
    """
    times = period_times(settings) if settings.show_times else None
    width = TIME_COL_WIDTH if times else PERIOD_COL_WIDTH
    cell_width = None
    if available_width:
        cell_width = (available_width - width - GAP * settings.days) / settings.days
        if cell_width <= 0:
            cell_width = None
    cell_height = calc_cell_height(available_height, settings, cell_width=cell_width)
    ctx = _Ctx(
        on_click=on_cell_click,
        on_long_press=on_cell_long_press,
        drag_mode=drag_mode,
        on_move_cell=on_move_cell,
        cell_width=cell_width,
        cell_height=cell_height,
        landing_keys=landing_keys or set(),
        landing_controls=landing_controls,
        on_resize_block=on_resize_block,
        on_extend_block=on_extend_block,
        on_drag_change=on_drag_change,
        timetable=timetable,
        settings=settings,
    )

    if has_lunch(settings):
        sections = [(PERIOD_MIN, settings.lunch_after), (settings.lunch_after + 1, settings.periods)]
    else:
        sections = [(PERIOD_MIN, settings.periods)]
    blocks = day_blocks(timetable, settings)

    rows: list[ft.Control] = [_header(settings.days, width, today_weekday=today_weekday)]
    for index, (first, last) in enumerate(sections):
        if index > 0:
            rows.append(_lunch_row(settings, width))
        labels = ft.Column(
            [
                _period_label(
                    period,
                    times[period - PERIOD_MIN] if times else None,
                    width,
                    cell_height=cell_height,
                    is_last=(period == settings.periods),
                    on_add_period=on_add_period,
                )
                for period in range(first, last + 1)
            ],
            spacing=GAP,
            width=width,
        )
        columns = [
            _day_column([b for b in day if first <= b.start <= last], first, last, ctx)
            for day in blocks
        ]
        rows.append(
            ft.Row([labels, *columns], spacing=GAP, vertical_alignment=ft.CrossAxisAlignment.START)
        )
    # 시간표 맨 아래에 넉넉한 여유 영역을 추가하여 마지막 교시 셀이 잘리지 않고 스크롤/배치가 안정되도록 함
    rows.append(ft.Container(height=52))
    return ft.Column(rows, spacing=GAP, scroll=ft.ScrollMode.AUTO, expand=True)


def resolve_drop_target(
    src_key: str | None,
    dest_key: str,
    src_span: int,
    timetable: Timetable | None,
    settings: Settings | None,
) -> tuple[int, int, int]:
    """드롭 시 수업이 위치할 (day, start_period, span)을 계산한다."""
    try:
        dest_day, dest_start = parse_cell_key(dest_key)
    except Exception:
        return 0, PERIOD_MIN, 1

    if src_span <= 1 or timetable is None or settings is None:
        return dest_day, dest_start, 1

    # 2칸 이상의 연속 수업인 경우
    src_block_keys: set[str] = set()
    if src_key:
        try:
            s_day, s_start = parse_cell_key(src_key)
            src_block_keys = {cell_key(s_day, p) for p in range(s_start, s_start + src_span)}
        except Exception:
            pass

    if dest_key not in timetable.cells or dest_key in src_block_keys:
        candidate_starts = [dest_start - offset for offset in range(src_span)]
        for c_start in candidate_starts:
            if c_start < PERIOD_MIN:
                continue
            c_end = c_start + src_span - 1
            if c_end > settings.periods:
                continue
            c_keys = [cell_key(dest_day, p) for p in range(c_start, c_end + 1)]
            if not any(k in timetable.cells and k not in src_block_keys for k in c_keys):
                return dest_day, c_start, src_span

    c_start = dest_start
    if c_start + src_span - 1 > settings.periods:
        c_start = max(PERIOD_MIN, settings.periods - src_span + 1)
    return dest_day, c_start, src_span


class _Ctx:
    """칸을 그릴 때 공통으로 쓰는 핸들러·상태 묶음."""

    def __init__(self, **kwargs) -> None:
        self.on_click: KeyHandler | None = kwargs["on_click"]
        self.on_long_press: KeyHandler | None = kwargs["on_long_press"]
        self.drag_mode: bool = kwargs["drag_mode"]
        self.on_move_cell: Callable[[str, str], None] | None = kwargs["on_move_cell"]
        self.cell_width: float | None = kwargs["cell_width"]
        self.cell_height: float = kwargs["cell_height"]
        self.landing_keys: set[str] = kwargs["landing_keys"]
        self.landing_controls: list[ft.Control] | None = kwargs["landing_controls"]
        self.on_resize_block: ResizeHandler | None = kwargs["on_resize_block"]
        self.on_extend_block: ExtendHandler | None = kwargs["on_extend_block"]
        self.on_drag_change: Callable[[bool, str | None], None] | None = kwargs.get("on_drag_change")
        self.active_drag_key: str | None = None
        self.last_drag_key: str | None = None
        self.active_drag_span: int = 1
        self.last_hover_key: str | None = None
        self.timetable: Timetable | None = kwargs.get("timetable")
        self.settings: Settings | None = kwargs.get("settings")
        # 각 셀 키별 하이라이트 제어 함수: key -> set_hover(active, is_top, is_bottom)
        self.hover_registry: dict[str, Callable[[bool, bool, bool], None]] = {}
        self.current_highlight_keys: set[str] = set()

    def highlight_slot(self, dest_key: str) -> None:
        """드래그 중인 수업 셀의 크기(span)에 맞춰 옮겨질 영역 전체를 하이라이트한다."""
        src_key = self.active_drag_key or self.last_drag_key
        span = self.active_drag_span
        self.last_hover_key = dest_key
        dest_day, dest_start, span = resolve_drop_target(
            src_key, dest_key, span, self.timetable, self.settings
        )
        target_keys = [cell_key(dest_day, p) for p in range(dest_start, dest_start + span)]
        new_keys_set = set(target_keys)

        # 이전 하이라이트 중 제외된 칸들 해제
        for k in (self.current_highlight_keys - new_keys_set):
            fn = self.hover_registry.get(k)
            if fn:
                fn(False, True, True)

        # 새 영역의 칸들 하이라이트 (모퉁이 보조선 및 테두리 연결)
        total = len(target_keys)
        for idx, k in enumerate(target_keys):
            fn = self.hover_registry.get(k)
            if fn:
                is_top = (idx == 0)
                is_bottom = (idx == total - 1)
                fn(True, is_top, is_bottom)

        self.current_highlight_keys = new_keys_set

    def clear_highlight(self) -> None:
        """모든 하이라이트를 즉시 해제한다."""
        for k in self.current_highlight_keys:
            fn = self.hover_registry.get(k)
            if fn:
                fn(False, True, True)
        self.current_highlight_keys.clear()
        self.last_hover_key = None


def span_height(span: int, cell_height: float = CELL_HEIGHT) -> float:
    """교시 span개를 이어 붙인 높이 (사이 틈 포함)."""
    return span * cell_height + (span - 1) * GAP


def _day_column(blocks: list[Block], first: int, last: int, ctx: _Ctx) -> ft.Control:
    """한 요일의 세로 칸. 수업 묶음을 교시 위치에 겹쳐 놓는다."""
    children: list[ft.Control] = []
    for block in blocks:
        top = (block.start - first) * (ctx.cell_height + GAP)
        children.extend(_block(block, top, ctx))
    return ft.Container(
        ft.Stack(children, clip_behavior=ft.ClipBehavior.NONE),
        expand=1,
        height=span_height(last - first + 1, ctx.cell_height),
    )


def _lunch_row(settings: Settings, label_width: float) -> ft.Row:
    """교시 사이의 점심시간 띠 (F9)."""
    times = lunch_time(settings)
    caption = "점심시간"
    if settings.show_times and times:
        caption = f"점심시간 · {times[0]}–{times[1]}"
    return ft.Row(
        [
            ft.Container(width=label_width),
            ft.Container(
                text(caption, LUNCH_TEXT, color=d.MUTED, text_align=ft.TextAlign.CENTER),
                expand=1,
                height=LUNCH_HEIGHT,
                border=ft.Border.all(1, d.HAIRLINE),
                border_radius=ft.BorderRadius.all(RADIUS),
                alignment=ft.Alignment.CENTER,
            ),
        ],
        spacing=GAP,
    )


def _header(days: int, label_width: float, today_weekday: int | None = None) -> ft.Row:
    if today_weekday is None:
        today_weekday = datetime.now().weekday()  # 0: 월 ~ 6: 일
    labels = []
    for day in range(days):
        is_today = (day == today_weekday)
        if is_today:
            # 사용하는 요일에 맞춘 검은 동그라미 하이라이트
            content: ft.Control = ft.Container(
                content=text(
                    DAY_LABELS[day],
                    HEADER_TEXT,
                    color=d.ON_PRIMARY,
                    text_align=ft.TextAlign.CENTER,
                ),
                width=24,
                height=24,
                bgcolor=d.INK,
                shadow=ft.BoxShadow(
                    blur_radius=4,
                    spread_radius=0,
                    color="#25000000",
                    offset=ft.Offset(0, 1.5),
                ),
                border_radius=ft.BorderRadius.all(12),
                alignment=ft.Alignment.CENTER,
            )
        else:
            content = text(
                DAY_LABELS[day],
                HEADER_TEXT,
                color=d.MUTED,
                text_align=ft.TextAlign.CENTER,
            )
        labels.append(
            ft.Container(
                content,
                expand=1,
                height=HEADER_HEIGHT,
                alignment=ft.Alignment.CENTER,
            )
        )
    return ft.Row([ft.Container(width=label_width), *labels], spacing=GAP)


def _period_label(
    period: int,
    times: tuple[str, str] | None,
    width: float,
    cell_height: float = CELL_HEIGHT,
    is_last: bool = False,
    on_add_period: Callable[[], None] | None = None,
) -> ft.Container:
    num_text = text(str(period), PERIOD_TEXT, color=d.MUTED)
    # 7교시 이상 마지막 교시 옆에 + 버튼 제공 (8교시, 9교시... 추가 가능)
    if is_last and on_add_period and period >= 7 and period < PERIOD_MAX:
        add_btn = ft.Container(
            content=ft.Icon(ft.Icons.ADD, size=13, color=d.INK),
            width=18,
            height=18,
            bgcolor=d.SURFACE_STRONG,
            border_radius=ft.BorderRadius.all(9),
            alignment=ft.Alignment.CENTER,
            tooltip="교시 추가",
            ink=True,
            on_click=lambda e: on_add_period(),
        )
        first_line: ft.Control = ft.Row(
            [num_text, add_btn],
            spacing=2,
            tight=True,
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
    else:
        first_line = num_text

    lines: list[ft.Control] = [first_line]
    if times:
        lines += [
            text(value, TIME_TEXT, color=d.MUTED, text_align=ft.TextAlign.CENTER)
            for value in times
        ]
    return ft.Container(
        ft.Column(
            lines,
            spacing=0,
            tight=True,
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        width=width,
        height=cell_height,
        alignment=ft.Alignment.CENTER,
    )


def _card_lines(cell: Cell) -> list[ft.Control]:
    fg = text_color(cell.color)
    lines: list[ft.Control] = [
        text(
            cell.subject,
            SUBJECT_TEXT,  # 셀 안에서도 굵게가 아니라 중간 굵기 (DESIGN.md)
            color=fg,
            max_lines=3,
            overflow=ft.TextOverflow.ELLIPSIS,
            text_align=ft.TextAlign.CENTER,
        )
    ]
    if cell.room:
        lines.append(
            text(
                cell.room,
                ROOM_TEXT,
                color=fg,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
                text_align=ft.TextAlign.CENTER,
            )
        )
    if cell.show_memo and cell.memo:
        lines.append(
            text(
                cell.memo,
                MEMO_TEXT,  # 메모는 가장 작은 글씨로 최대 2줄 (F1)
                color=fg,
                max_lines=MEMO_MAX_LINES,
                overflow=ft.TextOverflow.ELLIPSIS,
                text_align=ft.TextAlign.CENTER,
            )
        )
    return lines


def _card(cell: Cell, height: float = CELL_HEIGHT, **kwargs) -> ft.Container:
    """수업 칸의 모양. Figma 스타일의 부드러운 그라데이션과 입체 그림자를 적용한다."""
    base_hex = resolve_hex(cell.color)
    top_tint = lighten_hex(base_hex, 0.05)
    bottom_tint = darken_hex(base_hex, 0.02)

    return ft.Container(
        ft.Column(
            _card_lines(cell),
            spacing=2,
            tight=True,
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        height=height,
        gradient=ft.LinearGradient(
            begin=ft.Alignment.TOP_CENTER,
            end=ft.Alignment.BOTTOM_CENTER,
            colors=[top_tint, bottom_tint],
        ),
        shadow=kwargs.pop(
            "shadow",
            ft.BoxShadow(
                blur_radius=6,
                spread_radius=0,
                color="#10000000",
                offset=ft.Offset(0, 2),
            ),
        ),
        border_radius=ft.BorderRadius.all(RADIUS),
        padding=ft.Padding.all(d.SPACE_XS),
        alignment=ft.Alignment.CENTER,
        **kwargs,
    )


def _card_with_handles(cell: Cell, height: float, width: float, shadow: ft.BoxShadow) -> ft.Control:
    """드래그 중 손끝을 따라다니는 피드백 카드. 모퉁이 곡선 보조선을 함께 포함해 옮겨질 자리를 일체감 있게 표시한다."""
    card = _card(cell, height=height, width=width, shadow=shadow)
    arc_color = ft.Colors.with_opacity(0.48, text_color(cell.color))

    def corner_arc(is_top: bool, is_left: bool) -> ft.Container:
        border_kwargs: dict[str, ft.BorderSide] = {}
        radius_kwargs: dict[str, float] = {}
        if is_top:
            border_kwargs["top"] = ft.BorderSide(2.5, arc_color)
        else:
            border_kwargs["bottom"] = ft.BorderSide(2.5, arc_color)

        if is_left:
            border_kwargs["left"] = ft.BorderSide(2.5, arc_color)
            if is_top:
                radius_kwargs["top_left"] = RADIUS
            else:
                radius_kwargs["bottom_left"] = RADIUS
        else:
            border_kwargs["right"] = ft.BorderSide(2.5, arc_color)
            if is_top:
                radius_kwargs["top_right"] = RADIUS
            else:
                radius_kwargs["bottom_right"] = RADIUS

        pos: dict[str, float] = {}
        if is_top:
            pos["top"] = 4
        else:
            pos["bottom"] = 4
        if is_left:
            pos["left"] = 4
        else:
            pos["right"] = 4

        return ft.Container(
            width=22,
            height=22,
            border=ft.Border(**border_kwargs),
            border_radius=ft.BorderRadius.only(**radius_kwargs),
            bgcolor=ft.Colors.TRANSPARENT,
            **pos,
        )

    return ft.Stack(
        [
            card,
            corner_arc(True, True),
            corner_arc(True, False),
            corner_arc(False, True),
            corner_arc(False, False),
        ],
        width=width,
        height=height,
    )


def _block(block: Block, top: float, ctx: _Ctx) -> list[ft.Control]:
    """수업 묶음 하나 (+ 수정 모드면 가장자리 손잡이). Stack 안에 놓을 컨트롤들을 돌려준다."""
    cell = block.cell
    key = cell_key(block.day, block.start)
    height = span_height(block.span, ctx.cell_height)

    if ctx.drag_mode:
        interaction: dict = {}
    else:
        interaction = {
            "ink": ctx.on_click is not None or ctx.on_long_press is not None,
            "on_click": (lambda e: ctx.on_click(key)) if ctx.on_click else None,
            "on_long_press": (lambda e: ctx.on_long_press(key)) if ctx.on_long_press else None,
        }

    keys = {cell_key(block.day, p) for p in range(block.start, block.end + 1)}
    if cell is None:
        base: ft.Container = ft.Container(
            height=height,
            border=ft.Border.all(1, ft.Colors.with_opacity(0.45, d.HAIRLINE)),
            border_radius=ft.BorderRadius.all(RADIUS),
            bgcolor=ft.Colors.with_opacity(0.22, "#FFFFFF"),
            **interaction,
        )
    else:
        base = _card(cell, height=height, **interaction)
        if keys & ctx.landing_keys:
            # 방금 놓은 수업: 랙 없이 즉각 정돈되도록 정적으로 렌더링
            if ctx.landing_controls is not None:
                ctx.landing_controls.append(base)

    handles_holder: list[ft.Control] = []
    content: ft.Control = base
    half_gap = GAP / 2.0
    if ctx.drag_mode:
        # 셀과 셀 사이 빈 공간(GAP)에서도 가장 가까운 셀로 하이라이트 및 드롭이 연결되도록
        # DragTarget 반응 영역을 상하좌우 half_gap만큼 확장하고, 카드는 margin으로 원위치 정렬한다.
        base.margin = ft.Margin(top=half_gap, bottom=half_gap, left=half_gap, right=half_gap)
        content = _drag_wrap(base, block, key, height, ctx, handles_holder)
        holder_top = top - half_gap
        holder_height = height + GAP
        holder_left = -half_gap
        holder_right = -half_gap
    else:
        holder_top = top
        holder_height = height
        holder_left = 0
        holder_right = 0

    # 일반 보기 모드에서는 수십 개 셀의 애니메이션 컨트롤러를 꺼서 GPU/메모리 부하를 방지한다
    needs_anim = bool(ctx.drag_mode or (keys & ctx.landing_keys))
    anim = ft.Animation(170, ft.AnimationCurve.EASE_OUT_CUBIC) if needs_anim else None

    holder = ft.Container(
        content,
        top=holder_top,
        left=holder_left,
        right=holder_right,
        height=holder_height,
        animate_position=anim,
        animate_size=anim,
    )
    if not (ctx.drag_mode and cell is not None):
        return [holder]
    handles = _handles(holder, block, top, height, ctx)
    handles_holder.extend(handles)
    return [holder, *handles]


def _guide_corner_arcs(arc_color: str) -> list[ft.Container]:
    """옮겨질 자리를 표시하는 4개 모퉁이 곡선 보조선."""
    def corner_arc(is_top: bool, is_left: bool) -> ft.Container:
        border_kwargs: dict[str, ft.BorderSide] = {}
        radius_kwargs: dict[str, float] = {}
        if is_top:
            border_kwargs["top"] = ft.BorderSide(2.5, arc_color)
        else:
            border_kwargs["bottom"] = ft.BorderSide(2.5, arc_color)

        if is_left:
            border_kwargs["left"] = ft.BorderSide(2.5, arc_color)
            if is_top:
                radius_kwargs["top_left"] = RADIUS
            else:
                radius_kwargs["bottom_left"] = RADIUS
        else:
            border_kwargs["right"] = ft.BorderSide(2.5, arc_color)
            if is_top:
                radius_kwargs["top_right"] = RADIUS
            else:
                radius_kwargs["bottom_right"] = RADIUS

        pos: dict[str, float] = {}
        if is_top:
            pos["top"] = 4
        else:
            pos["bottom"] = 4
        if is_left:
            pos["left"] = 4
        else:
            pos["right"] = 4

        return ft.Container(
            width=22,
            height=22,
            border=ft.Border(**border_kwargs),
            border_radius=ft.BorderRadius.only(**radius_kwargs),
            bgcolor=ft.Colors.TRANSPARENT,
            **pos,
        )

    return [
        corner_arc(True, True),
        corner_arc(True, False),
        corner_arc(False, True),
        corner_arc(False, False),
    ]


def _drag_wrap(
    base: ft.Container,
    block: Block,
    key: str,
    height: float,
    ctx: _Ctx,
    handles_holder: list[ft.Control] | None = None,
) -> ft.Control:
    """수정 모드: 수업은 끌 수 있고, 모든 칸(빈 칸 포함)은 놓을 자리가 된다."""
    orig_border = base.border
    orig_shadow = base.shadow
    orig_bgcolor = base.bgcolor

    # 옮겨질 자리를 실시간으로 표시하는 모퉁이 보조선 스택
    guide_stack = ft.Stack(_guide_corner_arcs(d.LINK), expand=True, visible=False)
    if base.content is None:
        base.content = guide_stack
    else:
        # 기존 수업 내용물 위에 가이드 보조선을 오버레이
        base.content = ft.Stack([base.content, guide_stack], expand=True)

    is_highlighted = [False]

    def set_hover(active: bool, is_top: bool = True, is_bottom: bool = True) -> None:
        if active == is_highlighted[0] and (not active or (guide_stack.controls[0].visible == is_top and guide_stack.controls[2].visible == is_bottom)):
            return
        is_highlighted[0] = active
        guide_stack.visible = active
        if active:
            # 옮겨질 수업 크기에 맞춰 모퉁이 보조선 표시: 최상단은 상단 호, 최하단은 하단 호, 1칸이면 4개 모두 표시
            guide_stack.controls[0].visible = is_top
            guide_stack.controls[1].visible = is_top
            guide_stack.controls[2].visible = is_bottom
            guide_stack.controls[3].visible = is_bottom

            # 테두리: 단독 1칸이면 all(2), 연속 칸이면 맞닿는 중간선은 은은하게 연결
            if is_top and is_bottom:
                base.border = ft.Border.all(2, d.LINK)
            elif is_top:
                base.border = ft.Border(
                    top=ft.BorderSide(2, d.LINK),
                    left=ft.BorderSide(2, d.LINK),
                    right=ft.BorderSide(2, d.LINK),
                    bottom=ft.BorderSide(1, ft.Colors.with_opacity(0.35, d.LINK)),
                )
            elif is_bottom:
                base.border = ft.Border(
                    bottom=ft.BorderSide(2, d.LINK),
                    left=ft.BorderSide(2, d.LINK),
                    right=ft.BorderSide(2, d.LINK),
                    top=ft.BorderSide(1, ft.Colors.with_opacity(0.35, d.LINK)),
                )
            else:
                base.border = ft.Border(
                    left=ft.BorderSide(2, d.LINK),
                    right=ft.BorderSide(2, d.LINK),
                    top=ft.BorderSide(1, ft.Colors.with_opacity(0.35, d.LINK)),
                    bottom=ft.BorderSide(1, ft.Colors.with_opacity(0.35, d.LINK)),
                )

            if block.cell is None:
                base.bgcolor = ft.Colors.with_opacity(0.18, d.LINK)
            base.shadow = ft.BoxShadow(
                blur_radius=12,
                spread_radius=1,
                color="#302060FF",
                offset=ft.Offset(0, 2),
            )
        else:
            guide_stack.controls[0].visible = True
            guide_stack.controls[1].visible = True
            guide_stack.controls[2].visible = True
            guide_stack.controls[3].visible = True
            base.border = orig_border
            base.bgcolor = orig_bgcolor
            base.shadow = orig_shadow
        try:
            guide_stack.update()
            base.update()
        except Exception:
            pass

    def get_sub_key(e) -> str:
        if block.span <= 1:
            return key
        y = None
        pos = getattr(e, "local_position", None)
        if pos is not None and hasattr(pos, "y"):
            y = pos.y
        elif hasattr(e, "local_y"):
            y = e.local_y
        elif hasattr(e, "y"):
            y = e.y
        if y is not None:
            row_step = ctx.cell_height + GAP
            p_idx = int(y // row_step)
            p_idx = max(0, min(block.span - 1, p_idx))
            return cell_key(block.day, block.start + p_idx)
        return key

    ctx.hover_registry[key] = set_hover

    def handle_will_accept(e) -> None:
        sub_k = get_sub_key(e)
        ctx.highlight_slot(sub_k)

    def handle_move(e) -> None:
        sub_k = get_sub_key(e)
        ctx.highlight_slot(sub_k)

    def handle_leave(e) -> None:
        # 셀 사이 빈 공간에 커서가 있어도 하이라이트가 꺼지지 않고 가장 가까운/최근 셀로 유지
        pass

    def handle_accept(e: ft.DragTargetEvent) -> None:
        ctx.clear_highlight()
        sub_k = get_sub_key(e)
        src = ctx.active_drag_key or ctx.last_drag_key
        if not src:
            if hasattr(e, "src_id") and e.src_id and e.control and e.control.page:
                ctrl = e.control.page.get_control(e.src_id)
                if ctrl and hasattr(ctrl, "data") and ctrl.data:
                    src = ctrl.data
        if not src and hasattr(e, "src") and hasattr(e.src, "data"):
            src = e.src.data
        if not src and hasattr(e, "data") and e.data:
            src = e.data
        if src and src != sub_k and ctx.on_move_cell:
            ctx.on_move_cell(src, sub_k)
        ctx.active_drag_key = None
        ctx.last_drag_key = None
        ctx.active_drag_span = 1

    target = ft.DragTarget(
        group="cells",
        content=base,
        on_accept=handle_accept,
        on_will_accept=handle_will_accept,
        on_move=handle_move,
        on_leave=handle_leave,
        data=key,
    )
    cell = block.cell
    if cell is None:
        return target

    def on_drag_start(e) -> None:
        ctx.active_drag_key = key
        ctx.last_drag_key = key
        ctx.active_drag_span = block.span
        # 원래 자리에 남아있는 모퉁이 보조 선들을 즉시 숨겨 깨끗한 빈 칸만 남김
        if handles_holder:
            for h in handles_holder:
                h.visible = False
                try:
                    h.update()
                except Exception:
                    pass
        if ctx.on_drag_change:
            ctx.on_drag_change(True, key)

    def on_drag_complete(e) -> None:
        ctx.active_drag_key = None
        ctx.active_drag_span = 1
        ctx.clear_highlight()
        # 드래그가 끝나면 모퉁이 보조 선 복원
        if handles_holder:
            for h in handles_holder:
                h.visible = True
                try:
                    h.update()
                except Exception:
                    pass
        if ctx.on_drag_change:
            ctx.on_drag_change(False, None)

    # 수업 카드가 드래그되어 들려있는 동안, 원래 자리를 1교시 기본 크기의 셀들로 나누어 표시
    # (3개짜리 수업이어도 원래 자리가 개별 셀로 나뉘어 다른 셀들과 동일하게 하이라이트 가능)
    if block.span > 1:
        sub_bases: list[ft.Container] = []
        for p in range(block.start, block.end + 1):
            sub_k = cell_key(block.day, p)
            s_guide = ft.Stack(_guide_corner_arcs(d.LINK), expand=True, visible=False)
            s_base = ft.Container(
                content=s_guide,
                height=ctx.cell_height,
                border=ft.Border.all(1, ft.Colors.with_opacity(0.45, d.HAIRLINE)),
                border_radius=ft.BorderRadius.all(RADIUS),
                bgcolor=ft.Colors.with_opacity(0.22, "#FFFFFF"),
            )
            sub_bases.append(s_base)

            # 드래그 중 원래 자리의 각 셀에 마우스가 올라왔을 때의 독립적인 하이라이트 제어
            def make_sub_hover(base_ctrl: ft.Container, guide_ctrl: ft.Stack):
                is_sub_hl = [False]

                def sub_hover_fn(active: bool, is_top: bool = True, is_bottom: bool = True) -> None:
                    if active == is_sub_hl[0] and (not active or (guide_ctrl.controls[0].visible == is_top and guide_ctrl.controls[2].visible == is_bottom)):
                        return
                    is_sub_hl[0] = active
                    guide_ctrl.visible = active
                    if active:
                        guide_ctrl.controls[0].visible = is_top
                        guide_ctrl.controls[1].visible = is_top
                        guide_ctrl.controls[2].visible = is_bottom
                        guide_ctrl.controls[3].visible = is_bottom
                        if is_top and is_bottom:
                            base_ctrl.border = ft.Border.all(2, d.LINK)
                        elif is_top:
                            base_ctrl.border = ft.Border(
                                top=ft.BorderSide(2, d.LINK),
                                left=ft.BorderSide(2, d.LINK),
                                right=ft.BorderSide(2, d.LINK),
                                bottom=ft.BorderSide(1, ft.Colors.with_opacity(0.35, d.LINK)),
                            )
                        elif is_bottom:
                            base_ctrl.border = ft.Border(
                                bottom=ft.BorderSide(2, d.LINK),
                                left=ft.BorderSide(2, d.LINK),
                                right=ft.BorderSide(2, d.LINK),
                                top=ft.BorderSide(1, ft.Colors.with_opacity(0.35, d.LINK)),
                            )
                        else:
                            base_ctrl.border = ft.Border(
                                left=ft.BorderSide(2, d.LINK),
                                right=ft.BorderSide(2, d.LINK),
                                top=ft.BorderSide(1, ft.Colors.with_opacity(0.35, d.LINK)),
                                bottom=ft.BorderSide(1, ft.Colors.with_opacity(0.35, d.LINK)),
                            )
                        base_ctrl.bgcolor = ft.Colors.with_opacity(0.18, d.LINK)
                        base_ctrl.shadow = ft.BoxShadow(
                            blur_radius=12,
                            spread_radius=1,
                            color="#302060FF",
                            offset=ft.Offset(0, 2),
                        )
                    else:
                        guide_ctrl.controls[0].visible = True
                        guide_ctrl.controls[1].visible = True
                        guide_ctrl.controls[2].visible = True
                        guide_ctrl.controls[3].visible = True
                        base_ctrl.border = ft.Border.all(1, ft.Colors.with_opacity(0.45, d.HAIRLINE))
                        base_ctrl.bgcolor = ft.Colors.with_opacity(0.22, "#FFFFFF")
                        base_ctrl.shadow = None
                    try:
                        guide_ctrl.update()
                        base_ctrl.update()
                    except Exception:
                        pass

                return sub_hover_fn

            ctx.hover_registry[sub_k] = make_sub_hover(s_base, s_guide)

        placeholder = ft.Column(
            sub_bases,
            spacing=GAP,
            tight=True,
        )
    else:
        p_guide = ft.Stack(_guide_corner_arcs(d.LINK), expand=True, visible=False)
        placeholder = ft.Container(
            content=p_guide,
            height=height,
            border=ft.Border.all(1, ft.Colors.with_opacity(0.45, d.HAIRLINE)),
            border_radius=ft.BorderRadius.all(RADIUS),
            bgcolor=ft.Colors.with_opacity(0.22, "#FFFFFF"),
        )
        # 1칸 수업이 드래그 중 제자리로 돌아올 때도 placeholder가 정상 하이라이트되도록 연결
        orig_set_hover = set_hover

        def single_hover_fn(active: bool, is_top: bool = True, is_bottom: bool = True) -> None:
            orig_set_hover(active, is_top, is_bottom)
            p_guide.visible = active
            if active:
                p_guide.controls[0].visible = is_top
                p_guide.controls[1].visible = is_top
                p_guide.controls[2].visible = is_bottom
                p_guide.controls[3].visible = is_bottom
                placeholder.border = ft.Border.all(2, d.LINK)
                placeholder.bgcolor = ft.Colors.with_opacity(0.18, d.LINK)
                placeholder.shadow = ft.BoxShadow(
                    blur_radius=12,
                    spread_radius=1,
                    color="#302060FF",
                    offset=ft.Offset(0, 2),
                )
            else:
                p_guide.controls[0].visible = True
                p_guide.controls[1].visible = True
                p_guide.controls[2].visible = True
                p_guide.controls[3].visible = True
                placeholder.border = ft.Border.all(1, ft.Colors.with_opacity(0.45, d.HAIRLINE))
                placeholder.bgcolor = ft.Colors.with_opacity(0.22, "#FFFFFF")
                placeholder.shadow = None
            try:
                p_guide.update()
                placeholder.update()
            except Exception:
                pass

        ctx.hover_registry[key] = single_hover_fn

    target.content = ft.Draggable(
        group="cells",
        data=key,
        content=base,
        # 손끝을 따라다니는 피드백 카드에 모퉁이 보조 선을 포함하여 옮겨질 자리를 일체감 있게 표시
        content_feedback=_card_with_handles(
            cell,
            height=height,
            width=ctx.cell_width or FEEDBACK_FALLBACK_WIDTH,
            shadow=ft.BoxShadow(
                blur_radius=16, spread_radius=1, color="#35000000", offset=ft.Offset(0, 6)
            ),
        ),
        # 원래 자리는 기본 셀 크기들로 나뉘어져 남는다
        content_when_dragging=placeholder,
        on_drag_start=on_drag_start,
        on_drag_complete=on_drag_complete,
    )
    return target


def _handles(
    holder: ft.Container, block: Block, top: float, height: float, ctx: _Ctx
) -> list[ft.Control]:
    """수업 모퉁이의 얇고 투명한 곡선 손잡이. 터치 반응 속도를 극대화하고 손을 놓을 때 부드러운 스냅 애니메이션 적용."""
    assert block.cell is not None
    arc_color = ft.Colors.with_opacity(0.42, text_color(block.cell.color))
    row_step = ctx.cell_height + GAP
    col_step = (ctx.cell_width or FEEDBACK_FALLBACK_WIDTH) + GAP
    cell_h = ctx.cell_height
    moved_x = [0.0]
    moved_y = [0.0]

    all_handles: list[ft.Container] = []

    def preview(top_edge: bool | None, left_edge: bool | None) -> None:
        dx, dy = moved_x[0], moved_y[0]
        cur_top, cur_h = top, height
        cur_l, cur_r = 0.0, 0.0

        if top_edge is True:
            clamped_dy = min(dy, height - cell_h)
            cur_top, cur_h = top + clamped_dy, height - clamped_dy
        elif top_edge is False:
            cur_h = max(cell_h, height + dy)

        if left_edge is True:
            cur_l = min(0.0, dx)
        elif left_edge is False:
            cur_r = min(0.0, -dx)

        # 조절 중에는 손끝을 지연 없이 즉각 따라가도록 애니메이션 해제
        holder.animate_position = None
        holder.animate_size = None
        half_gap = GAP / 2.0
        holder.top = cur_top - half_gap
        holder.height = cur_h + GAP
        holder.left = cur_l - half_gap
        holder.right = cur_r - half_gap
        try:
            holder.update()
        except Exception:
            pass

        # 모퉁이 표시선(핸들)도 늘어나는 수업 카드 모퉁이 위치를 실시간으로 따라가도록 동기화
        if len(all_handles) == 4:
            tl, tr, bl, br = all_handles
            for h in all_handles:
                h.animate_position = None

            tl.top = cur_top
            tl.left = cur_l

            tr.top = cur_top
            tr.right = cur_r

            bl.top = cur_top + cur_h - HANDLE
            bl.left = cur_l

            br.top = cur_top + cur_h - HANDLE
            br.right = cur_r

            for h in all_handles:
                try:
                    h.update()
                except Exception:
                    pass

    def finish(top_edge: bool | None, left_edge: bool | None) -> None:
        dx, dy = moved_x[0], moved_y[0]
        moved_x[0], moved_y[0] = 0.0, 0.0

        # 손을 놓았을 때 격자 칸에 스냅될 최종 목표 위치 계산
        target_top, target_h = top, height
        target_l, target_r = 0.0, 0.0

        steps_y = 0
        if top_edge is True:
            steps_y = round(dy / row_step)
            new_start = max(PERIOD_MIN, min(block.end, block.start + steps_y))
            actual_steps = new_start - block.start
            target_top = top + actual_steps * row_step
            target_h = height - actual_steps * row_step
        elif top_edge is False:
            steps_y = round(dy / row_step)
            new_end = min(PERIOD_MAX, max(block.start, block.end + steps_y))
            actual_steps = new_end - block.end
            target_top = top
            target_h = height + actual_steps * row_step

        steps_x = 0
        if left_edge is not None:
            raw_steps_x = round(dx / col_step)
            if (left_edge and raw_steps_x > 0) or (not left_edge and raw_steps_x < 0):
                steps_x = 0
            else:
                steps_x = raw_steps_x
            if steps_x != 0:
                if left_edge:
                    target_l = min(0.0, steps_x * col_step)
                else:
                    target_r = min(0.0, -steps_x * col_step)

        if steps_y == 0 and steps_x == 0:
            # 이동 변화 없음: 원래 자리로 부드럽게 복귀
            half_gap = GAP / 2.0
            try:
                holder.animate_position = ft.Animation(170, ft.AnimationCurve.EASE_OUT_CUBIC)
                holder.animate_size = ft.Animation(170, ft.AnimationCurve.EASE_OUT_CUBIC)
                holder.top, holder.height, holder.left, holder.right = top - half_gap, height + GAP, -half_gap, -half_gap
                holder.update()
            except Exception:
                pass
            if len(all_handles) == 4:
                tl, tr, bl, br = all_handles
                for h in all_handles:
                    try:
                        h.animate_position = ft.Animation(170, ft.AnimationCurve.EASE_OUT_CUBIC)
                    except Exception:
                        pass
                tl.top, tl.left = top, 0
                tr.top, tr.right = top, 0
                bl.top, bl.left = top + height - HANDLE, 0
                br.top, br.right = top + height - HANDLE, 0
                for h in all_handles:
                    try:
                        h.update()
                    except Exception:
                        pass
            return

        # 손을 놓았을 때 화면상으로 먼저 목표 위치 스냅 애니메이션 적용 (과한 튕김 없이 부드럽게 감속)
        half_gap = GAP / 2.0
        try:
            holder.animate_position = ft.Animation(170, ft.AnimationCurve.EASE_OUT_CUBIC)
            holder.animate_size = ft.Animation(170, ft.AnimationCurve.EASE_OUT_CUBIC)
            holder.top = target_top - half_gap
            holder.height = target_h + GAP
            holder.left = target_l - half_gap
            holder.right = target_r - half_gap
            holder.update()
        except Exception:
            pass

        if len(all_handles) == 4:
            tl, tr, bl, br = all_handles
            for h in all_handles:
                try:
                    h.animate_position = ft.Animation(170, ft.AnimationCurve.EASE_OUT_CUBIC)
                except Exception:
                    pass
            tl.top, tl.left = target_top, target_l
            tr.top, tr.right = target_top, target_r
            bl.top, bl.left = target_top + target_h - HANDLE, target_l
            br.top, br.right = target_top + target_h - HANDLE, target_r
            for h in all_handles:
                try:
                    h.update()
                except Exception:
                    pass

        # 데이터 업데이트 처리 (컨트롤러 내부에서 self.render()가 불려 전체 그리드가 갱신됨)
        if top_edge is not None and steps_y and ctx.on_resize_block:
            if top_edge:
                ctx.on_resize_block(block.day, block.start, block.end, block.start + steps_y, block.end)
            else:
                ctx.on_resize_block(block.day, block.start, block.end, block.start, block.end + steps_y)
        elif left_edge is not None and steps_x and ctx.on_extend_block:
            ctx.on_extend_block(block.day, block.start, block.end, block.day + steps_x)

        # 주의: 컨트롤러 호출 후에는 holder가 이미 이전 페이지 트리의 객체이므로 holder.update()를 부르지 않는다!

    def corner_widget(corner: str) -> ft.Container:
        is_top = 'top' in corner
        is_left = 'left' in corner

        def on_pan_update(e: ft.DragUpdateEvent) -> None:
            if hasattr(e, 'local_delta') and e.local_delta:
                moved_x[0] += e.local_delta.x
                moved_y[0] += e.local_delta.y
            elif hasattr(e, 'primary_delta') and e.primary_delta:
                moved_x[0] += e.primary_delta
                moved_y[0] += e.primary_delta
            preview(is_top, is_left)

        def on_pan_end(e) -> None:
            finish(is_top, is_left)

        # 셀의 둥근 모서리(RADIUS) 굴곡을 따라 살짝 휜 선 (Arc line)
        border_kwargs: dict[str, ft.BorderSide] = {}
        radius_kwargs: dict[str, float] = {}
        if is_top:
            border_kwargs["top"] = ft.BorderSide(2.5, arc_color)
        else:
            border_kwargs["bottom"] = ft.BorderSide(2.5, arc_color)

        if is_left:
            border_kwargs["left"] = ft.BorderSide(2.5, arc_color)
            if is_top:
                radius_kwargs["top_left"] = RADIUS
            else:
                radius_kwargs["bottom_left"] = RADIUS
        else:
            border_kwargs["right"] = ft.BorderSide(2.5, arc_color)
            if is_top:
                radius_kwargs["top_right"] = RADIUS
            else:
                radius_kwargs["bottom_right"] = RADIUS

        curved_arc = ft.Container(
            width=22,
            height=22,
            border=ft.Border(**border_kwargs),
            border_radius=ft.BorderRadius.only(**radius_kwargs),
            bgcolor=ft.Colors.TRANSPARENT,
        )

        align = (
            ft.Alignment.TOP_LEFT if (is_top and is_left)
            else ft.Alignment.TOP_RIGHT if (is_top and not is_left)
            else ft.Alignment.BOTTOM_LEFT if (not is_top and is_left)
            else ft.Alignment.BOTTOM_RIGHT
        )

        pad = ft.Padding(
            left=4 if is_left else 0,
            right=4 if not is_left else 0,
            top=4 if is_top else 0,
            bottom=4 if not is_top else 0,
        )

        detector = ft.GestureDetector(
            content=ft.Container(
                curved_arc,
                alignment=align,
                padding=pad,
            ),
            mouse_cursor=ft.MouseCursor.RESIZE_UP_LEFT_DOWN_RIGHT if (is_top == is_left) else ft.MouseCursor.RESIZE_UP_RIGHT_DOWN_LEFT,
            drag_interval=0,  # 딜레이 없이 실시간 반응
            on_pan_update=on_pan_update,
            on_pan_end=on_pan_end,
        )

        pos: dict[str, float] = {}
        if is_top:
            pos["top"] = top
        else:
            pos["top"] = top + height - HANDLE

        if is_left:
            pos["left"] = 0
        else:
            pos["right"] = 0

        pos["width"] = HANDLE
        pos["height"] = HANDLE
        return ft.Container(detector, **pos)

    tl = corner_widget("top_left")
    tr = corner_widget("top_right")
    bl = corner_widget("bottom_left")
    br = corner_widget("bottom_right")
    all_handles.extend([tl, tr, bl, br])
    return all_handles
