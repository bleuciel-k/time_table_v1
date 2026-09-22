"""Firebase Auth REST 인증 (spec 3.3, 2.7). 데이터 동기화·병합은 T10에서 추가. Flet 비의존 (P5)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import httpx

from app.model import Clock, utc_now
from app.storage import _atomic_write, _remove, storage_dir

SIGN_IN_URL = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
REFRESH_URL = "https://securetoken.googleapis.com/v1/token"
AUTH_FILE = "auth.json"
REFRESH_MARGIN = timedelta(seconds=60)  # 만료 60초 전에 미리 갱신
TIMEOUT = 10.0

ErrorCode = Literal[
    "wrong_password",
    "user_not_found",
    "invalid_email",
    "user_disabled",
    "too_many_attempts",
    "network",
    "reauth_required",
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


class AuthError(Exception):
    def __init__(self, code: ErrorCode, detail: str = "") -> None:
        super().__init__(MESSAGES[code])
        self.code = code
        self.detail = detail  # Firebase 원문 등 디버깅용

    @property
    def message(self) -> str:
        return MESSAGES[self.code]


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
