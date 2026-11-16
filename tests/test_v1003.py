"""10.0.3 Luna: user, bug hunter, security and privacy regressions."""

from __future__ import annotations

import shutil
from contextlib import contextmanager

import httpx
import pytest

from aquaticy import web
from aquaticy.auth import ultra_code_for
from tests.anmeldung import AGENT, FETCH, SPRACHE, wie_die_app
from tests.test_v965 import parallel_site as parallel_site
from tests.test_v967 import learners as learners


@pytest.fixture
def upgrade_page(parallel_site):
    playwright = pytest.importorskip("playwright.sync_api")
    chromium = shutil.which("chromium")
    if not chromium:
        pytest.skip("System-Chromium fehlt")
    client, _, _, _, _, url = parallel_site
    account = web.AUTH.register("upgrading@example.org", "luna-upgrade-test-passwort", "ultra",
                                pro_code=ultra_code_for(web.AUTH.data_dir),
                                terms_accepted=True, terms_version="1")
    assert client.post("/api/auth/login", headers=FETCH, json=wie_die_app({
        "email": account.email, "password": "luna-upgrade-test-passwort",
    })).status_code == 200
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=chromium)
        try:
            context = browser.new_context(viewport={"width": 390, "height": 800},
                                          user_agent=AGENT,
                                          extra_http_headers={"Accept-Language": SPRACHE})
            context.add_cookies([{"name": k, "value": v, "url": url}
                                for k, v in client.cookies.items()])
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(url, wait_until="networkidle")
            page.locator("#auth-gate").wait_for(state="hidden")
            if page.evaluate("document.body.classList.contains('collapsed')"):
                page.click("#btn-side")
            yield page, playwright.expect
            assert not errors
        finally:
            browser.close()



# 16.0.0: 17 Test(s) entfallen -- sie pruefen Teile, die es nicht mehr gibt
# (Auto-Upgrading und die Einstellungen unter Helfer & Grenzen).


@contextmanager
def compressed_response(payload, encoding):
    response = httpx.Response(200, headers={"Content-Encoding": encoding},
                              stream=httpx.ByteStream(payload),
                              request=httpx.Request("POST", "http://localhost:11434/api/chat"))
    try:
        yield response
    finally:
        response.close()


