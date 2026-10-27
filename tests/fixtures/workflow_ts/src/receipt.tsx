import { money } from '../lib/format.cjs';
import { Step } from './model';

export function Line(props: { step: Step; amount: number }) {
  return <li>{props.step.label()} {money(props.amount)}</li>;
}

export function ReceiptView(props: { steps: Step[]; amount: number }) {
  return <ul>{props.steps.map((step) => <Line step={step} amount={props.amount} />)}</ul>;
}
