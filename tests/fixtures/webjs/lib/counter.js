const add1 = (n) => n + 1;

class Counter {
  constructor() {
    this.value = 0;
  }

  increment() {
    this.value = add1(this.value);
  }
}

module.exports = Counter;
