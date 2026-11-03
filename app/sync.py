"""Firebase Auth·RTDB REST 인증, 클라우드 읽기/쓰기, 병합 (spec 3.3, 2.7, F7). Flet 비의존 (P5)."""

from __future__ import annotations

import copy
import json
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Literal

import httpx

from app.model import DEFAULT_NAME, AppData, Clock, to_dict, utc_now
from app.storage import StorageFormatError, _atomic_write, _remove, parse_document, storage_dir

SIGN_IN_URL = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
DELETE_ACCOUNT_URL = "https://identitytoolkit.googleapis.com/v1/accounts:delete"
REFRESH_URL = "https://securetoken.googleapis.com/v1/token"
AUTH_FILE = "auth.json"
REFRESH_MARGIN = timedelta(seconds=60)  # 만료 60초 전에 미리 갱신
TIMEOUT = 10.0
RETRY_SECONDS = 30.0  # 동기화 실패 시 재시도 간격 (온라인 복귀 감지 대신)

ErrorCode = Literal[
    "wrong_password",
    "user_not_found",
    "invalid_email",
    "user_disabled",
    "too_many_attempts",
    "network",
    "reauth_required",
    "permission_denied",
    "remote_invalid",
    "remote_newer",
    "conflict",
    "unknown",
]

MESSAGES: dict[ErrorCode, str] = {
    "wrong_password": "이메일 또는 비밀번호가 올바르지 않습니다.",
    "user_not_found": "등록되지 않은 이메일입니다.",
    "invalid_email": "이메일 형식이 올바르지 않습니다.",
    "user_disabled": "사용이 중지된 계정입니다.",
    "too_many_attempts": "시도 횟수가 너무 많습니다. 잠시 후 다시 시도하세요.",
    "network": "네트워크에 연결할 수 없습니다.",
    "reauth_required": "로그인이 만료되었습니다. 다시 로그인하세요.",
    "permission_denied": "클라우드 접근 권한이 없습니다. 데이터베이스 보안 규칙을 확인하세요.",
    "remote_invalid": "클라우드 데이터를 읽을 수 없어 동기화를 멈췄습니다.",
    "remote_newer": "다른 기기의 앱이 더 새 버전입니다. 앱을 업데이트하세요.",
    "conflict": "다른 기기와 동시에 저장하는 중입니다. 잠시 후 다시 시도합니다.",
    "unknown": "알 수 없는 오류가 발생했습니다.",
}

# Firebase 오류 메시지(앞부분) → 오류 코드
_SIGN_IN_ERRORS: dict[str, ErrorCode] = {
    "INVALID_PASSWORD": "wrong_password",
    "INVALID_LOGIN_CREDENTIALS": "wrong_password",  # 이메일 열거 보호 시 계정 없음도 이 코드
    "MISSING_PASSWORD": "wrong_password",
    "EMAIL_NOT_FOUND": "user_not_found",
    "INVALID_EMAIL": "invalid_email",
    "USER_DISABLED": "user_disabled",
    "TOO_MANY_ATTEMPTS_TRY_LATER": "too_many_attempts",
}
# 갱신 시 서버가 refresh token을 거부한 경우 → 저장된 토큰 삭제 + 재로그인
_REFRESH_REJECTED = {"TOKEN_EXPIRED", "INVALID_REFRESH_TOKEN", "USER_DISABLED", "USER_NOT_FOUND"}


class SyncError(Exception):
    """인증·동기화 오류. `code`로 구분하고 `message`를 사용자에게 보여준다."""

    def __init__(self, code: ErrorCode, detail: str = "") -> None:
        super().__init__(MESSAGES[code])
        self.code = code
        self.detail = detail  # Firebase 원문 등 디버깅용

    @property
    def message(self) -> str:
        return MESSAGES[self.code]


class AuthError(SyncError):
    """로그인·토큰 갱신 오류."""


@dataclass
class Session:
    uid: str
    email: str
    refresh_token: str
    id_token: str = ""  # 메모리에만 보관
    expires_at: datetime | None = None


# ---------------------------------------------------------------- 토큰 파일


class TokenStore:
    """`auth.json`에 uid·email·refresh token만 보관한다 (spec 3.3)."""

    def __init__(self, directory: Path | str | None = None) -> None:
        self.directory = Path(directory) if directory is not None else storage_dir()

    @property
    def path(self) -> Path:
        return self.directory / AUTH_FILE

    def load(self) -> Session | None:
        try:
            raw = json.loads(self.path.read_bytes().decode("utf-8"))
        except FileNotFoundError:
            return None
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.clear()  # 손상된 토큰 파일은 버리고 재로그인
            return None
        fields = ("uid", "email", "refresh_token")
        if not isinstance(raw, dict) or not all(isinstance(raw.get(k), str) for k in fields):
            self.clear()
            return None
        if not raw["uid"] or not raw["refresh_token"]:
            self.clear()
            return None
        return Session(uid=raw["uid"], email=raw["email"], refresh_token=raw["refresh_token"])

    def save(self, session: Session) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = {"uid": session.uid, "email": session.email, "refresh_token": session.refresh_token}
        _atomic_write(self.path, json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def clear(self) -> None:
        _remove(self.path)


# ---------------------------------------------------------------- 인증


class Auth:
    """이메일/비밀번호 로그인, ID token 자동 갱신, 로그아웃."""

    def __init__(
        self,
        api_key: str,
        store: TokenStore | None = None,
        client: httpx.Client | None = None,
        clock: Clock = utc_now,
    ) -> None:
        self._api_key = api_key
        self._store = store if store is not None else TokenStore()
        self._client = client if client is not None else httpx.Client(timeout=TIMEOUT)
        self._clock = clock
        self.session: Session | None = self._store.load()

    @property
    def signed_in(self) -> bool:
        return self.session is not None

    def sign_in(self, email: str, password: str) -> Session:
        body = self._post(
            SIGN_IN_URL,
            json={"email": email.strip(), "password": password, "returnSecureToken": True},
            errors=_SIGN_IN_ERRORS,
        )
        session = Session(
            uid=_field(body, "localId"),
            email=body.get("email") or email.strip(),
            refresh_token=_field(body, "refreshToken"),
            id_token=_field(body, "idToken"),
            expires_at=self._expiry(body.get("expiresIn")),
        )
        self._store.save(session)
        self.session = session
        return session

    def sign_out(self) -> None:
        """토큰만 지운다. 로컬 시간표 데이터는 건드리지 않는다 (F7)."""
        self._store.clear()
        self.session = None

    def delete_account(self) -> None:
        """Firebase Auth 계정을 삭제하고 토큰을 지운다.

        로그인 안 됨·토큰 거부 → AuthError("reauth_required"), 오프라인 → AuthError("network").
        """
        session = self.session
        if session is None:
            raise AuthError("reauth_required", "로그인되어 있지 않음")
        token = self.id_token()
        self._post(
            DELETE_ACCOUNT_URL,
            json={"idToken": token},
            errors={
                "USER_NOT_FOUND": "user_not_found",
                "TOKEN_EXPIRED": "reauth_required",
                "INVALID_ID_TOKEN": "reauth_required",
            },
        )
        self.sign_out()

    def id_token(self) -> str:
        """유효한 ID token. 만료가 가까우면 갱신한다.

        로그인 안 됨·토큰 거부 → AuthError("reauth_required"), 오프라인 → AuthError("network").
        """
        session = self.session
        if session is None:
            raise AuthError("reauth_required", "로그인되어 있지 않음")
        if session.id_token and session.expires_at and self._clock() < session.expires_at - REFRESH_MARGIN:
            return session.id_token
        self.refresh()
        assert self.session is not None
        return self.session.id_token

    def refresh(self) -> None:
        session = self.session
        if session is None:
            raise AuthError("reauth_required", "로그인되어 있지 않음")
        try:
            body = self._post(
                REFRESH_URL,
                data={"grant_type": "refresh_token", "refresh_token": session.refresh_token},
                errors={},
            )
        except AuthError as ex:
            if ex.detail.split(" ")[0] in _REFRESH_REJECTED:
                self.sign_out()
                raise AuthError("reauth_required", ex.detail) from ex
            raise  # 네트워크 등 일시적 오류: 토큰 유지
        session.id_token = _field(body, "id_token")
        session.expires_at = self._expiry(body.get("expires_in"))
        new_refresh = body.get("refresh_token")
        if isinstance(new_refresh, str) and new_refresh and new_refresh != session.refresh_token:
            session.refresh_token = new_refresh
            self._store.save(session)

    # ---- 내부

    def _post(self, url: str, errors: dict[str, ErrorCode], **kwargs: Any) -> dict[str, Any]:
        try:
            resp = self._client.post(url, params={"key": self._api_key}, **kwargs)
        except httpx.TransportError as ex:
            raise AuthError("network", str(ex)) from ex
        try:
            body = resp.json()
        except ValueError:
            body = None
        if resp.is_success and isinstance(body, dict):
            return body
        detail = _error_message(body) or f"HTTP {resp.status_code}"
        # "TOO_MANY_ATTEMPTS_TRY_LATER : ..." 처럼 뒤에 설명이 붙는 경우가 있다
        code = errors.get(detail.split(" ")[0], "unknown")
        raise AuthError(code, detail)

    def _expiry(self, expires_in: Any) -> datetime:
        try:
            seconds = int(expires_in)
        except (TypeError, ValueError):
            seconds = 3600
        return self._clock() + timedelta(seconds=seconds)


def _error_message(body: Any) -> str:
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict) and isinstance(err.get("message"), str):
            return err["message"]
        if isinstance(err, str):  # securetoken은 {"error": "invalid_grant"} 형태일 때도 있다
            return err
    return ""


def _field(body: dict[str, Any], key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value:
        raise AuthError("unknown", f"응답에 {key} 없음")
    return value


# ---------------------------------------------------------------- 클라우드 문서


def to_cloud(data: AppData) -> dict[str, Any]:
    """클라우드에 올릴 dict. `active_id`는 기기별 값이라 뺀다 (spec 3.3)."""
    raw = to_dict(data)
    del raw["active_id"]
    return raw


def from_cloud(body: Any) -> AppData:
    """RTDB 응답 → AppData. 빈 객체·배열이 빠진 형태를 채우고 로컬 파일과 같은 규칙으로 검증한다."""
    if not isinstance(body, dict) or "schema_version" not in body:
        raise SyncError("remote_invalid", "최상위 형식 오류")
    raw = {**body, "active_id": ""}
    timetables = raw.get("timetables", [])
    if isinstance(timetables, dict):  # RTDB는 정수 키가 듬성듬성하면 배열 대신 객체로 준다
        try:
            timetables = [timetables[k] for k in sorted(timetables, key=int)]
        except ValueError as ex:
            raise SyncError("remote_invalid", "timetables 키 오류") from ex
    if isinstance(timetables, list):
        timetables = [t for t in timetables if t is not None]
    raw["timetables"] = timetables
    try:
        data, newer = parse_document(json.dumps(raw))
    except StorageFormatError as ex:
        raise SyncError("remote_invalid", str(ex)) from ex
    if newer:
        raise SyncError("remote_newer", f"schema_version {data.schema_version}")
    return data


class CloudStore:
    """`/users/{uid}.json` 읽기/조건부 쓰기 (spec 3.3)."""

    def __init__(self, auth: Auth, database_url: str, client: httpx.Client | None = None) -> None:
        self._auth = auth
        self._base = database_url.rstrip("/")
        self._client = client if client is not None else httpx.Client(timeout=TIMEOUT)

    def fetch(self) -> tuple[AppData | None, str]:
        """(원격 데이터 또는 None, ETag)."""
        resp = self._request("GET", headers={"X-Firebase-ETag": "true"})
        try:
            body = resp.json()
        except ValueError as ex:
            raise SyncError("remote_invalid", "JSON 아님") from ex
        etag = resp.headers.get("ETag", "")
        return (None if body is None else from_cloud(body)), etag

    def push(self, document: dict[str, Any], etag: str) -> bool:
        """`etag`가 그대로일 때만 쓴다. 다른 기기가 먼저 썼으면(412) False."""
        resp = self._request("PUT", json=document, headers={"if-match": etag}, allow=(412,))
        return resp.status_code != 412

    def delete_user(self) -> None:
        """클라우드의 `/users/{uid}.json` 데이터를 영구 삭제한다."""
        self._request("DELETE")

    def _request(self, method: str, allow: tuple[int, ...] = (), **kwargs: Any) -> httpx.Response:
        for attempt in range(2):
            session = self._auth.session
            token = self._auth.id_token()  # 로그아웃·거부 → AuthError
            assert session is not None
            url = f"{self._base}/users/{session.uid}.json"
            try:
                resp = self._client.request(method, url, params={"auth": token}, **kwargs)
            except httpx.TransportError as ex:
                raise SyncError("network", str(ex)) from ex
            if resp.status_code == 401 and attempt == 0:
                self._auth.refresh()  # ID token이 서버에서 거부됨 → 갱신 후 한 번 더
                continue
            break
        if resp.is_success or resp.status_code in allow:
            return resp
        try:
            detail = _error_message(resp.json())
        except ValueError:
            detail = ""
        detail = f"HTTP {resp.status_code} {detail}".strip()
        raise SyncError("permission_denied" if resp.status_code == 401 else "unknown", detail)


# ---------------------------------------------------------------- 병합


def merge(local: AppData, remote: AppData | None, initial: bool = False) -> AppData:
    """시간표 id 기준 Last-Write-Wins 병합 (spec 3.3). 같은 시각이면 원격 채택. 입력은 바꾸지 않는다."""
    merged = copy.deepcopy(local)
    if remote is None:
        return merged
    if remote.settings_updated_at >= local.settings_updated_at:
        merged.settings = copy.deepcopy(remote.settings)
        merged.settings_updated_at = remote.settings_updated_at

    remote_by_id = {t.id: t for t in remote.timetables}
    locals_ = list(local.timetables)
    if initial and _is_pristine(local, remote_by_id) and remote.visible():
        pristine = local.visible()[0]
        locals_ = [t for t in locals_ if t.id != pristine.id]

    timetables = []
    for mine in locals_:
        theirs = remote_by_id.get(mine.id)
        chosen = theirs if theirs is not None and theirs.updated_at >= mine.updated_at else mine
        timetables.append(copy.deepcopy(chosen))
    local_ids = {t.id for t in locals_}
    timetables += [copy.deepcopy(t) for t in remote.timetables if t.id not in local_ids]
    merged.timetables = timetables
    return merged


def _is_pristine(local: AppData, remote_by_id: dict[str, Any]) -> bool:
    """새 기기에서 자동으로 만들어진 빈 시간표 1개뿐인지."""
    visible = local.visible()
    if len(visible) != 1:
        return False
    t = visible[0]
    return not t.cells and t.name == DEFAULT_NAME and t.id not in remote_by_id


# ---------------------------------------------------------------- 백그라운드 실행


class SyncWorker:
    """동기화 요청을 한 스레드에서 차례로 처리한다. 실행 중 들어온 요청은 한 번으로 합친다.

    `job`이 True를 반환하면(실패) `retry_seconds` 뒤에 다시 실행한다.
    """

    def __init__(self, job: Callable[[], bool], retry_seconds: float = RETRY_SECONDS) -> None:
        self._job = job
        self._retry_seconds = retry_seconds
        self._wake = threading.Event()
        self._stopped = False
        self._thread = threading.Thread(target=self._loop, name="sync", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def request(self) -> None:
        self._wake.set()

    def stop(self, timeout: float | None = None) -> None:
        self._stopped = True
        self._wake.set()
        self._thread.join(timeout)

    def _loop(self) -> None:
        retry = False
        while True:
            self._wake.wait(self._retry_seconds if retry else None)
            if self._stopped:
                return
            self._wake.clear()
            retry = self._job()
