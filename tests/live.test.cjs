const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
let now = 2000;
class Socket {
  static OPEN = 1;
  readyState = 1;
  sent = [];
  send(data) { this.sent.push(data); }
  close() { this.readyState = 3; this.onclose?.(); }
}
const context = {window: {}, WebSocket: Socket, location: {protocol: 'https:', host: 'localhost'}, performance: {now: () => now}, Float32Array};
vm.runInNewContext(fs.readFileSync('static/live.js', 'utf8'), context);
const rendered = [];
const live = new context.window.LiveTranscript(text => rendered.push(text), audio => audio);
live.connect();
live.begin();
live.frame(new Float32Array(16000));
assert.equal(live.ws.sent.length, 1);
now += 2000;
live.frame(new Float32Array(16000));
assert.equal(live.ws.sent.length, 1, 'only one request in flight');
live.end(); live.begin();
live.ws.onmessage({data: JSON.stringify({type: 'partial', text: 'old turn'})});
assert.notEqual(rendered.at(-1), 'old turn', 'stale results must be ignored');
live.frame(new Float32Array(16000));
live.ws.onmessage({data: JSON.stringify({type: 'partial', text: 'বাংলা'})});
assert.equal(rendered.at(-1), 'বাংলা');
for (let i = 0; i < 1000; i++) live.frame(new Float32Array(512));
assert.ok(live.samples <= 320000, 'bounded rolling audio buffer');
const old = live.ws;
live.close();
old.onmessage({data: JSON.stringify({type: 'partial', text: 'late'})});
assert.equal(rendered.at(-1), '');
console.log('Live preview lifecycle, backpressure, stale-response and buffer tests passed');
