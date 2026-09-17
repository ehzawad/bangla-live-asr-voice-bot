import asyncio
import base64
import io
import unittest
import wave
from unittest.mock import patch

import httpx
import llm


def wav_bytes(frames=1600, rate=16000, channels=1, width=2):
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(b'\0' * frames * channels * width)
    return buffer.getvalue()


class GemmaAudioTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_audio_payload_and_transcript(self):
        blob = wav_bytes()
        async def respond(request):
            import json
            payload = json.loads(request.content)
            self.assertEqual(request.url.path, '/api/chat')
            self.assertEqual(payload['model'], llm.MODEL)
            self.assertFalse(payload['think'])
            self.assertFalse(payload['stream'])
            self.assertEqual(payload['options'], {'temperature': 0, 'num_predict': 256})
            self.assertEqual(base64.b64decode(payload['messages'][0]['images'][0]), blob)
            return httpx.Response(200, json={'message': {'content': ' হ্যালো '}})
        client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        with patch.object(llm.httpx, 'AsyncClient', return_value=client):
            self.assertEqual(await llm.transcribe_audio(blob), 'হ্যালো')
        self.assertTrue(client.is_closed)

    async def test_rejects_invalid_audio_before_request(self):
        invalid = [b'not wav', wav_bytes(0), wav_bytes(480001),
                   wav_bytes(rate=8000), wav_bytes(channels=2),
                   wav_bytes(width=1), wav_bytes()[:-8], b'x' * 1_000_001]
        with patch.object(llm.httpx, 'AsyncClient') as client:
            for blob in invalid:
                with self.subTest(size=len(blob)), self.assertRaises(ValueError):
                    await llm.transcribe_audio(blob)
            client.assert_not_called()

    async def test_cancellation_closes_client(self):
        started = asyncio.Event()
        async def respond(request):
            started.set()
            await asyncio.Event().wait()
        client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        with patch.object(llm.httpx, 'AsyncClient', return_value=client):
            task = asyncio.create_task(llm.transcribe_audio(wav_bytes()))
            await asyncio.wait_for(started.wait(), 1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertTrue(client.is_closed)

    async def test_backend_error_is_not_a_transcript(self):
        client = httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(503, json={'error': 'unavailable'})))
        with patch.object(llm.httpx, 'AsyncClient', return_value=client):
            with self.assertRaises(httpx.HTTPStatusError):
                await llm.transcribe_audio(wav_bytes())


if __name__ == '__main__':
    unittest.main()
