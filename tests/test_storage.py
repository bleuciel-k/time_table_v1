import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import app.storage as storage_mod
from app.model import AppData, Cell, Workspace, to_dict
from app.storage import (
    BACKUP_FILE,
    DATA_FILE,
    ReadOnlyError,
    Storage,
    StorageFormatError,
    parse_document,
    storage_dir,
)

NOW = datetime(2026, 9, 15, 10, 0, 0, tzinfo=timezone.utc)


def clock() -> datetime:
    return NOW


@pytest.fixture
def store(tmp_path: Path) -> Storage:
    return Storage(tmp_path, clock=clock)


def sample_data(subject: str = "알고리즘") -> AppData:
    ws = Workspace(clock=clock)
    ws.rename_timetable(ws.active.id, "2026 후기")
    ws.set_cell("0-1", Cell(subject=subject, room="K301", color="red"))
    ws.set_cell("2-3", Cell(subject="日本語", memo="メモ"))
    other = ws.add_timetable("다른 학기")
    ws.delete_timetable(other.id)
    return ws.data


def valid_json(**overrides) -> str:
    raw = to_dict(sample_data())
    raw.update(overrides)
    return json.dumps(raw, ensure_ascii=False)


def corrupt_files(directory: Path) -> list[Path]:
    return sorted(directory.glob("corrupt_*.json"))


# ---- 경로


def test_storage_dir_env_and_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path))
    assert storage_dir() == tmp_path
    monkeypatch.delenv("FLET_APP_STORAGE_DATA")
    assert storage_dir() == Path("./.data")


# ---- 저장 → 로드 동일성


def test_first_run_is_new_and_empty(store):
    result = store.load()
    assert result.source == "new"
    assert result.data == AppData()
    assert result.warnings == []


def test_save_load_roundtrip(store, tmp_path):
    data = sample_data()
    store.save(data)
    result = Storage(tmp_path).load()
    assert result.source == "primary"
    assert result.data == data
    assert not result.read_only
    text = (tmp_path / DATA_FILE).read_text(encoding="utf-8")
    assert "알고리즘" in text and "日本語" in text  # 사람이 읽을 수 있는 UTF-8


def test_second_save_keeps_previous_as_backup(store, tmp_path):
    first, second = sample_data("첫번째"), sample_data("두번째")
    store.save(first)
    assert not (tmp_path / BACKUP_FILE).exists()
    store.save(second)
    backup, _ = parse_document((tmp_path / BACKUP_FILE).read_text(encoding="utf-8"))
    assert backup == first
    assert store.load().data == second


# ---- 손상 → 백업 복구


@pytest.mark.parametrize(
    "garbage",
    [
        b"{not json",
        b"",
        b"\xff\xfe\x00",
        b"[]",
        json.dumps({"timetables": []}).encode(),  # schema_version 누락
    ],
)
def test_corrupt_primary_recovers_from_backup(store, tmp_path, garbage):
    good = sample_data("백업본")
    store.save(good)
    store.save(sample_data("최신"))
    (tmp_path / DATA_FILE).write_bytes(garbage)

    result = Storage(tmp_path, clock=clock).load()

    assert result.source == "backup"
    assert result.data == good
    [kept] = corrupt_files(tmp_path)
    assert kept.name == "corrupt_20260915T100000Z.json"
    assert kept.read_bytes() == garbage
    assert result.preserved == [kept]
    assert result.warnings
    # data.json이 복구본으로 다시 쓰여 다음 실행은 정상 로드
    assert Storage(tmp_path).load().source == "primary"


@pytest.mark.parametrize(
    "overrides",
    [
        {"settings": {"days": 7, "periods": 5}},
        {"settings": {"days": "5", "periods": 5}},
        {"schema_version": True},
        {"active_id": 3},
        {"timetables": [{"id": "a", "name": "x", "updated_at": "t", "cells": {"9-9": {}}}]},
        {"timetables": [{"id": "a", "name": "x", "updated_at": "t", "cells": {"0-1": {"subject": 1}}}]},
        {"timetables": [{"id": "a", "name": "x"}]},
        {"timetables": [
            {"id": "a", "name": "x", "updated_at": "t"},
            {"id": "a", "name": "y", "updated_at": "t"},
        ]},
    ],
)
def test_structural_errors_are_corruption(overrides):
    with pytest.raises(StorageFormatError):
        parse_document(valid_json(**overrides))


def test_missing_primary_recovers_from_backup(store, tmp_path):
    good = sample_data()
    store.save(good)
    store.save(good)
    (tmp_path / DATA_FILE).unlink()
    result = Storage(tmp_path).load()
    assert result.source == "backup"
    assert result.data == good
    assert (tmp_path / DATA_FILE).exists()
    assert corrupt_files(tmp_path) == []


def test_both_corrupt_starts_empty_and_preserves_both(tmp_path):
    (tmp_path / DATA_FILE).write_text("{broken", encoding="utf-8")
    (tmp_path / BACKUP_FILE).write_text("{also broken", encoding="utf-8")

    result = Storage(tmp_path, clock=clock).load()

    assert result.source == "empty"
    assert result.data == AppData()
    names = {p.name: p.read_text(encoding="utf-8") for p in corrupt_files(tmp_path)}
    assert names == {
        "corrupt_20260915T100000Z.json": "{broken",
        "corrupt_20260915T100000Z_bak.json": "{also broken",
    }
    assert len(result.warnings) == 2
    assert not (tmp_path / DATA_FILE).exists()
    assert Workspace(result.data).active.name == "새 시간표"


def test_corrupt_primary_without_backup(tmp_path):
    (tmp_path / DATA_FILE).write_text("nope", encoding="utf-8")
    result = Storage(tmp_path, clock=clock).load()
    assert result.source == "empty"
    assert len(corrupt_files(tmp_path)) == 1


def test_preserve_does_not_overwrite_existing_corrupt_file(tmp_path):
    (tmp_path / "corrupt_20260915T100000Z.json").write_text("earlier", encoding="utf-8")
    (tmp_path / DATA_FILE).write_text("{broken", encoding="utf-8")
    Storage(tmp_path, clock=clock).load()
    contents = sorted(p.read_text(encoding="utf-8") for p in corrupt_files(tmp_path))
    assert contents == ["earlier", "{broken"]


def test_unknown_color_falls_back_to_default_and_unknown_keys_ignored():
    raw = to_dict(sample_data())
    raw["future_field"] = 1
    cell = raw["timetables"][0]["cells"]["0-1"]
    cell["color"] = "neon"
    cell["emoji"] = "📚"
    data, _ = parse_document(json.dumps(raw))
    assert data.timetables[0].cells["0-1"].color == "blue"


# ---- 원자적 쓰기


def test_failed_write_leaves_previous_file_intact(store, tmp_path, monkeypatch):
    good = sample_data("원본")
    store.save(good)
    before = (tmp_path / DATA_FILE).read_bytes()

    def boom(fd):
        raise OSError("disk full")

    monkeypatch.setattr(storage_mod.os, "fsync", boom)
    with pytest.raises(OSError):
        store.save(sample_data("실패할 변경"))
    monkeypatch.undo()

    assert (tmp_path / DATA_FILE).read_bytes() == before
    assert list(tmp_path.glob("*.tmp")) == []
    assert Storage(tmp_path).load().data == good


def test_crash_before_replace_keeps_primary(store, tmp_path, monkeypatch):
    good = sample_data("원본")
    store.save(good)
    real_replace = storage_mod.os.replace

    def replace(src, dst):
        if Path(dst).name == DATA_FILE:
            raise KeyboardInterrupt  # 교체 직전 강제 종료 흉내
        real_replace(src, dst)

    monkeypatch.setattr(storage_mod.os, "replace", replace)
    with pytest.raises(KeyboardInterrupt):
        store.save(sample_data("변경"))
    monkeypatch.undo()

    assert Storage(tmp_path).load().data == good


def test_leftover_tmp_is_cleaned_on_load(store, tmp_path):
    store.save(sample_data())
    (tmp_path / (DATA_FILE + ".tmp")).write_text("partial", encoding="utf-8")
    (tmp_path / (BACKUP_FILE + ".tmp")).write_text("partial", encoding="utf-8")
    assert store.load().source == "primary"
    assert list(tmp_path.glob("*.tmp")) == []


# ---- 스키마 버전


def test_future_version_is_read_only_and_not_overwritten(tmp_path):
    text = valid_json(schema_version=2)
    (tmp_path / DATA_FILE).write_text(text, encoding="utf-8")
    store = Storage(tmp_path)
    result = store.load()
    assert result.read_only and store.read_only
    assert any("읽기 전용" in w for w in result.warnings)
    assert result.data.timetables
    with pytest.raises(ReadOnlyError):
        store.save(result.data)
    assert (tmp_path / DATA_FILE).read_text(encoding="utf-8") == text


def test_old_version_is_migrated(monkeypatch):
    raw = to_dict(sample_data())
    raw["schema_version"] = 0
    raw["title"] = raw["timetables"][0].pop("name")  # v0에서는 이름이 다른 곳에 있었다고 가정

    def v0_to_v1(doc):
        doc = dict(doc)
        doc["timetables"][0]["name"] = doc.pop("title")
        doc["schema_version"] = 1
        return doc

    monkeypatch.setitem(storage_mod.MIGRATIONS, 0, v0_to_v1)
    data, read_only = parse_document(json.dumps(raw))
    assert not read_only
    assert data.schema_version == 1
    assert data.timetables[0].name == "2026 후기"


def test_old_version_without_migration_is_corruption():
    with pytest.raises(StorageFormatError):
        parse_document(valid_json(schema_version=0))
