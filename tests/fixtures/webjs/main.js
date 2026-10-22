const { add } = require('./lib/math');
const Counter = require('./lib/counter');

function run() {
  const c = new Counter();
  c.increment();
  return add(c.value, 1);
}

run();
