import copy
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from app.controller import AppController, SyncManager
from app.model import DEFAULT_NAME, AppData, Cell, Settings, Timetable, Workspace, to_dict
from app.storage import Storage
from app.sync import (
    Auth,
    CloudStore,
    Session,
    SyncError,
    SyncWorker,
    TokenStore,
    from_cloud,
    merge,
    to_cloud,
)

NOW = datetime(2026, 9, 23, 10, 0, 0, tzinfo=timezone.utc)
DB_URL = "https://demo-default-rtdb.firebaseio.com/"
UID = "uid-1"


def ts(minutes: int) -> str:
    return (NOW + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


def tt(tid: str, minutes: int, name: str = "시간표", deleted: bool = False, **cells: str) -> Timetable:
    return Timetable(
        id=tid,
        name=name,
        updated_at=ts(minutes),
        deleted=deleted,
        cells={k[1:].replace("_", "-"): Cell(subject=v) for k, v in cells.items()},  # c0_1 → "0-1"
    )


def data(*timetables: Timetable, active: str = "", settings_at: str = "", **settings) -> AppData:
    return AppData(
        active_id=active or (timetables[0].id if timetables else ""),
        settings=Settings(**settings),
        settings_updated_at=settings_at,
        timetables=list(timetables),
    )


# ---------------------------------------------------------------- 병합


def test_merge_without_remote_keeps_local():
    local = data(tt("a", 0, c0_1="수학"))
    merged = merge(local, None)
    assert merged == local and merged is not local


def test_merge_last_write_wins_per_timetable():
    local = data(tt("a", 5, name="로컬 최신"), tt("b", 0, name="로컬 옛날"))
    remote = data(tt("a", 1, name="원격 옛날"), tt("b", 3, name="원격 최신"))
    merged = merge(local, remote)
    assert [t.name for t in merged.timetables] == ["로컬 최신", "원격 최신"]


def test_merge_tie_prefers_remote():
    merged = merge(data(tt("a", 0, name="로컬")), data(tt("a", 0, name="원격")))
    assert merged.timetables[0].name == "원격"


def test_merge_applies_remote_deletion_and_newer_local_restore():
    local = data(tt("a", 0), tt("b", 9, name="되살림"))
    remote = data(tt("a", 2, deleted=True), tt("b", 5, deleted=True))
    merged = merge(local, remote)
    assert [(t.id, t.deleted) for t in merged.timetables] == [("a", True), ("b", False)]


def test_merge_order_local_first_then_remote_only():
    local = data(tt("b", 0), tt("a", 0))
    remote = data(tt("x", 0), tt("a", 0), tt("y", 0))
    assert [t.id for t in merge(local, remote).timetables] == ["b", "a", "x", "y"]


def test_merge_keeps_local_active_id_and_does_not_mutate_inputs():
    local = data(tt("a", 0), tt("b", 0), active="b")
    remote = data(tt("a", 5, c0_1="원격"), active="")
    before = (copy.deepcopy(local), copy.deepcopy(remote))
    merged = merge(local, remote)
    assert merged.active_id == "b"
    assert (local, remote) == before


def test_merge_settings_last_write_wins():
    local = data(tt("a", 0), settings_at=ts(5), periods=7)
    remote = data(tt("a", 0), settings_at=ts(1), periods=3)
    assert merge(local, remote).settings.periods == 7
    remote.settings_updated_at = ts(6)
    merged = merge(local, remote)
    assert merged.settings.periods == 3 and merged.settings_updated_at == ts(6)


def test_merge_initial_drops_pristine_local_timetable():
    local = data(tt("new", 0, name=DEFAULT_NAME))
    remote = data(tt("a", 0, c0_1="수학"))
    assert [t.id for t in merge(local, remote, initial=True).timetables] == ["a"]
    assert [t.id for t in merge(local, remote).timetables] == ["new", "a"]  # 첫 동기화가 아니면 유지


@pytest.mark.parametrize(
    "local",
    [
        data(tt("new", 0, name=DEFAULT_NAME, c0_1="수학")),  # 내용 있음
        data(tt("new", 0, name="내 시간표")),  # 이름 바꿈
        data(tt("new", 0, name=DEFAULT_NAME), tt("b", 0)),  # 2개
    ],
)
def test_merge_initial_keeps_non_pristine(local):
    merged = merge(local, data(tt("a", 0)), initial=True)
    assert "new" in [t.id for t in merged.timetables]


def test_merge_initial_keeps_pristine_when_remote_has_nothing_visible():
    local = data(tt("new", 0, name=DEFAULT_NAME))
    merged = merge(local, data(tt("a", 0, deleted=True)), initial=True)
    assert [t.id for t in merged.timetables] == ["new", "a"]


# ---------------------------------------------------------------- 클라우드 문서


def test_to_cloud_omits_active_id_and_roundtrips():
    local = data(tt("a", 0, c0_1="日本語"), tt("b", 1, deleted=True), settings_at=ts(1), days=6)
    doc = to_cloud(local)
    assert "active_id" not in doc
    restored = from_cloud(json.loads(json.dumps(doc)))
    assert restored.timetables == local.timetables
    assert restored.settings == local.settings
    assert restored.settings_updated_at == ts(1)


def test_from_cloud_fills_fields_rtdb_drops():
    body = {
        "schema_version": 1,
        "settings": {"days": 5, "periods": 5},
        "timetables": [{"id": "a", "name": "n", "updated_at": ts(0)}],  # cells·deleted 없음
    }
    restored = from_cloud(body)
    assert restored.timetables == [tt("a", 0, name="n")]
    assert from_cloud({"schema_version": 1}).timetables == []


def test_from_cloud_accepts_sparse_array_forms():
    item = {"id": "a", "name": "n", "updated_at": ts(0)}
    assert [t.id for t in from_cloud({"schema_version": 1, "timetables": [None, item]}).timetables] == ["a"]
    as_dict = {"schema_version": 1, "timetables": {"10": {**item, "id": "b"}, "2": item}}
    assert [t.id for t in from_cloud(as_dict).timetables] == ["a", "b"]


@pytest.mark.parametrize(
    "body",
    [
        "문자열",
        {"settings": {}},
        {"schema_version": 1, "timetables": [{"id": "a"}]},
        {"schema_version": 1, "timetables": {"x": {}}},
        {"schema_version": 1, "settings": {"days": 9}},
    ],
)
def test_from_cloud_invalid(body):
    with pytest.raises(SyncError) as info:
        from_cloud(body)
    assert info.value.code == "remote_invalid"


def test_from_cloud_newer_schema():
    with pytest.raises(SyncError) as info:
        from_cloud({"schema_version": 99})
    assert info.value.code == "remote_newer"


# ---------------------------------------------------------------- 가짜 RTDB


class FakeRTDB:
    """`/users/{uid}.json` 하나를 흉내 낸다: ETag, if-match(412), auth 검사, 빈 객체 제거."""

    def __init__(self) -> None:
        self.value: object = None
        self.version = 0
        self.valid_tokens = {"id-1"}
        self.grant_on_refresh = True
        self.fail_next: list[Exception | httpx.Response] = []
        self.requests: list[httpx.Request] = []
        self.before_put = None  # PUT 직전에 끼어들기 (다른 기기 흉내)
        self.refreshes = 0

    @property
    def etag(self) -> str:
        return f"etag-{self.version}"

    def write(self, value: object) -> None:
        self.value = _strip_empty(value)
        self.version += 1

    def _reply(self, status: int) -> httpx.Response:
        # json=None은 빈 본문이 되므로 RTDB처럼 "null"을 직접 쓴다
        body = json.dumps(self.value, ensure_ascii=False).encode()
        return httpx.Response(status, content=body, headers={"ETag": self.etag})

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "securetoken.googleapis.com":
            self.refreshes += 1
            if self.grant_on_refresh:
                self.valid_tokens.add("id-2")
            return httpx.Response(
                200, json={"id_token": "id-2", "refresh_token": "rt-1", "expires_in": "3600"}
            )
        self.requests.append(request)
        if self.fail_next:
            item = self.fail_next.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        assert request.url.path == f"/users/{UID}.json"
        if request.url.params.get("auth") not in self.valid_tokens:
            return httpx.Response(401, json={"error": "Permission denied"})
        if request.method == "GET":
            assert request.headers.get("X-Firebase-ETag") == "true"
            return self._reply(200)
        if request.method == "PUT":
            if self.before_put is not None:
                hook, self.before_put = self.before_put, None
                hook()
            if request.headers.get("if-match") != self.etag:
                return self._reply(412)
            self.write(json.loads(request.content))
            return self._reply(200)
        raise AssertionError(request.method)


def _strip_empty(value):
    if isinstance(value, dict):
        out = {k: _strip_empty(v) for k, v in value.items()}
        return {k: v for k, v in out.items() if v not in ({}, [], None)} or None
    if isinstance(value, list):
        out = [_strip_empty(v) for v in value]
        return out or None
    return value


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now

    def tick(self, minutes: int = 1) -> None:
        self.now += timedelta(minutes=minutes)


@pytest.fixture
def db() -> FakeRTDB:
    return FakeRTDB()


@pytest.fixture
def clock() -> Clock:
    return Clock()


def make_cloud(db: FakeRTDB, clock: Clock, tmp_path: Path) -> CloudStore:
    client = httpx.Client(transport=httpx.MockTransport(db))
    store = TokenStore(tmp_path / "auth")
    store.save(Session(uid=UID, email="me@example.com", refresh_token="rt-1"))
    auth = Auth("key", store, client=client, clock=clock)
    auth.session.id_token = "id-1"
    auth.session.expires_at = NOW + timedelta(hours=1)
    return CloudStore(auth, DB_URL, client=client)


class Device:
    """저장 폴더 하나 + 컨트롤러 + 클라우드 연결 = 기기 한 대."""

    def __init__(self, name: str, db: FakeRTDB, clock: Clock, root: Path) -> None:
        self.dir = root / name
        self.clock = clock
        self.cloud = make_cloud(db, clock, self.dir)
        self.ctrl = self.open()

    def open(self) -> AppController:
        ctrl, _ = AppController.open(Storage(self.dir / "data", clock=self.clock))
        ctrl.workspace._clock = self.clock
        return ctrl

    def add(self, key: str, subject: str) -> None:
        self.clock.tick()
        form = self.ctrl.form_for(key)
        self.ctrl.update_subject(form, subject)
        assert self.ctrl.save_form(form).applied

    def subjects(self) -> dict[str, str]:
        return {k: c.subject for k, c in self.ctrl.workspace.active.cells.items()}


@pytest.fixture
def device_a(db, clock, tmp_path) -> Device:
    return Device("a", db, clock, tmp_path)


@pytest.fixture
def device_b(db, clock, tmp_path) -> Device:
    return Device("b", db, clock, tmp_path)


# ---------------------------------------------------------------- CloudStore


def test_fetch_empty_returns_none_and_etag(db, clock, tmp_path):
    cloud = make_cloud(db, clock, tmp_path)
    assert cloud.fetch() == (None, "etag-0")
    req = db.requests[0]
    assert str(req.url).startswith("https://demo-default-rtdb.firebaseio.com/users/uid-1.json")


def test_push_conditional(db, clock, tmp_path):
    cloud = make_cloud(db, clock, tmp_path)
    doc = to_cloud(data(tt("a", 0)))
    assert cloud.push(doc, "etag-0")
    assert not cloud.push(doc, "etag-0")  # 이미 etag-1
    remote, etag = cloud.fetch()
    assert etag == "etag-1" and remote.timetables == [tt("a", 0)]


def test_request_401_refreshes_token_once(db, clock, tmp_path):
    cloud = make_cloud(db, clock, tmp_path)
    db.valid_tokens = {"id-2"}  # 서버가 id-1을 거부
    assert cloud.fetch() == (None, "etag-0")
    assert db.refreshes == 1


def test_request_permission_denied_after_refresh(db, clock, tmp_path):
    cloud = make_cloud(db, clock, tmp_path)
    db.valid_tokens, db.grant_on_refresh = set(), False
    with pytest.raises(SyncError) as info:
        cloud.fetch()
    assert info.value.code == "permission_denied"


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (httpx.ConnectError("offline"), "network"),
        (httpx.Response(500, text="oops"), "unknown"),
        (httpx.Response(200, text="not json"), "remote_invalid"),
    ],
)
def test_fetch_failures(db, clock, tmp_path, failure, code):
    cloud = make_cloud(db, clock, tmp_path)
    db.fail_next.append(failure)
    with pytest.raises(SyncError) as info:
        cloud.fetch()
    assert info.value.code == code


def test_signed_out_cloud_raises_reauth(db, clock, tmp_path):
    cloud = make_cloud(db, clock, tmp_path)
    cloud._auth.sign_out()
    with pytest.raises(SyncError) as info:
        cloud.fetch()
    assert info.value.code == "reauth_required"


# ---------------------------------------------------------------- 컨트롤러 동기화 (기기 2대)


def test_first_sync_uploads_local(device_a, db):
    device_a.add("0-1", "수학")
    assert device_a.ctrl.dirty
    assert device_a.ctrl.sync(device_a.cloud) is False
    assert not device_a.ctrl.dirty
    remote = from_cloud(db.value)
    assert remote.timetables == device_a.ctrl.workspace.data.timetables
    assert "active_id" not in db.value


def test_second_device_initial_login_adopts_remote(device_a, device_b, tmp_path):
    device_a.add("0-1", "수학")
    device_a.ctrl.sync(device_a.cloud)

    assert device_b.ctrl.sync(device_b.cloud, initial=True) is True
    assert device_b.subjects() == {"0-1": "수학"}
    assert len(device_b.ctrl.workspace.data.timetables) == 1  # 빈 기본 시간표는 버림
    assert device_b.open().workspace.active.cells["0-1"].subject == "수학"  # 로컬 파일에 저장됨


def test_edits_on_both_devices_converge(device_a, device_b):
    device_a.add("0-1", "수학")
    device_a.ctrl.sync(device_a.cloud)
    device_b.ctrl.sync(device_b.cloud, initial=True)

    tid = device_a.ctrl.workspace.active.id
    device_b.clock.tick()
    device_b.ctrl.add_timetable("B의 시간표")
    device_b.ctrl.sync(device_b.cloud)
    device_a.add("1-1", "영어")  # 같은 시간표를 A가 나중에 수정 → A 채택
    device_a.ctrl.sync(device_a.cloud)
    device_b.ctrl.sync(device_b.cloud)

    names = lambda d: [t.name for t in d.ctrl.workspace.data.visible()]
    assert names(device_a) == names(device_b) == [DEFAULT_NAME, "B의 시간표"]
    assert device_b.ctrl.workspace.timetable(tid).cells.keys() == {"0-1", "1-1"}


def test_remote_deletion_of_active_switches(device_a, device_b):
    device_a.ctrl.add_timetable("둘째")
    device_a.ctrl.sync(device_a.cloud)
    device_b.ctrl.sync(device_b.cloud, initial=True)
    first = device_b.ctrl.workspace.data.visible()[0].id
    device_b.ctrl.switch_timetable(first)

    device_a.clock.tick()
    device_a.ctrl.workspace.switch_timetable(first)
    device_a.ctrl.delete_timetable()
    device_a.ctrl.sync(device_a.cloud)

    assert device_b.ctrl.sync(device_b.cloud) is True
    assert device_b.ctrl.workspace.active.name == "둘째"


def test_settings_sync(device_a, device_b):
    device_a.ctrl.sync(device_a.cloud)
    device_b.ctrl.sync(device_b.cloud, initial=True)
    device_a.clock.tick()
    assert device_a.ctrl.update_settings(Settings(days=6, periods=7)).applied
    device_a.ctrl.sync(device_a.cloud)
    device_b.ctrl.sync(device_b.cloud)
    assert device_b.ctrl.workspace.data.settings.periods == 7


def test_no_put_when_nothing_changed(device_a, db):
    device_a.ctrl.sync(device_a.cloud)
    puts = sum(r.method == "PUT" for r in db.requests)
    device_a.ctrl.sync(device_a.cloud)
    assert sum(r.method == "PUT" for r in db.requests) == puts


def test_concurrent_write_412_retries_with_merge(device_a, device_b, db):
    device_a.ctrl.sync(device_a.cloud)
    device_b.ctrl.sync(device_b.cloud, initial=True)
    device_a.add("0-1", "A 과목")
    device_b.ctrl.add_timetable("B 추가")

    # A가 PUT하기 직전에 B가 먼저 씀 → A는 412를 받고 다시 병합
    db.before_put = lambda: device_b.ctrl.sync(device_b.cloud)
    device_a.ctrl.sync(device_a.cloud)

    remote = from_cloud(db.value)
    assert [t.name for t in remote.visible()] == [DEFAULT_NAME, "B 추가"]
    assert remote.visible()[0].cells["0-1"].subject == "A 과목"
    assert not device_a.ctrl.dirty


def test_conflict_after_repeated_412(device_a, db):
    device_a.add("0-1", "수학")

    def interfere():
        db.version += 1
        db.before_put = interfere

    db.before_put = interfere
    with pytest.raises(SyncError) as info:
        device_a.ctrl.sync(device_a.cloud)
    assert info.value.code == "conflict"
    assert device_a.ctrl.dirty


def test_offline_keeps_dirty_then_uploads(device_a, db):
    device_a.add("0-1", "수학")
    db.fail_next.append(httpx.ConnectError("offline"))
    with pytest.raises(SyncError) as info:
        device_a.ctrl.sync(device_a.cloud)
    assert info.value.code == "network"
    assert device_a.ctrl.dirty
    assert device_a.subjects() == {"0-1": "수학"}  # 로컬 변경 유지

    device_a.ctrl.sync(device_a.cloud)  # 온라인 복귀
    assert not device_a.ctrl.dirty
    assert from_cloud(db.value).visible()[0].cells["0-1"].subject == "수학"


def test_edit_during_sync_keeps_dirty(device_a, db):
    device_a.add("0-1", "수학")
    db.before_put = lambda: device_a.add("1-1", "영어")  # 업로드 중에 편집
    device_a.ctrl.sync(device_a.cloud)
    assert device_a.ctrl.dirty


def test_remote_invalid_is_not_overwritten(device_a, db):
    db.value = {"schema_version": 1, "timetables": [{"id": "broken"}]}
    device_a.add("0-1", "수학")
    with pytest.raises(SyncError) as info:
        device_a.ctrl.sync(device_a.cloud)
    assert info.value.code == "remote_invalid"
    assert db.value == {"schema_version": 1, "timetables": [{"id": "broken"}]}


def test_read_only_local_does_not_sync(device_a, db):
    device_a.ctrl.storage.read_only = True
    assert device_a.ctrl.sync(device_a.cloud) is False
    assert db.requests == []


def test_merge_invalidates_undo_only_when_local_changes(device_a, device_b):
    device_a.add("0-1", "수학")
    device_a.ctrl.sync(device_a.cloud)
    device_a.ctrl.clear_cell("0-1")
    device_a.ctrl.sync(device_a.cloud)  # 올리기만 함 → 되돌리기 유지
    assert device_a.ctrl.workspace.can_undo

    device_b.ctrl.sync(device_b.cloud, initial=True)
    device_a.add("3-3", "음악")
    device_a.ctrl.sync(device_a.cloud)
    device_b.ctrl.add_timetable("B")
    device_b.ctrl.clear_timetable() if device_b.ctrl.workspace.active.cells else None
    device_b.ctrl.delete_timetable()
    assert device_b.ctrl.workspace.can_undo
    device_b.ctrl.sync(device_b.cloud)  # A 변경을 받아 로컬이 바뀜 → 되돌리기 무효
    assert not device_b.ctrl.workspace.can_undo


# ---------------------------------------------------------------- SyncManager / SyncWorker


class ManualWorker:
    def __init__(self, job):
        self.job = job
        self.requests = 0
        self.started = False

    def start(self):
        self.started = True

    def request(self):
        self.requests += 1

    def stop(self, timeout=None):
        pass


def make_manager(device: Device, updates: list) -> SyncManager:
    return SyncManager(
        device.ctrl,
        device.cloud._auth,
        device.cloud,
        on_update=updates.append,
        clock=device.clock,
        worker_factory=ManualWorker,
    )


def test_manager_requests_sync_after_change_and_on_start(device_a):
    manager = make_manager(device_a, [])
    manager.start()
    assert manager._worker.started and manager._worker.requests == 1
    device_a.add("0-1", "수학")
    assert manager._worker.requests == 2


def test_manager_job_success_and_status(device_a):
    updates = []
    manager = make_manager(device_a, updates)
    device_a.add("0-1", "수학")
    assert manager._job() is False
    status = manager.status
    assert status.signed_in and status.email == "me@example.com"
    assert status.error is None and status.last_synced_at == device_a.clock.now
    assert updates == [False]


def test_manager_job_network_error_retries(device_a, db):
    manager = make_manager(device_a, [])
    db.fail_next.append(httpx.ConnectError("offline"))
    assert manager._job() is True
    assert manager.status.error.code == "network"


def test_manager_job_remote_newer_does_not_retry(device_a, db):
    db.value = {"schema_version": 99}
    manager = make_manager(device_a, [])
    assert manager._job() is False
    assert manager.status.error.code == "remote_newer"


def test_manager_job_unexpected_exception_is_recorded(device_a, monkeypatch):
    manager = make_manager(device_a, [])
    monkeypatch.setattr(device_a.ctrl, "sync", lambda *a, **k: 1 / 0)
    assert manager._job() is True
    assert manager.status.error.code == "unknown"


def test_manager_sign_out_keeps_local_and_stops_requests(device_a):
    manager = make_manager(device_a, [])
    device_a.add("0-1", "수학")
    manager.sign_out()
    before = manager._worker.requests
    device_a.add("1-1", "영어")
    assert manager._worker.requests == before
    assert not manager.status.signed_in
    assert manager._job() is False
    assert device_a.subjects() == {"0-1": "수학", "1-1": "영어"}


def test_manager_sign_in_runs_initial_merge(db, clock, tmp_path, device_a):
    device_a.add("0-1", "수학")
    device_a.ctrl.sync(device_a.cloud)

    fresh = Device("fresh", db, clock, tmp_path)
    manager = make_manager(fresh, [])
    monkey_session = fresh.cloud._auth.session
    fresh.cloud._auth.sign_in = lambda email, pw: monkey_session  # 로그인은 test_sync.py에서 검증
    manager.sign_in("me@example.com", "pw")
    assert manager._worker.requests == 1
    manager._job()
    assert fresh.subjects() == {"0-1": "수학"}
    assert len(fresh.ctrl.workspace.data.timetables) == 1


def test_worker_coalesces_and_retries():
    calls = []
    done = threading.Event()
    gate = threading.Event()

    def job():
        calls.append(len(calls))
        if len(calls) == 1:
            gate.wait(1)  # 첫 실행 중에 요청이 여러 번 들어옴
            return True  # 실패 → 재시도
        done.set()
        return False

    worker = SyncWorker(job, retry_seconds=0.01)
    worker.start()
    worker.request()
    for _ in range(5):
        worker.request()
    gate.set()
    assert done.wait(1)
    worker.stop(timeout=1)
    assert len(calls) == 2
