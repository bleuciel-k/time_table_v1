"""시간표 데이터 모델, 검증, 복사/삭제/되돌리기 로직 (spec 2.2, 2.4, 2.7). Flet 비의존 (P5)."""

from __future__ import annotations

import copy
import uuid
from dataclasses import asdict, dataclass, field, fields, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from app.palette import BACKGROUNDS, DEFAULT_BACKGROUND, DEFAULT_COLOR, PALETTE

SCHEMA_VERSION = 1
SUBJECT_MAX = 30
FIELD_MAX = 50
NAME_MAX = 30
DAYS_CHOICES = (5, 6)
PERIOD_MIN, PERIOD_MAX = 1, 7
MAX_DAY_INDEX = max(DAYS_CHOICES) - 1
UNDO_WINDOW = timedelta(seconds=5)
DEFAULT_NAME = "새 시간표"
OPTIONAL_FIELDS = ("room", "teacher", "memo")

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def format_timestamp(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime(TIMESTAMP_FORMAT)


def parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


class ModelError(ValueError):
    """모델 조작 오류의 기본 클래스."""


class ValidationError(ModelError):
    def __init__(self, errors: dict[str, str]) -> None:
        super().__init__(" ".join(errors.values()))  # 사용자에게 그대로 보여줄 문구
        self.errors = errors


class CellOccupiedError(ModelError):
    """붙여넣을 셀에 내용이 있어 덮어쓰기 확인이 필요함 (F3a)."""


# ---------------------------------------------------------------- 셀 키


def cell_key(day: int, period: int) -> str:
    if not 0 <= day <= MAX_DAY_INDEX:
        raise ModelError(f"요일 범위 밖: {day}")
    if not PERIOD_MIN <= period <= PERIOD_MAX:
        raise ModelError(f"교시 범위 밖: {period}")
    return f"{day}-{period}"


def parse_cell_key(key: str) -> tuple[int, int]:
    try:
        day_s, period_s = key.split("-")
        day, period = int(day_s), int(period_s)
    except ValueError as ex:
        raise ModelError(f"잘못된 셀 키: {key!r}") from ex
    cell_key(day, period)  # 범위 검사
    return day, period


# ---------------------------------------------------------------- 데이터 구조


@dataclass
class Cell:
    subject: str
    room: str = ""
    teacher: str = ""
    memo: str = ""
    color: str = DEFAULT_COLOR


@dataclass
class Settings:
    days: int = 5
    periods: int = 5
    show_times: bool = False  # 교시별 시간 표시 (F9)
    start_time: str = "09:00"  # 1교시 시작 시각
    class_minutes: int = 50
    break_minutes: int = 10
    background: str = DEFAULT_BACKGROUND  # 화면·내보내기 배경색 (F9)
    lunch: bool = False  # 점심시간 표시 (F9)
    lunch_after: int = 4  # 몇 교시 뒤에 오는지
    lunch_minutes: int = 60
    show_memo: bool = False  # 그리드 셀에 메모 표시 (F9)


def settings_from_dict(raw: dict[str, Any]) -> Settings:
    """알려진 필드만 읽고 없는 값은 기본값으로 채운다 (구버전 파일 호환)."""
    defaults = Settings()
    return Settings(**{f.name: raw.get(f.name, getattr(defaults, f.name)) for f in fields(Settings)})


@dataclass
class Timetable:
    id: str
    name: str
    updated_at: str
    deleted: bool = False
    cells: dict[str, Cell] = field(default_factory=dict)


@dataclass
class AppData:
    schema_version: int = SCHEMA_VERSION
    active_id: str = ""
    settings: Settings = field(default_factory=Settings)
    settings_updated_at: str = ""  # 설정 동기화용 (spec 2.4). ""이면 한 번도 바꾸지 않음
    timetables: list[Timetable] = field(default_factory=list)

    def visible(self) -> list[Timetable]:
        """삭제 표시되지 않은 시간표 (로컬 UI에 보이는 것)."""
        return [t for t in self.timetables if not t.deleted]

    def find(self, timetable_id: str) -> Timetable | None:
        return next((t for t in self.visible() if t.id == timetable_id), None)


def to_dict(data: AppData) -> dict[str, Any]:
    return asdict(data)


def from_dict(raw: dict[str, Any]) -> AppData:
    settings_raw = raw.get("settings", {})
    timetables = [
        Timetable(
            id=t["id"],
            name=t["name"],
            updated_at=t["updated_at"],
            deleted=bool(t.get("deleted", False)),
            cells={k: Cell(**c) for k, c in t.get("cells", {}).items()},
        )
        for t in raw.get("timetables", [])
    ]
    return AppData(
        schema_version=raw.get("schema_version", SCHEMA_VERSION),
        active_id=raw.get("active_id", ""),
        settings=settings_from_dict(settings_raw),
        settings_updated_at=raw.get("settings_updated_at", ""),
        timetables=timetables,
    )


# ---------------------------------------------------------------- 그리드 배치 (UI·내보내기 공용)

DAY_LABELS = ("월", "화", "수", "목", "금", "토")


def grid_cells(timetable: Timetable, settings: Settings) -> list[list[Cell | None]]:
    """`[교시][요일]` 순서의 셀 표. 설정 범위 밖 셀은 포함하지 않는다 (F9)."""
    return [
        [timetable.cells.get(f"{day}-{period}") for day in range(settings.days)]
        for period in range(PERIOD_MIN, settings.periods + 1)
    ]


def period_times(settings: Settings) -> list[tuple[str, str]]:
    """교시별 (시작, 끝) 시각. `show_times`와 무관하게 계산만 한다 (F9).

    점심시간이 켜져 있으면 그 자리의 쉬는 시간 대신 점심시간 길이를 쓴다.
    """
    start = parse_time(settings.start_time)
    times = []
    for index in range(settings.periods):
        end = start + settings.class_minutes
        times.append((format_time(start), format_time(end)))
        gap = settings.break_minutes
        if has_lunch(settings) and settings.lunch_after == index + 1:
            gap = settings.lunch_minutes
        start = end + gap
    return times


def has_lunch(settings: Settings) -> bool:
    """점심시간이 켜져 있고 교시 사이에 자리가 있는지 (F9)."""
    return settings.lunch and 1 <= settings.lunch_after < settings.periods


def lunch_time(settings: Settings) -> tuple[str, str] | None:
    """점심시간 (시작, 끝). 표시하지 않으면 None."""
    if not has_lunch(settings):
        return None
    start = period_times(settings)[settings.lunch_after - 1][1]
    return start, format_time(parse_time(start) + settings.lunch_minutes)


def parse_time(value: str) -> int:
    """`"HH:MM"` → 자정 기준 분."""
    try:
        hour_s, minute_s = value.split(":")
        hour, minute = int(hour_s), int(minute_s)
    except ValueError as ex:
        raise ModelError(f"잘못된 시각: {value!r}") from ex
    if len(value) != 5 or not (0 <= hour < 24 and 0 <= minute < 60):
        raise ModelError(f"잘못된 시각: {value!r}")
    return hour * 60 + minute


def format_time(minutes: int) -> str:
    return f"{minutes // 60 % 24:02d}:{minutes % 60:02d}"


# ---------------------------------------------------------------- 검증


def validate_cell(cell: Cell) -> dict[str, str]:
    """필드별 오류 메시지. 비어 있으면 유효 (F1, F2)."""
    errors: dict[str, str] = {}
    subject = cell.subject.strip()
    if not subject:
        errors["subject"] = "과목명을 입력하세요."
    elif len(subject) > SUBJECT_MAX:
        errors["subject"] = f"과목명은 {SUBJECT_MAX}자 이하로 입력하세요."
    for name in OPTIONAL_FIELDS:
        if len(getattr(cell, name).strip()) > FIELD_MAX:
            errors[name] = f"{FIELD_MAX}자 이하로 입력하세요."
    if cell.color not in PALETTE:
        errors["color"] = "알 수 없는 색상입니다."
    return errors


def normalize_cell(cell: Cell) -> Cell:
    """앞뒤 공백을 제거한 사본을 반환. 유효하지 않으면 ValidationError."""
    cleaned = Cell(
        subject=cell.subject.strip(),
        room=cell.room.strip(),
        teacher=cell.teacher.strip(),
        memo=cell.memo.strip(),
        color=cell.color,
    )
    errors = validate_cell(cleaned)
    if errors:
        raise ValidationError(errors)
    return cleaned


def validate_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise ValidationError({"name": "이름을 입력하세요."})
    if len(cleaned) > NAME_MAX:
        raise ValidationError({"name": f"이름은 {NAME_MAX}자 이하로 입력하세요."})
    return cleaned


def validate_settings(settings: Settings) -> None:
    errors: dict[str, str] = {}
    if settings.days not in DAYS_CHOICES:
        errors["days"] = f"요일 수는 {DAYS_CHOICES} 중 하나여야 합니다."
    if not PERIOD_MIN <= settings.periods <= PERIOD_MAX:
        errors["periods"] = f"교시 수는 {PERIOD_MIN}~{PERIOD_MAX}이어야 합니다."
    try:
        parse_time(settings.start_time)
    except ModelError:
        errors["start_time"] = "시작 시각은 HH:MM 형식이어야 합니다."
    if not 1 <= settings.class_minutes <= 180:
        errors["class_minutes"] = "수업 시간은 1~180분이어야 합니다."
    if not 0 <= settings.break_minutes <= 120:
        errors["break_minutes"] = "쉬는 시간은 0~120분이어야 합니다."
    if settings.background not in BACKGROUNDS:
        errors["background"] = "알 수 없는 배경색입니다."
    if not PERIOD_MIN <= settings.lunch_after <= PERIOD_MAX - 1:
        errors["lunch_after"] = f"점심시간은 {PERIOD_MIN}~{PERIOD_MAX - 1}교시 뒤여야 합니다."
    if not 1 <= settings.lunch_minutes <= 180:
        errors["lunch_minutes"] = "점심시간은 1~180분이어야 합니다."
    if errors:
        raise ValidationError(errors)


def new_timetable_id() -> str:
    return f"tt_{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------- 조작 + 되돌리기


@dataclass
class UndoRecord:
    label: str
    snapshot: AppData
    touched_ids: tuple[str, ...]
    expires_at: datetime


class Workspace:
    """AppData에 대한 모든 변경의 진입점.

    데이터를 바꾸는 조작은 이전 되돌리기 기록을 무효화하고, 지우기 조작(F4)만
    새 기록을 남긴다. 저장(F5)은 storage 계층이 담당한다.
    """

    def __init__(
        self,
        data: AppData | None = None,
        clock: Clock = utc_now,
        id_factory: Callable[[], str] = new_timetable_id,
    ) -> None:
        self.data = data if data is not None else AppData()
        self._clock = clock
        self._id_factory = id_factory
        self._undo: UndoRecord | None = None
        self.clipboard: Cell | None = None
        self._ensure_active()

    # ---- 조회

    @property
    def active(self) -> Timetable:
        found = self.data.find(self.data.active_id)
        assert found is not None
        return found

    def timetable(self, timetable_id: str | None = None) -> Timetable:
        if timetable_id is None:
            return self.active
        found = self.data.find(timetable_id)
        if found is None:
            raise ModelError(f"시간표 없음: {timetable_id}")
        return found

    def get_cell(self, key: str, timetable_id: str | None = None) -> Cell | None:
        return self.timetable(timetable_id).cells.get(key)

    def suggest_color(self, subject: str) -> str | None:
        """같은 과목명이 이미 있으면 그 색을 제안 (F2). 활성 시간표 우선."""
        target = subject.strip()
        if not target:
            return None
        ordered = [self.active] + [t for t in self.data.visible() if t.id != self.active.id]
        for tt in ordered:
            for cell in tt.cells.values():
                if cell.subject == target:
                    return cell.color
        return None

    # ---- 셀 (F1, F3a, F4a)

    def set_cell(self, key: str, cell: Cell, timetable_id: str | None = None) -> Cell:
        self._check_key_in_settings(key)
        cleaned = normalize_cell(cell)
        tt = self.timetable(timetable_id)
        self._invalidate_undo()
        tt.cells[key] = cleaned
        self._touch(tt)
        return cleaned

    def copy_cell(self, key: str, timetable_id: str | None = None) -> Cell | None:
        cell = self.get_cell(key, timetable_id)
        self.clipboard = copy.deepcopy(cell) if cell else None
        return self.clipboard

    def needs_overwrite_confirm(self, key: str, timetable_id: str | None = None) -> bool:
        return self.get_cell(key, timetable_id) is not None

    def paste_cell(self, key: str, overwrite: bool = False, timetable_id: str | None = None) -> Cell:
        if self.clipboard is None:
            raise ModelError("복사한 셀이 없습니다.")
        if not overwrite and self.needs_overwrite_confirm(key, timetable_id):
            raise CellOccupiedError(f"셀 {key}에 내용이 있습니다.")
        return self.set_cell(key, copy.deepcopy(self.clipboard), timetable_id)

    def clear_cell(self, key: str, timetable_id: str | None = None) -> bool:
        tt = self.timetable(timetable_id)
        if key not in tt.cells:
            return False
        self._record_undo("셀 삭제", tt.id)
        del tt.cells[key]
        self._touch(tt)
        return True

    # ---- 시간표 (F3b, F4b, F4c, F8)

    def add_timetable(self, name: str = DEFAULT_NAME) -> Timetable:
        cleaned = validate_name(name)
        self._invalidate_undo()
        return self._create_timetable(cleaned)

    def rename_timetable(self, timetable_id: str, name: str) -> None:
        cleaned = validate_name(name)
        tt = self.timetable(timetable_id)
        self._invalidate_undo()
        tt.name = cleaned
        self._touch(tt)

    def switch_timetable(self, timetable_id: str) -> None:
        tt = self.timetable(timetable_id)
        self._invalidate_undo()
        self.data.active_id = tt.id

    def clear_timetable(self, timetable_id: str | None = None) -> bool:
        tt = self.timetable(timetable_id)
        if not tt.cells:
            return False
        self._record_undo("시간표 비우기", tt.id)
        tt.cells.clear()
        self._touch(tt)
        return True

    def delete_timetable(self, timetable_id: str | None = None) -> None:
        tt = self.timetable(timetable_id)
        self._record_undo("시간표 삭제", tt.id)
        tt.deleted = True  # 동기화용 소프트 삭제 (spec 2.4)
        self._touch(tt)
        if self.data.active_id == tt.id:
            self._ensure_active()

    # ---- 설정 (F9)

    def update_settings(self, settings: Settings) -> None:
        validate_settings(settings)
        self._invalidate_undo()
        # 범위 밖 셀은 지우지 않고 숨긴다 (설정을 되돌리면 다시 보임)
        self.data.settings = replace(settings)
        self.data.settings_updated_at = format_timestamp(self._clock())

    # ---- 동기화 (F7)

    def replace_data(self, data: AppData) -> None:
        """병합 결과로 교체한다. 되돌리기 기록은 교체 전 데이터 기준이라 버린다."""
        self._invalidate_undo()
        self.data = data
        self._ensure_active()

    # ---- 되돌리기 (F4)

    @property
    def undo_label(self) -> str | None:
        return self._undo.label if self.can_undo else None

    @property
    def can_undo(self) -> bool:
        return self._undo is not None and self._clock() <= self._undo.expires_at

    def undo(self) -> bool:
        if not self.can_undo:
            self._undo = None
            return False
        assert self._undo is not None
        record, self._undo = self._undo, None
        restored = copy.deepcopy(record.snapshot)
        # 복원본이 원격의 삭제 기록보다 새로워야 LWW 병합에서 살아남는다
        extra_ids = {t.id for t in self.data.timetables} - {t.id for t in restored.timetables}
        restored.timetables += [t for t in self.data.timetables if t.id in extra_ids]
        for t in restored.timetables:
            if t.id in record.touched_ids:
                t.updated_at = format_timestamp(self._clock())
            elif t.id in extra_ids:
                t.deleted = True  # 자동 생성된 빈 시간표 정리
                t.updated_at = format_timestamp(self._clock())
        self.data = restored
        return True

    # ---- 내부

    def _check_key_in_settings(self, key: str) -> None:
        day, period = parse_cell_key(key)
        s = self.data.settings
        if day >= s.days or period > s.periods:
            raise ModelError(f"현재 설정({s.days}요일, {s.periods}교시) 밖의 셀: {key}")

    def _touch(self, tt: Timetable) -> None:
        """변경 시각을 1초 단위로 반드시 앞당긴다.

        같은 초 안의 두 변경이 같은 값을 가지면 병합에서 뒤의 변경이 원격에 밀리므로(동률은
        원격 우선, spec 3.3), 직전 값보다 항상 크게 만든다.
        """
        now = self._clock()
        previous = parse_timestamp(tt.updated_at)
        if previous is not None and now <= previous:
            now = previous + timedelta(seconds=1)
        tt.updated_at = format_timestamp(now)

    def _invalidate_undo(self) -> None:
        self._undo = None

    def _record_undo(self, label: str, *touched_ids: str) -> None:
        self._undo = UndoRecord(
            label=label,
            snapshot=copy.deepcopy(self.data),
            touched_ids=touched_ids,
            expires_at=self._clock() + UNDO_WINDOW,
        )

    def _create_timetable(self, name: str, after: Timetable | None = None) -> Timetable:
        existing = {t.id for t in self.data.timetables}
        new_id = self._id_factory()
        while new_id in existing:
            new_id = self._id_factory()
        tt = Timetable(id=new_id, name=name, updated_at=format_timestamp(self._clock()))
        if after is None:
            self.data.timetables.append(tt)
        else:
            self.data.timetables.insert(self.data.timetables.index(after) + 1, tt)
        return tt

    def _ensure_active(self) -> None:
        if self.data.find(self.data.active_id) is not None:
            return
        visible = self.data.visible()
        tt = visible[0] if visible else self._create_timetable(DEFAULT_NAME)
        self.data.active_id = tt.id
