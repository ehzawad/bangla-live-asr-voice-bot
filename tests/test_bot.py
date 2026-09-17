import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
import server


class BotTests(unittest.TestCase):
    def test_reply_uses_transcript_history_and_is_saved(self):
        client = TestClient(server.app)
        with tempfile.TemporaryDirectory() as directory, patch.object(server, 'CONVS', Path(directory)), patch('llm.reply_async', return_value='আমি ভালো আছি।') as reply:
            sid = client.post('/api/sessions').json()['session_id']
            server._save(Path(directory) / sid, [{'index': 1, 'role': 'user', 'text': 'কেমন আছো'}])
            result = client.post(f'/api/sessions/{sid}/reply', json={})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()['text'], 'আমি ভালো আছি।')
            reply.assert_called_once_with([{'role': 'user', 'content': 'কেমন আছো'}], None)
            self.assertEqual(len(client.get(f'/api/sessions/{sid}').json()['turns']), 2)

    def test_empty_conversation_has_no_reply(self):
        client = TestClient(server.app)
        with tempfile.TemporaryDirectory() as directory, patch.object(server, 'CONVS', Path(directory)):
            sid = client.post('/api/sessions').json()['session_id']
            self.assertEqual(client.post(f'/api/sessions/{sid}/reply', json={}).status_code, 400)


class InterruptionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import httpx
        self.directory = tempfile.TemporaryDirectory()
        self.storage = patch.object(server, 'CONVS', Path(self.directory.name))
        self.storage.start()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url='http://test')
        self.sid = (await self.client.post('/api/sessions')).json()['session_id']
        self.path = Path(self.directory.name) / self.sid
        server._save(self.path, [{'index': 1, 'role': 'user', 'text': 'কেমন আছো'}])

    async def asyncTearDown(self):
        await self.client.aclose()
        server._interrupted.pop(self.sid, None)
        self.storage.stop()
        self.directory.cleanup()

    async def test_interrupt_cancels_in_flight_generation(self):
        import asyncio
        started, cancelled = asyncio.Event(), asyncio.Event()
        async def slow_reply(*args):
            started.set()
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                cancelled.set()
                raise
        with patch('llm.reply_async', side_effect=slow_reply):
            request = asyncio.create_task(self.client.post(f'/api/sessions/{self.sid}/reply', json={'request_id': 'first'}))
            await asyncio.wait_for(started.wait(), 2)
            response = await self.client.post(f'/api/sessions/{self.sid}/interrupt', json={'request_id': 'first'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual((await asyncio.wait_for(request, 2)).status_code, 409)
            self.assertTrue(cancelled.is_set())
            self.assertEqual(len(server._load(self.path)), 1)

    async def test_interrupt_arriving_before_reply_blocks_it(self):
        await self.client.post(f'/api/sessions/{self.sid}/interrupt', json={'request_id': 'early'})
        with patch('llm.reply_async') as reply:
            response = await self.client.post(f'/api/sessions/{self.sid}/reply', json={'request_id': 'early'})
            self.assertEqual(response.status_code, 409)
            reply.assert_not_called()

    async def test_interrupted_playback_is_not_used_as_conversation_context(self):
        with patch('llm.reply_async', return_value='পুরনো উত্তর'):
            await self.client.post(f'/api/sessions/{self.sid}/reply', json={'request_id': 'spoken'})
        await self.client.post(f'/api/sessions/{self.sid}/interrupt', json={'request_id': 'spoken'})
        self.assertTrue(server._load(self.path)[-1]['interrupted'])
        with patch('llm.reply_async', return_value='নতুন উত্তর') as reply:
            await self.client.post(f'/api/sessions/{self.sid}/reply', json={'request_id': 'next'})
            reply.assert_awaited_once_with([{'role': 'user', 'content': 'কেমন আছো'}], None)

    async def test_new_speech_discards_stale_reply(self):
        async def replying(*args):
            turns = server._load(self.path)
            turns.append({'index': 2, 'role': 'user', 'text': 'আরেকটা কথা'})
            server._save(self.path, turns)
            return 'stale'
        with patch('llm.reply_async', side_effect=replying):
            response = await self.client.post(f'/api/sessions/{self.sid}/reply', json={})
            self.assertEqual(response.status_code, 409)
            self.assertEqual(len(server._load(self.path)), 2)

    async def test_speech_fallback_response(self):
        with patch('tts.synthesize', return_value=b'RIFF-audio') as synthesize:
            response = await self.client.post('/api/speech', json={'text': 'বাংলা'})
            self.assertEqual(response.headers['content-type'], 'audio/wav')
            synthesize.assert_awaited_once_with('বাংলা')
        self.assertEqual((await self.client.post('/api/speech', json={'text': ''})).status_code, 422)
