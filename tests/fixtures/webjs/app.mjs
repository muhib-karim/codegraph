import { Bus } from './lib/events.mjs';
import { add } from './lib/math.js';

export function start() {
  const bus = new Bus();
  bus.on('x', (n) => add(n, 1));
  return bus.emit('x');
}
