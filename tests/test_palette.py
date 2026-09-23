import re

import pytest

from app.palette import (
    BACKGROUND_LABELS,
    BACKGROUNDS,
    BLACK,
    DEFAULT_BACKGROUND,
    DEFAULT_COLOR,
    PALETTE,
    WHITE,
    background_hex,
    contrast_ratio,
    resolve_hex,
    text_color,
)


def test_at_least_16_colors():
    assert len(PALETTE) >= 16
    assert DEFAULT_COLOR in PALETTE


def test_hex_format():
    for key, hex_ in PALETTE.items():
        assert re.fullmatch(r"#[0-9A-F]{6}", hex_), key


@pytest.mark.parametrize("key", list(PALETTE))
def test_text_color_picks_higher_contrast(key):
    chosen = text_color(key)
    other = WHITE if chosen == BLACK else BLACK
    assert contrast_ratio(key, chosen) >= contrast_ratio(key, other)
    assert contrast_ratio(key, chosen) >= 4.5


def test_known_text_colors():
    assert text_color("yellow") == BLACK
    assert text_color("#000000") == WHITE
    assert text_color("#FFFFFF") == BLACK


def test_unknown_color_raises():
    with pytest.raises(ValueError):
        text_color("not-a-color")


# ---- 배경색 (F9, spec 2.5.1)


def test_backgrounds_are_pale_and_labelled():
    assert len(BACKGROUNDS) >= 6
    assert BACKGROUNDS.keys() == BACKGROUND_LABELS.keys()
    assert BACKGROUNDS[DEFAULT_BACKGROUND] == "#FFFFFF"
    for key, hex_color in BACKGROUNDS.items():
        assert resolve_hex(hex_color) == hex_color  # 형식 검사
        # 먹색 글자가 읽히고, 흰 빈 칸과도 구분될 만큼만 연한 색
        assert contrast_ratio(hex_color, "#181D26") >= 12, key
        assert contrast_ratio(hex_color, "#FFFFFF") <= 1.2, key


def test_background_hex_falls_back_to_default():
    assert background_hex("ivory") == BACKGROUNDS["ivory"]
    assert background_hex("없는색") == BACKGROUNDS[DEFAULT_BACKGROUND]
