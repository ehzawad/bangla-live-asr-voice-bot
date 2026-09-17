// Decode split UTF-8/network chunks without losing Bengali text.
async function consumeReplyStream(response, onEvent) {
  if (!response.ok) throw new Error(await response.text());
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '', completed = false;
  function accept(line) {
    if (!line.trim()) return;
    const event = JSON.parse(line);
    if (event.type === 'error') throw new Error(event.error);
    if (event.type === 'done') completed = true;
    onEvent(event);
  }
  try {
    while (true) {
      const {value, done} = await reader.read();
      buffer += done ? decoder.decode() : decoder.decode(value, {stream: true});
      let newline;
      while ((newline = buffer.indexOf('\n')) >= 0) {
        accept(buffer.slice(0, newline));
        buffer = buffer.slice(newline + 1);
      }
      if (done) break;
    }
    if (buffer.trim()) accept(buffer);
    if (!completed) throw new Error('Reply connection ended before completion');
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

class SpeechChunks {
  constructor() { this.pending = ''; }
  push(text, final = false) {
    this.pending += text;
    const chunks = [];
    while (this.pending) {
      const match = this.pending.match(/^[\s\S]*?(?:[।!?]|\.(?=\s))/u);
      let length = match?.[0].length || 0;
      if (!length && this.pending.length > 180) length = this.pending.lastIndexOf(' ', 180);
      if (!length && final) length = this.pending.length;
      if (!length) break;
      const chunk = this.pending.slice(0, length).trim();
      this.pending = this.pending.slice(length).trimStart();
      if (chunk) chunks.push(chunk);
    }
    return chunks;
  }
}
window.consumeReplyStream = consumeReplyStream;
window.SpeechChunks = SpeechChunks;
