"""Image composer and mixed voice/chat control-flow regression with mocked APIs."""
import asyncio
import json
import os
from pathlib import Path
from playwright.async_api import async_playwright

VAD = '''window.vad = {
 NonRealTimeVAD: {new: async () => ({})},
 MicVAD: {new: async o => {window.testVAD=o; return {start: async()=>{}, pause:async()=>{}, destroy:async()=>{}};}},
 utils: {encodeWAV: () => new ArrayBuffer(44)}
};'''
PNG = bytes.fromhex('89504e470d0a1a0a0000000d4948445200000001000000010804000000b51c0c020000000b4944415478da6364f80f00010501012718e3660000000049454e44ae426082')

async def main():
    requests, errors = [], []
    fail_message = False
    slow_reply = False
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path='/usr/bin/google-chrome', headless=True)
        page = await browser.new_page()
        page.on('pageerror', lambda e: errors.append(str(e)))
        await page.route('**/ort.wasm.min.js', lambda r: r.fulfill(body='window.ort={};', content_type='application/javascript'))
        await page.route('**/bundle.min.js', lambda r: r.fulfill(body=VAD, content_type='application/javascript'))
        async def api(route):
            path = route.request.url.split('/api/')[1]
            requests.append(path)
            if path == 'health':
                data = {'asr': {'loaded': True}, 'llm': {'available': True, 'model': 'gemma4:e2b', 'models': ['gemma4:e2b']}, 'tts': {'loaded': True}}
            elif path == 'sessions':
                data = {'session_id': 'images-test'}
            elif path.endswith('/messages'):
                if fail_message:
                    await route.fulfill(status=400, json={'detail': 'Image could not be read'})
                    return
                payload = route.request.post_data_buffer.decode(errors='replace')
                text = payload.split('name="text"\r\n\r\n')[1].split('\r\n')[0]
                data = {'text': text or 'ছবিতে কী আছে?', 'image': 'image-test.png' if 'name="image"' in payload else None}
            elif '/images/' in path:
                await route.fulfill(body=PNG, content_type='image/png')
                return
            elif path.endswith('/reply/stream'):
                if slow_reply:
                    await asyncio.sleep(0.6)
                turn = {'text': 'উত্তর', 'model': 'gemma4:e2b', 'gen_ms': 1}
                await route.fulfill(body='\n'.join(json.dumps(e) for e in [{'type':'delta','text':'উত্তর'},{'type':'done','turn':turn}])+'\n', content_type='application/x-ndjson')
                return
            elif path.endswith('/turns'):
                data = {'text': 'হ্যালো', 'file': 'test.wav', 'asr_ms': 1}
            else:
                data = {'ok': True}
            await route.fulfill(json=data)
        await page.route('**/api/**', api)
        await page.goto(os.environ.get('CTC_URL', 'https://localhost:8443'))
        await page.locator('#micBtn:not([disabled])').wait_for()
        await page.locator('#doSpeak').uncheck()
        assert not await page.locator('#doPreview').is_checked()
        assert await page.locator('#sendChatBtn').is_disabled()
        image_file = {'name': 'picture.png', 'mimeType': 'image/png', 'buffer': PNG}
        await page.locator('#imageInput').set_input_files(image_file)
        assert await page.locator('#imagePreview').is_visible()
        await page.locator('#removeImageBtn').click()
        assert await page.locator('#imagePreview').is_hidden()
        assert await page.locator('#sendChatBtn').is_disabled()
        await page.locator('#imageInput').set_input_files({'name': 'bad.svg', 'mimeType': 'image/svg+xml', 'buffer': b'<svg/>'})
        assert 'Choose a JPEG' in await page.locator('#chatError').inner_text()
        await page.locator('#imageInput').set_input_files(image_file)
        await page.locator('#sendChatBtn').click()
        await page.locator('.turn.chat img').wait_for()
        await page.locator('.turn.bot').wait_for()
        assert await page.locator('#stSpeech').inner_text() == '0.0s'
        assert await page.locator('#exportWavBtn').is_disabled()
        assert await page.locator('#imagePreview').is_hidden()
        malicious = '<img src=x onerror=alert(1)>'
        await page.locator('#chatText').fill(malicious)
        await page.locator('#chatText').press('Control+Enter')
        await page.wait_for_function('document.querySelectorAll(".turn.chat").length===2')
        assert await page.locator('.turn.chat').nth(1).locator('.text').inner_text() == malicious
        assert await page.locator('.turn.chat').nth(1).locator('img').count() == 0
        await page.locator('#showText').uncheck()
        assert await page.locator('.turn.chat .text').first.is_hidden()
        assert await page.locator('.turn.chat img').first.is_visible()
        assert await page.locator('.turn.chat .text').nth(1).text_content() == malicious
        async with page.expect_download() as event:
            await page.locator('#exportJsonBtn').click()
        data = json.loads(Path(await (await event.value).path()).read_text())
        assert data['turns'][0]['image'] == 'image-test.png'
        assert data['turns'][0]['start_ms'] is None
        assert any(t['text'] == malicious for t in data['turns'])
        await page.locator('#showText').check()
        assert await page.locator('.turn.chat .text').first.is_visible()
        fail_message = True
        await page.locator('#chatText').fill('Keep my draft')
        await page.locator('#sendChatBtn').click()
        await page.wait_for_function('document.getElementById("chatError").textContent.includes("Image could not be read")')
        assert await page.locator('#chatText').input_value() == 'Keep my draft'
        fail_message = False
        await page.locator('#micBtn').click()
        await page.evaluate('testVAD.onSpeechStart(); testVAD.onSpeechRealStart();')
        count = sum(x.endswith('/reply/stream') for x in requests)
        await page.locator('#sendChatBtn').click()
        await page.wait_for_function('document.getElementById("chatText").value===""')
        await page.wait_for_timeout(150)
        assert sum(x.endswith('/reply/stream') for x in requests) == count, 'chat replied over speech'
        await page.evaluate('testVAD.onSpeechEnd(new Float32Array(32000));')
        await page.wait_for_timeout(1300)
        assert sum(x.endswith('/reply/stream') for x in requests) == count + 1
        await page.locator('#micBtn').click()
        slow_reply = True
        await page.locator('#chatText').fill('First')
        await page.locator('#sendChatBtn').click()
        await page.wait_for_timeout(80)
        await page.locator('#chatText').fill('Second')
        await page.locator('#sendChatBtn').click()
        await page.wait_for_timeout(850)
        assert 'sessions/images-test/interrupt' in requests
        assert not errors, errors
        print('Image chat passed: preview/remove, validation, image-only, safe text, export, error recovery, speech deferral and reply interruption.')
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
