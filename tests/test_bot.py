import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
import server


class BotTests(unittest.TestCase):
    def test_reply_uses_transcript_history_and_is_saved(self):
        client = TestClient(server.app)
        with tempfile.TemporaryDirectory() as directory, patch.object(server, 'CONVS', Path(directory)), patch('llm.reply', return_value='আমি ভালো আছি।') as reply:
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
