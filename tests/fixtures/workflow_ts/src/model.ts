// Contracts for pricing steps. Callers only ever see Step.
export interface Named {
  label(): string;
}

export interface Step extends Named {
  apply(amount: number): number;
}

export interface PricedStep extends Step {
  rate(): number;
}
