"""Nur den lokalen Anmelde-QR zeigen -- niemals den Desktop oder den QR-Inhalt."""

from __future__ import annotations

import base64
import io
import re
from collections.abc import Iterator
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from PIL import Image

MAX_BYTES = 6 * 1024 * 1024
MAX_PIXELS = 4_000_000


def pairing_code(text: str, messenger: str) -> bool:
    """Nur Kopplungscodes des gewaehlten Diensts, keine fremden QR-Links."""
    if not 20 <= len(text) <= 4096:
        return False
    if messenger == "signal":
        return text.startswith(("sgnl://linkdevice?", "tsdevice:/?"))
    if messenger == "whatsapp":
        if text.startswith("https://"):
            try:
                url = urlsplit(text)
            except ValueError:
                return False
            if (url.scheme != "https" or url.netloc != "wa.me"
                    or url.path != "/settings/linked_devices" or url.query):
                return False
            text = url.fragment
        return bool(re.fullmatch(r"[0-9]+@[^,\s]+(?:,[^,\s]+){2,}", text))
    return False


MAX_SIDE = 520


def _variants(image: Image.Image) -> Iterator[tuple[int, Image.Image]]:
    """Das Bild so, wie es ist -- und dann in Formen, die dichte QR-Codes lesbar machen.

    Ein Kopplungscode von WhatsApp ist dicht (rund 80 Punkte je Seite) und steht auf dem
    Bildschirm nur etwa 3 Pixel je Punkt gross. Das Original scheitert dann oft; ein
    vergroessertes oder hart schwarz-weisses Bild nicht. Gelesen wird in der Reihenfolge
    vom billigsten zum teuersten und beim ersten gueltigen Treffer aufgehoert.

    Yields: (Faktor gegenueber dem Original, Bild).
    """
    from PIL import Image, ImageFilter, ImageOps

    rgb = image.convert("RGB")
    klein = rgb.width * rgb.height <= 1_500_000
    yield 1, rgb
    grau = ImageOps.autocontrast(rgb.convert("L"))
    gross = grau.resize((grau.width * 2, grau.height * 2), Image.Resampling.BICUBIC)
    yield 2, gross
    yield 2, rgb.resize((rgb.width * 2, rgb.height * 2), Image.Resampling.BICUBIC)
    for grenze in (110, 190, 150):
        yield 1, grau.point(lambda wert, g=grenze: 255 if wert > g else 0)
    if klein:
        yield 3, rgb.resize((rgb.width * 3, rgb.height * 3), Image.Resampling.BICUBIC)
    weich = rgb.filter(ImageFilter.GaussianBlur(0.8))
    yield 2, weich.resize((rgb.width * 2, rgb.height * 2), Image.Resampling.BICUBIC)


def _render(text: str, ec_level: str) -> str:
    """Den Code frisch zeichnen: scharf, schwarz auf weiss, mit weissem Rand.

    Ein Ausschnitt aus dem Bildschirm waere unscharf und je nach Vergroesserung schwer zu
    scannen. Gezeichnet wird nur, was als Kopplungscode des gewaehlten Diensts geprueft ist.
    """
    import zxingcpp
    from PIL import Image

    level = ec_level if ec_level in {"L", "M", "Q", "H"} else "M"
    code = zxingcpp.create_barcode(text, zxingcpp.BarcodeFormat.QRCode, ec_level=level)
    seite = int(zxingcpp.write_barcode_to_image(code, scale=1).shape[0])
    scale = max(2, min(8, MAX_SIDE // max(1, seite)))
    qr = Image.fromarray(zxingcpp.write_barcode_to_image(code, scale=scale)).convert("RGB")
    rand = 16
    result = Image.new("RGB", (qr.width + 2 * rand, qr.height + 2 * rand), "white")
    result.paste(qr, (rand, rand))
    out = io.BytesIO()
    result.save(out, format="PNG")
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode("ascii")


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
        for faktor, version in _variants(image):
            for code in zxingcpp.read_barcodes(version, formats=formats):
                if not code.valid or not pairing_code(code.text, messenger):
                    continue
                points = (code.position.top_left, code.position.top_right,
                          code.position.bottom_left, code.position.bottom_right)
                breite = (max(p.x for p in points) - min(p.x for p in points)) / faktor
                hoehe = (max(p.y for p in points) - min(p.y for p in points)) / faktor
                if min(breite, hoehe) < 40:
                    continue
                return _render(code.text, str(code.ec_level or ""))
    return None


def render_qr(text: str, ec_level: str = "M") -> str:
    """Zeichnet einen Kopplungscode, den Aquaticy selbst bekommen hat (direkte Kopplung).

    Anders als :func:`qr_image` kommt der Text nicht aus einem Bildschirmfoto, sondern aus dem
    Protokoll. Er muss trotzdem wie ein Kopplungscode aussehen.
    """
    text = str(text or "")
    if not (pairing_code(text, "whatsapp") or pairing_code(text, "signal")):
        raise ValueError("Das ist kein Kopplungscode.")
    return _render(text, ec_level)
