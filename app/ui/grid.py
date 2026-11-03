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
    period_times,
)
from app.palette import resolve_hex, text_color
from app.ui.theme import text

PERIOD_COL_WIDTH = 34
TIME_COL_WIDTH = 48  # 교시 시간을 함께 표시할 때 (F9)
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
LANDING_SCALE = 1.06  # 놓은 직후 크기 → 1.0으로 내려앉는다
LANDING_MS = 260
HANDLE = 12  # 수정 모드에서 수업 가장자리를 잡는 영역 두께
HANDLE_PILL = 16  # 가장자리 손잡이 표시 길이

KeyHandler = Callable[[str], None]
ResizeHandler = Callable[[int, int, int, int, int], None]  # (요일, 시작, 끝, 새 시작, 새 끝)
ExtendHandler = Callable[[int, int, int, int], None]  # (요일, 시작, 끝, 늘릴 요일)


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
    landing_keys: set[str] | None = None,
    landing_controls: list[ft.Control] | None = None,
    on_resize_block: ResizeHandler | None = None,
    on_extend_block: ExtendHandler | None = None,
) -> ft.Control:
    """핸들러가 None이면 해당 조작 없음 (읽기 전용).

    available_width: 그리드가 차지하는 가로 폭. 드래그 카드·옆으로 늘리기 계산에 칸 너비가 필요하다.
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
    ctx = _Ctx(
        on_click=on_cell_click,
        on_long_press=on_cell_long_press,
        drag_mode=drag_mode,
        on_move_cell=on_move_cell,
        cell_width=cell_width,
        landing_keys=landing_keys or set(),
        landing_controls=landing_controls,
        on_resize_block=on_resize_block,
        on_extend_block=on_extend_block,
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
    return ft.Column(rows, spacing=GAP, scroll=ft.ScrollMode.AUTO, expand=True)


class _Ctx:
    """칸을 그릴 때 공통으로 쓰는 핸들러·상태 묶음."""

    def __init__(self, **kwargs) -> None:
        self.on_click: KeyHandler | None = kwargs["on_click"]
        self.on_long_press: KeyHandler | None = kwargs["on_long_press"]
        self.drag_mode: bool = kwargs["drag_mode"]
        self.on_move_cell: Callable[[str, str], None] | None = kwargs["on_move_cell"]
        self.cell_width: float | None = kwargs["cell_width"]
        self.landing_keys: set[str] = kwargs["landing_keys"]
        self.landing_controls: list[ft.Control] | None = kwargs["landing_controls"]
        self.on_resize_block: ResizeHandler | None = kwargs["on_resize_block"]
        self.on_extend_block: ExtendHandler | None = kwargs["on_extend_block"]
        self.active_drag_key: str | None = None


def span_height(span: int) -> float:
    """교시 span개를 이어 붙인 높이 (사이 틈 포함)."""
    return span * CELL_HEIGHT + (span - 1) * GAP


def _day_column(blocks: list[Block], first: int, last: int, ctx: _Ctx) -> ft.Control:
    """한 요일의 세로 칸. 수업 묶음을 교시 위치에 겹쳐 놓는다."""
    children: list[ft.Control] = []
    for block in blocks:
        top = (block.start - first) * (CELL_HEIGHT + GAP)
        children.extend(_block(block, top, ctx))
    return ft.Container(
        ft.Stack(children, clip_behavior=ft.ClipBehavior.NONE),
        expand=1,
        height=span_height(last - first + 1),
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
        height=CELL_HEIGHT,
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
    """수업 칸의 모양. 그리드 칸과 드래그 중 손끝을 따라다니는 카드가 같은 모양을 쓴다."""
    return ft.Container(
        ft.Column(
            _card_lines(cell),
            spacing=2,
            tight=True,
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        height=height,
        bgcolor=resolve_hex(cell.color),
        border_radius=ft.BorderRadius.all(RADIUS),
        padding=ft.Padding.all(d.SPACE_XS),
        alignment=ft.Alignment.CENTER,
        **kwargs,
    )


def _block(block: Block, top: float, ctx: _Ctx) -> list[ft.Control]:
    """수업 묶음 하나 (+ 수정 모드면 가장자리 손잡이). Stack 안에 놓을 컨트롤들을 돌려준다."""
    cell = block.cell
    key = cell_key(block.day, block.start)
    height = span_height(block.span)

    if ctx.drag_mode:
        interaction: dict = {}
    else:
        interaction = {
            "ink": ctx.on_click is not None or ctx.on_long_press is not None,
            "on_click": (lambda e: ctx.on_click(key)) if ctx.on_click else None,
            "on_long_press": (lambda e: ctx.on_long_press(key)) if ctx.on_long_press else None,
        }

    if cell is None:
        base: ft.Container = ft.Container(
            height=height,
            border=ft.Border.all(1, d.HAIRLINE),
            border_radius=ft.BorderRadius.all(RADIUS),
            **interaction,
        )
    else:
        base = _card(cell, height=height, **interaction)
        keys = {cell_key(block.day, p) for p in range(block.start, block.end + 1)}
        if keys & ctx.landing_keys:
            # 방금 놓은 수업: 살짝 떠 있는 상태로 그린 뒤 제자리 크기로 부드럽게 내려앉힌다
            base.scale = LANDING_SCALE
            base.animate_scale = ft.Animation(LANDING_MS, ft.AnimationCurve.EASE_OUT_BACK)
            if ctx.landing_controls is not None:
                ctx.landing_controls.append(base)

    content: ft.Control = base
    if ctx.drag_mode:
        content = _drag_wrap(base, block, key, height, ctx)

    holder = ft.Container(content, top=top, left=0, right=0, height=height)
    if not (ctx.drag_mode and cell is not None):
        return [holder]
    return [holder, *_handles(holder, block, top, height, ctx)]


def _drag_wrap(base: ft.Container, block: Block, key: str, height: float, ctx: _Ctx) -> ft.Control:
    """수정 모드: 수업은 끌 수 있고, 모든 칸(빈 칸 포함)은 놓을 자리가 된다."""

    def handle_accept(e: ft.DragTargetEvent) -> None:
        src = ctx.active_drag_key
        if not src and hasattr(e, "src") and hasattr(e.src, "data"):
            src = e.src.data
        if src and src != key and ctx.on_move_cell:
            ctx.on_move_cell(src, key)
        ctx.active_drag_key = None

    target = ft.DragTarget(group="cells", content=base, on_accept=handle_accept, data=key)
    cell = block.cell
    if cell is None:
        return target

    def on_drag_start(e) -> None:
        ctx.active_drag_key = key

    def on_drag_complete(e) -> None:
        ctx.active_drag_key = None

    target.content = ft.Draggable(
        group="cells",
        data=key,
        content=base,
        # 손끝을 따라다니는 카드는 칸과 같은 크기·모양 그대로 (작아지지 않게)
        content_feedback=_card(
            cell,
            height=height,
            width=ctx.cell_width or FEEDBACK_FALLBACK_WIDTH,
            shadow=ft.BoxShadow(
                blur_radius=12, spread_radius=0, color="#33000000", offset=ft.Offset(0, 4)
            ),
        ),
        # 원래 자리는 빈 칸 모양으로 남겨 둔다
        content_when_dragging=ft.Container(
            height=height,
            border=ft.Border.all(1, d.HAIRLINE),
            border_radius=ft.BorderRadius.all(RADIUS),
        ),
        on_drag_start=on_drag_start,
        on_drag_complete=on_drag_complete,
    )
    return target


def _handles(
    holder: ft.Container, block: Block, top: float, height: float, ctx: _Ctx
) -> list[ft.Control]:
    """수업 가장자리 네 곳의 손잡이. 끄는 동안 수업 모양을 미리 늘여 보여 주고, 놓으면 칸 단위로 맞춘다."""
    assert block.cell is not None
    pill_color = ft.Colors.with_opacity(0.45, text_color(block.cell.color))
    row_step = CELL_HEIGHT + GAP
    col_step = (ctx.cell_width or FEEDBACK_FALLBACK_WIDTH) + GAP
    moved = [0.0]

    def preview(edge: str) -> None:
        delta = moved[0]
        if edge == "top":
            delta = min(delta, height - CELL_HEIGHT)
            holder.top, holder.height = top + delta, height - delta
        elif edge == "bottom":
            holder.height = max(CELL_HEIGHT, height + delta)
        elif edge == "left":
            holder.left = min(0, delta)
        else:
            holder.right = min(0, -delta)
        holder.update()

    def reset() -> None:
        holder.top, holder.height, holder.left, holder.right = top, height, 0, 0
        holder.update()

    def finish(edge: str) -> None:
        delta, moved[0] = moved[0], 0.0
        if edge in ("top", "bottom"):
            steps = round(delta / row_step)
            reset()
            if steps and ctx.on_resize_block:
                if edge == "top":
                    ctx.on_resize_block(block.day, block.start, block.end, block.start + steps, block.end)
                else:
                    ctx.on_resize_block(block.day, block.start, block.end, block.start, block.end + steps)
        else:
            steps = round(delta / col_step)
            if (edge == "left" and steps > 0) or (edge == "right" and steps < 0):
                steps = 0  # 옆으로는 늘리기만 한다 (줄이려면 늘어난 칸을 지운다)
            reset()
            if steps and ctx.on_extend_block:
                ctx.on_extend_block(block.day, block.start, block.end, block.day + steps)

    def handle(edge: str) -> ft.Control:
        vertical = edge in ("top", "bottom")

        def on_update(e: ft.DragUpdateEvent) -> None:
            moved[0] += e.primary_delta or 0
            preview(edge)

        def on_end(e) -> None:
            finish(edge)

        pill = ft.Container(
            width=HANDLE_PILL if vertical else 3,
            height=3 if vertical else HANDLE_PILL,
            bgcolor=pill_color,
            border_radius=ft.BorderRadius.all(2),
        )
        drag = {"on_vertical_drag_update": on_update, "on_vertical_drag_end": on_end} if vertical else {
            "on_horizontal_drag_update": on_update, "on_horizontal_drag_end": on_end
        }
        detector = ft.GestureDetector(
            content=ft.Container(pill, alignment=ft.Alignment.CENTER),
            mouse_cursor=ft.MouseCursor.RESIZE_UP_DOWN if vertical else ft.MouseCursor.RESIZE_LEFT_RIGHT,
            drag_interval=10,
            **drag,
        )
        if edge == "top":
            pos = {"top": top, "left": HANDLE, "right": HANDLE, "height": HANDLE}
        elif edge == "bottom":
            pos = {"top": top + height - HANDLE, "left": HANDLE, "right": HANDLE, "height": HANDLE}
        elif edge == "left":
            pos = {"top": top + HANDLE, "left": 0, "width": HANDLE, "height": height - 2 * HANDLE}
        else:
            pos = {"top": top + HANDLE, "right": 0, "width": HANDLE, "height": height - 2 * HANDLE}
        return ft.Container(detector, **pos)

    handles = []
    if ctx.on_extend_block:
        handles += [handle("left"), handle("right")]
    if ctx.on_resize_block:
        handles += [handle("top"), handle("bottom")]
    return handles
