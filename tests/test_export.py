"""내보내기 연결 (F6): 컨트롤러가 이미지 bytes와 파일명을 만든다."""

import json
from dataclasses import replace
from datetime import date
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from app.controller import AppController
from app.exporter import ExportOptions, Layout
from app.model import Cell, Settings, to_dict
from app.sample import sample_data
from app.storage import DATA_FILE, Storage

WHEN = date(2026, 9, 17)


@pytest.fixture
def ctrl(tmp_path: Path) -> AppController:
    controller, _ = AppController.open(Storage(tmp_path), seed=sample_data)
    return controller


def size_of(data: bytes) -> tuple[int, int]:
    return Image.open(BytesIO(data)).size


def test_export_png_of_active_timetable(ctrl):
    image, filename = ctrl.export_image(ExportOptions(), WHEN)
    assert image.startswith(b"\x89PNG\r\n\x1a\n")
    assert filename == "timetable_2026_후기_20260917.png"
    assert size_of(image) == (Layout(Settings()).width, Layout(Settings()).height)


def test_export_jpg_and_scale(ctrl):
    image, filename = ctrl.export_image(ExportOptions(fmt="jpg", scale=2), WHEN)
    assert image.startswith(b"\xff\xd8\xff")
    assert filename.endswith("_20260917.jpg")
    assert size_of(image) == (Layout(Settings(), 2).width, Layout(Settings(), 2).height)


def test_export_uses_current_settings(ctrl):
    ctrl.update_settings(Settings(days=6, periods=7, show_times=True))
    image, _ = ctrl.export_image(ExportOptions(), WHEN)
    expected = Layout(Settings(days=6, periods=7, show_times=True))
    assert size_of(image) == (expected.width, expected.height)


def test_export_follows_active_timetable(ctrl):
    ctrl.add_timetable("2027 전기")
    other = ctrl.workspace.data.visible()[1]
    ctrl.switch_timetable(other.id)
    ctrl.save_form(_form(ctrl, "0-1", "영어"))

    image, filename = ctrl.export_image(ExportOptions(), WHEN)
    assert filename == "timetable_2027_전기_20260917.png"

    first = ctrl.workspace.data.visible()[0]
    ctrl.switch_timetable(first.id)
    other_image, other_filename = ctrl.export_image(ExportOptions(), WHEN)
    assert other_filename == "timetable_2026_후기_20260917.png"
    assert other_image != image


def test_export_without_today_uses_current_date(ctrl):
    _, filename = ctrl.export_image(ExportOptions())
    assert filename == f"timetable_2026_후기_{date.today():%Y%m%d}.png"


def test_export_allowed_in_read_only_mode(tmp_path):
    raw = to_dict(sample_data())
    raw["schema_version"] = 99
    (tmp_path / DATA_FILE).write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    controller, _ = AppController.open(Storage(tmp_path))
    assert controller.read_only

    image, filename = controller.export_image(ExportOptions(), WHEN)  # 읽기 전용이어도 내보내기는 가능
    assert image.startswith(b"\x89PNG\r\n\x1a\n")
    assert filename.endswith(".png")


def _form(ctrl: AppController, key: str, subject: str):
    form = ctrl.form_for(key)
    ctrl.update_subject(form, subject)
    return form
