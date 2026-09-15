"""T0 스파이크: Flet 없이 Pillow만으로 PNG bytes 생성 (P5)."""

from io import BytesIO

from PIL import Image, ImageDraw


def make_png(width: int = 400, height: int = 240) -> bytes:
    img = Image.new("RGB", (width, height), "#FFFFFF")
    draw = ImageDraw.Draw(img)
    colors = ["#EF5350", "#42A5F5", "#66BB6A", "#FFCA28", "#AB47BC"]
    cell_w = width // len(colors)
    for i, color in enumerate(colors):
        draw.rectangle([i * cell_w, 40, (i + 1) * cell_w - 4, height - 1], fill=color)
    draw.text((10, 12), "T0 spike PNG", fill="#000000")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
