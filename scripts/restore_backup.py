#!/usr/bin/env python3
"""다운로드받은 백업 파일(JSON)을 앱 저장소 데이터로 복원/적용하는 스크립트.

지원하는 백업 형식:
1. 로컬 저장소 형식: {"schema_version": 1, "active_id": "...", "settings": {...}, "timetables": [...]}
2. Firebase RTDB 내보내기 형식:
   - {"timetables": [...], "settings": {...}, "schema_version": 1}
   - {"users": {"<uid>": {"timetables": [...], ...}}}

사용법:
    python scripts/restore_backup.py <백업_파일_경로.json>
    (경로를 지정하지 않으면 현재 디렉토리 및 Downloads 폴더에서 가장 최근 json 파일을 탐색합니다)
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

# 프로젝트 루트 경로 등록
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

try:
    from app.model import SCHEMA_VERSION, AppData, Settings, Timetable, from_dict, to_dict
    from app.storage import parse_document
except ImportError:
    # Flet 패키지 등 의존성이 아직 없을 경우를 대비한 독립 실행 모드 지원
    SCHEMA_VERSION = 1
    parse_document = None


def find_default_backup_file() -> Path | None:
    """작업 디렉토리 또는 Downloads 폴더에서 백업으로 추정되는 JSON 파일을 탐색."""
    candidates = []
    # 1. 루트 디렉토리
    candidates.extend(ROOT_DIR.glob("*.json"))
    # 2. 홈 Downloads 폴더
    downloads = Path.home() / "Downloads"
    if downloads.exists():
        candidates.extend(downloads.glob("*timetable*.json"))
        candidates.extend(downloads.glob("*data*.json"))
        candidates.extend(downloads.glob("*-default-rtdb-export.json"))

    # config, manifest, package 관련 파일 제외
    filtered = [
        p for p in candidates
        if not p.name.startswith((".", "pyproject", "package", "tsconfig", "claude", "speckit"))
        and "config" not in p.name
    ]

    if not filtered:
        return None
    # 가장 최근에 수정된 파일 반환
    filtered.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return filtered[0]


def normalize_backup_data(raw: dict) -> dict:
    """다양한 형식의 백업 데이터를 표준 AppData dict 포맷으로 정규화."""
    # 형태 1: Firebase RTDB 전체 내보내기 {"users": {"<uid>": { ... }}}
    if "users" in raw and isinstance(raw["users"], dict):
        users = raw["users"]
        if users:
            first_user_data = next(iter(users.values()))
            if isinstance(first_user_data, dict):
                raw = first_user_data

    # 형태 2: RTDB 사용자 하위 문서 (active_id 누락 가능)
    schema_version = raw.get("schema_version", SCHEMA_VERSION)
    settings = raw.get("settings", {})
    settings_updated_at = raw.get("settings_updated_at", "")
    timetables = raw.get("timetables", [])

    # timetables가 리스트가 아니거나 딕셔너리 맵인 경우 보정
    if isinstance(timetables, dict):
        timetables = list(timetables.values())

    active_id = raw.get("active_id")
    if not active_id:
        # timetables에서 첫 번째 유효한 id를 active_id로 선택
        for tt in timetables:
            if isinstance(tt, dict) and not tt.get("deleted", False):
                active_id = tt.get("id")
                break
        if not active_id and timetables and isinstance(timetables[0], dict):
            active_id = timetables[0].get("id")

    return {
        "schema_version": schema_version,
        "active_id": active_id or "tt_default",
        "settings": settings,
        "settings_updated_at": settings_updated_at,
        "timetables": timetables,
    }


def restore_backup(backup_path: Path) -> bool:
    print(f"📦 백업 파일 읽는 중: {backup_path}")
    try:
        content = backup_path.read_text(encoding="utf-8")
        raw = json.loads(content)
    except Exception as e:
        print(f"❌ JSON 파싱 실패: {e}")
        return False

    if not isinstance(raw, dict):
        print("❌ 유효한 JSON 객체가 아닙니다.")
        return False

    normalized = normalize_backup_data(raw)

    # 파싱 및 스키마 검증 (app.storage 사용 가능한 경우)
    if parse_document:
        try:
            doc_str = json.dumps(normalized, ensure_ascii=False)
            app_data, read_only = parse_document(doc_str)
            print(f"✅ 데이터 검증 통과 (시간표 {len(app_data.timetables)}개, 활성 ID: {app_data.active_id})")
        except Exception as e:
            print(f"⚠️ 경고: 스키마 검증 중 오류 발생 (계속 진행합니다): {e}")

    # 저장할 대상 위치 2곳 (flet run 용 및 python main.py fallback 용)
    target_dirs = [
        ROOT_DIR / ".flet" / "storage" / "data",
        ROOT_DIR / ".data",
    ]

    for target_dir in target_dirs:
        target_dir.mkdir(parents=True, exist_ok=True)
        data_file = target_dir / "data.json"
        bak_file = target_dir / "data.json.bak"

        # 기존 파일이 있다면 백업
        if data_file.exists():
            shutil.copy2(data_file, bak_file)

        # 포맷팅하여 저장
        with open(data_file, "w", encoding="utf-8") as f:
            json.dump(normalized, f, ensure_ascii=False, indent=2)

        print(f"💾 복원 완료 -> {data_file.relative_to(ROOT_DIR)}")

    print("\n🎉 백업 파일이 앱 저장소로 성공적으로 복원되었습니다!")
    print("이제 `bash run.sh` 또는 `flet run main.py`를 실행하면 해당 데이터로 시작됩니다.")
    return True


def main() -> None:
    if len(sys.argv) > 1:
        backup_file = Path(sys.argv[1]).resolve()
        if not backup_file.exists():
            print(f"❌ 파일을 찾을 수 없습니다: {backup_file}")
            sys.exit(1)
    else:
        backup_file = find_default_backup_file()
        if not backup_file:
            print("❌ 백업 파일을 찾을 수 없습니다. 파일 경로를 직접 인자로 전달해주세요.")
            print("예: python scripts/restore_backup.py /path/to/backup.json")
            sys.exit(1)
        print(f"🔍 자동으로 탐색된 백업 파일: {backup_file}")

    success = restore_backup(backup_file)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
