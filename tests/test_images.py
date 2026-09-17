import base64
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from fastapi.testclient import TestClient
import server
from media import normalize_image


def image_bytes(color='red', mode='RGB'):
    out=io.BytesIO()
    Image.new(mode,(64,64),color).save(out,format='PNG')
    return out.getvalue()


class ImageChatTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.storage=patch.object(server,'CONVS',Path(self.temp.name))
        self.storage.start()
        self.client=TestClient(server.app)
        self.sid=self.client.post('/api/sessions').json()['session_id']

    def tearDown(self):
        self.storage.stop()
        self.temp.cleanup()

    def test_image_sent_to_gemma_and_retained_for_voice_followup(self):
        response=self.client.post(f'/api/sessions/{self.sid}/messages',data={'text':'এই ছবির রং কী?'},files={'image':('red.png',image_bytes(),'image/png')})
        self.assertEqual(response.status_code,200)
        name=response.json()['image']
        self.assertEqual(self.client.get(f'/api/sessions/{self.sid}/images/{name}').status_code,200)
        with patch('llm.reply_async',return_value='লাল') as reply:
            self.client.post(f'/api/sessions/{self.sid}/reply',json={})
            message=reply.call_args.args[0][0]
            self.assertEqual(message['content'],'এই ছবির রং কী?')
            self.assertEqual(Image.open(io.BytesIO(base64.b64decode(message['images'][0]))).format,'JPEG')
        self.client.post(f'/api/sessions/{self.sid}/messages',data={'text':'আর কী দেখা যায়?'})
        with patch('llm.reply_async',return_value='বর্গক্ষেত্র') as reply:
            self.client.post(f'/api/sessions/{self.sid}/reply',json={})
            self.assertIn('images',reply.call_args.args[0][0])

    def test_text_only_image_only_and_empty(self):
        self.assertEqual(self.client.post(f'/api/sessions/{self.sid}/messages',data={'text':'হ্যালো'}).status_code,200)
        result=self.client.post(f'/api/sessions/{self.sid}/messages',files={'image':('a.png',image_bytes())})
        self.assertTrue(result.json()['text'])
        self.assertEqual(self.client.post(f'/api/sessions/{self.sid}/messages',data={}).status_code,400)

    def test_invalid_and_oversized_images_rejected(self):
        for blob, code in [(b'not an image',400),(b'x'*(8*1024*1024+1),413)]:
            response=self.client.post(f'/api/sessions/{self.sid}/messages',files={'image':('a.png',blob)})
            self.assertEqual(response.status_code,code)
        self.assertEqual(list((Path(self.temp.name)/self.sid).iterdir()),[])

    def test_transparency_uses_white_background(self):
        picture=Image.open(io.BytesIO(normalize_image(image_bytes((0,0,0,0),'RGBA'))))
        self.assertEqual(picture.getpixel((0,0)),(255,255,255))
