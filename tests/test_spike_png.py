from app.spike_png import make_png


def test_png_signature_and_size():
    data = make_png(400, 240)
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    from io import BytesIO

    from PIL import Image

    assert Image.open(BytesIO(data)).size == (400, 240)
