"""개발 확인용 샘플 데이터 (한글·일본어, 긴 과목명, 밝은/어두운 색 포함)."""

from app.model import AppData, Cell, Workspace

_ENTRIES = [
    ("0-1", "알고리즘", "K301", "blue"),
    ("0-2", "선형대수", "N201", "indigo"),
    ("1-1", "日本語会話", "L105", "pink"),
    ("1-3", "운영체제", "K402", "teal"),
    ("2-2", "컴퓨터네트워크와 분산시스템 설계 특론", "E310", "yellow"),
    ("2-4", "영어", "", "lime"),
    ("3-1", "알고리즘", "K301", "blue"),
    ("3-5", "데이터베이스", "K205", "amber"),
    ("4-2", "체육", "체육관", "green"),
    ("4-4", "캡스톤디자인", "창의관 3층", "brown"),
]


def sample_data() -> AppData:
    ws = Workspace()
    ws.rename_timetable(ws.active.id, "2026 후기")
    for key, subject, room, color in _ENTRIES:
        ws.set_cell(key, Cell(subject=subject, room=room, color=color))
    return ws.data
