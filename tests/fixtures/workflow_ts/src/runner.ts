import { Step } from './model';
import { TaxStep, DiscountStep } from './index';

// step.apply runs TaxStep (inherited BaseStep.apply) or DiscountStep.apply at runtime.
export function runStep(step: Step, amount: number): number {
  return step.apply(amount);
}

export function runSteps(amount: number): number {
  const steps: Step[] = [new TaxStep(), new DiscountStep()];
  return steps.reduce((acc, step) => runStep(step, acc), amount);
}
