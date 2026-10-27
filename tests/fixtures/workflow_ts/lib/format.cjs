'use strict';

function money(amount) {
  return `$${amount.toFixed(2)}`;
}

function padLeft(text, width) {
  return String(text).padStart(width);
}

module.exports = { money };
