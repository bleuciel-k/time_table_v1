"""UI 이벤트를 모델 조작 + 자동 저장으로 연결하고 편집 폼 상태를 관리한다 (F1, F2, F5, P4). Flet 비의존 (P5)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.model import AppData, Cell, ModelError, Workspace, validate_cell
from app.palette import DEFAULT_COLOR
from app.storage import Storage, StorageError

READ_ONLY_MESSAGE = "앱보다 새 버전의 데이터라 편집할 수 없습니다."


@dataclass(frozen=True)
class SaveResult:
    applied: bool  # 모델에 반영됨 → 편집 시트를 닫아도 됨
    message: str | None = None  # 사용자에게 보여줄 오류 (반영됐어도 파일 저장 실패 가능)


@dataclass
class CellForm:
    """셀 편집 시트의 입력 상태."""

    key: str
    subject: str = ""
    room: str = ""
    teacher: str = ""
    memo: str = ""
    color: str = DEFAULT_COLOR
    is_new: bool = True
    base_color: str = DEFAULT_COLOR  # 편집 시작 시의 색
    color_chosen: bool = False  # 사용자가 직접 고르면 자동 적용 중단 (F2)
    suggested: bool = False  # 현재 색이 기존 과목에서 자동 적용된 것인지

    @classmethod
    def for_cell(cls, key: str, cell: Cell | None) -> CellForm:
        if cell is None:
            return cls(key)
        return cls(
            key,
            subject=cell.subject,
            room=cell.room,
            teacher=cell.teacher,
            memo=cell.memo,
            color=cell.color,
            is_new=False,
            base_color=cell.color,
        )

    def to_cell(self) -> Cell:
        return Cell(self.subject, self.room, self.teacher, self.memo, self.color)

    @property
    def errors(self) -> dict[str, str]:
        return validate_cell(self.to_cell())

    @property
    def can_save(self) -> bool:
        return not self.errors

    def set_subject(self, value: str, suggestion: str | None) -> None:
        self.subject = value
        if self.color_chosen:
            return
        self.suggested = suggestion is not None
        self.color = suggestion or self.base_color

    def choose_color(self, color: str) -> None:
        self.color = color
        self.color_chosen = True
        self.suggested = False


class AppController:
    def __init__(self, storage: Storage, workspace: Workspace) -> None:
        self.storage = storage
        self.workspace = workspace

    @classmethod
    def open(
        cls, storage: Storage, seed: Callable[[], AppData] | None = None
    ) -> tuple[AppController, list[str]]:
        """저장소를 읽어 컨트롤러와 사용자에게 보여줄 경고를 반환한다."""
        result = storage.load()
        data = result.data
        if seed is not None and result.source == "new":
            data = seed()
        return cls(storage, Workspace(data)), result.warnings

    @property
    def read_only(self) -> bool:
        return self.storage.read_only

    # ---- 셀 편집 (F1, F2)

    def form_for(self, key: str) -> CellForm:
        return CellForm.for_cell(key, self.workspace.get_cell(key))

    def update_subject(self, form: CellForm, value: str) -> None:
        form.set_subject(value, self.workspace.suggest_color(value))

    def save_form(self, form: CellForm) -> SaveResult:
        """셀을 반영하고 즉시 저장한다."""
        if self.read_only:
            return SaveResult(False, READ_ONLY_MESSAGE)
        try:
            self.workspace.set_cell(form.key, form.to_cell())
        except ModelError as ex:
            return SaveResult(False, str(ex))
        return SaveResult(True, self._persist())

    # ---- 자동 저장 (F5)

    def _persist(self) -> str | None:
        try:
            self.storage.save(self.workspace.data)
        except (StorageError, OSError) as ex:
            return f"저장 실패: {ex}"
        return None
