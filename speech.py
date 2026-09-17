"""VAD segments to native Gemma audio input, within its 30-second limit."""
import io
import wave

import llm

_status = {'model': llm.MODEL, 'loaded': False, 'device': 'ollama', 'error': None}


def status():
    return dict(_status)


async def warmup():
    # Load the audio encoder before the first user greeting, using only silence.
    output = io.BytesIO()
    with wave.open(output, 'wb') as audio:
        audio.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        audio.writeframes(b'\0\0' * 8000)
    try:
        await llm.transcribe_audio(output.getvalue())
        _status['loaded'] = True
        _status['error'] = None
    except Exception as exc:
        _status['error'] = str(exc)


def wav_chunks(blob: bytes):
    with wave.open(io.BytesIO(blob), 'rb') as audio:
        if (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) != (16000, 1, 2):
            raise ValueError('Expected 16 kHz mono PCM16 WAV')
        frames = audio.getnframes()
        pcm = audio.readframes(frames)
        if frames < 1 or len(pcm) != frames * 2:
            raise ValueError('Empty or truncated audio')
    offset = 0
    limit = 29 * 16000 * 2
    while offset < len(pcm):
        end = min(offset + limit, len(pcm))
        if end < len(pcm):
            # Prefer a quiet boundary in the final two seconds of this window.
            import numpy as np
            window_start = end - 2 * 16000 * 2
            samples = np.frombuffer(pcm[window_start:end], dtype='<i2').astype('float32')
            energy = (samples.reshape(-1, 320) ** 2).mean(axis=1)
            end = window_start + (int(energy.argmin()) + 1) * 320 * 2
        output = io.BytesIO()
        with wave.open(output, 'wb') as audio:
            audio.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            audio.writeframes(pcm[offset:end])
        yield output.getvalue()
        offset = end


async def transcribe_wav(blob: bytes) -> str:
    parts = []
    for chunk in wav_chunks(blob):
        text = await llm.transcribe_audio(chunk)
        if text:
            parts.append(text)
    return ' '.join(parts)
