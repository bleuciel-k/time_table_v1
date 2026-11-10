"""app.qr 모듈 단위 테스트 (QR 인코딩, 디코딩, 이미지 생성, 컨트롤러 임포트 연동)."""

import pytest

from app.controller import AppController
from app.model import Cell, Settings, Timetable
from app.qr import (
    decode_timetable,
    encode_timetable,
    extract_token,
    make_qr_base64,
    make_qr_image,
)
from app.storage import Storage


def test_qr_encode_and_decode_roundtrip():
    """시간표 데이터를 딥링크 URL로 인코딩하고, 다시 Timetable 객체로 오차 없이 복원하는지 검증."""
    cells = {
        "0-1": Cell(subject="네트워크", room="IT301", teacher="김교수", memo="과제 있음", color="blue", show_memo=True),
        "0-2": Cell(subject="네트워크", room="IT301", teacher="김교수", memo="과제 있음", color="blue", show_memo=True),
        "2-3": Cell(subject="운영체제", room="공학관201", color="emerald"),
    }
    tt = Timetable(id="tt_orig", name="2026 1학기", updated_at="2026-09-15T10:00:00Z", cells=cells)
    settings = Settings(days=5, periods=6, start_time="09:00", class_minutes=50, break_minutes=10)

    url = encode_timetable(tt, settings)
    assert url.startswith("https://bleuciel-k.github.io/time_table_v1/#")

    # 1. 전체 딥링크 URL에서 복원
    decoded_tt, decoded_settings = decode_timetable(url)
    assert decoded_tt.name == "2026 1학기"
    assert len(decoded_tt.cells) == 3
    assert decoded_tt.cells["0-1"].subject == "네트워크"
    assert decoded_tt.cells["0-1"].room == "IT301"
    assert decoded_tt.cells["0-1"].teacher == "김교수"
    assert decoded_tt.cells["0-1"].memo == "과제 있음"
    assert decoded_tt.cells["0-1"].color == "blue"
    assert decoded_tt.cells["0-1"].show_memo is True
    assert decoded_tt.cells["2-3"].subject == "운영체제"
    assert decoded_tt.cells["2-3"].color == "emerald"

    assert decoded_settings is not None
    assert decoded_settings["d"] == 5
    assert decoded_settings["p"] == 6

    # 2. 커스텀 스킴 URL(timetable://import?data=...)에서 복원
    token = extract_token(url)
    custom_scheme_url = f"timetable://import?data={token}"
    from_scheme_tt, _ = decode_timetable(custom_scheme_url)
    assert from_scheme_tt.name == "2026 1학기"
    assert len(from_scheme_tt.cells) == 3

    # 3. 순수 토큰 또는 tt: 접두사에서 복원
    from_token_tt, _ = decode_timetable(token)
    assert from_token_tt.name == "2026 1학기"
    from_prefix_tt, _ = decode_timetable(f"tt:{token}")
    assert from_prefix_tt.name == "2026 1학기"


def test_qr_decode_invalid_inputs():
    """잘못되거나 손상된 입력값에 대해 명확한 ValueError를 발생시키는지 검증."""
    with pytest.raises(ValueError, match="공유 코드나 링크가 비어 있습니다"):
        decode_timetable("")

    with pytest.raises(ValueError, match="올바른 시간표 QR 코드나 링크가 아닙니다"):
        decode_timetable("https://timetable.app/import#invalid_base64_!@#$")

    with pytest.raises(ValueError, match="올바른 시간표 QR 코드나 링크가 아닙니다"):
        decode_timetable("not_a_valid_token")


def test_qr_image_generation():
    """고해상도 PNG 바이트 및 Flet Image용 Base64 문자열이 정상 생성되는지 검증."""
    test_url = "https://timetable.app/import#test_token"
    png_bytes = make_qr_image(test_url)
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")  # PNG 매직 넘버 검증
    assert len(png_bytes) > 200

    b64_str = make_qr_base64(test_url)
    assert isinstance(b64_str, str)
    assert len(b64_str) > 200


def test_controller_import_timetable(tmp_path):
    """가져온 시간표가 Controller를 통해 새 시간표로 등록되고 활성화되는지 검증."""
    storage = Storage(tmp_path / "data.json")
    ctrl, _ = AppController.open(storage)

    cells = {
        "0-1": Cell(subject="알고리즘", color="blue"),
        "1-2": Cell(subject="자료구조", color="rose"),
    }
    imported_tt = Timetable(id="", name="친구의 시간표", updated_at="", cells=cells)

    result = ctrl.import_timetable(imported_tt, switch_to=True)
    assert result.applied is True
    assert "친구의 시간표" in result.message

    # 활성 시간표가 가져온 시간표로 전환되었고 내용이 저장되었는지 검증
    assert ctrl.workspace.active.name == "친구의 시간표"
    assert len(ctrl.workspace.active.cells) == 2
    assert ctrl.workspace.active.cells["0-1"].subject == "알고리즘"
    assert ctrl.workspace.active.cells["1-2"].subject == "자료구조"
