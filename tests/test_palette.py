import re

import pytest

from app.palette import BLACK, DEFAULT_COLOR, PALETTE, WHITE, contrast_ratio, text_color


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
