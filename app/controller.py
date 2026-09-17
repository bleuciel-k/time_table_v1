"""UI 이벤트를 모델 조작 + 자동 저장으로 연결하고 편집 폼 상태를 관리한다 (F1~F5, P4). Flet 비의존 (P5)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.model import DEFAULT_NAME, AppData, Cell, ModelError, Settings, Workspace, validate_cell
from app.palette import DEFAULT_COLOR
from app.storage import Storage, StorageError

READ_ONLY_MESSAGE = "앱보다 새 버전의 데이터라 편집할 수 없습니다."
UNDO_EXPIRED_MESSAGE = "되돌릴 수 있는 시간이 지났습니다."


@dataclass(frozen=True)
class ActionResult:
    applied: bool  # 모델에 반영됨 → 화면 갱신, 편집 시트를 닫아도 됨
    message: str | None = None  # 스낵바 문구 (파일 저장 실패가 안내 문구보다 우선)
    undoable: bool = False  # 5초간 "되돌리기" 제공 (F4)


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

    def save_form(self, form: CellForm) -> ActionResult:
        return self._mutate(lambda: self.workspace.set_cell(form.key, form.to_cell()))

    # ---- 복사 (F3)

    @property
    def has_clipboard(self) -> bool:
        return self.workspace.clipboard is not None

    def copy_cell(self, key: str) -> ActionResult:
        cell = self.workspace.copy_cell(key)
        if cell is None:
            return ActionResult(False, "복사할 내용이 없습니다.")
        return ActionResult(True, f"복사했어요: {cell.subject} — 붙여넣을 칸을 길게 누르세요.")

    def needs_overwrite_confirm(self, key: str) -> bool:
        return self.workspace.needs_overwrite_confirm(key)

    def paste_cell(self, key: str, overwrite: bool = False) -> ActionResult:
        return self._mutate(lambda: self.workspace.paste_cell(key, overwrite), "붙여넣었어요.")

    def duplicate_timetable(self) -> ActionResult:
        return self._mutate(
            self.workspace.duplicate_timetable, lambda tt: f"복제했어요: {tt.name}"
        )

    # ---- 여러 시간표 (F8)

    def add_timetable(self, name: str = DEFAULT_NAME) -> ActionResult:
        return self._mutate(
            lambda: self.workspace.add_timetable(name), lambda tt: f"추가했어요: {tt.name}"
        )

    def rename_timetable(self, timetable_id: str, name: str) -> ActionResult:
        return self._mutate(
            lambda: self.workspace.rename_timetable(timetable_id, name), "이름을 바꿨어요."
        )

    def switch_timetable(self, timetable_id: str) -> ActionResult:
        return self._mutate(lambda: self.workspace.switch_timetable(timetable_id))

    # ---- 설정 (F9)

    def update_settings(self, settings: Settings) -> ActionResult:
        return self._mutate(lambda: self.workspace.update_settings(settings), "설정을 저장했어요.")

    # ---- 지우기 + 되돌리기 (F4)

    def clear_cell(self, key: str) -> ActionResult:
        return self._mutate(lambda: self.workspace.clear_cell(key), "셀을 삭제했어요.")

    def clear_timetable(self) -> ActionResult:
        return self._mutate(self.workspace.clear_timetable, "시간표를 비웠어요.", "이미 비어 있습니다.")

    def delete_timetable(self) -> ActionResult:
        name = self.workspace.active.name
        return self._mutate(self.workspace.delete_timetable, f"삭제했어요: {name}")

    def undo(self) -> ActionResult:
        return self._mutate(self.workspace.undo, "되돌렸어요.", UNDO_EXPIRED_MESSAGE)

    # ---- 공통: 조작 → 자동 저장 (F5)

    def _mutate(
        self,
        action: Callable[[], Any],
        notice: str | Callable[[Any], str] | None = None,
        noop_message: str | None = None,
    ) -> ActionResult:
        """`action`이 False를 반환하면 변경 없음으로 보고 저장하지 않는다."""
        if self.read_only:
            return ActionResult(False, READ_ONLY_MESSAGE)
        try:
            outcome = action()
        except ModelError as ex:
            return ActionResult(False, str(ex))
        if outcome is False:
            return ActionResult(False, noop_message)
        text = notice(outcome) if callable(notice) else notice
        return ActionResult(True, self._persist() or text, undoable=self.workspace.can_undo)

    def _persist(self) -> str | None:
        try:
            self.storage.save(self.workspace.data)
        except (StorageError, OSError) as ex:
            return f"저장 실패: {ex}"
        return None
