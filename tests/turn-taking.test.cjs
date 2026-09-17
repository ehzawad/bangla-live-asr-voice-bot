const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = {window: {}, Float32Array, performance, setTimeout, clearTimeout};
vm.runInNewContext(fs.readFileSync('static/turn-taking.js', 'utf8'), context);
function fixture() {
  let time = 0, next = 0;
  const timers = new Map(), turns = [];
  const controller = new context.window.TurnTaking({
    onTurn: turn => turns.push(turn), now: () => time,
    schedule: (fn, ms) => { const id = ++next; timers.set(id, {fn, when: time + ms}); return id; },
    cancel: id => timers.delete(id),
  });
  const advance = ms => {
    time += ms;
    for (const [id, timer] of [...timers]) if (timer.when <= time) {timers.delete(id); timer.fn();}
  };
  return {controller, turns, advance, timers};
}
{
  const {controller:c, turns, advance} = fixture();
  c.start(); advance(2000);
  c.end({audio: new Float32Array(32000), startMs: 0, endMs: 2000});
  advance(499); assert.equal(turns.length, 0);
  advance(1); assert.equal(turns.length, 1, 'reply after 800 ms total silence');
}
{
  const {controller:c, turns, advance} = fixture();
  c.start(); advance(2000);
  c.end({audio: new Float32Array(32000).fill(1), startMs: 0, endMs: 2000});
  advance(300); c.start();
  advance(1500); assert.equal(turns.length, 0, 'resuming cancels the pending turn');
  c.end({audio: new Float32Array(32000).fill(2), startMs: 1800, endMs: 3800});
  advance(2400);
  assert.equal(turns.length, 1, 'segments around a thinking pause form one turn');
  assert.equal(turns[0].audio.length, 60800, 'overlapping pre-roll is not duplicated');
  assert.equal(turns[0].audio[30000], 2);
}
{
  const {controller:c, turns, advance} = fixture();
  c.start(); advance(1000); c.hint('আমি চাই কিন্তু');
  c.end({audio: new Float32Array(16000), startMs: 0, endMs: 1000});
  advance(1499); assert.equal(turns.length, 0, 'unfinished phrase gets more time');
  advance(1); assert.equal(turns.length, 1);
}
{
  const {controller:c, turns, advance, timers} = fixture();
  c.start(); advance(1000);
  c.end({audio: new Float32Array(16000), startMs: 0, endMs: 1000});
  advance(899); assert.equal(turns.length, 0, 'short fragment needs 1200 ms silence');
  c.flush(); c.reset(); advance(10000);
  assert.equal(turns.length, 1, 'stop flushes once'); assert.equal(timers.size, 0);
}
{
  const {controller:c, turns, advance} = fixture();
  c.start(); c.misfire(); advance(5000); assert.equal(turns.length, 0, 'noise never makes an empty turn');
}
console.log('Natural pause, continuation, interruption, overlap, and stop-flush tests passed');
