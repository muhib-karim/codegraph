import type { Shape } from './shapes';

export default class Registry {
  private items: Shape[] = [];

  add(shape: Shape): void {
    this.items.push(shape);
  }

  size(): number {
    return this.items.length;
  }
}
