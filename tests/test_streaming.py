import io
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import server
import streaming


def wav_bytes(rate=16000, frames=16000):
    out = io.BytesIO()
    with wave.open(out, 'wb') as wav:
        wav.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
        wav.writeframes(b'\0\0' * frames)
    return out.getvalue()


class StreamingTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(server.app)

    def test_preview_and_recovery_after_invalid_audio(self):
        paths = []
        def transcribe(path, timeout):
            self.assertTrue(path.exists())
            paths.append(path)
            return 'বাংলা কথা'
        with patch('asr.status', return_value={'loaded': True}), patch('asr.transcribe', side_effect=transcribe):
            with self.client.websocket_connect('/api/transcribe/live') as ws:
                ws.send_bytes(wav_bytes(rate=8000))
                self.assertEqual(ws.receive_json()['type'], 'error')
                ws.send_bytes(wav_bytes())
                self.assertEqual(ws.receive_json(), {'type': 'partial', 'text': 'বাংলা কথা'})
        self.assertFalse(paths[0].exists())

    def test_model_not_ready(self):
        with patch('asr.status', return_value={'loaded': False}):
            with self.client.websocket_connect('/api/transcribe/live') as ws:
                ws.send_bytes(wav_bytes())
                self.assertEqual(ws.receive_json()['type'], 'error')

    def test_oversized_preview_closes_socket(self):
        with self.client.websocket_connect('/api/transcribe/live') as ws:
            ws.send_bytes(b'0' * (streaming.MAX_AUDIO_BYTES + 1))
            with self.assertRaises(WebSocketDisconnect) as error:
                ws.receive_json()
            self.assertEqual(error.exception.code, 1009)

    def test_final_turn_is_saved(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(server, 'CONVS', Path(directory)), patch('asr.transcribe', return_value='বাংলা'):
            sid = self.client.post('/api/sessions').json()['session_id']
            response = self.client.post(f'/api/sessions/{sid}/turns', data={'source': 'mic', 'start_ms': 0, 'end_ms': 1000}, files={'audio': ('turn.wav', wav_bytes(), 'audio/wav')})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['text'], 'বাংলা')
            self.assertEqual(self.client.get(f'/api/sessions/{sid}').json()['turns'][0]['text'], 'বাংলা')
            self.assertTrue((Path(directory) / sid / response.json()['file']).exists())

    def test_bad_source_rejected(self):
        response = self.client.post('/api/sessions/test/turns', data={'source': '../bad', 'start_ms': 0, 'end_ms': 1}, files={'audio': ('a.wav', wav_bytes())})
        self.assertEqual(response.status_code, 400)


if __name__ == '__main__':
    unittest.main()
