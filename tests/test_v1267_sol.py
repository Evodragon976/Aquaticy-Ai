"""Aktuelle WhatsApp-Kopplungscodes und robuste QR-Anzeige."""

import base64
import io
import random

import pytest
import zxingcpp
from PIL import Image, ImageDraw

from aquaticy.messenger_login import pairing_code, qr_image
from tests.test_v965 import parallel_site as parallel_site
from tests.test_v1266_sol import login as login


def whatsapp_payload() -> str:
    rng = random.Random(1267)
    fields = ['2@' + base64.b64encode(rng.randbytes(100)).decode()]
    fields.extend(base64.b64encode(rng.randbytes(32)).decode() for _ in range(3))
    return 'https://wa.me/settings/linked_devices#' + ','.join([*fields, '1'])


def qr_screen(payload: str, size: int = 240) -> bytes:
    code = zxingcpp.create_barcode(payload, zxingcpp.BarcodeFormat.QRCode, ec_level='H')
    qr = Image.fromarray(zxingcpp.write_barcode_to_image(code, scale=4)).convert('RGB')
    qr = qr.resize((size, size))
    draw = ImageDraw.Draw(qr)
    mid, radius = size // 2, size // 12
    draw.rectangle((mid-radius, mid-radius, mid+radius, mid+radius), fill='white')
    draw.ellipse((mid-radius+2, mid-radius+2, mid+radius-2, mid+radius-2), fill='#25d366')
    image = Image.new('RGB', (1280, 800), 'white')
    image.paste(qr, (800, 150))
    out = io.BytesIO()
    image.save(out, format='JPEG', quality=75)
    return out.getvalue()


def test_current_whatsapp_link_device_url_is_a_pairing_code() -> None:
    assert pairing_code(whatsapp_payload(), 'whatsapp')


@pytest.mark.parametrize('size', [200, 240, 300])
def test_current_whatsapp_code_with_logo_survives_the_desktop_jpeg(size: int) -> None:
    payload = whatsapp_payload()
    result = qr_image(qr_screen(payload, size), 'whatsapp')
    assert result is not None
    with Image.open(io.BytesIO(base64.b64decode(result.split(',', 1)[1]))) as image:
        assert zxingcpp.read_barcodes(image)[0].text == payload


@pytest.mark.parametrize('url', [
    'https://wa.me.attacker.test/settings/linked_devices#',
    'https://wa.me@attacker.test/settings/linked_devices#',
    'http://wa.me/settings/linked_devices#',
    'https://wa.me:444/settings/linked_devices#',
    'https://wa.me/settings/other#',
    'https://wa.me/settings/linked_devices?redirect=evil#',
])
def test_similar_urls_never_count_as_whatsapp_pairing(url: str) -> None:
    assert not pairing_code(url + whatsapp_payload().split('#', 1)[1], 'whatsapp')


def test_long_window_titles_match_the_helpers_truncated_window_list(
    tmp_path, monkeypatch,
) -> None:
    import json
    import subprocess
    import time

    from aquaticy import addons, sandbox, web
    from tests.test_addons import _sitzung
    from tests.test_v1266_sol import Box

    session = _sitzung(tmp_path, monkeypatch, 'ultra')
    addons._update(session.settings(), 'signal', installed=True, enabled=True)
    session._qr_login = ('signal', 'test-token', time.monotonic() + 60)
    title = 'Signal ' + 'x' * 230

    class LongTitle(Box):
        def desktop(self, *args, **kwargs):
            if args == ('windows',):
                data = {'fenster': [{'id': '0x123', 'klasse': self.klass, 'titel': title[:200]}],
                        'aktiv': title, 'aktiv_klasse': self.klass}
                return subprocess.CompletedProcess(args, 0, json.dumps(data).encode(), b'')
            return super().desktop(*args, **kwargs)

    monkeypatch.setattr(sandbox, 'shared', lambda settings: LongTitle())
    result, status = web.addon_qr(session, {'id': 'signal', 'token': 'test-token'})
    assert status == 200 and result['image']




@pytest.mark.parametrize('status', [502, 429, 403, 503])
def test_qr_polling_recovers_from_transient_errors_but_stops_on_denial(parallel_site, status):
    import shutil

    from tests.anmeldung import AGENT, SPRACHE

    playwright = pytest.importorskip('playwright.sync_api')
    chromium = shutil.which('chromium')
    if not chromium:
        pytest.skip('System-Chromium fehlt')
    client, _, _, _, _, url = parallel_site
    account_data = client.get('/api/addons').json()
    image = qr_image(qr_screen(whatsapp_payload()), 'whatsapp')
    attempts = []
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=chromium)
        context = browser.new_context(user_agent=AGENT,
                                      extra_http_headers={'Accept-Language': SPRACHE})
        context.add_cookies([{'name': k, 'value': v, 'url': url}
                            for k, v in client.cookies.items()])
        page = context.new_page()

        def frame(route):
            if route.request.post_data_json.get('close'):
                route.fulfill(status=200, json={'ok': True})
                return
            attempts.append(1)
            if len(attempts) == 1 or status in (403, 503):
                route.fulfill(status=status, json={'error': 'Vorübergehend nicht erreichbar.'})
            else:
                route.fulfill(status=200, json={'ok': True, 'image': image})

        page.route('**/api/addons', lambda route: route.fulfill(status=200,
            json={**account_data, 'ok': True, 'qr_token': 'test-token'})
            if route.request.method == 'POST' else route.continue_())
        page.route('**/api/addons/qr', frame)
        try:
            page.goto(url, wait_until='networkidle')
            page.locator('#auth-gate').wait_for(state='hidden')
            page.evaluate("() => { qrAnmelden({id:'whatsapp',name:'WhatsApp Web'}); }")
            if status == 403:
                playwright.expect(page.locator('#qr-retry')).to_be_visible()
                page.wait_for_timeout(2500)
                assert len(attempts) == 1
            elif status == 503:
                playwright.expect(page.locator('#qr-retry')).to_be_visible(timeout=20000)
                page.wait_for_timeout(2200)
                assert len(attempts) == 4
            else:
                playwright.expect(page.locator('#qr-image')).to_be_visible(timeout=10000)
                assert len(attempts) == 2
                playwright.expect(page.locator('#errorbox')).not_to_be_visible()
            page.click('#qr-close')
            assert page.locator('#qr-image').get_attribute('src') is None
        finally:
            browser.close()


def test_closing_during_a_screen_capture_releases_the_login_immediately(login, monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from aquaticy import web

    session, box, payload = login
    entered, release = threading.Event(), threading.Event()
    original = box.screenshot

    def screenshot(**kwargs):
        entered.set()
        assert release.wait(5)
        return original(**kwargs)

    monkeypatch.setattr(box, 'screenshot', screenshot)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(web.addon_qr, session, payload)
        try:
            assert entered.wait(5)
            assert web.addon_qr(session, {**payload, 'close': True})[1] == 200
            assert session._qr_login == ('', '', 0.0)
        finally:
            release.set()
        result, status = future.result(timeout=5)
        assert status == 409 and 'image' not in result


def test_a_login_response_cannot_steal_a_newer_dialogs_token(login, monkeypatch):
    import time

    from aquaticy import web

    session, _, _ = login
    monkeypatch.setattr(web.secrets, 'token_urlsafe', lambda size: 'request-token')

    def view(s):
        with s._qr_state_lock:
            s._qr_login = ('signal', 'newer-token', time.monotonic() + 600)
        return {'addons': []}

    monkeypatch.setattr(web, 'addons_view', view)
    result, status = web.addon_action({'action': 'login', 'id': 'signal'})
    assert status == 200 and result['qr_token'] == 'request-token'
    assert session._qr_login[1] == 'newer-token'


def test_missing_qr_libraries_get_an_actionable_error(login, monkeypatch):
    import sys

    from aquaticy import web

    session, _, payload = login
    monkeypatch.setitem(sys.modules, 'zxingcpp', None)
    result, status = web.addon_qr(session, payload)
    assert status == 503 and 'Aktualisiere Aquaticy' in result['error']
