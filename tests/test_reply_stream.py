import asyncio
import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
import llm
import server


class ReplyStreamTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.storage = patch.object(server, 'CONVS', Path(self.directory.name))
        self.storage.start()
        self.sid = server.create_session()['session_id']
        self.path = Path(self.directory.name) / self.sid
        server._save(self.path, [{'index': 1, 'role': 'user', 'text': 'হ্যালো'}])

    async def asyncTearDown(self):
        server._interrupted.pop(self.sid, None)
        self.storage.stop()
        self.directory.cleanup()

    async def collect(self, reply_id='test'):
        response = await server.stream_reply(self.sid, server.ReplyIn(request_id=reply_id))
        return [json.loads(line) async for line in response.body_iterator]

    async def test_order_saved_text_and_image_context(self):
        filename = 'image-' + 'a' * 32 + '.jpg'
        (self.path / filename).write_bytes(b'image')
        turns = server._load(self.path)
        turns[0]['image'] = filename
        server._save(self.path, turns)
        async def chunks(history, model):
            self.assertEqual(history[0]['images'], [base64.b64encode(b'image').decode()])
            yield 'হ্যালো! '
            yield 'কেমন আছেন?'
        with patch.object(llm, 'reply_stream', chunks):
            events = await self.collect()
        self.assertEqual([e['type'] for e in events], ['delta', 'delta', 'done'])
        self.assertEqual(events[-1]['turn']['text'], 'হ্যালো! কেমন আছেন?')
        self.assertEqual(server._load(self.path)[-1], events[-1]['turn'])
        self.assertNotIn((self.sid, 'test'), server._replies)

    async def test_interrupt_cancels_producer_without_saving(self):
        started, closed = asyncio.Event(), asyncio.Event()
        async def chunks(*args):
            try:
                yield 'partial'
                started.set()
                await asyncio.Event().wait()
            finally:
                closed.set()
        with patch.object(llm, 'reply_stream', chunks):
            result = asyncio.create_task(self.collect())
            await asyncio.wait_for(started.wait(), 1)
            await server.interrupt_reply(self.sid, server.InterruptIn(request_id='test'))
            events = await asyncio.wait_for(result, 2)
        self.assertEqual(events[-1]['type'], 'error')
        self.assertTrue(closed.is_set())
        self.assertEqual(len(server._load(self.path)), 1)

    async def test_new_user_prevents_stale_response_storage(self):
        async def chunks(*args):
            yield 'outdated'
            turns = server._load(self.path)
            turns.append({'index': 2, 'role': 'user', 'text': 'new question'})
            server._save(self.path, turns)
        with patch.object(llm, 'reply_stream', chunks):
            events = await self.collect()
        self.assertEqual(events[-1]['type'], 'error')
        self.assertIn('superseded', events[-1]['error'])
        self.assertEqual(len(server._load(self.path)), 2)

    async def test_disconnect_closes_producer(self):
        closed = asyncio.Event()
        async def chunks(*args):
            try:
                yield 'partial'
                await asyncio.Event().wait()
            finally:
                closed.set()
        with patch.object(llm, 'reply_stream', chunks):
            response = await server.stream_reply(self.sid, server.ReplyIn(request_id='disconnect'))
            iterator = response.body_iterator
            self.assertEqual(json.loads(await anext(iterator))['type'], 'delta')
            await iterator.aclose()
        self.assertTrue(closed.is_set())
        self.assertNotIn((self.sid, 'disconnect'), server._replies)
        self.assertEqual(len(server._load(self.path)), 1)

    async def test_ollama_stream_ignores_thinking(self):
        def respond(request):
            payload = json.loads(request.content)
            self.assertTrue(payload['stream'])
            self.assertFalse(payload['think'])
            return httpx.Response(200, content='\n'.join(json.dumps(e) for e in [
                {'message': {'thinking': 'private'}},
                {'message': {'content': 'Hello'}},
                {'message': {'content': '!'}, 'done': True},
            ]))
        client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        with patch.object(llm.httpx, 'AsyncClient', return_value=client):
            output = [chunk async for chunk in llm.reply_stream([{'role': 'user', 'content': 'Hi'}])]
        self.assertEqual(output, ['Hello', '!'])
        self.assertTrue(client.is_closed)


if __name__ == '__main__':
    unittest.main()
