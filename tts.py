"""Local neural Bengali speech in a dedicated CPU worker.

MMS Bengali (facebook/mms-tts-ben) weights are CC-BY-NC-4.0.
The worker keeps CPU thread limits separate from the GPU ASR process.
"""
import asyncio
import io
import multiprocessing
import os
import re
from concurrent.futures import ProcessPoolExecutor

MODEL_ID = os.environ.get('CTC_TTS_MODEL', 'facebook/mms-tts-ben')
_pool = None
_model = None
_tokenizer = None
_status = {'model': MODEL_ID, 'loaded': False, 'error': None, 'device': 'cpu'}


def _initialize():
    global _model, _tokenizer
    import torch
    from transformers import AutoTokenizer, VitsModel
    torch.set_num_threads(max(1, int(os.environ.get('CTC_TTS_THREADS', '4'))))
    _model = VitsModel.from_pretrained(MODEL_ID, use_safetensors=True).eval()
    _tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    return True


def status():
    return dict(_status)


def start_loading():
    global _pool
    if _pool is not None:
        return
    _pool = ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context('spawn'))
    future = _pool.submit(_initialize)
    def ready(result):
        try:
            result.result()
            _status['loaded'] = True
        except Exception as exc:
            _status['error'] = str(exc)
    future.add_done_callback(ready)


def stop():
    global _pool
    if _pool is not None:
        _pool.shutdown(wait=False, cancel_futures=True)
        _pool = None
    _status['loaded'] = False


def _chunks(text):
    # Bound synthesis memory without cutting words in the middle.
    for sentence in re.split(r'(?<=[।.!?])\s*', text.strip()):
        chunk = ''
        for word in sentence.split():
            if chunk and len(chunk) + len(word) > 220:
                yield chunk
                chunk = ''
            chunk = (chunk + ' ' + word).strip()
        if chunk:
            yield chunk


def _synthesize(text):
    import numpy as np
    import soundfile as sf
    import torch
    if _model is None:
        _initialize()
    audio = []
    rate = _model.config.sampling_rate
    for chunk in _chunks(text):
        inputs = _tokenizer(chunk, return_tensors='pt')
        with torch.inference_mode():
            wave = _model(**inputs).waveform.squeeze().cpu().numpy()
        if audio:
            audio.append(np.zeros(int(rate * .10), dtype=np.float32))
        audio.append(wave)
    if not audio:
        raise ValueError('No speakable text')
    output = io.BytesIO()
    sf.write(output, np.concatenate(audio), rate, format='WAV', subtype='PCM_16')
    return output.getvalue()


async def synthesize(text: str) -> bytes:
    start_loading()
    if _status['error']:
        raise RuntimeError(_status['error'])
    return await asyncio.wait_for(asyncio.wrap_future(_pool.submit(_synthesize, text)), timeout=60)
