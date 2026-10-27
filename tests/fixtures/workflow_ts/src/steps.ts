import { PricedStep } from './model';
import { roundCents as round } from './pricing';

export abstract class BaseStep implements PricedStep {
  abstract rate(): number;

  label(): string {
    return `step:${this.rate()}`;
  }

  apply(amount: number): number {
    return round(amount + this.charge(amount));
  }

  protected charge(amount: number): number {
    return amount * this.rate();
  }
}

export class TaxStep extends BaseStep {
  rate(): number {
    return 0.2;
  }
}

export class DiscountStep extends BaseStep {
  rate(): number {
    return -0.1;
  }

  apply(amount: number): number {
    return Math.max(0, super.apply(amount));
  }

  private audit(): string {
    return this.label();
  }
}
