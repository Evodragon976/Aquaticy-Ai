"""Nur den lokalen Anmelde-QR zeigen -- niemals den Desktop oder den QR-Inhalt."""

from __future__ import annotations

import base64
import io
import re

MAX_BYTES = 6 * 1024 * 1024
MAX_PIXELS = 4_000_000


def pairing_code(text: str, messenger: str) -> bool:
    """Nur Kopplungscodes des gewaehlten Diensts, keine fremden QR-Links."""
    if not 20 <= len(text) <= 4096:
        return False
    if messenger == "signal":
        return text.startswith(("sgnl://linkdevice?", "tsdevice:/?"))
    if messenger == "whatsapp":
        return bool(re.fullmatch(r"[0-9]+@[^,\s]+(?:,[^,\s]+){2,}", text))
    return False


def qr_image(data: bytes, messenger: str) -> str | None:
    """QR als PNG-Datenadresse, ohne restlichen Bildschirm. Keine Speicherung/Modellaufrufe."""
    if len(data) > MAX_BYTES:
        raise ValueError("Bild zu gross")

    import zxingcpp
    from PIL import Image

    with Image.open(io.BytesIO(data)) as image:
        if image.width * image.height > MAX_PIXELS:
            raise ValueError("Bild zu gross")
        image.load()
        formats = zxingcpp.BarcodeFormats(zxingcpp.BarcodeFormat.QRCode)
        for code in zxingcpp.read_barcodes(image, formats=formats):
            if not code.valid or not pairing_code(code.text, messenger):
                continue
            points = (code.position.top_left, code.position.top_right,
                      code.position.bottom_left, code.position.bottom_right)
            left, top = min(p.x for p in points), min(p.y for p in points)
            right, bottom = max(p.x for p in points), max(p.y for p in points)

            if min(right - left, bottom - top) < 40:
                continue
            crop = image.crop((left, top, right + 1, bottom + 1)).convert("RGB")
            pad = max(16, crop.width // 8)
            result = Image.new("RGB", (crop.width + 2 * pad, crop.height + 2 * pad), "white")
            result.paste(crop, (pad, pad))
            out = io.BytesIO()
            result.save(out, format="PNG")
            return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode("ascii")
    return None
