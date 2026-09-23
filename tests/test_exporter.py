"""이미지 내보내기 (F6, spec 3.4)."""

from datetime import date
from io import BytesIO

import pytest
from PIL import Image

from app.exporter import (
    ExportOptions,
    Layout,
    export_filename,
    font_path,
    has_cjk_font,
    load_font,
    render,
    wrap_text,
)
from app.model import Cell, Settings, Workspace
from app.sample import sample_data

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SIGNATURE = b"\xff\xd8\xff"


@pytest.fixture
def workspace() -> Workspace:
    return Workspace(sample_data())


def open_image(data: bytes) -> Image.Image:
    return Image.open(BytesIO(data))


# ---- 형식


def test_png_signature_and_size(workspace):
    settings = workspace.data.settings
    data = render(workspace.active, settings)
    assert data.startswith(PNG_SIGNATURE)
    image = open_image(data)
    assert image.mode == "RGBA"
    assert image.size == (Layout(settings).width, Layout(settings).height)


def test_jpg_is_flattened_on_white(workspace):
    data = render(workspace.active, workspace.data.settings, ExportOptions(fmt="jpg"))
    assert data.startswith(JPEG_SIGNATURE)
    image = open_image(data)
    assert image.mode == "RGB"
    assert image.getpixel((0, 0)) == (255, 255, 255)  # 바깥 여백은 흰 배경


def test_png_background_is_transparent(workspace):
    image = open_image(render(workspace.active, workspace.data.settings))
    assert image.getpixel((0, 0))[3] == 0


def test_scale_doubles_size(workspace):
    settings = workspace.data.settings
    one = open_image(render(workspace.active, settings)).size
    two = open_image(render(workspace.active, settings, ExportOptions(scale=2))).size
    assert two == (one[0] * 2, one[1] * 2)


@pytest.mark.parametrize("options", [ExportOptions(fmt="gif"), ExportOptions(scale=3)])
def test_unsupported_options(workspace, options):
    with pytest.raises(ValueError):
        render(workspace.active, workspace.data.settings, options)


# ---- 설정 반영


def test_empty_timetable_renders(workspace):
    workspace.clear_timetable()
    data = render(workspace.active, workspace.data.settings)
    assert data.startswith(PNG_SIGNATURE)


def test_six_days_and_seven_periods_are_larger(workspace):
    small = Settings()
    large = Settings(days=6, periods=7)
    assert Layout(large).width > Layout(small).width
    assert Layout(large).height > Layout(small).height
    image = open_image(render(workspace.active, large))
    assert image.size == (Layout(large).width, Layout(large).height)


def test_period_times_widen_the_label_column():
    plain = Settings()
    with_times = Settings(show_times=True)
    assert Layout(with_times).width > Layout(plain).width


def test_cell_colors_are_drawn(workspace):
    settings = workspace.data.settings
    layout = Layout(settings)
    image = open_image(render(workspace.active, settings))
    left, top, right, bottom = layout.cell_box(0, 0)  # 월 1교시 = 알고리즘(blue)
    assert image.getpixel(((left + right) // 2, top + 6))[:3] == (0x42, 0xA5, 0xF5)


# ---- 줄바꿈과 말줄임


def test_wrap_text_breaks_and_truncates():
    font = load_font(13)
    short = wrap_text("영어", font, 96, 3)
    assert short == ["영어"]

    long_subject = "컴퓨터네트워크와 분산시스템 설계 특론 심화 세미나 추가 내용"
    lines = wrap_text(long_subject, font, 96, 3)
    assert len(lines) == 3
    assert lines[-1].endswith("…")
    assert all(font.getlength(line) <= 96 for line in lines)


def test_wrap_text_handles_empty_and_single_char():
    font = load_font(13)
    assert wrap_text("", font, 96, 3) == [""]
    assert wrap_text("가", font, 96, 3) == ["가"]


def test_long_subject_renders(workspace):
    workspace.set_cell("0-1", Cell(subject="가" * 30, room="창의관 3층 3강의실", color="red"))
    data = render(workspace.active, workspace.data.settings)
    assert data.startswith(PNG_SIGNATURE)


# ---- 한글·일본어


CJK_SAMPLE = "한국어체육日本語会話応用"


def test_cjk_font_is_available():
    assert has_cjk_font(), "CJK 폰트를 찾지 못했습니다 (app.exporter.FONT_CANDIDATES 확인)"


def test_font_covers_korean_and_japanese():
    """없는 글자는 두부(□)로 그려진다 — 전용 영역 문자와 같은 모양이면 빠진 글자."""
    font = load_font(13)
    tofu = bytes(font.getmask("", mode="L"))
    missing = [char for char in CJK_SAMPLE if bytes(font.getmask(char, mode="L")) == tofu]
    assert not missing, f"폰트에 없는 글자: {''.join(missing)} ({font_path()})"


def test_korean_and_japanese_draw_different_glyphs(workspace):
    """같은 길이의 한글·일본어가 다르게 그려지면 글자가 두부(□)로 깨지지 않은 것."""
    settings = workspace.data.settings
    workspace.set_cell("0-1", Cell(subject="한국어", color="gray"))
    korean = render(workspace.active, settings)
    workspace.set_cell("0-1", Cell(subject="日本語", color="gray"))
    japanese = render(workspace.active, settings)
    assert korean != japanese

    blank = Cell(subject=" ".strip() or "x", color="gray")
    workspace.set_cell("0-1", blank)
    assert render(workspace.active, settings) != korean


# ---- 파일 이름


def test_export_filename():
    when = date(2026, 9, 17)
    assert export_filename("2026 후기", when) == "timetable_2026_후기_20260917.png"
    assert export_filename("2026 후기", when, "jpg") == "timetable_2026_후기_20260917.jpg"
    assert export_filename("a/b:c", when) == "timetable_a_b_c_20260917.png"
    assert export_filename("   ", when) == "timetable_timetable_20260917.png"
    with pytest.raises(ValueError):
        export_filename("이름", when, "gif")


# ---- 배경색 (F9, spec 3.4)


def background_pixel(data: bytes) -> tuple:
    return open_image(data).convert("RGBA").getpixel((1, 1))


def test_default_background_keeps_transparent_png(workspace):
    settings = workspace.data.settings
    assert background_pixel(render(workspace.active, settings))[3] == 0


def test_chosen_background_fills_png(workspace):
    from dataclasses import replace

    from app.palette import BACKGROUNDS

    settings = replace(workspace.data.settings, background="ivory")
    pixel = background_pixel(render(workspace.active, settings))
    assert pixel[3] == 255
    assert pixel[:3] == tuple(int(BACKGROUNDS["ivory"][i : i + 2], 16) for i in (1, 3, 5))


def test_chosen_background_applies_to_jpg(workspace):
    from dataclasses import replace

    settings = replace(workspace.data.settings, background="mint")
    data = render(workspace.active, settings, ExportOptions(fmt="jpg"))
    r, g, b = open_image(data).convert("RGB").getpixel((1, 1))
    assert (r, g, b) != (255, 255, 255) and min(r, g, b) > 220  # 연한 민트
