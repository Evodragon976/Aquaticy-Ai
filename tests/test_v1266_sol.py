"""QR-Anmeldung: lokale Bilder, Kontogrenzen, Abbruch und echter Browserdialog."""

from __future__ import annotations

import base64
import contextlib
import io
import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest
import zxingcpp
from PIL import Image

from aquaticy import addons, sandbox, web
from aquaticy.messenger_login import pairing_code, qr_image
from tests.anmeldung import AGENT, SPRACHE
from tests.test_addons import _sitzung
from tests.test_desktop_helper import helfer as helfer
from tests.test_v965 import parallel_site as parallel_site

CODES = {
    "signal": "sgnl://linkdevice?uuid=local-test&pub_key=example-public-key",
    "whatsapp": "2@test-key-with-random-text,public-key,identity-key,client-key",
}


def screenshot(messenger: str) -> bytes:
    code = zxingcpp.create_barcode(CODES[messenger], zxingcpp.BarcodeFormat.QRCode)
    qr = Image.fromarray(zxingcpp.write_barcode_to_image(code, scale=5))
    image = Image.new("RGB", (1280, 800), "red")
    image.paste(qr, (450, 200))
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=95)
    return out.getvalue()


@pytest.mark.parametrize("messenger", CODES)
def test_only_the_scannable_qr_leaves_the_server(messenger: str) -> None:
    data = qr_image(screenshot(messenger), messenger)
    assert data is not None and data.startswith("data:image/png;base64,")
    with Image.open(io.BytesIO(base64.b64decode(data.split(",", 1)[1]))) as image:
        assert image.width < 600 and image.height < 600
        assert image.getpixel((0, 0)) == (255, 255, 255)
        assert zxingcpp.read_barcodes(image)[0].text == CODES[messenger]


@pytest.mark.parametrize("messenger", CODES)
def test_another_services_code_is_never_shown(messenger: str) -> None:
    other = "whatsapp" if messenger == "signal" else "signal"
    assert qr_image(screenshot(other), messenger) is None
    assert not pairing_code("https://example.org/attacker-login", messenger)


def test_corrupt_and_oversized_images_fail_closed() -> None:
    with pytest.raises((OSError, ValueError)):
        qr_image(b"not-an-image", "signal")
    out = io.BytesIO()
    Image.new("L", (2100, 2000)).save(out, format="PNG")
    with pytest.raises(ValueError):
        qr_image(out.getvalue(), "signal")


class Box:
    alive = True
    user_mode = True
    active = "Signal Messenger"
    reads = 0
    messenger = "signal"
    klass = "signal.Signal"

    def desktop(self, *args: str, **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        data = {"fenster": [{"id": "0x123", "klasse": self.klass, "titel": "Signal Messenger"}],
                "aktiv": self.active, "aktiv_klasse": self.klass}
        return subprocess.CompletedProcess(args, 0, json.dumps(data).encode(), b"")

    def screenshot(self, **kwargs: Any) -> bytes:
        self.reads += 1
        return screenshot(self.messenger)


@pytest.fixture
def login(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    session = _sitzung(tmp_path, monkeypatch, "ultra")
    addons._update(session.settings(), "signal", installed=True, enabled=True)
    box = Box()
    monkeypatch.setattr(sandbox, "shared", lambda settings: box)
    result, status = web.addon_action({"action": "login", "id": "signal"})
    assert status == 200
    return session, box, {"id": "signal", "token": result["qr_token"]}


def test_qr_session_is_tied_to_the_owner_and_can_be_cancelled(login):
    session, box, payload = login
    other = web.ChatSession()
    assert web.addon_qr(other, payload)[1] != 200
    result, status = web.addon_qr(session, payload)
    assert status == 200 and result["image"]
    assert CODES["signal"] not in json.dumps(result)
    assert web.addon_qr(session, {**payload, "close": True})[1] == 200
    reads = box.reads
    assert web.addon_qr(session, payload)[1] == 409 and box.reads == reads


@pytest.mark.parametrize("change", [
    "wrong_token", "wrong_id", "expired", "busy", "other_chat", "disabled"])
def test_invalid_or_busy_sessions_never_read_a_frame(login, monkeypatch, change):
    session, box, payload = login
    if change == "wrong_token":
        payload["token"] = "wrong"
    elif change == "wrong_id":
        payload["id"] = "whatsapp"
    elif change == "expired":
        session._qr_login = ("signal", payload["token"], time.monotonic() - 1)
    elif change == "busy":
        monkeypatch.setattr(session, "has_running_chat", lambda: True)
    elif change == "other_chat":
        from types import SimpleNamespace

        session._chat_sessions["other"] = SimpleNamespace(has_running_chat=lambda: True)
    else:
        addons._update(session.settings(), "signal", enabled=False)
    assert web.addon_qr(session, payload)[1] in (403, 409)
    assert box.reads == 0


def test_other_window_and_changed_foreground_cannot_leak_a_code(login):
    session, box, payload = login
    box.klass = "unrelated.browser"
    assert web.addon_qr(session, payload)[0]["image"] is None and box.reads == 0
    box.klass = "signal.Signal"
    box.active = "0x456"
    assert web.addon_qr(session, payload)[0]["image"] is None


def test_the_real_desktop_helper_protocol_uses_a_title_not_a_window_id(login, helfer, monkeypatch):
    session, box, payload = login
    windows = [{"id": "0x123", "klasse": "signal.Signal", "titel": "Signal Messenger"}]
    monkeypatch.setattr(helfer, "fenster_liste", lambda: windows)
    monkeypatch.setattr(helfer, "aktives_fenster", lambda: "Signal Messenger")
    monkeypatch.setattr(helfer, "aktive_klasse", lambda entries: "signal.Signal")
    original = box.desktop

    def desktop(*args, **kwargs):
        if args == ("windows",):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                helfer.cmd_windows([])
            return subprocess.CompletedProcess(args, 0, output.getvalue().encode(), b"")
        return original(*args, **kwargs)

    monkeypatch.setattr(box, "desktop", desktop)
    result, status = web.addon_qr(session, payload)
    assert status == 200 and result["image"]


def test_login_exception_releases_the_background_pause(login, monkeypatch):
    session, box, _ = login

    def fail(*args, **kwargs):
        raise OSError("private-data-that-must-not-escape")

    monkeypatch.setattr(box, "desktop", fail)
    with pytest.raises(OSError):
        web._addon_login(session, addons.get("signal"))
    assert session._qr_login == ("", "", 0.0)


def test_old_dialog_cannot_close_a_new_login(login):
    session, _, old = login
    fresh, status = web.addon_action({"action": "login", "id": "signal"})
    assert status == 200
    assert web.addon_qr(session, {**old, "close": True})[1] == 409
    assert session._qr_login[1] == fresh["qr_token"]


def test_confirming_the_current_login_marks_only_that_addon(login):
    session, _, payload = login
    result, status = web.addon_action({"action": "login_done", **payload})
    assert status == 200
    assert next(a for a in result["addons"] if a["id"] == "signal")["login"]["state"]
    assert session._qr_login == ("", "", 0.0)


def test_expired_confirmation_cannot_mark_an_addon_signed_in(login):
    session, _, payload = login
    session._qr_login = ("signal", payload["token"], time.monotonic() - 1)
    assert web.addon_action({"action": "login_done", **payload})[1] == 400
    assert (addons.load_state(session.settings())["signal"].get("login") or {}).get(
        "state") != "angemeldet"


def test_http_login_frame_requires_authentication_and_same_origin(parallel_site):
    client, _, _, _, _, url = parallel_site
    import httpx

    with httpx.Client(base_url=url, trust_env=False) as outsider:
        assert outsider.post("/api/addons/qr", json={}).status_code == 401
    assert client.post("/api/addons/qr", json={}, headers={"Origin": "https://evil.example"}
                       ).status_code == 403
    response = client.post("/api/addons/qr", json={})
    assert response.status_code == 403
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("messenger", CODES)
@pytest.mark.parametrize("finish", ["cancel", "confirm", "already_linked"])
def test_qr_popup_opens_early_and_discards_late_frames(parallel_site, messenger, finish):
    playwright = pytest.importorskip("playwright.sync_api")
    chromium = shutil.which("chromium")
    if not chromium:
        pytest.skip("System-Chromium fehlt")
    client, _, _, _, _, url = parallel_site
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=chromium)
        context = browser.new_context(user_agent=AGENT,
                                      extra_http_headers={"Accept-Language": SPRACHE})
        context.add_cookies([{"name": k, "value": v, "url": url}
                            for k, v in client.cookies.items()])
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        held = []
        frames = []

        def addons_route(route):
            if route.request.method == "POST":
                held.append(route)
            else:
                route.continue_()

        page.route("**/api/addons", addons_route)
        page.route("**/api/addons/qr", lambda route: frames.append(route)
                   if not route.request.post_data_json.get("close") else route.fulfill(
                       status=200, json={"ok": True}))
        try:
            page.goto(url, wait_until="networkidle")
            page.locator("#auth-gate").wait_for(state="hidden")
            page.evaluate("""id => {
              const card=addonAnmeldung({id, name:id, login:{state:''}, login_kind:'qr',
                usable:true, enabled:true});
              card.id='test-login-card'; document.body.append(card);
            }""", messenger)
            page.locator("#test-login-card").get_by_role(
                "button", name="Anmelden", exact=True).click()
            playwright.expect(page.locator("#qrbox")).to_have_class("overlay open")
            playwright.expect(page.locator("#qr-image")).to_be_hidden()
            assert len(held) == 1
            data = client.get("/api/addons").json()
            held.pop().fulfill(status=200, json={**data, "ok": True, "qr_token": "test-token"})
            page.wait_for_function("() => qrRequest !== null")
            for _ in range(50):
                if frames:
                    break
                page.wait_for_timeout(20)
            assert frames
            frames.pop().fulfill(status=200, json={"ok": True, "image":
                None if finish == "already_linked" else qr_image(screenshot(messenger), messenger)})
            if finish == "already_linked":
                playwright.expect(page.locator("#qr-image")).to_be_hidden()
            else:
                playwright.expect(page.locator("#qr-image")).to_be_visible()
            assert not page.locator("#qr-done").is_disabled()
            assert not page.locator("#qrbox input").count()
            page.evaluate("""() => {
              Object.defineProperty(document,'hidden',{value:true,configurable:true});
              document.dispatchEvent(new Event('visibilitychange'));
              qrAktualisieren();
            }""")
            page.wait_for_timeout(2200)
            assert not frames, "versteckte Tabs lesen keine QR-Bilder"
            page.evaluate("""() => {
              Object.defineProperty(document,'hidden',{value:false,configurable:true});
              document.dispatchEvent(new Event('visibilitychange'));
            }""")
            for _ in range(50):
                if frames:
                    break
                page.wait_for_timeout(20)
            assert frames
            if finish in ("confirm", "already_linked"):
                page.click("#qr-done")
                assert held and held[0].request.post_data_json == {
                    "action": "login_done", "id": messenger, "token": "test-token"}
                held.pop().fulfill(status=200, json={**data, "ok": True})
            else:
                page.keyboard.press("Escape")
            playwright.expect(page.locator("#qrbox")).not_to_have_class("overlay open")

            with contextlib.suppress(playwright.Error):
                frames.pop().fulfill(status=200, json={"ok": True,
                    "image": qr_image(screenshot(messenger), messenger)})
            assert page.locator("#qr-image").get_attribute("src") is None
            assert not errors
        finally:
            browser.close()
