import { Circle, Ring, resize } from './index';
import * as util from './util';
import Registry from './registry';

// make() in a comment is not a call
export function make(r: number): Circle {
  return new Circle(resize(r));
}

export function main(): number {
  const c = make(1);
  const reg = new Registry();
  reg.add(c);
  const ring = new Ring(util.double(2));
  return c.describe().length + ring.area() + reg.size();
}

export function apply(make: (n: number) => number): number {
  return make(5);
}

const label = 'make';
