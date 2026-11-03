import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from app.sync import (
    AUTH_FILE,
    DELETE_ACCOUNT_URL,
    REFRESH_URL,
    SIGN_IN_URL,
    Auth,
    AuthError,
    CloudStore,
    Session,
    TokenStore,
)

NOW = datetime(2026, 9, 23, 10, 0, 0, tzinfo=timezone.utc)
API_KEY = "test-key"


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


class FakeFirebase:
    """httpx.MockTransport 핸들러. 응답을 큐로 지정하고 받은 요청을 기록한다."""

    def __init__(self) -> None:
        self.responses: list[httpx.Response | Exception] = []
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def ok(body: dict) -> httpx.Response:
    return httpx.Response(200, json=body)


def fail(message: str, status: int = 400) -> httpx.Response:
    return httpx.Response(status, json={"error": {"code": status, "message": message}})


SIGN_IN_OK = {
    "localId": "uid-1",
    "email": "me@example.com",
    "idToken": "id-1",
    "refreshToken": "rt-1",
    "expiresIn": "3600",
}


def refresh_ok(id_token: str = "id-2", refresh_token: str = "rt-1") -> httpx.Response:
    return ok(
        {"id_token": id_token, "refresh_token": refresh_token, "expires_in": "3600", "user_id": "uid-1"}
    )


@pytest.fixture
def fb() -> FakeFirebase:
    return FakeFirebase()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def make_auth(fb, clock, tmp_path):
    def make() -> Auth:
        client = httpx.Client(transport=httpx.MockTransport(fb))
        return Auth(API_KEY, TokenStore(tmp_path), client=client, clock=clock)

    return make


def signed_in(make_auth, fb) -> Auth:
    auth = make_auth()
    fb.responses.append(ok(SIGN_IN_OK))
    auth.sign_in("me@example.com", "pw")
    return auth


# ---- 로그인


def test_sign_in_success_saves_refresh_token_only(make_auth, fb, tmp_path):
    auth = make_auth()
    fb.responses.append(ok(SIGN_IN_OK))
    session = auth.sign_in("  me@example.com ", "pw")

    assert session.uid == "uid-1" and session.id_token == "id-1"
    assert session.expires_at == NOW + timedelta(hours=1)
    assert auth.signed_in

    req = fb.requests[0]
    assert str(req.url).startswith(SIGN_IN_URL)
    assert req.url.params["key"] == API_KEY
    assert json.loads(req.content) == {
        "email": "me@example.com",
        "password": "pw",
        "returnSecureToken": True,
    }

    saved = json.loads((tmp_path / AUTH_FILE).read_text("utf-8"))
    assert saved == {"uid": "uid-1", "email": "me@example.com", "refresh_token": "rt-1"}


@pytest.mark.parametrize(
    ("firebase_message", "code"),
    [
        ("INVALID_PASSWORD", "wrong_password"),
        ("INVALID_LOGIN_CREDENTIALS", "wrong_password"),
        ("EMAIL_NOT_FOUND", "user_not_found"),
        ("INVALID_EMAIL", "invalid_email"),
        ("USER_DISABLED", "user_disabled"),
        ("TOO_MANY_ATTEMPTS_TRY_LATER : Access to this account has been disabled", "too_many_attempts"),
        ("SOMETHING_NEW", "unknown"),
    ],
)
def test_sign_in_error_codes(make_auth, fb, tmp_path, firebase_message, code):
    auth = make_auth()
    fb.responses.append(fail(firebase_message))
    with pytest.raises(AuthError) as info:
        auth.sign_in("me@example.com", "pw")
    assert info.value.code == code
    assert info.value.message
    assert not auth.signed_in
    assert not (tmp_path / AUTH_FILE).exists()


def test_sign_in_network_error(make_auth, fb):
    auth = make_auth()
    fb.responses.append(httpx.ConnectError("offline"))
    with pytest.raises(AuthError) as info:
        auth.sign_in("me@example.com", "pw")
    assert info.value.code == "network"


def test_sign_in_timeout_is_network_error(make_auth, fb):
    auth = make_auth()
    fb.responses.append(httpx.ReadTimeout("slow"))
    with pytest.raises(AuthError) as info:
        auth.sign_in("me@example.com", "pw")
    assert info.value.code == "network"


def test_sign_in_server_error_without_json(make_auth, fb):
    auth = make_auth()
    fb.responses.append(httpx.Response(503, text="Service Unavailable"))
    with pytest.raises(AuthError) as info:
        auth.sign_in("me@example.com", "pw")
    assert info.value.code == "unknown"
    assert "503" in info.value.detail


def test_sign_in_response_missing_field(make_auth, fb):
    auth = make_auth()
    fb.responses.append(ok({**SIGN_IN_OK, "idToken": ""}))
    with pytest.raises(AuthError) as info:
        auth.sign_in("me@example.com", "pw")
    assert info.value.code == "unknown"
    assert not auth.signed_in


# ---- 토큰 사용·갱신


def test_id_token_cached_until_near_expiry(make_auth, fb, clock):
    auth = signed_in(make_auth, fb)
    clock.now = NOW + timedelta(minutes=58)
    assert auth.id_token() == "id-1"
    assert len(fb.requests) == 1  # 갱신 없음


def test_id_token_refreshes_within_margin(make_auth, fb, clock):
    auth = signed_in(make_auth, fb)
    clock.now = NOW + timedelta(minutes=59, seconds=30)
    fb.responses.append(refresh_ok())
    assert auth.id_token() == "id-2"

    req = fb.requests[1]
    assert str(req.url).startswith(REFRESH_URL)
    assert req.url.params["key"] == API_KEY
    assert parse_qs(req.content.decode()) == {
        "grant_type": ["refresh_token"],
        "refresh_token": ["rt-1"],
    }
    assert auth.session.expires_at == clock.now + timedelta(hours=1)


def test_refresh_rotated_token_is_saved(make_auth, fb, clock, tmp_path):
    auth = signed_in(make_auth, fb)
    clock.now = NOW + timedelta(hours=2)
    fb.responses.append(refresh_ok(refresh_token="rt-2"))
    auth.id_token()
    saved = json.loads((tmp_path / AUTH_FILE).read_text("utf-8"))
    assert saved["refresh_token"] == "rt-2"


def test_restored_session_refreshes_on_first_use(make_auth, fb):
    signed_in(make_auth, fb)
    auth = make_auth()  # 앱 재시작
    assert auth.signed_in
    assert auth.session.id_token == ""
    fb.responses.append(refresh_ok())
    assert auth.id_token() == "id-2"


@pytest.mark.parametrize(
    "firebase_message",
    ["TOKEN_EXPIRED", "INVALID_REFRESH_TOKEN", "USER_DISABLED", "USER_NOT_FOUND"],
)
def test_refresh_rejected_requires_reauth_and_clears_token(
    make_auth, fb, clock, tmp_path, firebase_message
):
    auth = signed_in(make_auth, fb)
    clock.now = NOW + timedelta(hours=2)
    fb.responses.append(fail(firebase_message))
    with pytest.raises(AuthError) as info:
        auth.id_token()
    assert info.value.code == "reauth_required"
    assert not auth.signed_in
    assert not (tmp_path / AUTH_FILE).exists()


def test_refresh_network_error_keeps_token(make_auth, fb, clock, tmp_path):
    auth = signed_in(make_auth, fb)
    clock.now = NOW + timedelta(hours=2)
    fb.responses.append(httpx.ConnectError("offline"))
    with pytest.raises(AuthError) as info:
        auth.id_token()
    assert info.value.code == "network"
    assert auth.signed_in
    assert (tmp_path / AUTH_FILE).exists()

    fb.responses.append(refresh_ok())  # 온라인 복귀
    assert auth.id_token() == "id-2"


def test_refresh_unknown_server_error_keeps_token(make_auth, fb, clock):
    auth = signed_in(make_auth, fb)
    clock.now = NOW + timedelta(hours=2)
    fb.responses.append(httpx.Response(500, text="oops"))
    with pytest.raises(AuthError) as info:
        auth.id_token()
    assert info.value.code == "unknown"
    assert auth.signed_in


def test_id_token_when_signed_out(make_auth):
    auth = make_auth()
    with pytest.raises(AuthError) as info:
        auth.id_token()
    assert info.value.code == "reauth_required"


# ---- 로그아웃


def test_sign_out_clears_token_only(make_auth, fb, tmp_path):
    (tmp_path / "data.json").write_text("{}", "utf-8")
    auth = signed_in(make_auth, fb)
    auth.sign_out()
    assert not auth.signed_in
    assert not (tmp_path / AUTH_FILE).exists()
    assert (tmp_path / "data.json").exists()  # 로컬 데이터 유지
    assert not make_auth().signed_in


# ---- 토큰 파일


def test_token_store_roundtrip(tmp_path):
    store = TokenStore(tmp_path)
    assert store.load() is None
    store.save(Session(uid="u", email="e@x.com", refresh_token="rt", id_token="secret"))
    assert "secret" not in (tmp_path / AUTH_FILE).read_text("utf-8")
    assert store.load() == Session(uid="u", email="e@x.com", refresh_token="rt")


@pytest.mark.parametrize(
    "content",
    [b"{not json", b"\xff\xfe", b"[]", b'{"uid": "u", "email": "e"}', b'{"uid": "", "email": "e", "refresh_token": "rt"}'],
)
def test_token_store_corrupt_file_is_discarded(tmp_path: Path, content):
    (tmp_path / AUTH_FILE).write_bytes(content)
    assert TokenStore(tmp_path).load() is None
    assert not (tmp_path / AUTH_FILE).exists()


def test_token_store_default_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path))
    assert TokenStore().path == tmp_path / AUTH_FILE


# ---- 계정 및 데이터 삭제


def test_delete_account_success(make_auth, fb, tmp_path):
    (tmp_path / "data.json").write_text("{}", "utf-8")
    auth = signed_in(make_auth, fb)
    fb.responses.append(ok({"kind": "identitytoolkit#DeleteAccountResponse"}))

    auth.delete_account()

    req = fb.requests[-1]
    assert req.method == "POST"
    assert str(req.url).startswith(DELETE_ACCOUNT_URL)
    body = json.loads(req.content.decode("utf-8"))
    assert body == {"idToken": "id-1"}
    assert not auth.signed_in
    assert not (tmp_path / AUTH_FILE).exists()
    assert (tmp_path / "data.json").exists()  # 로컬 데이터 유지


def test_delete_account_not_signed_in(make_auth):
    auth = make_auth()
    with pytest.raises(AuthError) as ex:
        auth.delete_account()
    assert ex.value.code == "reauth_required"


def test_delete_account_user_not_found(make_auth, fb):
    auth = signed_in(make_auth, fb)
    fb.responses.append(fail("USER_NOT_FOUND"))
    with pytest.raises(AuthError) as ex:
        auth.delete_account()
    assert ex.value.code == "user_not_found"


def test_cloud_store_delete_user(make_auth, fb):
    auth = signed_in(make_auth, fb)
    client = httpx.Client(transport=httpx.MockTransport(fb))
    store = CloudStore(auth, "https://db.firebaseio.com", client=client)
    fb.responses.append(httpx.Response(200, json=None))

    store.delete_user()

    req = fb.requests[-1]
    assert req.method == "DELETE"
    assert str(req.url).startswith("https://db.firebaseio.com/users/uid-1.json")
