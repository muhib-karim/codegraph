const format = require('./format.cjs');
const { money: asMoney } = require('./format.cjs');

function legacyReceipt(amount) {
  const head = format.money(amount);
  return head + ' / ' + asMoney(amount);
}

function subtotal(items) {
  let sum = 0;
  for (const item of items) sum += item;
  return sum;
}

module.exports = { legacyReceipt, subtotal };
