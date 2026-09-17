"""Browser control-flow regression using synthetic VAD and mocked API responses.
Run against a running app: .venv/bin/python tests/browser_duplex.py
Requires Playwright and a local Chrome executable; no microphone recordings used.
"""
import asyncio
import json
import os
from playwright.async_api import async_playwright

VAD = '''
window.vad = {
  NonRealTimeVAD: {new: async () => ({})},
  MicVAD: {new: async options => {
    window.testVAD = options;
    return {start: async () => {}, pause: async () => {window.pauseCount++}, destroy: async () => {}};
  }},
  utils: {encodeWAV: () => new ArrayBuffer(44)}
};
'''
SPEECH = '''
window.pauseCount = 0; window.speakCount = 0; window.cancelCount = 0;
Object.defineProperty(window, 'speechSynthesis', {value: {
  getVoices: () => [{lang: 'bn-BD'}],
  speak: u => { if (u.volume !== 0) window.speakCount++; },
  cancel: () => {window.cancelCount++;}
}});
window.SpeechSynthesisUtterance = class {constructor(text) {this.text = text;}};
'''

async def main():
    requests = []
    errors = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(executable_path='/usr/bin/google-chrome', headless=True)
        page = await browser.new_page()
        await page.add_init_script(SPEECH)
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.route('**/ort.wasm.min.js', lambda route: route.fulfill(body='window.ort = {};', content_type='application/javascript'))
        await page.route('**/bundle.min.js', lambda route: route.fulfill(body=VAD, content_type='application/javascript'))
        async def api(route):
            path = route.request.url.split('/api/')[1]
            requests.append(path)
            if path == 'health':
                data = {'asr': {'loaded': True, 'device': 'test'}, 'llm': {'available': True, 'model': 'gemma4:e2b', 'models': ['gemma4:e2b']}}
            elif path == 'sessions':
                data = {'session_id': 'browser-test'}
            elif path.endswith('/turns'):
                data = {'text': 'আমার কথা শুনতে পাচ্ছেন', 'file': 'test.wav', 'asr_ms': 1}
            elif path.endswith('/reply'):
                data = {'text': 'হ্যাঁ, আমি শুনতে পাচ্ছি।', 'model': 'gemma4:e2b', 'gen_ms': 1}
            else:
                data = {'ok': True}
            await route.fulfill(json=data)
        await page.route('**/api/**', api)
        await page.goto(os.environ.get('CTC_URL', 'https://localhost:8443'))
        await page.locator('#micBtn:not([disabled])').wait_for()
        await page.locator('#micBtn').click()
        await page.wait_for_timeout(100)
        assert await page.evaluate('!!window.testVAD'), {'errors': errors, 'ui': await page.locator('#err').inner_text(), 'status': await page.locator('#statusText').inner_text()}
        await page.evaluate('''() => {
          testVAD.onSpeechStart(); testVAD.onSpeechRealStart();
          testVAD.onSpeechEnd(new Float32Array(32000));
        }''')
        await page.wait_for_timeout(200)
        assert not any(path.endswith('/reply') for path in requests), 'replied before natural pause'
        await page.evaluate('testVAD.onSpeechStart(); testVAD.onSpeechRealStart();')
        await page.wait_for_timeout(650)
        assert not any(path.endswith('/reply') for path in requests), 'replied while user continued'
        await page.evaluate('testVAD.onSpeechEnd(new Float32Array(32000));')
        await page.wait_for_function('window.speakCount === 1')
        assert await page.evaluate('window.pauseCount') == 0, 'microphone paused during bot speech'
        assert requests.count('sessions/browser-test/turns') == 1, 'thinking pause split the user turn'
        await page.evaluate('testVAD.onSpeechStart(); testVAD.onSpeechRealStart();')
        await page.wait_for_function('window.cancelCount > 0')
        await page.wait_for_timeout(100)
        assert 'sessions/browser-test/interrupt' in requests, 'server was not told about interruption'
        assert await page.locator('.turn.bot').inner_text() and 'interrupted' in await page.locator('.turn.bot').inner_text()
        await page.evaluate('testVAD.onSpeechEnd(new Float32Array(32000));')
        await page.wait_for_function('window.speakCount === 2')
        await page.locator('#micBtn').click()
        assert await page.evaluate('window.pauseCount') == 1, 'stop should release the microphone'
        assert not errors, errors
        print('Browser duplex passed: natural pause, continuation, live mic during reply, interruption, next reply, stop.')
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
