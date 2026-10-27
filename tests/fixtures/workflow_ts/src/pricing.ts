export const TAX_RATE = 0.2;
export const UNUSED_RATE = 0.99;

export const roundCents = (value: number): number => Math.round(value * 100) / 100;

const addItem = (sum: number, item: number): number => sum + item;

export function subtotal(items: number[]): number {
  return items.reduce(addItem, 0);
}

export function total(items: number[]): number {
  return roundCents(subtotal(items) * (1 + TAX_RATE));
}

function legacyDiscount(amount: number): number {
  return amount - 1;
}
