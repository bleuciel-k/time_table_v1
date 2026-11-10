"""QR 코드 인코딩/디코딩 및 이미지 생성 모듈.

인터넷 연결(서버) 없이 오프라인에서 시간표 전체를 압축하여 QR 코드 및 딥링크 URL로 공유하고,
다른 기기에서 스캔하거나 붙여넣어 그대로 가져올 수 있도록 한다.
"""

from __future__ import annotations

import base64
import io
import json
import zlib
from typing import Any

import qrcode

from app.model import Cell, Settings, Timetable, utc_now

DEEP_LINK_BASE = "https://bleuciel-k.github.io/time_table_v1/#"
SCHEME_PREFIX = "timetable://import?data="


def encode_timetable(timetable: Timetable, settings: Settings | None = None) -> str:
    """시간표 데이터를 zlib으로 압축하고 Base64로 인코딩하여 딥링크 URL을 생성한다."""
    cells_data: dict[str, dict[str, Any]] = {}
    for key, cell in timetable.cells.items():
        item: dict[str, Any] = {"s": cell.subject}
        if cell.room:
            item["r"] = cell.room
        if cell.teacher:
            item["t"] = cell.teacher
        if cell.memo:
            item["m"] = cell.memo
        if cell.color:
            item["c"] = cell.color
        if cell.show_memo:
            item["sm"] = 1
        cells_data[key] = item

    payload: dict[str, Any] = {
        "v": 1,
        "name": timetable.name,
        "cells": cells_data,
    }
    if settings is not None:
        payload["settings"] = {
            "d": settings.days,
            "p": settings.periods,
            "st": settings.start_time,
            "cm": settings.class_minutes,
            "bm": settings.break_minutes,
        }

    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    compressed = zlib.compress(raw, level=9)
    token = base64.urlsafe_b64encode(compressed).decode("ascii")
    return f"{DEEP_LINK_BASE}{token}"


def extract_token(text: str) -> str:
    """URL, 딥링크, 공유 코드 등에서 순수 Base64 데이터 토큰만 추출한다."""
    cleaned = text.strip()
    if "#" in cleaned:
        return cleaned.split("#", 1)[1].strip()
    if "?data=" in cleaned:
        return cleaned.split("?data=", 1)[1].strip()
    if cleaned.startswith("tt:"):
        return cleaned[3:].strip()
    return cleaned


def decode_timetable(text_or_url: str) -> tuple[Timetable, dict[str, Any] | None]:
    """공유 코드나 딥링크 URL을 해석하여 Timetable 객체와 설정 dict를 복원한다."""
    token = extract_token(text_or_url)
    if not token:
        raise ValueError("공유 코드나 링크가 비어 있습니다.")

    try:
        # Base64 패딩 보정
        padded = token + "=" * (-len(token) % 4)
        compressed = base64.urlsafe_b64decode(padded.encode("ascii"))
        raw = zlib.decompress(compressed)
        data = json.loads(raw.decode("utf-8"))
    except Exception as ex:
        raise ValueError("올바른 시간표 QR 코드나 링크가 아닙니다.") from ex

    if not isinstance(data, dict) or data.get("v") != 1:
        raise ValueError("지원하지 않는 시간표 데이터 형식입니다.")

    name = str(data.get("name") or "가져온 시간표")
    cells_raw = data.get("cells", {})
    cells: dict[str, Cell] = {}
    for key, c in cells_raw.items():
        if isinstance(c, dict):
            cells[str(key)] = Cell(
                subject=str(c.get("s", "")),
                room=str(c.get("r", "")),
                teacher=str(c.get("t", "")),
                memo=str(c.get("m", "")),
                color=str(c.get("c", "blue")),
                show_memo=bool(c.get("sm", False)),
            )

    imported_tt = Timetable(
        id="",  # 가져올 때 새로운 ID가 할당됨
        name=name,
        updated_at=utc_now(),
        cells=cells,
    )
    return imported_tt, data.get("settings")


def make_qr_image(url_or_token: str, box_size: int = 8, border: int = 2) -> bytes:
    """주어진 URL이나 토큰으로 고해상도 QR 코드 PNG 이미지 바이트를 생성한다."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(url_or_token)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#18181B", back_color="#FFFFFF")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_qr_base64(url_or_token: str, box_size: int = 8, border: int = 2) -> str:
    """Flet ft.Image(src_base64=...)에 바로 넣을 수 있는 Base64 인코딩 문자열을 반환한다."""
    png_bytes = make_qr_image(url_or_token, box_size=box_size, border=border)
    return base64.b64encode(png_bytes).decode("ascii")
