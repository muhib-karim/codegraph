export const SCALE = 2;

export function scale(n: number): number {
  return n * SCALE;
}

export const double = (n: number): number => scale(n) * 2;
