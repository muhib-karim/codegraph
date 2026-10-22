export class Emitter {
  on(name, fn) {
    this.handler = fn;
    return this;
  }

  emit(name) {
    return this.handler(name);
  }
}

export class Bus extends Emitter {
  emit(name) {
    return super.emit(name);
  }
}
