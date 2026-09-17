// One request in flight per microphone. Old responses never overwrite a new turn.
class LiveTranscript {
  constructor(render, encode) {
    this.render = render;
    this.encode = encode;
    this.epoch = 0;
    this.frames = [];
    this.samples = 0;
    this.active = false;
    this.pending = false;
  }
  connect() {
    this.close();
    const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/api/transcribe/live`);
    this.ws = ws;
    ws.onmessage = ({data}) => {
      if (this.ws !== ws) return;
      this.pending = false;
      const result = JSON.parse(data);
      if (this.active && this.sentEpoch === this.epoch) {
        this.render(result.type === 'partial' ? result.text : result.error, result.type);
      }
    };
    ws.onclose = () => {
      if (this.ws !== ws) return;
      this.pending = false;
      this.render('Live preview disconnected. Final transcripts still work; restart listening to reconnect.');
    };
    ws.onerror = () => {};
  }
  begin() {
    this.epoch++;
    this.active = true;
    this.lastSent = 0;
    this.render('Listening…');
  }
  end() {
    this.epoch++;
    this.active = false;
    this.frames = [];
    this.samples = 0;
    this.render('');
  }
  frame(frame) {
    this.frames.push(frame.slice());
    this.samples += frame.length;
    // Keep a little pre-roll when silent, and at most 20 seconds while speaking.
    const limit = this.active ? 320000 : 16000;
    while (this.frames.length && this.samples > limit) {
      this.samples -= this.frames.shift().length;
    }
    if (!this.active || this.pending || this.samples < 16000 ||
        this.ws?.readyState !== WebSocket.OPEN || performance.now() - this.lastSent < 1000) return;
    const audio = new Float32Array(this.samples);
    let offset = 0;
    for (const chunk of this.frames) { audio.set(chunk, offset); offset += chunk.length; }
    this.pending = true;
    this.sentEpoch = this.epoch;
    this.lastSent = performance.now();
    this.ws.send(this.encode(audio));
  }
  close() {
    const ws = this.ws;
    this.ws = null;
    if (ws) ws.close();
    this.pending = false;
    this.end();
  }
}
window.LiveTranscript = LiveTranscript;
