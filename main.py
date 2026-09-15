"""T0 스파이크: 빈 Flet 앱 + Pillow PNG 생성 + 파일 저장 다이얼로그."""

import os
from datetime import date

import flet as ft

from app.spike_png import make_png


def main(page: ft.Page) -> None:
    page.title = "시간표 T0 스파이크"
    status = ft.Text("버튼을 눌러 PNG를 저장하세요.")
    picker = ft.FilePicker()

    async def save_with_dialog(e: ft.Event[ft.Button]) -> None:
        try:
            data = make_png()
            path = await picker.save_file(
                dialog_title="PNG 저장",
                file_name=f"timetable_spike_{date.today():%Y%m%d}.png",
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["png"],
                src_bytes=data,
            )
            status.value = f"저장됨: {path} ({len(data)} bytes)" if path else "취소됨"
        except Exception as ex:  # 스파이크: 원인 그대로 표시
            status.value = f"실패: {ex!r}"
        page.update()

    def save_to_app_storage(e: ft.Event[ft.Button]) -> None:
        # R1 대체 경로 확인용: 앱 저장소에 직접 쓰기
        base = os.getenv("FLET_APP_STORAGE_DATA", "./.data")
        os.makedirs(base, exist_ok=True)
        path = os.path.join(base, "spike.png")
        with open(path, "wb") as f:
            f.write(make_png())
        status.value = f"앱 저장소에 저장됨: {path}"
        page.update()

    page.add(
        ft.SafeArea(
            ft.Column(
                [
                    ft.Text("T0 스파이크", size=24),
                    ft.Button("PNG 저장 (다이얼로그)", on_click=save_with_dialog),
                    ft.Button("PNG 저장 (앱 저장소)", on_click=save_to_app_storage),
                    status,
                ]
            )
        )
    )


if __name__ == "__main__":
    ft.run(main)
