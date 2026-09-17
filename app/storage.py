"""로컬 JSON 저장소: 원자적 쓰기, 백업·손상 복구, 스키마 마이그레이션 (spec 2.6, 2.7, P7). Flet 비의존 (P5)."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

from app.model import (
    OPTIONAL_FIELDS,
    SCHEMA_VERSION,
    AppData,
    Clock,
    ModelError,
    Settings,
    ValidationError,
    from_dict,
    parse_cell_key,
    to_dict,
    utc_now,
    validate_settings,
)
from app.palette import DEFAULT_COLOR, PALETTE

DATA_FILE = "data.json"
BACKUP_FILE = "data.json.bak"
TMP_SUFFIX = ".tmp"
STORAGE_ENV = "FLET_APP_STORAGE_DATA"
FALLBACK_DIR = "./.data"

Migration = Callable[[dict[str, Any]], dict[str, Any]]
# schema_version N → N+1 변환 함수. 스키마를 올릴 때 여기에 등록한다.
MIGRATIONS: dict[int, Migration] = {}

Source = Literal["new", "primary", "backup", "empty"]


class StorageError(Exception):
    """저장소 오류의 기본 클래스."""


class StorageFormatError(StorageError):
    """파일 내용이 손상되었거나 읽을 수 없는 형식."""


class ReadOnlyError(StorageError):
    """미래 버전 데이터를 덮어쓰려 함."""


@dataclass
class LoadResult:
    data: AppData
    source: Source  # new: 첫 실행, primary: 정상, backup: 백업 복구, empty: 복구 실패
    read_only: bool = False
    warnings: list[str] = field(default_factory=list)
    preserved: list[Path] = field(default_factory=list)


def storage_dir() -> Path:
    return Path(os.environ.get(STORAGE_ENV) or FALLBACK_DIR)


# ---------------------------------------------------------------- 문서 파싱


def parse_document(text: str) -> tuple[AppData, bool]:
    """JSON 문자열 → (AppData, 읽기 전용 여부). 손상 시 StorageFormatError."""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as ex:
        raise StorageFormatError(f"JSON 파싱 실패: {ex}") from ex
    if not isinstance(raw, dict):
        raise StorageFormatError("최상위 값이 객체가 아닙니다.")
    version = _expect_int(raw.get("schema_version"), "schema_version")
    read_only = version > SCHEMA_VERSION
    while version < SCHEMA_VERSION:
        migrate = MIGRATIONS.get(version)
        if migrate is None:
            raise StorageFormatError(f"schema_version {version}의 마이그레이션이 없습니다.")
        raw = migrate(raw)
        new_version = _expect_int(raw.get("schema_version"), "schema_version")
        if new_version <= version:
            raise StorageFormatError(f"마이그레이션이 버전을 올리지 않았습니다: {version}")
        version = new_version
    return from_dict(_clean(raw)), read_only


def _clean(raw: dict[str, Any]) -> dict[str, Any]:
    """타입을 검사하고 알려진 필드만 남긴 dict를 만든다."""
    settings_raw = _expect(raw.get("settings", {}), dict, "settings")
    defaults = Settings()
    settings = Settings(
        days=_expect_int(settings_raw.get("days", defaults.days), "settings.days"),
        periods=_expect_int(settings_raw.get("periods", defaults.periods), "settings.periods"),
        show_times=_expect(
            settings_raw.get("show_times", defaults.show_times), bool, "settings.show_times"
        ),
        start_time=_expect(
            settings_raw.get("start_time", defaults.start_time), str, "settings.start_time"
        ),
        class_minutes=_expect_int(
            settings_raw.get("class_minutes", defaults.class_minutes), "settings.class_minutes"
        ),
        break_minutes=_expect_int(
            settings_raw.get("break_minutes", defaults.break_minutes), "settings.break_minutes"
        ),
    )
    try:
        validate_settings(settings)
    except ValidationError as ex:
        raise StorageFormatError(str(ex)) from ex

    timetables: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, t in enumerate(_expect(raw.get("timetables", []), list, "timetables")):
        where = f"timetables[{i}]"
        _expect(t, dict, where)
        tid = _expect(t.get("id"), str, f"{where}.id")
        if tid in seen:
            raise StorageFormatError(f"중복 id: {tid}")
        seen.add(tid)
        cells: dict[str, dict[str, str]] = {}
        for key, c in _expect(t.get("cells", {}), dict, f"{where}.cells").items():
            try:
                parse_cell_key(key)
            except ModelError as ex:
                raise StorageFormatError(str(ex)) from ex
            _expect(c, dict, f"{where}.cells[{key}]")
            cell = {
                name: _expect(c.get(name, ""), str, f"{where}.cells[{key}].{name}")
                for name in ("subject", *OPTIONAL_FIELDS)
            }
            color = c.get("color")
            cell["color"] = color if isinstance(color, str) and color in PALETTE else DEFAULT_COLOR
            cells[key] = cell
        timetables.append(
            {
                "id": tid,
                "name": _expect(t.get("name"), str, f"{where}.name"),
                "updated_at": _expect(t.get("updated_at"), str, f"{where}.updated_at"),
                "deleted": _expect(t.get("deleted", False), bool, f"{where}.deleted"),
                "cells": cells,
            }
        )
    return {
        "schema_version": raw["schema_version"],
        "active_id": _expect(raw.get("active_id", ""), str, "active_id"),
        "settings": asdict(settings),
        "timetables": timetables,
    }


def _expect(value: Any, typ: type, where: str) -> Any:
    if not isinstance(value, typ):
        raise StorageFormatError(f"{where}: {typ.__name__} 필요, {type(value).__name__} 있음")
    return value


def _expect_int(value: Any, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise StorageFormatError(f"{where}: int 필요, {type(value).__name__} 있음")
    return value


# ---------------------------------------------------------------- 파일 저장소


class Storage:
    """`data.json`(현재) + `data.json.bak`(직전 저장본)을 관리한다."""

    def __init__(self, directory: Path | str | None = None, clock: Clock = utc_now) -> None:
        self.directory = Path(directory) if directory is not None else storage_dir()
        self._clock = clock
        self.read_only = False

    @property
    def primary_path(self) -> Path:
        return self.directory / DATA_FILE

    @property
    def backup_path(self) -> Path:
        return self.directory / BACKUP_FILE

    def load(self) -> LoadResult:
        self.directory.mkdir(parents=True, exist_ok=True)
        for path in (self.primary_path, self.backup_path):
            _remove(_tmp_path(path))  # 중단된 쓰기의 잔여물

        warnings: list[str] = []
        preserved: list[Path] = []
        if self.primary_path.exists():
            try:
                data, read_only = self._read(self.primary_path)
                return self._finish(LoadResult(data, "primary", read_only, warnings, preserved))
            except StorageFormatError as ex:
                warnings.append(f"{DATA_FILE} 손상: {ex}")
                preserved.append(self._preserve(self.primary_path, ""))

        if self.backup_path.exists():
            try:
                data, read_only = self._read(self.backup_path)
            except StorageFormatError as ex:
                warnings.append(f"{BACKUP_FILE} 손상: {ex}")
                preserved.append(self._preserve(self.backup_path, "_bak"))
            else:
                warnings.append(f"{BACKUP_FILE}에서 복구했습니다.")
                result = self._finish(LoadResult(data, "backup", read_only, warnings, preserved))
                if not read_only:
                    self._write(data)  # data.json 재생성
                return result

        source: Source = "empty" if warnings else "new"
        return self._finish(LoadResult(AppData(), source, False, warnings, preserved))

    def save(self, data: AppData) -> None:
        if self.read_only:
            raise ReadOnlyError("앱보다 새 버전의 데이터라 저장하지 않습니다.")
        self._write(data)

    # ---- 내부

    def _read(self, path: Path) -> tuple[AppData, bool]:
        try:
            text = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError as ex:
            raise StorageFormatError(f"UTF-8 아님: {ex}") from ex
        return parse_document(text)

    def _write(self, data: AppData) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(to_dict(data), ensure_ascii=False, indent=2).encode("utf-8")
        # 순서: 백업 갱신 → 본 파일 교체. 어느 단계에서 중단돼도 data.json은 온전하다.
        if self.primary_path.exists():
            _atomic_write(self.backup_path, self.primary_path.read_bytes())
        _atomic_write(self.primary_path, payload)

    def _finish(self, result: LoadResult) -> LoadResult:
        self.read_only = result.read_only
        if result.read_only:
            result.warnings.append(
                f"앱보다 새 버전(schema_version {result.data.schema_version})의 데이터입니다. "
                "읽기 전용으로 엽니다."
            )
        return result

    def _preserve(self, path: Path, suffix: str) -> Path:
        stamp = self._clock().strftime("%Y%m%dT%H%M%SZ")
        dest = self.directory / f"corrupt_{stamp}{suffix}.json"
        n = 1
        while dest.exists():
            dest = self.directory / f"corrupt_{stamp}{suffix}-{n}.json"
            n += 1
        os.replace(path, dest)
        return dest


def _tmp_path(path: Path) -> Path:
    return path.with_name(path.name + TMP_SUFFIX)


def _atomic_write(dest: Path, payload: bytes) -> None:
    """임시 파일에 쓰고 fsync 후 교체한다 (P7)."""
    tmp = _tmp_path(dest)
    try:
        with open(tmp, "wb") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, dest)
    except BaseException:
        _remove(tmp)
        raise
    _fsync_dir(dest.parent)


def _fsync_dir(directory: Path) -> None:
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return  # 디렉터리 fsync 미지원 플랫폼
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _remove(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
