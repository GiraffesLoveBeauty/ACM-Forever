"""Optional browser smoke test; run against the isolated local preview only.
Requires playwright and its Chromium browser. No production credentials needed.
"""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = os.getenv('ACM_THEME_TEST_URL', 'http://127.0.0.1:8088')
if not BASE.startswith(('http://127.0.0.1:', 'http://localhost:')):
    raise RuntimeError('Browser smoke test is restricted to localhost.')

with sync_playwright() as p:
    browser = p.chromium.launch(channel=os.getenv('ACM_THEME_BROWSER_CHANNEL', 'msedge'))
    context = browser.new_context(viewport={'width': 1440, 'height': 1000}, color_scheme='light')
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(BASE + '/index.html')
    page.locator('.theme-trigger').click()
    assert page.locator('dialog.theme-editor').is_visible()
    original = page.evaluate("document.body.style.getPropertyValue('--brand')")
    page.locator('#theme-hex-primary').fill('#9342ac')
    assert page.evaluate("document.body.style.getPropertyValue('--brand')") == '#9342ac'
    assert page.evaluate("localStorage.getItem('acm.theme.v1')") is None
    page.keyboard.press('Escape')
    assert page.evaluate("document.body.style.getPropertyValue('--brand')") == original
    page.locator('.theme-trigger').click()
    page.locator('#theme-mode').select_option('light')
    page.locator('#theme-hex-primary').fill('#9342ac')
    page.locator('#theme-hex-background').fill('#f8f3fa')
    page.locator('.theme-save').click()
    page.reload()
    page.wait_for_function("window.ACMTheme && document.body.dataset.customTheme==='true'")
    assert page.evaluate("document.body.style.getPropertyValue('--brand')") == '#9342ac'
    page.goto(BASE + '/leaderboard.html')
    page.locator('.theme-trigger').click()
    assert page.locator('#theme-hex-primary').input_value() == '#9342ac'
    page.locator('#theme-edit-mode').select_option('dark')
    page.locator('#theme-hex-primary').fill('#d4a7ff')
    page.locator('.theme-save').click()
    theme = page.evaluate("JSON.parse(localStorage.getItem('acm.theme.v1'))")
    assert theme['light']['colors']['primary'] == '#9342ac'
    assert theme['dark']['colors']['primary'] == '#d4a7ff'
    page.locator('.theme-trigger').click()
    page.locator('.theme-advanced summary').click()
    page.locator('#theme-hex-text').fill('#f8f3fa')
    assert page.locator('.theme-contrast-item[data-pass=false]').count() > 0
    page.locator('.theme-repair').click()
    assert page.locator('.theme-contrast-item[data-pass=false]').count() == 0
    page.locator('#theme-scheme-name').fill('我的测试配色')
    page.locator('.theme-scheme-save').click()
    assert page.locator('.theme-library-name').inner_text() == '我的测试配色'
    with page.expect_download() as download:
        page.locator('.theme-export').click()
    assert download.value.suggested_filename == 'acm-forever-theme.json'
    page.locator('#theme-import-file').set_input_files({'name':'bad.json','mimeType':'application/json','buffer':b'{"version":1,"css":"url(x)"}'})
    page.wait_for_function("document.querySelector('dialog .theme-status').textContent.includes('导入失败')")
    page.locator('.theme-cancel').click()
    page.goto(BASE + '/login.html')
    page.locator('.theme-trigger').click()
    page.locator('.theme-cancel').click()
    page.set_viewport_size({'width':390,'height':844})
    page.goto(BASE + '/index.html')
    page.locator('.theme-trigger').click()
    box = page.locator('dialog.theme-editor').bounding_box()
    assert box['width'] <= 390 and box['x'] >= 0
    assert page.locator('.theme-save').is_visible()
    page.keyboard.press('Escape')
    page.set_viewport_size({'width':1440,'height':1000})
    page.locator('.theme-trigger').click()
    output = Path(__file__).resolve().parents[3] / 'data' / 'theme-preview.png'
    output.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(output))
    assert not errors, errors
    print('PASS: preview/cancel/save/reload/cross-page/dark profiles/contrast/repair/library/export/invalid import/login/mobile; no JS errors')
    print('Screenshot:', output)
    context.close()
    browser.close()
