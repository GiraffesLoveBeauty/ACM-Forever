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
    assert page.locator('.theme-preset').count() == 4
    for preset in ['gray', 'sunshine', 'rose', 'mint']:
        page.locator('[data-preset=' + preset + ']').click()
        assert page.locator('[data-preset=' + preset + ']').get_attribute('aria-pressed') == 'true'
    page.locator('.theme-restore-original').click()
    assert page.evaluate("document.body.style.getPropertyValue('--brand')") == original
    assert page.evaluate("getComputedStyle(document.body).transitionDuration") == '0s'
    page.locator('#theme-hex-primary').fill('#9342ac')
    page.wait_for_function("document.body.style.getPropertyValue('--brand') === '#9342ac'")
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
    page.wait_for_function("document.body.style.getPropertyValue('--brand') === '#9342ac'")
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
    page.locator('.theme-contrast-item[data-pass=false]').first.wait_for()
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
    # One task emits 40 inputs: only the newest value paints; cancel must also
    # prevent an old callback from touching a newly opened dialog session.
    result = page.evaluate("""async () => {
      const input=document.querySelector('#theme-color-primary');
      const proto=CSSStyleDeclaration.prototype, original=proto.setProperty;
      let writes=0;
      proto.setProperty=function(...args){writes++;return original.apply(this,args)};
      for(let i=0;i<40;i++) {
        input.value='#'+(0x220000+i).toString(16);
        input.dispatchEvent(new Event('input',{bubbles:true}));
      }
      const syncWrites=writes;
      await new Promise(requestAnimationFrame);
      const firstWrites=writes, final=document.body.style.getPropertyValue('--brand');
      input.dispatchEvent(new Event('input',{bubbles:true}));
      await new Promise(requestAnimationFrame);
      const repeatedWrites=writes-firstWrites;
      proto.setProperty=original;
      input.value='#123456';input.dispatchEvent(new Event('input',{bubbles:true}));
      document.querySelector('.theme-cancel').click();ACMTheme.open();
      const restored=document.body.style.getPropertyValue('--brand');
      await new Promise(requestAnimationFrame);
      return {syncWrites,firstWrites,repeatedWrites,final,restored,
        after:document.body.style.getPropertyValue('--brand')};
    }""")
    assert result['syncWrites'] == 0, result
    assert 0 < result['firstWrites'] <= 160, result
    assert result['repeatedWrites'] == 0, result
    assert result['final'] == '#220027', result
    assert result['restored'] == result['after'], result
    page.locator('.theme-cancel').click()
    assert page.evaluate("document.documentElement.dataset.themeEditing") == 'false'
    assert page.evaluate("getComputedStyle(document.body).transitionDuration") != '0s'
    # Saving within the input task must persist the newest draft even before RAF.
    page.locator('.theme-trigger').click()
    page.evaluate("""() => {
      const input=document.querySelector('#theme-color-primary');
      input.value='#345678';input.dispatchEvent(new Event('input',{bubbles:true}));
      document.querySelector('.theme-save').click();
    }""")
    assert page.evaluate("JSON.parse(localStorage.getItem('acm.theme.v1')).light.colors.primary") == '#345678'
    page.locator('.theme-trigger').click()
    output = Path(__file__).resolve().parents[3] / 'data' / 'theme-preview.png'
    output.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(output))
    assert not errors, errors
    print('PASS: preview/cancel/save/reload/cross-page/dark profiles/contrast/repair/library/export/invalid import/login/mobile; no JS errors')
    print('Screenshot:', output)
    context.close()
    browser.close()
