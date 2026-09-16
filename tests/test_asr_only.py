import sys
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
import server


class ASROnlyTests(unittest.TestCase):
    def test_health_has_no_llm_dependency(self):
        with patch('asr.status', return_value={'loaded': True}):
            self.assertEqual(TestClient(server.app).get('/api/health').json(), {'asr': {'loaded': True}})
        self.assertNotIn('llm', sys.modules)

    def test_reply_api_is_absent(self):
        self.assertEqual(TestClient(server.app).post('/api/sessions/test/reply', json={}).status_code, 404)

    def test_ui_has_no_bot_controls(self):
        html = TestClient(server.app).get('/').text
        for marker in ('doReply', 'doSpeak', 'llmModel', 'speechSynthesis', 'generateReply'):
            self.assertNotIn(marker, html)
