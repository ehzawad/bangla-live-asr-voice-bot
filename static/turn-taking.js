// VAD finds speech; this controller decides when a conversational turn is over.
// Timings are heuristics, not a semantic end-of-turn model.
class TurnTaking {
  constructor({onTurn, onWait = () => {}, basePause = () => 800,
               now = () => performance.now(), schedule = (fn, ms) => setTimeout(fn, ms), cancel = id => clearTimeout(id)}) {
    Object.assign(this, {onTurn, onWait, basePause, now, schedule, cancel});
    this.segments = [];
    this.speaking = false;
    this.epoch = 0;
    this.timer = null;
    this.pauseAverage = 0;
    this.text = '';
  }
  start() {
    if (this.segments.length && this.lastVoice != null) {
      const pause = this.now() - this.lastVoice;
      if (pause < 2400) this.pauseAverage = this.pauseAverage * 0.6 + pause * 0.4;
    }
    this.cancel(this.timer);
    this.timer = null;
    this.speaking = true;
    this.epoch++;
    this.text = '';
  }
  hint(text) {
    this.text = text;
    if (!this.speaking && this.segments.length) this.arm();
  }
  end(segment, silenceMs = 300) {
    this.speaking = false;
    this.segments.push(segment);
    this.lastVoice = this.now() - silenceMs;
    this.arm();
  }
  misfire() {
    this.speaking = false;
    if (this.segments.length) this.arm();
  }
  delay() {
    const duration = this.segments.reduce((sum, s) => sum + s.audio.length / 16, 0);
    let wait = Math.max(Number(this.basePause()), this.pauseAverage + 350);
    // Short fragments and trailing connectives often mean the speaker is thinking.
    if (duration < 1800) wait = Math.max(wait, 1200);
    const words = this.text.trim().replace(/[।.!?,;:]+$/u, '').split(/\s+/u);
    if (/^(আর|এবং|কিন্তু|কারণ|যদি|যে|মানে|তো|অথবা|তারপর|উম|and|but|because|if|so|um)$/iu.test(words.at(-1) || '')) {
      wait = Math.max(wait, 1800);
    }
    return Math.min(2400, Math.max(500, wait));
  }
  arm() {
    this.cancel(this.timer);
    const remaining = Math.max(0, this.delay() - (this.now() - this.lastVoice));
    this.onWait(remaining);
    this.timer = this.schedule(() => this.flush(), remaining);
  }
  flush() {
    this.cancel(this.timer);
    this.timer = null;
    if (!this.segments.length) return;
    const segments = this.segments;
    this.segments = [];
    // Preserve real pauses and avoid duplicating overlapping VAD pre-roll.
    const startMs = Math.min(...segments.map(s => s.startMs));
    const offsets = segments.map(s => Math.round((s.startMs - startMs) * 16));
    const length = Math.max(...segments.map((s, i) => offsets[i] + s.audio.length));
    const audio = new Float32Array(length);
    segments.forEach((s, i) => audio.set(s.audio, offsets[i]));
    this.onTurn({audio, startMs, endMs: startMs + length / 16, epoch: this.epoch});
    this.text = '';
  }
  reset() {
    this.cancel(this.timer);
    this.timer = null;
    this.segments = [];
    this.speaking = false;
    this.text = '';
    this.epoch++;
  }
}
window.TurnTaking = TurnTaking;
