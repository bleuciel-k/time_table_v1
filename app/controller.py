"""UI 이벤트를 모델 조작 + 자동 저장으로 연결하고 편집 폼 상태를 관리한다 (F1~F5, F7, P4). Flet 비의존 (P5)."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Callable

from app.exporter import ExportOptions, export_filename, render
from app.model import (
    DEFAULT_NAME,
    AppData,
    Cell,
    Clock,
    ModelError,
    Settings,
    Workspace,
    utc_now,
    validate_cell,
)
from app.palette import DEFAULT_COLOR
from app.storage import Storage, StorageError
from app.sync import Auth, CloudStore, SyncError, SyncWorker, merge, to_cloud

READ_ONLY_MESSAGE = "앱보다 새 버전의 데이터라 편집할 수 없습니다."
UNDO_EXPIRED_MESSAGE = "되돌릴 수 있는 시간이 지났습니다."
SYNC_ATTEMPTS = 3  # 다른 기기가 먼저 써서(412) 다시 시도하는 최대 횟수
# 기다리면 풀릴 수 있는 오류만 자동으로 다시 시도한다
RETRYABLE = {"network", "conflict", "unknown", "too_many_attempts"}


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
        # 동기화 스레드와 UI 이벤트가 같은 데이터를 만지므로 조작·병합은 이 잠금 안에서 한다
        self.lock = threading.RLock()
        self.revision = 0  # 변경할 때마다 증가
        self.dirty = False  # 클라우드에 아직 올리지 않은 변경이 있음 (spec 2.7)
        self.after_change: Callable[[], None] | None = None  # 변경 후 동기화 요청

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

    # ---- 이미지 내보내기 (F6)

    def export_image(
        self, options: ExportOptions, today: date | None = None
    ) -> tuple[bytes, str]:
        """현재 시간표를 이미지로 그려 (bytes, 파일명)을 돌려준다. 저장 위치는 UI가 묻는다."""
        timetable = self.workspace.active
        image = render(timetable, self.workspace.data.settings, options)
        return image, export_filename(timetable.name, today or date.today(), options.fmt)

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

    def delete_timetable(self, timetable_id: str | None = None) -> ActionResult:
        """id를 주지 않으면 활성 시간표를 지운다 (F4c). 되돌리기는 5초간 제공된다."""
        try:
            name = self.workspace.timetable(timetable_id).name
        except ModelError as ex:
            return ActionResult(False, str(ex))
        return self._mutate(
            lambda: self.workspace.delete_timetable(timetable_id), f"삭제했어요: {name}"
        )

    def undo(self) -> ActionResult:
        return self._mutate(self.workspace.undo, "되돌렸어요.", UNDO_EXPIRED_MESSAGE)

    # ---- 동기화 (F7)

    def sync(self, cloud: CloudStore, initial: bool = False) -> bool:
        """원격과 병합해 로컬에 저장하고, 원격과 다르면 올린다. 로컬이 바뀌었으면 True.

        네트워크 요청은 잠금 밖에서 하고, 병합은 잠금 안에서 그 시점의 로컬로 한다.
        실패는 SyncError로 올린다.
        """
        if self.read_only:
            return False
        changed = False
        for _ in range(SYNC_ATTEMPTS):
            remote, etag = cloud.fetch()
            with self.lock:
                revision = self.revision
                merged = merge(self.workspace.data, remote, initial)
                if to_cloud(merged) != to_cloud(self.workspace.data):
                    self.workspace.replace_data(merged)
                    self._persist()  # 실패해도 다음 변경 때 다시 저장한다 (spec 2.7)
                    changed = True
                document = to_cloud(self.workspace.data)
            if (remote is not None and document == to_cloud(remote)) or cloud.push(document, etag):
                with self.lock:
                    if self.revision == revision:
                        self.dirty = False
                return changed
        raise SyncError("conflict", f"{SYNC_ATTEMPTS}회 연속 412")

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
        with self.lock:
            try:
                outcome = action()
            except ModelError as ex:
                return ActionResult(False, str(ex))
            if outcome is False:
                return ActionResult(False, noop_message)
            self.revision += 1
            self.dirty = True
            text = notice(outcome) if callable(notice) else notice
            result = ActionResult(True, self._persist() or text, undoable=self.workspace.can_undo)
        if self.after_change is not None:
            self.after_change()
        return result

    def _persist(self) -> str | None:
        try:
            self.storage.save(self.workspace.data)
        except (StorageError, OSError) as ex:
            return f"저장 실패: {ex}"
        return None


@dataclass(frozen=True)
class SyncStatus:
    signed_in: bool
    email: str = ""
    running: bool = False
    last_synced_at: datetime | None = None
    error: SyncError | None = None


class SyncManager:
    """로그인 상태와 백그라운드 동기화를 묶는다 (F7, spec 3.3).

    `on_update(changed)`는 동기화 스레드에서 불린다. changed=True면 로컬 데이터가 바뀐 것.
    """

    def __init__(
        self,
        controller: AppController,
        auth: Auth,
        cloud: CloudStore,
        on_update: Callable[[bool], None] | None = None,
        clock: Clock = utc_now,
        worker_factory: Callable[[Callable[[], bool]], SyncWorker] = SyncWorker,
    ) -> None:
        self.controller = controller
        self.auth = auth
        self.cloud = cloud
        self.on_update = on_update
        self._clock = clock
        self._initial = False  # 로그인 직후 첫 동기화 (spec 3.3)
        self._running = False
        self._last_synced_at: datetime | None = None
        self._error: SyncError | None = None
        self._worker = worker_factory(self._job)
        controller.after_change = self.request

    @property
    def status(self) -> SyncStatus:
        session = self.auth.session
        return SyncStatus(
            signed_in=session is not None,
            email=session.email if session else "",
            running=self._running,
            last_synced_at=self._last_synced_at,
            error=self._error,
        )

    def start(self) -> None:
        self._worker.start()
        self.request()  # 앱 시작 시 다운로드

    def stop(self) -> None:
        self._worker.stop(timeout=1)

    def request(self) -> None:
        if self.auth.signed_in and not self.controller.read_only:
            self._worker.request()

    def sign_in(self, email: str, password: str) -> None:
        """실패하면 AuthError. 성공하면 병합을 예약한다."""
        self.auth.sign_in(email, password)
        self._initial = True
        self._error = None
        self._last_synced_at = None
        self.request()

    def sign_out(self) -> None:
        """토큰만 지운다. 로컬 데이터는 그대로 둔다 (F7)."""
        self.auth.sign_out()
        self._error = None
        self._last_synced_at = None

    def _job(self) -> bool:
        """SyncWorker가 실행한다. 다시 시도해야 하면 True."""
        if not self.auth.signed_in:
            return False
        self._running = True
        changed = False
        try:
            changed = self.controller.sync(self.cloud, initial=self._initial)
        except SyncError as ex:
            self._error = ex
        except Exception as ex:  # 스레드가 죽지 않도록 예상 밖 오류도 기록만 한다
            self._error = SyncError("unknown", repr(ex))
        else:
            self._initial = False
            self._error = None
            self._last_synced_at = self._clock()
        finally:
            self._running = False
        if self.on_update is not None:
            self.on_update(changed)
        return self._error is not None and self._error.code in RETRYABLE
