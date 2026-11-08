"""15.7.7: Tastaturbedienung in den echten Dialogen."""

import shutil

import pytest

from tests.test_end_to_end import AGENT, SPRACHE
from tests.test_v1300_luna import _anlegen, _zustimmung, server  # noqa: F401


@pytest.mark.parametrize('width', [390, 1280])
def test_f094_keyboard_focus_stays_inside_the_open_modal(server, width):  # noqa: F811
    playwright = pytest.importorskip('playwright.sync_api')
    executable = shutil.which('chromium') or shutil.which('chromium-browser')
    if not executable:
        pytest.skip('Chromium fehlt')
    consent = _zustimmung(server)
    status, headers, _ = _anlegen(server, consent)
    assert status == 200
    cookie = consent + '; ' + headers['Set-Cookie'].split(';', 1)[0]
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=executable, headless=True,
                                    args=['--no-sandbox'])
        page = browser.new_page(user_agent=AGENT, viewport={'width': width, 'height': 900},
                                extra_http_headers={'Cookie': cookie,
                                                    'Accept-Language': SPRACHE})
        page.goto(f'http://127.0.0.1:{server}')
        if width < 600:
            page.locator('#btn-side').click()
        page.locator('#btn-settings').click()
        page.locator('#overlay.open').wait_for(state='visible')
        page.evaluate('''() => {
          const fields = [...document.querySelectorAll(`#overlay button, #overlay input,
            #overlay select, #overlay textarea, #overlay a[href]`)]
            .filter(e => !e.disabled && e.tabIndex >= 0 && e.getClientRects().length);
          fields.at(-1).focus();
        }''')
        page.keyboard.press('Tab')
        assert page.evaluate("document.querySelector('#overlay').contains(document.activeElement)")
        browser.close()
