import io
import unittest
import wave
from speech import wav_chunks


def wav(seconds):
    output=io.BytesIO()
    with wave.open(output,'wb') as audio:
        audio.setparams((1,2,16000,0,'NONE','not compressed'))
        audio.writeframes(b'\0\0'*int(seconds*16000))
    return output.getvalue()


class SpeechChunkTests(unittest.TestCase):
    def test_long_audio_respects_model_limit_without_losing_samples(self):
        total=0
        for blob in wav_chunks(wav(65)):
            with wave.open(io.BytesIO(blob)) as audio:
                self.assertLessEqual(audio.getnframes(),30*16000)
                total+=audio.getnframes()
        self.assertEqual(total,65*16000)

    def test_short_greeting_is_one_complete_chunk(self):
        chunks=list(wav_chunks(wav(.18)))
        self.assertEqual(len(chunks),1)
        with wave.open(io.BytesIO(chunks[0])) as audio:
            self.assertEqual(audio.getnframes(),2880)
